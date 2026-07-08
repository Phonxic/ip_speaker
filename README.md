# Windows Broadcast Management Client

This project is a Windows tkinter control client for the PORTech IS-670 IP Speaker.

The currently working test path uses PJSUA from PJSIP:

```text
Python tkinter GUI -> pjsua.exe -> SIP/RTP G.711 PCMU -> PORTech IS-670
```

The SIP/RTP implementations are grouped under `sip_stacks/`:

- `sip_stacks/pjsua/`: current working PJSUA backend.
- `sip_stacks/baresip/`: previous Baresip backend, kept for comparison and future licensing experiments.
- `sip_stacks/native/`: old native Python SIP/RTP attempt and capture/debug files.

## Important Notes

- MicroSIP is not used by this branch.
- PJSUA has been verified to call the speaker, play `testing.wav`, and hang up automatically.
- PJSIP/PJSUA is GPL/commercial dual licensed. For closed-source or commercial formal delivery, handle the Teluu commercial license or move the verified behavior to a non-GPL stack.
- Baresip is still available as a selectable backend, but the speaker was silent in the current Baresip route.

## Folder Structure

```text
ip_speaker/
|-- app.py
|-- config.json
|-- run_demo.bat
|-- README.md
|-- audio/
|   |-- testing.wav
|   |-- fall_warning.wav
|   |-- baggage_warning.wav
|   |-- wheelchair_warning.wav
|   `-- stay_warning.wav
`-- sip_stacks/
    |-- pjsua/
    |   |-- __init__.py
    |   `-- backend.py
    |-- baresip/
    |   |-- __init__.py
    |   `-- backend.py
    `-- native/
        |-- __init__.py
        |-- native/
        |-- captures/
        |-- logs/
        |-- audio_backup/
        |-- README.md
        `-- TROUBLESHOOTING_NATIVE_RTP.md
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

## PJSUA Setup

`config.json` currently points to:

```text
C:\sipbuild\pjproject\build-cmake\pjsip-apps\Release\pjsua.exe
```

The GUI uses this successful call pattern:

```text
Local SIP: 140.124.42.67:64882
Local RTP: 140.124.42.67:4004
Speaker: sip:4267@192.168.6.120:5060
Codec: PCMU / payload type 0
Audio: 8000 Hz mono WAV
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

Recommended WAV format:

```text
8000 Hz
mono
16-bit PCM
.wav
```

If a WAV file is missing, the GUI will show an error instead of crashing.

## Config

Important fields in `config.json`:

- `backend`: use `pjsua` for the working route, or `baresip` for the old test route.
- `local.ip`: Windows IP address used for SIP/RTP bind.
- `local.advertise_ip`: IP announced in SIP/SDP. Usually same as `local.ip`.
- `local.sip_port`: local SIP UDP port, currently `64882`.
- `local.rtp_port`: local RTP base port, currently `4004`.
- `local.audio_gain`: playback volume percent, from `0` to `200`; `100` means original WAV volume.
- `local.sip_identity`: SIP identity used in From/Contact, currently `140.124.42.67`.
- `speaker.ip`: IP Speaker address.
- `speaker.sip_user`: IP Speaker SIP user.
- `speaker.sip_port`: IP Speaker SIP port.
- `pjsua.path`: PJSUA executable path.
- `pjsua.disable_codecs`: codecs hidden from the SDP offer so the speaker chooses PCMU/PCMA.
- `audio_files`: GUI label to WAV filename mapping.

## Operation

1. Run `python app.py` or double-click `run_demo.bat`.
2. Confirm Backend is `pjsua`.
3. Confirm Local IP, Advertise IP, Speaker IP, SIP User, and ports.
4. Adjust `播放音量` if needed. `100%` is the original WAV volume.
5. Click `套用設定`.
6. Click `測試撥號 / 播放 testing.wav` or one of the pre-recorded audio buttons.
7. The app starts PJSUA, dials the speaker, plays the selected WAV, and hangs up automatically.

## Troubleshooting

- If PJSUA cannot start, confirm `pjsua.path` in `config.json`.
- If the speaker does not ring, confirm MicroSIP/Baresip/PJSUA is not already occupying SIP port `64882`.
- If the speaker connects but has no sound, confirm the WAV is 8000 Hz mono 16-bit PCM.
- If the speaker is too quiet or too loud, adjust the `播放音量` slider. The app creates a temporary adjusted WAV in `logs/`; original WAV files are not modified.
- Check logs in `logs/pjsua_gui.log` and `logs/gui.log`.
- The known-good manual PJSUA test used PCMU payload type 0 and sent RTP to speaker port 20000 from local RTP port 4004.
