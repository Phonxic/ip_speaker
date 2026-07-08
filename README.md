# Windows Broadcast Management Client

This project is a Windows tkinter control client for the PORTech IS-670 IP Speaker.
The current formal test path uses Baresip as the SIP/RTP stack. It does not call MicroSIP.

```text
Python tkinter GUI -> Baresip ctrl_tcp -> SIP/RTP G.711 -> IP Speaker
```

## Important Notes

- MicroSIP is no longer used by this branch.
- Baresip is BSD licensed, which keeps this path away from MicroSIP/GPL code reuse concerns.
- The old Python native SIP/RTP implementation has been moved to `_legacy_native_rtp/`. It is kept only for reference and can be deleted later if the Baresip route works.
- This Windows Baresip build reads configuration from `%APPDATA%\.baresip`. The app backs up the existing files before the first overwrite.

## Folder Structure

```text
ip_speaker/
├── app.py
├── config.json
├── run_demo.bat
├── README.md
├── audio/
├── backends/
│   └── baresip_backend.py
├── tools/
└── _legacy_native_rtp/
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

## Baresip Setup

`config.json` currently points to:

```text
C:\sipbuild\baresip\build\Release\baresip.exe
```

When playback starts, the app writes a managed Baresip config to:

```text
%APPDATA%\.baresip
```

Before overwriting an existing Baresip config, it creates a backup like:

```text
%APPDATA%\.baresip_ip_speaker_backup_YYYYMMDD_HHMMSS
```

## Audio Files

Put WAV files in `audio/`.

Current active files:

```text
testing.wav
fall_warning.wav
baggage_warning.wav
wheelchair_warning.wav
stay_warning.wav
```

Recommended WAV format for this SIP speaker path:

```text
8000 Hz
mono
16-bit PCM
.wav
```

## Config

Important fields in `config.json`:

- `local.ip`: Windows IP address used for SIP/RTP.
- `local.advertise_ip`: IP announced in SIP/SDP. Usually same as `local.ip`.
- `local.sip_port`: local SIP UDP port.
- `local.rtp_port`: local RTP port range start.
- `speaker.ip`: IP Speaker address.
- `speaker.sip_user`: IP Speaker SIP user.
- `speaker.sip_port`: IP Speaker SIP port.
- `baresip.path`: Baresip executable path.
- `baresip.ctrl_tcp_port`: local Baresip control port.
- `baresip.audio_codecs`: codec priority, currently `pcmu/8000/1,pcma`.
- `audio_files`: GUI label to WAV filename mapping.

## Operation

1. Run `python app.py` or double-click `run_demo.bat`.
2. Confirm Local IP, Advertise IP, Speaker IP, SIP User, and ports.
3. Click `Apply Settings`.
4. Click `Test Call / Play Test Audio` or one of the pre-recorded audio buttons.
5. The app starts Baresip, creates an account through `ctrl_tcp`, dials the speaker, plays the selected WAV through Baresip `aufile`, and hangs up automatically.

## Troubleshooting

- If Baresip cannot start, confirm `baresip.path` in `config.json`.
- If the speaker connects but has no sound, try changing `baresip.audio_codecs` between `pcmu/8000/1,pcma` and `pcma,pcmu/8000/1`.
- If Baresip behaves unexpectedly, restore the backup folder from `%APPDATA%\.baresip_ip_speaker_backup_*`.
