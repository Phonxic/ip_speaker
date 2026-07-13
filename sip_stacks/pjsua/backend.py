import subprocess
import time
import wave
from pathlib import Path


class PjsuaError(RuntimeError):
    pass


class PjsuaBackend:
    def __init__(self, config: dict, base_dir: Path, notify):
        self.config = config
        self.base_dir = base_dir
        self.notify = notify
        self.process: subprocess.Popen | None = None
        self.live_process: subprocess.Popen | None = None
        self.is_live_broadcasting = False
        self.playback_audio_path: Path | None = None
        self.playback_log_name = "pjsua_gui.log"
        self.live_log_name = "pjsua_live.log"
        self.logs_dir = base_dir / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def start_broadcast(self, audio_path: Path) -> None:
        if self.process and self.process.poll() is None:
            raise PjsuaError("A pre-recorded broadcast is already running.")
        if self.live_process and self.live_process.poll() is None:
            raise PjsuaError("Live broadcast is running. Stop it before playing WAV audio.")
        if not audio_path.exists():
            raise PjsuaError(f"Audio file not found:\n{audio_path}")

        self.playback_audio_path = self._prepare_audio_file(audio_path)
        self.playback_log_name = self.config.get("pjsua", {}).get("playback_log_name", "pjsua_gui.log")
        args, target_uri = self._base_args(self.playback_log_name)
        args.extend(
            [
                "--null-audio",
                f"--play-file={self.playback_audio_path}",
                "--auto-play",
                "--auto-play-hangup",
                target_uri,
            ]
        )

        self.notify(f"PJSUA dialing {target_uri}")
        self.process = self._spawn(args)
        self._raise_if_startup_failed(self.playback_log_name, self.process, "pre-recorded broadcast")

    def wait_for_audio_then_hangup(self, audio_path: Path) -> None:
        duration = self._wave_duration(self.playback_audio_path or audio_path)
        timeout = duration + float(self.config.get("pjsua", {}).get("extra_wait_seconds", 8.0))
        started = time.monotonic()

        while time.monotonic() - started < timeout:
            if self.process and self.process.poll() is not None:
                error = self._extract_error(self.playback_log_name)
                if error:
                    self.process = None
                    raise PjsuaError(error)
                break
            if self._log_contains_disconnected(self.playback_log_name):
                break
            time.sleep(0.2)

        self.stop()

    def start_live_broadcast(self) -> None:
        if self.live_process and self.live_process.poll() is None:
            raise PjsuaError("Live broadcast is already running.")
        if self.process and self.process.poll() is None:
            raise PjsuaError("Pre-recorded broadcast is running. Stop it before live broadcast.")

        self.live_log_name = self.config.get("pjsua", {}).get("live_log_name", "pjsua_live.log")
        args, target_uri = self._base_args(self.live_log_name)
        pjsua_config = self.config.get("pjsua", {})
        capture_dev = pjsua_config.get("capture_dev")
        playback_dev = pjsua_config.get("playback_dev")
        if capture_dev not in (None, ""):
            args.append(f"--capture-dev={int(capture_dev)}")
        if playback_dev not in (None, ""):
            args.append(f"--playback-dev={int(playback_dev)}")
        args.append(target_uri)

        self.notify(f"Starting live broadcast to {target_uri}")
        self.live_process = self._spawn(args)
        self._raise_if_startup_failed(self.live_log_name, self.live_process, "live broadcast")
        self.is_live_broadcasting = True

    def stop_live_broadcast(self) -> None:
        self._stop_process("live")
        self.is_live_broadcasting = False
        self.notify("Live broadcast stopped")

    def stop(self) -> None:
        self._stop_process("playback")

    def is_playback_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def is_live_running(self) -> bool:
        return self.live_process is not None and self.live_process.poll() is None

    def _base_args(self, log_name: str) -> tuple[list[str], str]:
        pjsua_config = self.config.get("pjsua", {})
        local = self.config.get("local", {})
        speaker = self.config.get("speaker", {})

        exe_path = Path(pjsua_config.get("path") or pjsua_config.get("exe_path", ""))
        if not exe_path.exists():
            raise PjsuaError(f"PJSUA executable not found:\n{exe_path}")

        local_ip = str(local.get("ip", "")).strip()
        advertise_ip = str(local.get("advertise_ip") or local_ip).strip()
        local_sip_port = int(local.get("sip_port", 64882))
        local_rtp_port = int(local.get("rtp_port", 4004))
        speaker_ip = str(speaker.get("ip", "")).strip()
        speaker_user = str(speaker.get("sip_user", "4267")).strip()
        speaker_port = int(speaker.get("sip_port", 5060))
        sip_identity = str(local.get("sip_identity") or advertise_ip).strip()

        if not local_ip or not speaker_ip:
            raise PjsuaError("Local IP and Speaker IP are required.")

        log_path = self.logs_dir / log_name
        log_path.write_text("", encoding="utf-8")
        target_uri = f"sip:{speaker_user}@{speaker_ip}:{speaker_port}"
        contact = f"sip:{sip_identity}:{local_sip_port};ob"

        args = [
            str(exe_path),
            f"--log-file={log_path}",
            f"--log-level={int(pjsua_config.get('log_level', 5))}",
            f"--app-log-level={int(pjsua_config.get('app_log_level', 4))}",
            "--no-tcp",
            f"--local-port={local_sip_port}",
            f"--ip-addr={advertise_ip}",
            f"--bound-addr={local_ip}",
            f"--id=sip:{sip_identity}",
            f"--contact={contact}",
            f"--rtp-port={local_rtp_port}",
            "--ptime=20",
            "--no-vad",
            "--clock-rate=8000",
            "--snd-clock-rate=8000",
        ]

        for codec in pjsua_config.get("disable_codecs", []):
            args.append(f"--dis-codec={codec}")

        return args, target_uri

    def _spawn(self, args: list[str]) -> subprocess.Popen:
        return subprocess.Popen(
            args,
            cwd=str(self.base_dir),
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    def _raise_if_startup_failed(self, log_name: str, process: subprocess.Popen, label: str) -> None:
        time.sleep(0.5)
        if process.poll() is None:
            return
        error = self._extract_error(log_name) or f"PJSUA {label} exited immediately."
        if process is self.live_process:
            self.live_process = None
            self.is_live_broadcasting = False
        if process is self.process:
            self.process = None
        raise PjsuaError(error)

    def _stop_process(self, kind: str) -> None:
        process = self.live_process if kind == "live" else self.process
        if not process:
            return
        if process.poll() is None:
            try:
                if process.stdin:
                    process.stdin.write("h\nq\n")
                    process.stdin.flush()
                process.wait(timeout=4)
            except Exception:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except Exception:
                    process.kill()
        if kind == "live":
            self.live_process = None
        else:
            self.process = None

    def _log_contains_disconnected(self, log_name: str) -> bool:
        text = self._read_log(log_name)
        return "Call 0 is DISCONNECTED" in text or "Response msg 200/BYE" in text

    def _extract_error(self, log_name: str) -> str | None:
        text = self._read_log(log_name)
        if not text:
            return None
        checks = [
            ("WSAEADDRINUSE", "PJSUA SIP port is already in use. Please stop live broadcast or close the existing pjsua.exe, then try again."),
            ("Address already in use", "PJSUA SIP port is already in use. Please stop live broadcast or close the existing pjsua.exe, then try again."),
            ("bind() error", "PJSUA could not bind the configured SIP/RTP port. Please close the existing pjsua.exe or change the local ports in config.json."),
            ("Unable to open sound device", "PJSUA could not open the selected audio device. Please check capture_dev/playback_dev in config.json."),
            ("Invalid audio device", "PJSUA audio device setting is invalid. Please check capture_dev/playback_dev in config.json."),
        ]
        for marker, message in checks:
            if marker in text:
                return message
        return None

    def _read_log(self, log_name: str) -> str:
        log_path = self.logs_dir / log_name
        if not log_path.exists():
            return ""
        try:
            return log_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ""

    @staticmethod
    def _wave_duration(audio_path: Path) -> float:
        with wave.open(str(audio_path), "rb") as wav_file:
            return wav_file.getnframes() / float(wav_file.getframerate())

    def _prepare_audio_file(self, audio_path: Path) -> Path:
        gain_percent = float(self.config.get("local", {}).get("audio_gain", 100.0))
        gain_percent = max(0.0, min(200.0, gain_percent))
        if abs(gain_percent - 100.0) < 0.01:
            return audio_path

        instance_id = str(self.config.get("pjsua", {}).get("instance_id", "")).strip()
        suffix = f"_{instance_id}" if instance_id else ""
        output_path = self.logs_dir / f"_pjsua_volume_{audio_path.stem}{suffix}.wav"
        self._write_gain_adjusted_wav(audio_path, output_path, gain_percent / 100.0)
        self.notify(f"Prepared audio volume: {gain_percent:.0f}%")
        return output_path

    @staticmethod
    def _write_gain_adjusted_wav(source_path: Path, output_path: Path, gain: float) -> None:
        with wave.open(str(source_path), "rb") as source:
            params = source.getparams()
            frames = source.readframes(source.getnframes())

        if params.sampwidth != 2:
            raise PjsuaError("Volume adjustment currently supports 16-bit PCM WAV files only.")

        adjusted = bytearray(len(frames))
        for index in range(0, len(frames), 2):
            sample = int.from_bytes(frames[index:index + 2], byteorder="little", signed=True)
            sample = int(round(sample * gain))
            sample = max(-32768, min(32767, sample))
            adjusted[index:index + 2] = sample.to_bytes(2, byteorder="little", signed=True)

        with wave.open(str(output_path), "wb") as output:
            output.setparams(params)
            output.writeframes(bytes(adjusted))
