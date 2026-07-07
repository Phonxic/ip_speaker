import random
import socket
import struct
import threading
import time

from .g711 import encode_alaw_frame, encode_ulaw_frame
from .native_debug import debug_log


class RTPStreamer:
    def __init__(self, local_ip: str, local_rtp_port: int, remote_ip: str, remote_rtp_port: int, stop_event: threading.Event | None = None, payload_type: int = 8, ssrc: int | None = None, audio_gain: float = 1.0, start_delay_ms: int = 0):
        self.local_ip = local_ip
        self.local_rtp_port = int(local_rtp_port)
        self.remote_ip = remote_ip
        self.remote_rtp_port = int(remote_rtp_port)
        self.payload_type = int(payload_type)
        self.audio_gain = float(audio_gain)
        self.start_delay_ms = int(start_delay_ms)
        self.stop_event = stop_event or threading.Event()
        self.sequence = random.randint(0, 65535)
        self.timestamp = random.randint(0, 0xFFFFFFFF)
        self.ssrc = int(ssrc) if ssrc else random.randint(1, 0xFFFFFFFF)

    def _apply_gain(self, frame: list[int]) -> list[int]:
        if self.audio_gain == 1.0:
            return frame
        return [max(-32768, min(32767, int(sample * self.audio_gain))) for sample in frame]

    def _packet(self, payload: bytes, marker: bool = False) -> bytes:
        payload_type = (0x80 if marker else 0x00) | (self.payload_type & 0x7F)
        header = struct.pack(
            "!BBHII",
            0x80,
            payload_type,
            self.sequence & 0xFFFF,
            self.timestamp & 0xFFFFFFFF,
            self.ssrc,
        )
        return header + payload

    def _send_payload(self, sock: socket.socket, payload: bytes, marker: bool = False) -> None:
        sock.sendto(self._packet(payload, marker), (self.remote_ip, self.remote_rtp_port))
        self.sequence = (self.sequence + 1) & 0xFFFF
        self.timestamp = (self.timestamp + len(payload)) & 0xFFFFFFFF

    def _rtcp_packet(self) -> bytes:
        # Match MicroSIP's observed compound RTCP packet: Receiver Report + SDES CNAME.
        rr = struct.pack(
            "!BBHIIIIIII",
            0x81,
            201,
            7,
            self.ssrc & 0xFFFFFFFF,
            0,
            0,
            0,
            0,
            0,
            0,
        )
        cname = b"python-native-rtp"
        sdes_body = struct.pack("!IBB", self.ssrc & 0xFFFFFFFF, 1, len(cname)) + cname + bytes([0])
        while len(sdes_body) % 4:
            sdes_body += bytes([0])
        sdes = struct.pack("!BBH", 0x81, 202, (len(sdes_body) + 4) // 4 - 1) + sdes_body
        return rr + sdes

    def _send_rtcp(self, rtcp_sock: socket.socket) -> None:
        remote_rtcp_port = self.remote_rtp_port + 1
        rtcp_sock.sendto(self._rtcp_packet(), (self.remote_ip, remote_rtcp_port))
        debug_log(f"RTCP sent: local={self.local_ip}:{self.local_rtp_port + 1}, remote={self.remote_ip}:{remote_rtcp_port}, ssrc={self.ssrc}")

    def stream_samples(self, samples: list[int]) -> int:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        rtcp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        packet_count = 0
        try:
            sock.bind((self.local_ip, self.local_rtp_port))
            rtcp_sock.bind((self.local_ip, self.local_rtp_port + 1))
            debug_log(f"RTP START: local={self.local_ip}:{self.local_rtp_port}, remote={self.remote_ip}:{self.remote_rtp_port}, payload_type={self.payload_type}, audio_gain={self.audio_gain}, start_delay_ms={self.start_delay_ms}, samples={len(samples)}")
            self._send_rtcp(rtcp_sock)
            frame_size = 160
            next_send = time.perf_counter()
            self._send_rtcp(rtcp_sock)
            if self.start_delay_ms > 0:
                debug_log(f"RTP start delay: {self.start_delay_ms} ms")
                time.sleep(self.start_delay_ms / 1000)

            for packet_index, offset in enumerate(range(0, len(samples), frame_size)):
                if self.stop_event.is_set():
                    break
                if packet_index and packet_index % 50 == 0:
                    self._send_rtcp(rtcp_sock)
                frame = samples[offset : offset + frame_size]
                if len(frame) < frame_size:
                    frame = frame + [0] * (frame_size - len(frame))
                frame = self._apply_gain(frame)
                payload = encode_alaw_frame(frame) if self.payload_type == 8 else encode_ulaw_frame(frame)
                self._send_payload(sock, payload, marker=(packet_index == 0))
                packet_count += 1
                next_send += 0.02
                delay = next_send - time.perf_counter()
                if delay > 0:
                    time.sleep(delay)

            self._send_rtcp(rtcp_sock)
            debug_log(f"RTP END: packets_sent={packet_count}")
            return packet_count
        finally:
            rtcp_sock.close()
            sock.close()
