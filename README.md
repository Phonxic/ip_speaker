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
tools/pjsua/pjsua.exe

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
Select target group -> click an event Trigger -> PJSUA dials all speakers in parallel -> each speaker plays its audio assigned for that event -> PJSUA sends BYE
```

The GUI supports playback volume from `0%` to `200%`. The original WAV is not changed; the app creates a temporary adjusted WAV in `logs/`.

## Multiple Speakers

Pre-recorded playback supports speaker groups. The app starts one PJSUA process per speaker in the selected group, so speakers can be called at the same time.

Each process gets its own local SIP/RTP ports:

```text
speaker 1: local SIP 64882, RTP 4004
speaker 2: local SIP 64884, RTP 4006
speaker 3: local SIP 64886, RTP 4008
```

Each speaker has a default test audio through `audio_id`, plus event-specific audio through `event_audio_ids`. For example, clicking `Trigger：旅客跌倒` makes each speaker look up its own `event_audio_ids.fall_warning`. If a speaker has no override for that event, it plays the event's default audio.

The `Speaker 管理` tab can edit speaker names, create groups, assign event audio, and test one speaker at a time.

Add speakers in `config.json`:

```json
{
  "speakers": {
    "speaker_1": {
      "display_name": "IP Speaker 1",
      "ip": "192.168.6.120",
      "sip_user": "4267",
      "sip_port": 5060,
      "audio_id": "testing",
      "event_audio_ids": {
        "fall_warning": "fall_warning"
      }
    },
    "speaker_2": {
      "display_name": "IP Speaker 2",
      "ip": "192.168.6.121",
      "sip_user": "4267",
      "sip_port": 5060,
      "audio_id": "testing",
      "event_audio_ids": {
        "fall_warning": "testing_1"
      }
    }
  },
  "speaker_groups": {
    "all": {
      "display_name": "全部 Speaker",
      "speaker_ids": ["speaker_1", "speaker_2"]
    }
  },
  "selected_speaker_group": "all"
}
```

Live broadcast also attempts one PJSUA process per speaker in the selected group. For reliable group live broadcast, use a shared virtual input device such as VB-CABLE or VoiceMeeter. Some Windows physical microphones cannot be opened by multiple PJSUA processes at the same time.

## IBS / IPB Registration Server

The app can also act as a minimal SIP registrar for PORTech IBS/IPB registration.

1. Close any other SIP tool if it is using UDP `5060`.
2. In the GUI, click `啟動 IBS Server`.
3. In the IS-670 Web UI, set `Service Domain Settings`:

```text
Active: ON
User Name: 4267
Register Name: 4267
Register Password: empty for the current test
IPB Server: 140.124.42.67
```

4. Click `Submit`, then save/reboot the speaker if required.
5. Confirm the speaker page shows `Registered`.
6. In the GUI, click `重新整理註冊清單`.
7. Click `匯入註冊 Speaker`.

Imported speakers are written to `config.json` under `speakers`, and the app creates/updates a `registered` target group.

Registrar logs are written to:

```text
logs/sip_registrar.log
logs/sip_registrations.json
```

This registrar currently handles SIP `REGISTER` and returns `200 OK`. Broadcasting still uses the existing PJSUA path to call the registered speaker contact.

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
- `speakers`: named speaker list for multi-speaker playback
- `speaker_groups`: named target groups; each group contains speaker ids
- `selected_speaker_group`: default group selected by the GUI
- `registrar.host`: IBS/IPB registrar bind host, usually `0.0.0.0`
- `registrar.port`: IBS/IPB registrar UDP port, usually `5060`
- `pjsua.path`: PJSUA executable path; the default bundled path is `tools/pjsua/pjsua.exe`
- `pjsua.capture_dev`: optional PJSUA capture device id for live broadcast
- `audio.sample_rate`: recording sample rate, currently `8000`
- `audio.channels`: recording channels, currently `1`

## Troubleshooting

- If PJSUA cannot start, confirm `pjsua.path`.
- If playback connects but no sound, confirm WAV format.
- If live broadcast connects but no sound, check Windows default input device.
- If recording fails, install `sounddevice` and `numpy`.
- Logs are written to `logs/gui.log`, `logs/pjsua_gui.log`, and `logs/pjsua_live.log`.
