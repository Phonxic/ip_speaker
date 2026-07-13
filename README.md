# Windows Broadcast Management Client

Windows tkinter control client for PORTech IS-670 IP Speaker.

Current working SIP path:

```text
Python GUI -> PJSUA -> SIP/RTP G.711 PCMU -> PORTech IS-670
```

## Current Status

- Main backend: `pjsua`
- PJSUA can call `sip:4267@192.168.6.120:5060`
- Pre-recorded WAV playback works
- Playback auto-hangup works
- Live microphone broadcast has been added for PJSUA
- Audio recording and audio-file management have been added
- Baresip and native Python SIP/RTP stacks are kept for comparison and future licensing work

## License Note

PJSIP/PJSUA is GPL/commercial dual licensed. It is useful for technical validation and demo work, but closed-source or commercial formal delivery should either use a Teluu commercial license or move the verified behavior to a non-GPL SIP/RTP stack.

## Folder Structure

```text
ip_speaker/
|-- app.py
|-- audio_recorder.py
|-- config.json
|-- requirements.txt
|-- README.md
|-- run_demo.bat
|-- audio/
|-- logs/
`-- sip_stacks/
    |-- pjsua/
    |   `-- backend.py
    |-- baresip/
    |   `-- backend.py
    `-- native/
```

## Run

```powershell
cd C:\Users\user\Desktop\ip_speaker
python app.py
```

If you want to use GUI recording, install:

```powershell
pip install sounddevice numpy
```

## PJSUA Settings

Known-good path:

```text
PJSUA executable:
C:\sipbuild\pjproject\build-cmake\pjsip-apps\Release\pjsua.exe

Speaker:
sip:4267@192.168.6.120:5060

Local SIP:
140.124.42.67:64882

Local RTP:
140.124.42.67:4004

Codec:
PCMU / payload type 0
```

## Pre-recorded Broadcast

Audio files live in:

```text
audio/
```

Recommended format:

```text
8000 Hz
mono
16-bit PCM
.wav
```

Flow:

```text
Select audio button -> PJSUA dials speaker -> PJSUA plays WAV -> PJSUA sends BYE
```

The GUI supports playback volume from `0%` to `200%`. The original WAV is not changed; the app creates a temporary adjusted WAV in `logs/`.

## Live Broadcast

Use the `開始即時廣播` and `停止即時廣播` buttons.

Live broadcast uses PJSUA without:

```text
--null-audio
--play-file
--auto-play
--auto-play-hangup
```

PJSUA will use the Windows default capture device unless `pjsua.capture_dev` is set in `config.json`.

If there is no sound, check:

- Windows default microphone
- microphone permission
- PJSUA device selection
- whether another process is using local SIP port `64882`

## Audio Recording

The right-side audio manager can create new WAV files:

1. Enter an Audio ID, for example `custom_warning_01`.
2. Enter display name and description.
3. Click `開始錄音`.
4. Speak into the Windows default microphone.
5. Click `停止錄音並儲存`.

The app writes:

```text
audio/<audio_id>.wav
```

Recording format:

```text
8000 Hz
mono
16-bit PCM
```

The new audio entry is saved to `config.json`.

## Audio Config Schema

`audio_files` now uses a structured format:

```json
{
  "testing": {
    "display_name": "測試廣播",
    "filename": "testing.wav",
    "description": "確認 IP Speaker 是否可正常播放。"
  }
}
```

Old format is migrated automatically when `app.py` loads:

```json
{
  "測試廣播": "testing.wav"
}
```

## Useful Config Fields

- `backend`: currently `pjsua`
- `local.ip`: Windows IP address used for SIP/RTP bind
- `local.advertise_ip`: IP announced in SIP/SDP
- `local.sip_port`: local SIP UDP port
- `local.rtp_port`: local RTP base port
- `local.audio_gain`: playback volume percent
- `speaker.ip`: IP Speaker address
- `speaker.sip_user`: IP Speaker SIP user
- `speaker.sip_port`: IP Speaker SIP port
- `pjsua.path`: PJSUA executable path
- `pjsua.capture_dev`: optional PJSUA capture device id for live broadcast
- `audio.sample_rate`: recording sample rate, currently `8000`
- `audio.channels`: recording channels, currently `1`

## Troubleshooting

- If PJSUA cannot start, confirm `pjsua.path`.
- If playback connects but no sound, confirm WAV format.
- If live broadcast connects but no sound, check Windows default input device.
- If recording fails, install `sounddevice` and `numpy`.
- Logs are written to `logs/gui.log`, `logs/pjsua_gui.log`, and `logs/pjsua_live.log`.
