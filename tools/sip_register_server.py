import argparse
import socket
import sys
import time
from email.utils import formatdate
from pathlib import Path


DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 5060
BASE_DIR = Path(__file__).resolve().parents[1]
LOG_PATH = BASE_DIR / "logs" / "sip_register_server.log"


def log(message: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line, flush=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as file:
        file.write(line + "\n")


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


def build_register_ok(headers: dict[str, str]) -> bytes:
    via = get_header(headers, "Via")
    from_header = get_header(headers, "From")
    to_header = get_header(headers, "To")
    call_id = get_header(headers, "Call-ID")
    cseq = get_header(headers, "CSeq")
    contact = get_header(headers, "Contact")
    expires = get_header(headers, "Expires", "3600")

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
            "Server: Python-IPB-Register-Test/0.1",
            "Content-Length: 0",
            "",
            "",
        ]
    )
    return "\r\n".join(response_lines).encode("utf-8")


def print_register(addr: tuple[str, int], start_line: str, headers: dict[str, str]) -> None:
    log("=" * 72)
    log(f"REGISTER from {addr[0]}:{addr[1]}")
    log(start_line)
    for name in ("via", "from", "to", "contact", "call-id", "cseq", "expires", "user-agent"):
        value = get_header(headers, name)
        if value:
            log(f"{name.title()}: {value}")


def serve(host: str, port: int) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((host, port))
    except OSError as exc:
        raise SystemExit(
            f"Cannot bind UDP {host}:{port}: {exc}\n"
            "請先關閉 MicroSIP、PJSUA、Baresip，或改用 --port 指定其他 port。"
        ) from exc

    LOG_PATH.write_text("", encoding="utf-8")
    log(f"SIP REGISTER test server listening on UDP {host}:{port}")
    log("Press Ctrl+C to stop.")

    while True:
        data, addr = sock.recvfrom(65535)
        message = data.decode("utf-8", errors="replace")
        start_line, headers = parse_headers(message)
        if not start_line.upper().startswith("REGISTER "):
            log(f"Ignored non-REGISTER from {addr[0]}:{addr[1]}: {start_line}")
            continue

        print_register(addr, start_line, headers)
        response = build_register_ok(headers)
        sock.sendto(response, addr)
        log(f"Sent 200 OK to {addr[0]}:{addr[1]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Minimal SIP REGISTER 200 OK test server for PORTech IS-670.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    try:
        serve(args.host, args.port)
    except KeyboardInterrupt:
        log("Stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
