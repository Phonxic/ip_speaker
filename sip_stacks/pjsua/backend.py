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
        self.playback_audio_path: Path | None = None
        self.logs_dir = base_dir / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def start_broadcast(self, audio_path: Path) -> None:
        pjsua_config = self.config.get("pjsua", {})
        local = self.config.get("local", {})
        speaker = self.config.get("speaker", {})

        exe_path = Path(pjsua_config.get("path", ""))
        if not exe_path.exists():
            raise PjsuaError(f"PJSUA executable not found:\n{exe_path}")
        if not audio_path.exists():
            raise PjsuaError(f"Audio file not found:\n{audio_path}")
        self.playback_audio_path = self._prepare_audio_file(audio_path)

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

        log_path = self.logs_dir / "pjsua_gui.log"
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
            "--null-audio",
            f"--play-file={self.playback_audio_path}",
            "--auto-play",
            "--auto-play-hangup",
        ]

        for codec in pjsua_config.get("disable_codecs", []):
            args.append(f"--dis-codec={codec}")

        args.append(target_uri)

        self.notify(f"PJSUA dialing {target_uri}")
        self.process = subprocess.Popen(
            args,
            cwd=str(self.base_dir),
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    def wait_for_audio_then_hangup(self, audio_path: Path) -> None:
        duration = self._wave_duration(self.playback_audio_path or audio_path)
        timeout = duration + float(self.config.get("pjsua", {}).get("extra_wait_seconds", 8.0))
        started = time.monotonic()

        while time.monotonic() - started < timeout:
            if self.process and self.process.poll() is not None:
                break
            if self._log_contains_disconnected():
                break
            time.sleep(0.2)

        self.stop()

    def stop(self) -> None:
        if not self.process:
            return
        if self.process.poll() is None:
            try:
                if self.process.stdin:
                    self.process.stdin.write("q\n")
                    self.process.stdin.flush()
                self.process.wait(timeout=3)
            except Exception:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except Exception:
                    self.process.kill()
        self.process = None

    def _log_contains_disconnected(self) -> bool:
        log_path = self.logs_dir / "pjsua_gui.log"
        if not log_path.exists():
            return False
        try:
            text = log_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return False
        return "Call 0 is DISCONNECTED" in text or "Response msg 200/BYE" in text

    @staticmethod
    def _wave_duration(audio_path: Path) -> float:
        with wave.open(str(audio_path), "rb") as wav_file:
            return wav_file.getnframes() / float(wav_file.getframerate())

    def _prepare_audio_file(self, audio_path: Path) -> Path:
        gain_percent = float(self.config.get("local", {}).get("audio_gain", 100.0))
        gain_percent = max(0.0, min(200.0, gain_percent))
        if abs(gain_percent - 100.0) < 0.01:
            return audio_path

        output_path = self.logs_dir / f"_pjsua_volume_{audio_path.stem}.wav"
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
