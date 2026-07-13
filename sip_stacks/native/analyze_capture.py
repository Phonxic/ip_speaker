from __future__ import annotations

import struct
import sys
from collections import Counter
from pathlib import Path

SPEAKER_IP = "192.168.6.120"


def ipstr(raw: bytes) -> str:
    return ".".join(str(x) for x in raw)


def iter_udp_packets(path: Path):
    data = path.read_bytes()
    pos = 0
    while pos + 12 <= len(data):
        block_type, block_len = struct.unpack_from("<II", data, pos)
        if block_len < 12 or pos + block_len > len(data):
            break
        body = data[pos + 8 : pos + block_len - 4]
        if block_type == 0x00000006 and len(body) >= 20:
            cap_len = struct.unpack_from("<I", body, 12)[0]
            pkt = body[20 : 20 + cap_len]
            off = None
            if len(pkt) >= 34 and pkt[12:14] == b"\x08\x00":
                off = 14
            else:
                for i in range(0, min(80, len(pkt) - 20)):
                    if pkt[i] >> 4 == 4 and (pkt[i] & 0x0F) >= 5 and pkt[i + 9] == 17:
                        total_len = int.from_bytes(pkt[i + 2 : i + 4], "big")
                        if total_len >= 28 and i + total_len <= len(pkt):
                            off = i
                            break
            if off is not None:
                ihl = (pkt[off] & 0x0F) * 4
                src = ipstr(pkt[off + 12 : off + 16])
                dst = ipstr(pkt[off + 16 : off + 20])
                sport, dport, ulen = struct.unpack_from("!HHH", pkt, off + ihl)
                payload = pkt[off + ihl + 8 : off + ihl + ulen]
                yield src, sport, dst, dport, ulen, payload
        pos += block_len


def rtp_info(payload: bytes):
    if len(payload) < 12:
        return None
    version = payload[0] >> 6
    if version != 2:
        return None
    marker = (payload[1] & 0x80) >> 7
    payload_type = payload[1] & 0x7F
    seq = int.from_bytes(payload[2:4], "big")
    timestamp = int.from_bytes(payload[4:8], "big")
    ssrc = int.from_bytes(payload[8:12], "big")
    return version, marker, payload_type, seq, timestamp, ssrc, len(payload)


def analyze(path: Path) -> None:
    packets = list(iter_udp_packets(path))
    print(f"\n=== {path.name} ===")
    print(f"File size: {path.stat().st_size} bytes")
    print(f"UDP packets parsed: {len(packets)}")

    flows = Counter((src, sport, dst, dport, ulen) for src, sport, dst, dport, ulen, _payload in packets)
    print("\nTop UDP flows:")
    for flow, count in flows.most_common(20):
        print(f"{count:5d}  {flow[0]}:{flow[1]} -> {flow[2]}:{flow[3]}  udp_len={flow[4]}")

    speaker_packets = [p for p in packets if SPEAKER_IP in (p[0], p[2])]
    print(f"\nPackets involving speaker {SPEAKER_IP}: {len(speaker_packets)}")

    rtp_packets = []
    for packet in packets:
        src, sport, dst, dport, _ulen, payload = packet
        info = rtp_info(payload)
        if info and (sport not in (5060, 5062) and dport not in (5060, 5062)):
            rtp_packets.append((packet, info))

    print(f"Likely RTP packets: {len(rtp_packets)}")
    if rtp_packets:
        rtp_flows = Counter((p[0], p[1], p[2], p[3], info[2], info[6]) for p, info in rtp_packets)
        print("\nLikely RTP flows:")
        for flow, count in rtp_flows.most_common(20):
            print(
                f"{count:5d}  {flow[0]}:{flow[1]} -> {flow[2]}:{flow[3]}  "
                f"pt={flow[4]} rtp_len={flow[5]}"
            )
        first_packet, first_info = rtp_packets[0]
        last_packet, last_info = rtp_packets[-1]
        print("\nFirst RTP:", first_packet[:4], first_info)
        print("Last RTP: ", last_packet[:4], last_info)


def main() -> int:
    if len(sys.argv) > 1:
        paths = [Path(arg) for arg in sys.argv[1:]]
    else:
        base = Path(__file__).resolve().parent / "captures"
        paths = [base / "ip_speaker_trace.pcapng"]
    for path in paths:
        if path.exists():
            analyze(path)
        else:
            print(f"Missing: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
