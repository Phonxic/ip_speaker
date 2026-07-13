import json
import re
import socket
import threading
import time
from dataclasses import dataclass, asdict
from email.utils import formatdate
from pathlib import Path
from typing import Callable


@dataclass
class SipRegistration:
    key: str
    user: str
    source_ip: str
    source_port: int
    contact_uri: str
    contact_ip: str
    contact_port: int
    expires: int
    user_agent: str
    registered_at: float
    expires_at: float

    @property
    def is_online(self) -> bool:
        return self.expires > 0 and time.time() < self.expires_at


class SipRegistrarServer:
    def __init__(
        self,
        host: str,
        port: int,
        base_dir: Path,
        on_event: Callable[[str], None] | None = None,
        on_registration: Callable[[], None] | None = None,
    ):
        self.host = host
        self.port = port
        self.base_dir = base_dir
        self.on_event = on_event
        self.on_registration = on_registration
        self.logs_dir = base_dir / "logs"
        self.log_path = self.logs_dir / "sip_registrar.log"
        self.registry_path = self.logs_dir / "sip_registrations.json"
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._registrations: dict[str, SipRegistration] = {}

    def start(self) -> None:
        if self.is_running:
            return
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.log_path.write_text("", encoding="utf-8")
        self._stop_event.clear()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind((self.host, self.port))
        except OSError:
            sock.close()
            raise
        sock.settimeout(0.5)
        self._sock = sock
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        self._log(f"SIP registrar listening on UDP {self.host}:{self.port}")

    def stop(self) -> None:
        self._stop_event.set()
        sock = self._sock
        if sock:
            try:
                sock.close()
            except OSError:
                pass
        self._sock = None
        self._thread = None
        self._log("SIP registrar stopped")

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def registrations(self, online_only: bool = True) -> list[SipRegistration]:
        with self._lock:
            items = list(self._registrations.values())
        if online_only:
            items = [item for item in items if item.is_online]
        return sorted(items, key=lambda item: (item.user, item.contact_ip, item.contact_port))

    def _serve(self) -> None:
        while not self._stop_event.is_set():
            try:
                if not self._sock:
                    break
                data, addr = self._sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break

            message = data.decode("utf-8", errors="replace")
            start_line, headers = parse_headers(message)
            if not start_line.upper().startswith("REGISTER "):
                self._log(f"Ignored non-REGISTER from {addr[0]}:{addr[1]}: {start_line}")
                continue

            registration = self._registration_from_headers(addr, headers)
            if registration:
                self._store_registration(registration)
                self._log(
                    f"REGISTER {registration.user} contact={registration.contact_uri} "
                    f"source={registration.source_ip}:{registration.source_port} expires={registration.expires}"
                )
            response = build_register_ok(headers)
            try:
                self._sock.sendto(response, addr)
                self._log(f"Sent 200 OK to {addr[0]}:{addr[1]}")
            except OSError as exc:
                self._log(f"Failed to send 200 OK: {exc}")

    def _registration_from_headers(self, addr: tuple[str, int], headers: dict[str, str]) -> SipRegistration | None:
        contact = get_header(headers, "Contact")
        if not contact:
            return None
        contact_info = parse_contact(contact)
        if not contact_info:
            return None
        user, contact_ip, contact_port = contact_info
        expires = parse_expires(headers, contact)
        now = time.time()
        key = f"{user}@{contact_ip}:{contact_port}"
        return SipRegistration(
            key=key,
            user=user,
            source_ip=addr[0],
            source_port=addr[1],
            contact_uri=f"sip:{user}@{contact_ip}:{contact_port}",
            contact_ip=contact_ip,
            contact_port=contact_port,
            expires=expires,
            user_agent=get_header(headers, "User-Agent"),
            registered_at=now,
            expires_at=now + max(0, expires),
        )

    def _store_registration(self, registration: SipRegistration) -> None:
        with self._lock:
            if registration.expires <= 0:
                self._registrations.pop(registration.key, None)
            else:
                self._registrations[registration.key] = registration
            self._write_registry_locked()
        if self.on_registration:
            self.on_registration()

    def _write_registry_locked(self) -> None:
        data = [asdict(item) | {"online": item.is_online} for item in self._registrations.values()]
        self.registry_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _log(self, message: str) -> None:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {message}"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as file:
            file.write(line + "\n")
        if self.on_event:
            self.on_event(message)


def parse_headers(message: str) -> tuple[str, dict[str, str]]:
    lines = message.replace("\r\n", "\n").split("\n")
    start_line = lines[0].strip() if lines else ""
    headers: dict[str, str] = {}
    current_name = None

    for line in lines[1:]:
        if not line.strip():
            break
        if line.startswith((" ", "\t")) and current_name:
            headers[current_name] += " " + line.strip()
            continue
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        current_name = name.strip().lower()
        headers[current_name] = value.strip()
    return start_line, headers


def get_header(headers: dict[str, str], name: str, default: str = "") -> str:
    return headers.get(name.lower(), default)


def parse_contact(contact: str) -> tuple[str, str, int] | None:
    match = re.search(r"sip:([^@;>]+)@([^:;>]+)(?::(\d+))?", contact)
    if not match:
        return None
    user = match.group(1)
    ip = match.group(2)
    port = int(match.group(3) or 5060)
    return user, ip, port


def parse_expires(headers: dict[str, str], contact: str) -> int:
    contact_match = re.search(r"expires\s*=\s*(\d+)", contact, flags=re.IGNORECASE)
    if contact_match:
        return int(contact_match.group(1))
    expires = get_header(headers, "Expires", "3600")
    try:
        return int(expires)
    except ValueError:
        return 3600


def build_register_ok(headers: dict[str, str]) -> bytes:
    via = get_header(headers, "Via")
    from_header = get_header(headers, "From")
    to_header = get_header(headers, "To")
    call_id = get_header(headers, "Call-ID")
    cseq = get_header(headers, "CSeq")
    contact = get_header(headers, "Contact")
    expires = str(parse_expires(headers, contact))

    if "tag=" not in to_header.lower():
        to_header = f"{to_header};tag=python-registrar"

    response_lines = [
        "SIP/2.0 200 OK",
        f"Via: {via}",
        f"From: {from_header}",
        f"To: {to_header}",
        f"Call-ID: {call_id}",
        f"CSeq: {cseq}",
        f"Date: {formatdate(time.time(), localtime=False, usegmt=True)}",
    ]
    if contact:
        response_lines.append(f"Contact: {contact};expires={expires}")
    response_lines.extend(
        [
            "Server: Python-IPB-Registrar/0.1",
            "Content-Length: 0",
            "",
            "",
        ]
    )
    return "\r\n".join(response_lines).encode("utf-8")
