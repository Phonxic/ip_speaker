import json
import os
import re
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from sip_stacks.baresip.backend import BaresipBackend, BaresipError
from sip_stacks.pjsua.backend import PjsuaBackend, PjsuaError

APP_TITLE = "Windows Broadcast Management Client"
BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
AUDIO_DIR = BASE_DIR / "audio"
LOG_DIR = BASE_DIR / "logs"
GUI_LOG_PATH = LOG_DIR / "gui.log"

AUDIO_DEFAULTS = {
    "測試廣播": "testing.wav",
    "旅客跌倒": "fall_warning.wav",
    "行李滾落": "baggage_warning.wav",
    "輪椅進入": "wheelchair_warning.wav",
    "旅客逗留": "stay_warning.wav",
}

LABELS = {
    "settings": "IP Speaker 設定",
    "backend": "Backend",
    "local_ip": "Local IP",
    "advertise_ip": "Advertise IP",
    "speaker_ip": "Speaker IP",
    "sip_user": "SIP User",
    "local_sip_port": "Local SIP Port",
    "local_rtp_port": "Local RTP Port",
    "speaker_sip_port": "Speaker SIP Port",
    "audio_volume": "播放音量",
    "sip_uri": "Current SIP URI",
    "apply": "套用設定",
    "test": "測試撥號 / 播放 testing.wav",
    "live": "人員通話廣播",
    "live_disabled": "目前流程使用預錄 WAV 檔。PJSUA 可自動撥號、播放音檔、播放完自動掛斷。",
    "audio": "預錄語音廣播",
    "stop": "停止播放 / 掛斷",
    "open_audio": "開啟音訊資料夾",
    "log": "事件紀錄",
    "ready": "準備就緒",
}


def default_config() -> dict:
    return {
        "backend": "pjsua",
        "local": {
            "ip": "140.124.42.67",
            "advertise_ip": "140.124.42.67",
            "sip_port": 64882,
            "sip_user": "101",
            "sip_identity": "140.124.42.67",
            "rtp_port": 4004,
            "audio_gain": 100.0,
            "start_delay_ms": 500,
        },
        "speaker": {"ip": "192.168.6.120", "sip_user": "4267", "sip_port": 5060},
        "pjsua": {
            "path": r"C:\sipbuild\pjproject\build-cmake\pjsip-apps\Release\pjsua.exe",
            "log_level": 5,
            "app_log_level": 4,
            "extra_wait_seconds": 8.0,
            "disable_codecs": [
                "speex/16000",
                "speex/8000",
                "speex/32000",
                "GSM/8000",
                "iLBC/8000",
                "G722/8000",
                "G7221/16000",
                "G7221/32000",
            ],
        },
        "baresip": {
            "path": r"C:\sipbuild\baresip\build\Release\baresip.exe",
            "module_path": "",
            "module_suffix": "",
            "ctrl_tcp_port": 4444,
            "startup_delay_sec": 1.0,
            "max_call_seconds": 60,
            "audio_codecs": "pcma,pcmu/8000/1",
            "cleanup_existing": True,
            "pre_silence_ms": 1500,
            "audio_source": "wasapi",
            "sine_frequency_hz": 1000,
            "sip_trace": True,
            "net_interface": "",
            "rtp_ports": "4004-4005",
            "user_agent": "MicroSIP/3.22.12",
            "wasapi_source_device": "",
            "windows_playback_device": "CABLE Input",
        },
        "audio_files": AUDIO_DEFAULTS.copy(),
    }


def normalize_audio_files(audio_files: dict) -> dict:
    result = AUDIO_DEFAULTS.copy()
    if not isinstance(audio_files, dict):
        return result

    filename_to_label = {filename: label for label, filename in AUDIO_DEFAULTS.items()}
    for label, filename in audio_files.items():
        if not isinstance(filename, str):
            continue
        canonical = filename_to_label.get(filename)
        if canonical:
            result[canonical] = filename
        elif isinstance(label, str) and label.strip() and "?" not in label:
            result[label] = filename
    return result


def load_config() -> dict:
    config = default_config()
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("r", encoding="utf-8-sig") as file:
            old = json.load(file)
        config.update(old)
        defaults = default_config()
        config["local"] = {**defaults["local"], **old.get("local", {})}
        config["speaker"] = {**defaults["speaker"], **old.get("speaker", {})}
        config["pjsua"] = {**defaults["pjsua"], **old.get("pjsua", {})}
        config["baresip"] = {**defaults["baresip"], **old.get("baresip", {})}
        config["backend"] = old.get("backend", "pjsua")
        if "sip_uri" in old and not old.get("speaker"):
            user, ip = parse_sip_uri(old["sip_uri"])
            config["speaker"]["sip_user"] = user or config["speaker"]["sip_user"]
            config["speaker"]["ip"] = ip or config["speaker"]["ip"]
        config["audio_files"] = normalize_audio_files(old.get("audio_files", {}))
    else:
        save_config(config)
    return config


def save_config(config: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_sip_uri(uri: str) -> tuple[str | None, str | None]:
    match = re.match(r"sip:([^@]+)@([^:;]+)", uri or "")
    if not match:
        return None, None
    return match.group(1), match.group(2)


class BroadcastApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("920x760")
        self.minsize(820, 680)
        self.configure(padx=16, pady=16)
        self.config_data = load_config()
        self.active_backend = None
        self.worker_thread = None
        self.status_text = tk.StringVar(value=LABELS["ready"])
        self.sip_uri_text = tk.StringVar()
        self.volume_text = tk.StringVar()
        self.audio_frame = None
        self.log_text = None
        self._build_ui()
        self._load_config_to_vars()
        self.update_sip_uri()
        self.log("GUI ready")

    def _build_ui(self):
        tk.Label(self, text=APP_TITLE, font=("Microsoft JhengHei UI", 16, "bold")).pack(fill="x", pady=(0, 12))
        self._build_settings_section()
        self._build_live_section()
        self._build_audio_section()
        self._build_control_section()
        self._build_log_section()
        self._build_status_bar()

    def _build_settings_section(self):
        frame = tk.LabelFrame(self, text=LABELS["settings"], padx=12, pady=12, font=("Microsoft JhengHei UI", 10, "bold"))
        frame.pack(fill="x", pady=(0, 10))
        for col in range(8):
            frame.columnconfigure(col, weight=1)

        self.backend_var = tk.StringVar()
        self.local_ip_var = tk.StringVar()
        self.advertise_ip_var = tk.StringVar()
        self.speaker_ip_var = tk.StringVar()
        self.sip_user_var = tk.StringVar()
        self.local_sip_port_var = tk.StringVar()
        self.local_rtp_port_var = tk.StringVar()
        self.speaker_sip_port_var = tk.StringVar()
        self.audio_gain_var = tk.DoubleVar()

        fields = [
            (LABELS["backend"], self.backend_var, "combo"),
            (LABELS["local_ip"], self.local_ip_var, "entry"),
            (LABELS["advertise_ip"], self.advertise_ip_var, "entry"),
            (LABELS["speaker_ip"], self.speaker_ip_var, "entry"),
            (LABELS["sip_user"], self.sip_user_var, "entry"),
            (LABELS["local_sip_port"], self.local_sip_port_var, "entry"),
            (LABELS["local_rtp_port"], self.local_rtp_port_var, "entry"),
            (LABELS["speaker_sip_port"], self.speaker_sip_port_var, "entry"),
        ]
        for index, (label, var, kind) in enumerate(fields):
            row = index // 4
            col = (index % 4) * 2
            tk.Label(frame, text=label, anchor="w").grid(row=row, column=col, sticky="ew", padx=(0, 4), pady=4)
            if kind == "combo":
                widget = ttk.Combobox(frame, textvariable=var, values=("pjsua", "baresip"), state="readonly")
            else:
                widget = tk.Entry(frame, textvariable=var)
            widget.grid(row=row, column=col + 1, sticky="ew", padx=(0, 10), pady=4)
            if var is not self.backend_var:
                var.trace_add("write", lambda *_args: self.update_sip_uri())

        tk.Label(frame, text=LABELS["audio_volume"], anchor="w").grid(row=2, column=0, sticky="ew", padx=(0, 4), pady=4)
        volume_frame = tk.Frame(frame)
        volume_frame.grid(row=2, column=1, columnspan=3, sticky="ew", padx=(0, 10), pady=4)
        volume_frame.columnconfigure(0, weight=1)
        tk.Scale(
            volume_frame,
            variable=self.audio_gain_var,
            from_=0,
            to=200,
            orient="horizontal",
            resolution=5,
            showvalue=False,
            command=self.update_volume_text,
        ).grid(row=0, column=0, sticky="ew")
        tk.Label(volume_frame, textvariable=self.volume_text, width=6, anchor="e").grid(row=0, column=1, padx=(8, 0))

        tk.Label(frame, text=LABELS["sip_uri"], anchor="w").grid(row=2, column=4, sticky="ew", padx=(0, 4), pady=4)
        tk.Label(frame, textvariable=self.sip_uri_text, anchor="w").grid(row=2, column=5, columnspan=3, sticky="ew", pady=4)
        tk.Button(frame, text=LABELS["apply"], command=self.apply_settings, height=2).grid(row=3, column=0, columnspan=4, sticky="ew", padx=(0, 8), pady=(8, 0))
        tk.Button(frame, text=LABELS["test"], command=lambda: self.start_audio_broadcast("測試廣播"), height=2).grid(row=3, column=4, columnspan=4, sticky="ew", pady=(8, 0))

    def _build_live_section(self):
        frame = tk.LabelFrame(self, text=LABELS["live"], padx=12, pady=12, font=("Microsoft JhengHei UI", 10, "bold"))
        frame.pack(fill="x", pady=(0, 10))
        tk.Label(frame, text=LABELS["live_disabled"], anchor="w", justify="left", wraplength=850).pack(fill="x")

    def _build_audio_section(self):
        frame = tk.LabelFrame(self, text=LABELS["audio"], padx=12, pady=12, font=("Microsoft JhengHei UI", 10, "bold"))
        frame.pack(fill="x", pady=(0, 10))
        self.audio_frame = frame
        self.refresh_audio_buttons()

    def _build_control_section(self):
        frame = tk.Frame(self)
        frame.pack(fill="x", pady=(0, 10))
        tk.Button(frame, text=LABELS["stop"], command=self.stop_playback, height=2).pack(side="left", fill="x", expand=True, padx=(0, 8))
        tk.Button(frame, text=LABELS["open_audio"], command=self.open_audio_folder, height=2).pack(side="left", fill="x", expand=True)

    def _build_log_section(self):
        frame = tk.LabelFrame(self, text=LABELS["log"], padx=8, pady=8, font=("Microsoft JhengHei UI", 10, "bold"))
        frame.pack(fill="both", expand=True, pady=(0, 10))
        self.log_text = tk.Text(frame, height=8, wrap="word", state="disabled")
        scrollbar = tk.Scrollbar(frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def _build_status_bar(self):
        frame = tk.Frame(self, bd=1, relief="sunken")
        frame.pack(fill="x", side="bottom")
        tk.Label(frame, textvariable=self.status_text, anchor="w", padx=8, pady=7).pack(fill="x")

    def _load_config_to_vars(self):
        local = self.config_data.get("local", {})
        speaker = self.config_data.get("speaker", {})
        self.backend_var.set(self.config_data.get("backend", "pjsua"))
        self.local_ip_var.set(local.get("ip", ""))
        self.advertise_ip_var.set(local.get("advertise_ip", ""))
        self.local_sip_port_var.set(str(local.get("sip_port", 64882)))
        self.local_rtp_port_var.set(str(local.get("rtp_port", 4004)))
        self.speaker_ip_var.set(speaker.get("ip", "192.168.6.120"))
        self.sip_user_var.set(str(speaker.get("sip_user", "4267")))
        self.speaker_sip_port_var.set(str(speaker.get("sip_port", 5060)))
        self.audio_gain_var.set(float(local.get("audio_gain", 100.0)))
        self.update_volume_text()

    def refresh_audio_buttons(self):
        for child in self.audio_frame.winfo_children():
            child.destroy()
        audio_files = normalize_audio_files(self.config_data.get("audio_files", {}))
        self.config_data["audio_files"] = audio_files
        for index, audio_name in enumerate(audio_files):
            row = index // 2
            col = index % 2
            self.audio_frame.columnconfigure(col, weight=1)
            tk.Button(
                self.audio_frame,
                text=f"Auto Play: {audio_name}",
                command=lambda name=audio_name: self.start_audio_broadcast(name),
                height=2,
            ).grid(row=row, column=col, sticky="ew", padx=4, pady=4)

    def update_sip_uri(self):
        if hasattr(self, "sip_uri_text"):
            self.sip_uri_text.set(f"sip:{self.sip_user_var.get()}@{self.speaker_ip_var.get()}:{self.speaker_sip_port_var.get()}")

    def update_volume_text(self, _value=None):
        if hasattr(self, "volume_text"):
            self.volume_text.set(f"{self.audio_gain_var.get():.0f}%")

    def current_settings(self) -> dict:
        local_ip = self.local_ip_var.get().strip()
        advertise_ip = self.advertise_ip_var.get().strip()
        speaker_ip = self.speaker_ip_var.get().strip()
        sip_user = self.sip_user_var.get().strip()
        if not local_ip or local_ip.lower() == "localhost" or local_ip == "127.0.0.1":
            raise ValueError("Local IP must be your Windows LAN IP, not 127.0.0.1 or localhost.")
        if not speaker_ip:
            raise ValueError("Speaker IP cannot be empty.")
        if not sip_user:
            raise ValueError("SIP User cannot be empty.")
        try:
            local_sip_port = int(self.local_sip_port_var.get())
            local_rtp_port = int(self.local_rtp_port_var.get())
            speaker_sip_port = int(self.speaker_sip_port_var.get())
        except ValueError as exc:
            raise ValueError("Ports must be integers.") from exc
        return {
            "local_ip": local_ip,
            "advertise_ip": advertise_ip or local_ip,
            "local_sip_port": local_sip_port,
            "local_rtp_port": local_rtp_port,
            "speaker_ip": speaker_ip,
            "speaker_sip_user": sip_user,
            "speaker_sip_port": speaker_sip_port,
            "audio_gain": max(0.0, min(200.0, float(self.audio_gain_var.get()))),
            "start_delay_ms": int(self.config_data.get("local", {}).get("start_delay_ms", 500)),
        }

    def apply_settings(self, silent: bool = False):
        try:
            settings = self.current_settings()
        except ValueError as exc:
            if not silent:
                self.log(f"Settings error: {exc}")
                messagebox.showerror(APP_TITLE, str(exc))
            return False

        existing_local = self.config_data.get("local", {})
        self.config_data["backend"] = self.backend_var.get() or "pjsua"
        self.config_data["local"] = {
            "ip": settings["local_ip"],
            "advertise_ip": settings["advertise_ip"],
            "sip_port": settings["local_sip_port"],
            "rtp_port": settings["local_rtp_port"],
            "audio_gain": settings["audio_gain"],
            "start_delay_ms": settings["start_delay_ms"],
            "sip_identity": existing_local.get("sip_identity", settings["advertise_ip"]),
            "sip_user": existing_local.get("sip_user", "101"),
        }
        self.config_data["speaker"] = {
            "ip": settings["speaker_ip"],
            "sip_user": settings["speaker_sip_user"],
            "sip_port": settings["speaker_sip_port"],
        }
        self.config_data["audio_files"] = normalize_audio_files(self.config_data.get("audio_files", {}))
        save_config(self.config_data)
        self.update_sip_uri()
        self.update_volume_text()
        if not silent:
            self.set_status(f"設定已套用，音量 {settings['audio_gain']:.0f}%")
            self.log("Settings applied and saved")
        return True

    def start_audio_broadcast(self, audio_name: str):
        self.log(f"Button pressed: {audio_name}")
        self.set_status(f"準備廣播：{audio_name}，音量 {self.audio_gain_var.get():.0f}%")
        if self.worker_thread and self.worker_thread.is_alive():
            self.log("Broadcast ignored: previous broadcast is still running")
            messagebox.showwarning(APP_TITLE, "A broadcast is already running. Please stop it first.")
            return
        if not self.apply_settings(silent=True):
            return

        audio_files = normalize_audio_files(self.config_data.get("audio_files", {}))
        audio_file = audio_files.get(audio_name)
        if not audio_file:
            self.log(f"Audio setting not found: {audio_name}")
            messagebox.showerror(APP_TITLE, f"Audio setting not found: {audio_name}")
            return

        audio_path = AUDIO_DIR / audio_file
        self.log(f"Selected audio: {audio_path}")
        if not audio_path.exists():
            self.log(f"Audio file not found: {audio_path}")
            messagebox.showerror(APP_TITLE, f"Audio file not found:\n{audio_path}")
            return

        backend_name = self.config_data.get("backend", "pjsua")
        self.worker_thread = threading.Thread(target=self._broadcast_worker, args=(backend_name, audio_path), daemon=True)
        self.worker_thread.start()

    def _broadcast_worker(self, backend_name: str, audio_path: Path):
        try:
            self.set_status_threadsafe(f"Starting {backend_name} backend")
            self.log_threadsafe(f"Starting {backend_name} backend")
            if backend_name == "pjsua":
                backend = PjsuaBackend(self.config_data, BASE_DIR, self.log_and_status_threadsafe)
            elif backend_name == "baresip":
                backend = BaresipBackend(self.config_data, BASE_DIR, self.log_and_status_threadsafe)
            else:
                raise RuntimeError(f"Unknown backend: {backend_name}")

            self.active_backend = backend
            backend.start_broadcast(audio_path)
            self.log_threadsafe("Dial command sent, waiting for playback")
            backend.wait_for_audio_then_hangup(audio_path)
            self.log_threadsafe("Broadcast completed")
            self.set_status_threadsafe("廣播完成")
        except (PjsuaError, BaresipError) as exc:
            self.log_threadsafe(f"{backend_name} error: {exc}")
            self.show_error_threadsafe(str(exc))
            self.set_status_threadsafe(f"{backend_name} setup error")
        except Exception as exc:
            self.log_threadsafe(f"Unexpected error: {exc}")
            self.show_error_threadsafe(str(exc))
            self.set_status_threadsafe(f"{backend_name} error: {exc}")
        finally:
            self.active_backend = None

    def stop_playback(self):
        self.log("Stop requested")
        try:
            if self.active_backend:
                self.active_backend.stop()
        except Exception as exc:
            self.log(f"Stop error: {exc}")
        self.set_status("已送出停止請求")

    def open_audio_folder(self):
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        self.log(f"Opening audio folder: {AUDIO_DIR}")
        os.startfile(AUDIO_DIR)

    def set_status(self, message: str):
        self.status_text.set(message)

    def log(self, message: str):
        timestamp = time.strftime("%H:%M:%S")
        line = f"[{timestamp}] {message}"
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with GUI_LOG_PATH.open("a", encoding="utf-8") as file:
            file.write(line + "\n")
        if self.log_text:
            self.log_text.configure(state="normal")
            self.log_text.insert("end", line + "\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")

    def set_status_threadsafe(self, message: str):
        self.after(0, lambda msg=message: self.set_status(msg))

    def log_threadsafe(self, message: str):
        self.after(0, lambda msg=message: self.log(msg))

    def log_and_status_threadsafe(self, message: str):
        self.after(0, lambda msg=message: (self.log(msg), self.set_status(msg)))

    def show_error_threadsafe(self, message: str):
        self.after(0, lambda msg=message: messagebox.showerror(APP_TITLE, msg))


if __name__ == "__main__":
    app = BroadcastApp()
    app.mainloop()
