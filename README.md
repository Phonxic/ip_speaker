# Native SIP/RTP IP Speaker Demo

This project controls a PORTech IS-670 / IS-670P+ IP Speaker directly from Python.
It does not use MicroSIP, VB-CABLE, Asterisk, IBS, or a separate broadcast server.

Flow:

```text
Python tkinter GUI -> SIP INVITE / ACK / BYE -> RTP G.711 u-law -> IP Speaker
```

## Folder Structure

```text
ip_speaker/
??? app.py                 # Main GUI
??? config.json            # IP, SIP, RTP, and audio mapping settings
??? run_demo.bat           # Double-click launcher
??? README.md
??? audio/                 # Active 8000 Hz mono 16-bit PCM WAV files
??? audio_backup/          # Original backup WAV files, not used by the GUI
??? logs/                  # Native SIP/RTP debug logs
??? native/                # SIP, RTP, WAV, and G.711 implementation modules
```

## Run

```powershell
cd C:\Users\user\Desktop\ip_speaker
python app.py
```

Or double-click:

```text
run_demo.bat
```

## Current Settings

`config.json` contains:

- `local.ip`: the real Windows IP used to bind SIP/RTP sockets.
- `local.advertise_ip`: optional IP announced inside SIP SDP. Leave empty for normal LAN use. In routed/NAT environments, this can be set to the IP that the speaker sees, such as `192.168.6.1`.
- `local.sip_port`: local SIP UDP port.
- `local.rtp_port`: local RTP UDP port.
- `speaker.ip`: IP Speaker address.
- `speaker.sip_user`: IP Speaker SIP user.
- `speaker.sip_port`: IP Speaker SIP UDP port.
- `audio_files`: GUI button label to WAV filename mapping.

Current demo values:

```text
Local IP:      140.124.42.67
Advertise IP:  192.168.6.1
Speaker IP:    192.168.6.120
SIP User:      4267
```

## Audio Files

Put playable WAV files in `audio/`.

Required WAV format:

```text
8000 Hz
mono
16-bit PCM
.wav
```

Current audio files:

```text
testing.wav
fall_warning.wav
baggage_warning.wav
wheelchair_warning.wav
stay_warning.wav
```

The GUI validates the WAV format before sending RTP. If a file is missing or has the wrong format, it shows an error instead of crashing.

## Operation

1. Open `app.py` or run `run_demo.bat`.
2. Confirm the Local IP, Advertise IP, Speaker IP, SIP User, and ports.
3. Click `Apply Settings`.
4. Click `Test Call / Play Test Audio` or one of the pre-recorded audio buttons.
5. The program sends SIP INVITE, streams PCMU RTP audio, then sends BYE automatically.
6. Check `logs/native_debug.log` when troubleshooting SIP/RTP behavior.
