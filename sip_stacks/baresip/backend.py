import json
import os
import shutil
import socket
import subprocess
import threading
import time
import ctypes
import wave
from datetime import datetime
from pathlib import Path

try:
    import winsound
except ImportError:
    winsound = None


class BaresipError(RuntimeError):
    pass


class WaveOutError(RuntimeError):
    pass


class WaveOutPlayer:
    CALLBACK_NULL = 0
    WHDR_DONE = 0x00000001
    WAVE_MAPPER = 0xFFFFFFFF

    class WAVEFORMATEX(ctypes.Structure):
        _fields_ = [
            ("wFormatTag", ctypes.c_ushort),
            ("nChannels", ctypes.c_ushort),
            ("nSamplesPerSec", ctypes.c_uint),
            ("nAvgBytesPerSec", ctypes.c_uint),
            ("nBlockAlign", ctypes.c_ushort),
            ("wBitsPerSample", ctypes.c_ushort),
            ("cbSize", ctypes.c_ushort),
        ]

    class WAVEHDR(ctypes.Structure):
        pass

    WAVEHDR._fields_ = [
        ("lpData", ctypes.c_void_p),
        ("dwBufferLength", ctypes.c_uint),
        ("dwBytesRecorded", ctypes.c_uint),
        ("dwUser", ctypes.c_size_t),
        ("dwFlags", ctypes.c_uint),
        ("dwLoops", ctypes.c_uint),
        ("lpNext", ctypes.POINTER(WAVEHDR)),
        ("reserved", ctypes.c_size_t),
    ]

    class WAVEOUTCAPSW(ctypes.Structure):
        _fields_ = [
            ("wMid", ctypes.c_ushort),
            ("wPid", ctypes.c_ushort),
            ("vDriverVersion", ctypes.c_uint),
            ("szPname", ctypes.c_wchar * 32),
            ("dwFormats", ctypes.c_uint),
            ("wChannels", ctypes.c_ushort),
            ("wReserved1", ctypes.c_ushort),
            ("dwSupport", ctypes.c_uint),
        ]

    def __init__(self):
        self.winmm = ctypes.WinDLL("winmm")
        self._thread = None
        self._handle = None
        self._stop_event = threading.Event()

    def list_devices(self) -> list[tuple[int, str]]:
        devices = []
        for index in range(self.winmm.waveOutGetNumDevs()):
            caps = self.WAVEOUTCAPSW()
            result = self.winmm.waveOutGetDevCapsW(index, ctypes.byref(caps), ctypes.sizeof(caps))
            if result == 0:
                devices.append((index, caps.szPname))
        return devices

    def _device_id(self, requested_name: str) -> int:
        name = (requested_name or "default").strip()
        if not name or name.lower() == "default":
            return self.WAVE_MAPPER
        needle = name.lower()
        for index, device_name in self.list_devices():
            if needle in device_name.lower():
                return index
        available = "\n".join(f"{index}: {device}" for index, device in self.list_devices())
        raise WaveOutError(f"找不到播放裝置：{name}\n\n可用輸出裝置：\n{available}")

    def play(self, audio_path: Path, device_name: str) -> None:
        self.stop()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, args=(Path(audio_path), device_name), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._handle is not None:
            self.winmm.waveOutReset(self._handle)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def _run(self, audio_path: Path, device_name: str) -> None:
        handle = ctypes.c_void_p()
        header = None
        try:
            with wave.open(str(audio_path), "rb") as wav:
                if wav.getcomptype() != "NONE":
                    raise WaveOutError("waveOut 只支援未壓縮 PCM WAV。")
                channels = wav.getnchannels()
                sample_width = wav.getsampwidth()
                sample_rate = wav.getframerate()
                frames = wav.readframes(wav.getnframes())

            block_align = channels * sample_width
            fmt = self.WAVEFORMATEX(
                1,
                channels,
                sample_rate,
                sample_rate * block_align,
                block_align,
                sample_width * 8,
                0,
            )
            result = self.winmm.waveOutOpen(
                ctypes.byref(handle),
                ctypes.c_uint(self._device_id(device_name)),
                ctypes.byref(fmt),
                0,
                0,
                self.CALLBACK_NULL,
            )
            if result != 0:
                raise WaveOutError(f"waveOutOpen 失敗，錯誤碼：{result}")

            self._handle = handle
            buffer = ctypes.create_string_buffer(frames)
            header = self.WAVEHDR(ctypes.cast(buffer, ctypes.c_void_p), len(frames), 0, 0, 0, 0, None, 0)
            result = self.winmm.waveOutPrepareHeader(handle, ctypes.byref(header), ctypes.sizeof(header))
            if result != 0:
                raise WaveOutError(f"waveOutPrepareHeader 失敗，錯誤碼：{result}")
            result = self.winmm.waveOutWrite(handle, ctypes.byref(header), ctypes.sizeof(header))
            if result != 0:
                raise WaveOutError(f"waveOutWrite 失敗，錯誤碼：{result}")

            while not self._stop_event.is_set() and not (header.dwFlags & self.WHDR_DONE):
                time.sleep(0.05)
        finally:
            if handle.value:
                if header is not None:
                    self.winmm.waveOutUnprepareHeader(handle, ctypes.byref(header), ctypes.sizeof(header))
                self.winmm.waveOutClose(handle)
            self._handle = None


class BaresipBackend:
    def __init__(self, config: dict, base_dir: Path, status_callback=None):
        self.config = config
        self.base_dir = Path(base_dir)
        self.status_callback = status_callback or (lambda _message: None)
        self.process = None
        self.config_dir = None
        self.appdata_dir = None
        self.backup_dir = None
        self._reader_thread = None
        self._last_output = []
        self._wave_player = WaveOutPlayer()
        self.output_log_path = self.base_dir / "logs" / "baresip_output.log"

    def _status(self, message: str) -> None:
        self.status_callback(message)

    def _baresip_path(self) -> str:
        baresip = self.config.get("baresip", {})
        configured = str(baresip.get("path", "")).strip()
        candidates = []
        if configured:
            candidates.append(configured)
        candidates.extend(
            [
                r"C:\sipbuild\baresip\build\Release\baresip.exe",
                r"C:\sipbuild\install\bin\baresip.exe",
                "baresip",
                r"C:\Program Files\baresip\baresip.exe",
                r"C:\Program Files (x86)\baresip\baresip.exe",
                str(self.base_dir / "tools" / "baresip" / "baresip.exe"),
                str(self.base_dir / "tools" / "baresip" / "bin" / "baresip.exe"),
                str(self.base_dir / "tools" / "baresip" / "build" / "baresip.exe"),
                str(self.base_dir / "tools" / "baresip" / "build" / "src" / "Release" / "baresip.exe"),
            ]
        )
        for candidate in candidates:
            if candidate == "baresip":
                found = shutil.which("baresip")
                if found:
                    return found
            elif Path(candidate).exists():
                return candidate
        checked = "\n".join(candidates)
        raise BaresipError(f"找不到 baresip.exe，請在 config.json 的 baresip.path 設定正確路徑。\n\n已檢查：\n{checked}")

    def _speaker_uri(self) -> str:
        speaker = self.config.get("speaker", {})
        user = speaker.get("sip_user", "4267")
        ip = speaker.get("ip", "192.168.6.120")
        port = int(speaker.get("sip_port", 5060))
        return f"sip:{user}@{ip}:{port}"

    def _local_account(self) -> str:
        local = self.config.get("local", {})
        local_ip = local.get("advertise_ip") or local.get("ip") or "127.0.0.1"
        identity = str(local.get("sip_identity") or local.get("sip_user") or "101").strip()
        audio_codecs = self.config.get("baresip", {}).get("audio_codecs", "pcma,pcmu/8000/1")
        if "@" in identity:
            aor = identity
        else:
            aor = f"{identity}@{local_ip}"
        return f"<sip:{aor}>;regint=0;audio_codecs={audio_codecs};ptime=20"

    def _ctrl_tcp_port(self) -> int:
        return int(self.config.get("baresip", {}).get("ctrl_tcp_port", 4444))

    def _cleanup_existing_baresip(self, baresip_path: str) -> None:
        if not self.config.get("baresip", {}).get("cleanup_existing", True):
            return
        try:
            subprocess.run(
                ["taskkill", "/IM", "baresip.exe", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            time.sleep(0.3)
        except Exception:
            pass

    def _preflight_ports(self) -> None:
        local = self.config.get("local", {})
        sip_port = int(local.get("sip_port", 5062))
        ctrl_port = self._ctrl_tcp_port()
        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            udp_sock.bind(("0.0.0.0", sip_port))
        except OSError as exc:
            message = (
                f"本機 SIP UDP port {sip_port} 已被其他程式占用，Baresip 無法啟動。\n"
                "請關閉占用該 port 的程式，或在 config.json / GUI 改用其他 Local SIP Port，例如 5062、5070 或 5080。\n\n"
                f"Windows 錯誤：{exc}"
            )
            raise BaresipError(message) from exc
        finally:
            udp_sock.close()

        tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            tcp_sock.bind(("127.0.0.1", ctrl_port))
        except OSError as exc:
            message = (
                f"Baresip 控制 TCP port {ctrl_port} 已被占用。\n"
                "請先關閉殘留的 baresip.exe，或在 config.json 修改 baresip.ctrl_tcp_port。\n\n"
                f"Windows 錯誤：{exc}"
            )
            raise BaresipError(message) from exc
        finally:
            tcp_sock.close()

    def _module_suffix(self) -> str:
        return str(self.config.get("baresip", {}).get("module_suffix", ""))

    def _module_line(self, name: str) -> str:
        suffix = self._module_suffix()
        if name.endswith(".so") or name.endswith(".dll"):
            return f"module {name}"
        return f"module {name}{suffix}"

    def _module_app_line(self, name: str) -> str:
        suffix = self._module_suffix()
        if name.endswith(".so") or name.endswith(".dll"):
            return f"module_app {name}"
        return f"module_app {name}{suffix}"

    def _appdata_baresip_dir(self) -> Path:
        appdata = os.environ.get("APPDATA")
        if not appdata:
            raise BaresipError("找不到 APPDATA，無法定位 baresip 設定資料夾。")
        return Path(appdata) / ".baresip"

    def _backup_existing_config(self, target_dir: Path) -> None:
        if self.backup_dir:
            return
        if not target_dir.exists():
            return
        config_path = target_dir / "config"
        if config_path.exists():
            try:
                if config_path.read_text(encoding="utf-8", errors="ignore").startswith("# Managed by ip_speaker"):
                    return
            except OSError:
                pass
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = target_dir.parent / f".baresip_ip_speaker_backup_{timestamp}"
        backup_dir.mkdir(parents=True, exist_ok=False)
        for name in ("config", "accounts", "contacts", "current_contact", "uuid"):
            src = target_dir / name
            if src.exists():
                shutil.copy2(src, backup_dir / name)
        self.backup_dir = backup_dir
        self._status(f"已備份 baresip 設定：{backup_dir}")

    def _prepare_audio_source(self, audio_path: Path) -> Path:
        pre_silence_ms = int(self.config.get("baresip", {}).get("pre_silence_ms", 0))
        if pre_silence_ms <= 0:
            return audio_path
        import wave

        runtime_dir = self.base_dir / "logs"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        prepared_path = runtime_dir / "baresip_audio_source.wav"
        with wave.open(str(audio_path), "rb") as src:
            params = src.getparams()
            frames = src.readframes(src.getnframes())
            silence_frames = int(src.getframerate() * pre_silence_ms / 1000)
            silence = b"\x00" * silence_frames * src.getnchannels() * src.getsampwidth()
        with wave.open(str(prepared_path), "wb") as dst:
            dst.setparams(params)
            dst.writeframes(silence + frames)
        self._status(f"Prepared audio with {pre_silence_ms} ms pre-silence: {prepared_path.name}")
        return prepared_path

    def _write_config(self, audio_path: Path) -> Path:
        local = self.config.get("local", {})
        baresip = self.config.get("baresip", {})
        self.config_dir = self._appdata_baresip_dir()
        self._backup_existing_config(self.config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)

        config_path = self.config_dir / "config"
        accounts_path = self.config_dir / "accounts"
        contacts_path = self.config_dir / "contacts"

        sip_port = int(local.get("sip_port", 5062))
        rtp_port = int(local.get("rtp_port", 4004))
        rtp_range = baresip.get("rtp_ports") or f"{rtp_port}-{rtp_port + 20}"
        sip_listen = baresip.get("sip_listen") or f"0.0.0.0:{sip_port}"
        module_path = str(baresip.get("module_path", "")).strip()
        source_mode = str(baresip.get("audio_source", "aufile")).lower().strip()
        if source_mode == "ausine":
            sine_frequency = int(baresip.get("sine_frequency_hz", 1000))
            audio_source_line = f"audio_source ausine,{sine_frequency}"
        elif source_mode == "wasapi":
            device = str(baresip.get("wasapi_source_device", "default")).strip() or "default"
            audio_source_line = f"audio_source wasapi,{device}"
        else:
            normalized_audio = str(audio_path.resolve()).replace("\\", "/")
            audio_source_line = f"audio_source aufile,{normalized_audio}"

        module_lines = [
            self._module_line("g711"),
            self._module_line("auconv"),
            self._module_line("auresamp"),
            self._module_line("aufile"),
            self._module_line("ausine"),
            self._module_line("wasapi"),
            self._module_line("uuid"),
            self._module_app_line("account"),
            self._module_app_line("menu"),
            self._module_app_line("debug_cmd"),
            self._module_app_line("ctrl_tcp"),
        ]
        if module_path:
            module_lines.insert(0, f"module_path {module_path}")

        config_text = "\n".join(
            [
                "# Managed by ip_speaker_demo. Existing AppData config was backed up before first overwrite.",
                "sip_transports udp",
                f"sip_listen {sip_listen}",
                "call_accept no",
                "call_max_calls 1",
                "audio_player aufile,nil",
                audio_source_line,
                "audio_alert aufile,nil",
                "ausrc_format s16",
                "auenc_format s16",
                "ausrc_channels 1",
                "audio_telev_pt 101",
                f"rtp_ports {rtp_range}",
                "rtp_stats yes",
                "audio_jitter_buffer_type fixed",
                "audio_jitter_buffer_ms 20-100",
                f"ctrl_tcp_listen 127.0.0.1:{self._ctrl_tcp_port()}",
                "",
                *module_lines,
                "",
            ]
        )
        account_text = self._local_account()
        config_path.write_text(config_text, encoding="utf-8")
        accounts_path.write_text(account_text + "\n", encoding="utf-8")
        contacts_path.write_text("", encoding="utf-8")
        self._status(
            "Baresip config written: "
            f"account={account_text}, sip_listen={sip_listen}, "
            f"rtp_ports={rtp_range}, {audio_source_line}"
        )
        return self.config_dir

    def _read_output(self):
        if not self.process or not self.process.stdout:
            return
        self.output_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.output_log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(f"\n--- Baresip run {datetime.now().isoformat(timespec='seconds')} ---\n")
            for line in self.process.stdout:
                text = line.rstrip()
                if not text:
                    continue
                log_file.write(text + "\n")
                log_file.flush()
                self._last_output.append(text)
                self._last_output = self._last_output[-150:]
                lowered = text.lower()
                if "call established" in lowered or "established" in lowered:
                    self._status("Baresip 通話已建立，正在播放音檔")
                elif "terminated" in lowered or "disconnected" in lowered:
                    self._status("Baresip 通話已結束")
                elif "audio encoder" in lowered or "aufile:" in lowered or "sip:" in lowered or "call:" in lowered:
                    self._status(text)

    def start_broadcast(self, audio_path: Path) -> None:
        if self.process and self.process.poll() is None:
            raise BaresipError("Baresip broadcast is already running.")
        baresip_path = self._baresip_path()
        self._cleanup_existing_baresip(baresip_path)
        self._preflight_ports()
        audio_source_path = self._prepare_audio_source(audio_path)
        self._write_config(audio_source_path)
        exe_dir = str(Path(baresip_path).resolve().parent)
        self._status("啟動 Baresip")
        args = [baresip_path, "-4", "-c"]
        user_agent = str(self.config.get("baresip", {}).get("user_agent", "")).strip()
        if user_agent:
            args.extend(["-a", user_agent])
        net_interface = str(self.config.get("baresip", {}).get("net_interface", "")).strip()
        if net_interface:
            args.extend(["-n", net_interface])
        if self.config.get("baresip", {}).get("sip_trace", False):
            args.append("-s")
        self._status(f"Baresip command: {' '.join(args)}")
        self.process = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=exe_dir,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        self._reader_thread = threading.Thread(target=self._read_output, daemon=True)
        self._reader_thread.start()
        time.sleep(float(self.config.get("baresip", {}).get("startup_delay_sec", 1.0)))
        if self.config.get("baresip", {}).get("sip_trace", False):
            try:
                self._send_ctrl_command("siptrace", "on")
            except Exception:
                pass
        self._send_ctrl_command("dial", self._speaker_uri())
        self._status("已送出 Baresip 撥號請求")
        self._play_windows_audio_if_needed(audio_source_path)

    def _play_windows_audio_if_needed(self, audio_path: Path) -> None:
        source_mode = str(self.config.get("baresip", {}).get("audio_source", "aufile")).lower().strip()
        if source_mode != "wasapi":
            return
        delay_ms = int(self.config.get("local", {}).get("start_delay_ms", 500))
        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)
        playback_device = str(self.config.get("baresip", {}).get("windows_playback_device", "CABLE Input")).strip()
        try:
            self._wave_player.play(audio_path, playback_device)
        except WaveOutError as exc:
            if winsound is None:
                raise BaresipError(str(exc)) from exc
            winsound.PlaySound(str(audio_path), winsound.SND_FILENAME | winsound.SND_ASYNC)
            raise BaresipError(f"{exc}\n\n已退回預設輸出播放，但這通常只會進耳機，不會進 CABLE。") from exc
        self._status(f"已播放到 {playback_device}，供 WASAPI/CABLE 擷取：{audio_path.name}")

    def _send_ctrl_command(self, command: str, params: str = "") -> dict:
        payload = json.dumps(
            {"command": command, "params": params, "token": f"{command}-{time.time_ns()}"},
            separators=(",", ":"),
        ).encode("utf-8")
        frame = str(len(payload)).encode("ascii") + b":" + payload + b","
        deadline = time.monotonic() + 5
        last_error = None
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self._ctrl_tcp_port()), timeout=1.0) as sock:
                    sock.sendall(frame)
                    data = self._read_netstring(sock)
                    if not data:
                        return {}
                    response = json.loads(data.decode("utf-8", errors="replace"))
                    if response.get("response") and response.get("ok") is False:
                        raise BaresipError(f"Baresip command failed: {command} {params}\n{response.get('data', '')}")
                    return response
            except (ConnectionRefusedError, TimeoutError, OSError) as exc:
                last_error = exc
                time.sleep(0.2)
        output = "\n".join(self._last_output[-30:])
        raise BaresipError(f"Cannot connect to Baresip ctrl_tcp: {last_error}\n\nRecent output:\n{output}")

    @staticmethod
    def _read_netstring(sock: socket.socket) -> bytes:
        header = bytearray()
        while True:
            ch = sock.recv(1)
            if not ch:
                return b""
            if ch == b":":
                break
            header.extend(ch)
            if len(header) > 20:
                raise BaresipError("Invalid ctrl_tcp netstring header.")
        length = int(header.decode("ascii"))
        payload = bytearray()
        while len(payload) < length:
            chunk = sock.recv(length - len(payload))
            if not chunk:
                break
            payload.extend(chunk)
        comma = sock.recv(1)
        if comma != b",":
            raise BaresipError("Invalid ctrl_tcp netstring terminator.")
        return bytes(payload)

    def wait_for_audio_then_hangup(self, audio_path: Path) -> None:
        timeout = float(self.config.get("baresip", {}).get("max_call_seconds", 60))
        started = time.monotonic()
        duration = self._wav_duration(audio_path)
        while time.monotonic() - started < min(timeout, duration + 10):
            if self.process and self.process.poll() is not None:
                break
            time.sleep(0.2)
        self.stop()

    def stop(self) -> None:
        self._wave_player.stop()
        if winsound is not None:
            try:
                winsound.PlaySound(None, winsound.SND_PURGE)
            except RuntimeError:
                pass
        if not self.process:
            return
        if self.process.poll() is None:
            try:
                self._send_ctrl_command("hangup")
                time.sleep(0.5)
            except Exception:
                pass
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.terminate()
        self.process = None

    @staticmethod
    def _wav_duration(audio_path: Path) -> float:
        import wave

        with wave.open(str(audio_path), "rb") as wav:
            return wav.getnframes() / float(wav.getframerate())

