# Windows Broadcast Management Server

This project is a formalized Windows broadcast management architecture for PORTech IS-670 IP Speaker demos.

## Architecture

Windows GUI Client -> Broadcast Management Server -> MicroSIP CLI -> VB-CABLE -> IP Speaker

The tkinter GUI does not control MicroSIP directly. It calls the local FastAPI server through HTTP APIs. The server owns speaker/group management, task queueing, MicroSIP CLI calls, audio playback, hangup, and logs.

## Requirements

- Python 3.11+
- MicroSIP
- VB-CABLE
- IP Speaker reachable by SIP, for example `sip:4267@192.168.6.120`

## Install Python Packages

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## Run

Terminal 1:

```powershell
python broadcast_server.py
```

Terminal 2:

```powershell
python app.py
```

## MicroSIP Settings

- Set microphone device to `CABLE Output`.
- Prefer G.711 A-law / G.711 u-law codec.
- Confirm CLI works:

```powershell
"C:\Program Files\MicroSIP\microsip.exe" "sip:4267@192.168.6.120"
"C:\Program Files\MicroSIP\microsip.exe" /hangupall
```

## VB-CABLE Settings

- Windows audio output should go to `CABLE Input`.
- MicroSIP microphone should receive `CABLE Output`.

## Add Speaker

Edit `config.json` -> `speakers`.

## Add Group

Edit `config.json` -> `groups`.

## Add Audio File

Put a WAV file into `audio/`, then edit `config.json` -> `audio_files`.

Current test broadcast uses `testing.wav`.

## Recommended Audio Format

WAV, 8000 Hz, mono, 16-bit PCM.

## Logs

Logs are written to:

```text
logs/broadcast_log.csv
```

CSV columns:

```text
time, task_id, type, target_group, target_speakers, audio_file, status, message
```

## API

- `GET /api/health`
- `GET /api/speakers`
- `GET /api/groups`
- `GET /api/audio-files`
- `GET /api/logs`
- `POST /api/broadcast/audio`
- `POST /api/broadcast/live/start`
- `POST /api/broadcast/live/stop`
- `POST /api/broadcast/stop`

## Limitations

This is a single Windows host formalized solution. Multi-speaker simultaneous playback depends on MicroSIP multi-call behavior. For many speakers, precise sync, scheduling, and higher operational stability, upgrade to the vendor IBS solution or a dedicated SIP Broadcast Server.
