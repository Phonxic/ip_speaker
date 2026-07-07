# Native RTP Troubleshooting

The current Native SIP/RTP path successfully completes SIP but the speaker does not play audio. Use packet capture to determine where RTP is failing.

## Current Demo Network

```text
PC bind IP:       140.124.42.67
Advertise IP:     192.168.6.1
IP Speaker:       192.168.6.120
Local SIP port:   5062 UDP
Local RTP port:   40000 UDP
Speaker SIP port: 5060 UDP
Speaker RTP port: shown in logs, usually 20002 UDP
```

## Capture On This PC

1. Right-click `start_capture.bat`.
2. Choose `Run as administrator`.
3. Run the app:

```powershell
cd C:\Users\user\Desktop\ip_speaker
python app.py
```

4. Press `Test Call / Play Test Audio`.
5. Wait until the call ends.
6. Right-click `stop_capture.bat`.
7. Choose `Run as administrator`.
8. Open this file in Wireshark:

```text
captures\ip_speaker_trace.pcapng
```

## Wireshark Display Filters

Show all UDP between this PC path and speaker:

```text
ip.addr == 192.168.6.120 && udp
```

Show SIP:

```text
sip || udp.port == 5060 || udp.port == 5062
```

Show RTP target from the latest logs:

```text
udp.port == 20002
```

Show local RTP source port:

```text
udp.port == 40000
```

## What To Check

### Case A: PC capture shows RTP packets leaving

If you see packets like this:

```text
140.124.42.67:40000 -> 192.168.6.120:20002 UDP
```

then Python is sending RTP. If the speaker is silent, capture must be done on the `192.168.6.x` side or via switch mirror to confirm the speaker actually receives those packets.

### Case B: PC capture does not show RTP packets

Then Windows firewall, routing, or socket binding is blocking the local send. Check firewall rules and confirm `logs/native_debug.log` still says `RTP END: packets_sent=...`.

### Case C: Speaker-side capture receives RTP but no audio

Then the speaker accepts the SIP call but rejects or ignores the RTP media format/source behavior. Compare against a MicroSIP capture. Important fields to compare:

- SIP Via / Contact / From IP
- SDP `c=IN IP4`
- SDP `m=audio` port and codec list
- RTP payload type, usually `0` for PCMU
- RTP packet interval, usually 20 ms
- RTP source IP and source port

## Most Useful Comparison

Do two captures:

1. MicroSIP successful call.
2. Native Python failed call.

Then compare SIP INVITE/SDP and RTP streams side by side.
