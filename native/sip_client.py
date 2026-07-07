import random
import re
import socket
import time
import uuid

from .native_debug import debug_log

CRLF = "\r\n"


class SIPError(RuntimeError):
    pass


class SIPClient:
    def __init__(self, local_ip: str, local_sip_port: int, local_rtp_port: int, speaker_ip: str, speaker_sip_user: str, speaker_sip_port: int = 5060, advertise_ip: str | None = None):
        self.local_ip = local_ip
        self.local_sip_port = int(local_sip_port)
        self.local_rtp_port = int(local_rtp_port)
        self.advertise_ip = advertise_ip.strip() if advertise_ip else self.local_ip
        self.speaker_ip = speaker_ip
        self.speaker_sip_user = str(speaker_sip_user)
        self.speaker_sip_port = int(speaker_sip_port)
        self.call_id = f"{uuid.uuid4()}@{self.advertise_ip}"
        self.from_tag = uuid.uuid4().hex[:10]
        self.rtp_ssrc = random.randint(1, 0xFFFFFFFF)
        self.to_tag = ""
        self.branch = f"z9hG4bK-{uuid.uuid4().hex}"
        self.invite_cseq = 1
        self.bye_cseq = 2
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((self.local_ip, self.local_sip_port))
        self.sock.settimeout(1.0)
        self.remote_rtp_ip = self.speaker_ip
        self.remote_rtp_port = None
        self.remote_payload_type = 8
        self.remote_contact_uri = self.request_uri
        debug_log(f"SIP bind_ip={self.local_ip}, advertise_ip={self.advertise_ip}, local_sip_port={self.local_sip_port}, local_rtp_port={self.local_rtp_port}")

    @property
    def request_uri(self) -> str:
        return f"sip:{self.speaker_sip_user}@{self.speaker_ip}"

    @property
    def local_from_uri(self) -> str:
        return f"sip:{self.advertise_ip}"

    @property
    def local_contact(self) -> str:
        return f"sip:{self.advertise_ip}:{self.local_sip_port};ob"

    def _sdp(self) -> str:
        lines = [
            "v=0",
            f"o=- {int(time.time())} {int(time.time())} IN IP4 {self.advertise_ip}",
            "s=pjmedia",
            "b=AS:84",
            "t=0 0",
            "a=X-nat:0",
            f"m=audio {self.local_rtp_port} RTP/AVP 8 0 101",
            f"c=IN IP4 {self.advertise_ip}",
            "b=TIAS:64000",
            f"a=rtcp:{self.local_rtp_port + 1} IN IP4 {self.advertise_ip}",
            "a=sendrecv",
            "a=rtpmap:8 PCMA/8000",
            "a=rtpmap:0 PCMU/8000",
            "a=rtpmap:101 telephone-event/8000",
            "a=fmtp:101 0-16",
            f"a=ssrc:{self.rtp_ssrc} cname:python-native",
        ]
        debug_log(f"SDP advertise_ip={self.advertise_ip}, bind_ip={self.local_ip}")
        return CRLF.join(lines) + CRLF

    def _send(self, message: str) -> None:
        self.sock.sendto(message.encode("utf-8"), (self.speaker_ip, self.speaker_sip_port))
        print("\n--- SIP SEND ---")
        print(message)
        debug_log("SIP SEND:\n" + message)

    def send_invite(self) -> None:
        body = self._sdp()
        headers = [
            f"INVITE {self.request_uri} SIP/2.0",
            f"Via: SIP/2.0/UDP {self.advertise_ip}:{self.local_sip_port};branch={self.branch};rport",
            "Max-Forwards: 70",
            f"From: <{self.local_from_uri}>;tag={self.from_tag}",
            f"To: <{self.request_uri}>",
            f"Call-ID: {self.call_id}",
            f"CSeq: {self.invite_cseq} INVITE",
            "Allow: PRACK, INVITE, ACK, BYE, CANCEL, UPDATE, INFO, SUBSCRIBE, NOTIFY, REFER, MESSAGE, OPTIONS",
            "Supported: replaces, 100rel, timer, norefersub",
            "Session-Expires: 1800",
            "Min-SE: 90",
            "User-Agent: MicroSIP/3.22.12-compatible-python",
            f"Contact: <{self.local_contact}>",
            "Content-Type: application/sdp",
            f"Content-Length: {len(body.encode('utf-8'))}",
        ]
        self._send(CRLF.join(headers) + CRLF + CRLF + body)

    def wait_for_answer(self, timeout_sec: float = 15.0, status_callback=None) -> tuple[str, int]:
        deadline = time.time() + timeout_sec
        last_status = None
        while time.time() < deadline:
            try:
                data, _addr = self.sock.recvfrom(65535)
            except socket.timeout:
                continue
            text = data.decode("utf-8", errors="replace")
            print("\n--- SIP RECV ---")
            print(text)
            debug_log("SIP RECV:\n" + text)
            status = self._parse_status_code(text)
            if status and status != last_status:
                last_status = status
                if status_callback:
                    status_callback(status)
            if status == 200:
                self.to_tag = self._parse_to_tag(text)
                self.remote_contact_uri = self._parse_contact_uri(text) or self.request_uri
                self.remote_rtp_ip, self.remote_rtp_port, self.remote_payload_type = self._parse_sdp_rtp(text)
                debug_log(f"SIP 200 OK parsed: to_tag={self.to_tag}, contact={self.remote_contact_uri}, remote_rtp={self.remote_rtp_ip}:{self.remote_rtp_port}, payload_type={self.remote_payload_type}")
                return self.remote_rtp_ip, self.remote_rtp_port, self.remote_payload_type
            if status and status >= 300:
                raise SIPError(f"SIP call failed with status {status}")
        raise TimeoutError("Timed out waiting for SIP 200 OK")

    def send_ack(self) -> None:
        headers = [
            f"ACK {self.remote_contact_uri} SIP/2.0",
            f"Via: SIP/2.0/UDP {self.advertise_ip}:{self.local_sip_port};branch=z9hG4bK-{uuid.uuid4().hex};rport",
            "Max-Forwards: 70",
            f"From: <{self.local_from_uri}>;tag={self.from_tag}",
            f"To: <{self.request_uri}>;tag={self.to_tag}",
            f"Call-ID: {self.call_id}",
            f"CSeq: {self.invite_cseq} ACK",
            "Content-Length: 0",
        ]
        self._send(CRLF.join(headers) + CRLF + CRLF)

    def send_bye(self) -> None:
        if not self.to_tag:
            return
        headers = [
            f"BYE {self.remote_contact_uri} SIP/2.0",
            f"Via: SIP/2.0/UDP {self.advertise_ip}:{self.local_sip_port};branch=z9hG4bK-{uuid.uuid4().hex};rport",
            "Max-Forwards: 70",
            f"From: <{self.local_from_uri}>;tag={self.from_tag}",
            f"To: <{self.request_uri}>;tag={self.to_tag}",
            f"Call-ID: {self.call_id}",
            f"CSeq: {self.bye_cseq} BYE",
            "User-Agent: MicroSIP/3.22.12-compatible-python",
            "Content-Length: 0",
        ]
        self._send(CRLF.join(headers) + CRLF + CRLF)
        self._drain_bye_response()

    def close(self) -> None:
        self.sock.close()

    def _drain_bye_response(self) -> None:
        old_timeout = self.sock.gettimeout()
        self.sock.settimeout(1.0)
        try:
            data, _addr = self.sock.recvfrom(65535)
            text = data.decode("utf-8", errors="replace")
            print("\n--- SIP RECV ---")
            print(text)
            debug_log("SIP RECV:\n" + text)
        except socket.timeout:
            pass
        finally:
            self.sock.settimeout(old_timeout)

    @staticmethod
    def _parse_status_code(response: str) -> int | None:
        first_line = response.splitlines()[0] if response.splitlines() else ""
        match = re.match(r"SIP/2\.0\s+(\d{3})", first_line)
        return int(match.group(1)) if match else None

    @staticmethod
    def _parse_to_tag(response: str) -> str:
        match = re.search(r"^To:.*?;tag=([^;\s>]+)", response, flags=re.IGNORECASE | re.MULTILINE)
        return match.group(1) if match else ""

    @staticmethod
    def _parse_contact_uri(response: str) -> str:
        match = re.search(r"^Contact:\s*<([^>]+)>", response, flags=re.IGNORECASE | re.MULTILINE)
        return match.group(1).strip() if match else ""

    def _parse_sdp_rtp(self, response: str) -> tuple[str, int, int]:
        parts = response.split(CRLF + CRLF, 1)
        sdp = parts[1] if len(parts) == 2 else response
        ip_match = re.search(r"^c=IN IP4\s+([^\r\n]+)", sdp, flags=re.MULTILINE)
        port_match = re.search(r"^m=audio\s+(\d+)\s+RTP/AVP\s+([^\r\n]+)", sdp, flags=re.MULTILINE)
        rtp_ip = ip_match.group(1).strip() if ip_match else self.speaker_ip
        if not port_match:
            raise SIPError("Could not parse RTP port from 200 OK SDP")
        payloads = [int(part) for part in port_match.group(2).split() if part.isdigit()]
        payload_type = next((payload for payload in payloads if payload in (8, 0)), 8)
        return rtp_ip, int(port_match.group(1)), payload_type
