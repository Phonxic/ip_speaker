# Legacy Native RTP Files

This folder contains files from the earlier pure Python SIP/RTP experiment.

Current PJSUA-based development does not need these files to run. They are kept here only for reference, packet comparison, or rollback.

Contents:

- `native/`: old pure Python SIP/RTP implementation.
- `captures/`: pktmon captures from native tests.
- `logs/`: previous native debug logs.
- `audio_backup/`: original audio backups before WAV conversion.
- `analyze_capture.py`: helper script for capture analysis.
- `start_capture*.bat` / `stop_capture*.bat`: pktmon capture helpers.
- `TROUBLESHOOTING_NATIVE_RTP.md`: old native RTP notes.

If the PJSUA version is confirmed as the only supported SIP path, this entire folder can be deleted.
