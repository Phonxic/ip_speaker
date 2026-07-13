import json
import os
import re
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from audio_recorder import AudioRecorder, AudioRecorderError, filename_from_audio_id, validate_audio_id
from sip_stacks.baresip.backend import BaresipBackend, BaresipError
from sip_stacks.pjsua.backend import PjsuaBackend, PjsuaError

APP_TITLE = "Windows Broadcast Management Client"
BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
AUDIO_DIR = BASE_DIR / "audio"
LOG_DIR = BASE_DIR / "logs"
GUI_LOG_PATH = LOG_DIR / "gui.log"

DEFAULT_AUDIO_FILES = {
    "testing": {
        "display_name": "測試廣播",
        "filename": "testing.wav",
        "description": "確認 IP Speaker 是否可正常播放。",
    },
    "fall_warning": {
        "display_name": "旅客跌倒",
        "filename": "fall_warning.wav",
        "description": "旅客跌倒事件警示廣播。",
    },
    "baggage_warning": {
        "display_name": "行李滾落",
        "filename": "baggage_warning.wav",
        "description": "行李滾落事件警示廣播。",
    },
    "wheelchair_warning": {
        "display_name": "輪椅進入",
        "filename": "wheelchair_warning.wav",
        "description": "輪椅進入區域事件警示廣播。",
    },
    "stay_warning": {
        "display_name": "旅客逗留",
        "filename": "stay_warning.wav",
        "description": "旅客逗留事件警示廣播。",
    },
}


def default_config() -> dict:
    return {
        "backend": "pjsua",
        "local": {
            "ip": "140.124.42.67",
            "advertise_ip": "140.124.42.67",
            "sip_port": 64882,
            "rtp_port": 4004,
            "audio_gain": 100.0,
            "start_delay_ms": 900,
            "sip_identity": "140.124.42.67",
            "sip_user": "101",
        },
        "speaker": {"ip": "192.168.6.120", "sip_user": "4267", "sip_port": 5060},
        "pjsua": {
            "path": r"C:\sipbuild\pjproject\build-cmake\pjsip-apps\Release\pjsua.exe",
            "log_level": 5,
            "app_log_level": 4,
            "extra_wait_seconds": 8.0,
            "capture_dev": "",
            "playback_dev": "",
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
        "audio": {"folder": "audio", "sample_rate": 8000, "channels": 1, "sample_width": 2},
        "audio_files": DEFAULT_AUDIO_FILES.copy(),
    }


def normalize_audio_files(audio_files: dict) -> dict:
    result = {}
    if not isinstance(audio_files, dict):
        return DEFAULT_AUDIO_FILES.copy()

    old_filename_to_id = {item["filename"]: audio_id for audio_id, item in DEFAULT_AUDIO_FILES.items()}
    for key, value in audio_files.items():
        if isinstance(value, dict):
            audio_id = re.sub(r"[^A-Za-z0-9_-]+", "_", str(key).strip()).strip("_") or "audio"
            result[audio_id] = {
                "display_name": str(value.get("display_name") or audio_id),
                "filename": str(value.get("filename") or f"{audio_id}.wav"),
                "description": str(value.get("description") or ""),
            }
        elif isinstance(value, str):
            audio_id = old_filename_to_id.get(value) or re.sub(r"[^A-Za-z0-9_-]+", "_", Path(value).stem).strip("_")
            if not audio_id:
                continue
            default = DEFAULT_AUDIO_FILES.get(audio_id, {})
            display_name = default.get("display_name")
            if not display_name and isinstance(key, str) and "?" not in key:
                display_name = key
            result[audio_id] = {
                "display_name": display_name or audio_id,
                "filename": value,
                "description": default.get("description", ""),
            }

    for audio_id, item in DEFAULT_AUDIO_FILES.items():
        result.setdefault(audio_id, item.copy())
    return result


def load_config() -> dict:
    config = default_config()
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("r", encoding="utf-8-sig") as file:
            old = json.load(file)
        defaults = default_config()
        config.update(old)
        config["local"] = {**defaults["local"], **old.get("local", {})}
        config["speaker"] = {**defaults["speaker"], **old.get("speaker", {})}
        config["pjsua"] = {**defaults["pjsua"], **old.get("pjsua", {})}
        if "exe_path" in config["pjsua"] and "path" not in old.get("pjsua", {}):
            config["pjsua"]["path"] = config["pjsua"]["exe_path"]
        config["baresip"] = {**defaults["baresip"], **old.get("baresip", {})}
        config["audio"] = {**defaults["audio"], **old.get("audio", {})}
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
        self.geometry("1080x820")
        self.minsize(980, 720)
        self.configure(padx=16, pady=16)
        self.config_data = load_config()
        self.active_backend = None
        self.live_backend = None
        self.worker_thread = None
        self.recorder = AudioRecorder(
            sample_rate=int(self.config_data.get("audio", {}).get("sample_rate", 8000)),
            channels=int(self.config_data.get("audio", {}).get("channels", 1)),
        )
        self.recording_audio_id = None

        self.status_text = tk.StringVar(value="準備就緒")
        self.sip_uri_text = tk.StringVar()
        self.volume_text = tk.StringVar()
        self.audio_frame = None
        self.log_text = None
        self.audio_list = None
        self._build_ui()
        self._load_config_to_vars()
        self.update_sip_uri()
        self.refresh_audio_buttons()
        self.refresh_audio_list()
        self.log("GUI ready")

    def _build_ui(self):
        tk.Label(self, text=APP_TITLE, font=("Microsoft JhengHei UI", 16, "bold")).pack(fill="x", pady=(0, 12))
        self._build_settings_section()

        middle = tk.Frame(self)
        middle.pack(fill="both", expand=True, pady=(0, 10))
        middle.columnconfigure(0, weight=1)
        middle.columnconfigure(1, weight=1)
        middle.rowconfigure(0, weight=1)

        left = tk.Frame(middle)
        right = tk.Frame(middle)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        self._build_live_section(left)
        self._build_audio_section(left)
        self._build_control_section(left)
        self._build_audio_manager(right)
        self._build_log_section()
        self._build_status_bar()

    def _build_settings_section(self):
        frame = tk.LabelFrame(self, text="IP Speaker 設定", padx=12, pady=12, font=("Microsoft JhengHei UI", 10, "bold"))
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
            ("Backend", self.backend_var, "combo"),
            ("Local IP", self.local_ip_var, "entry"),
            ("Advertise IP", self.advertise_ip_var, "entry"),
            ("Speaker IP", self.speaker_ip_var, "entry"),
            ("SIP User", self.sip_user_var, "entry"),
            ("Local SIP Port", self.local_sip_port_var, "entry"),
            ("Local RTP Port", self.local_rtp_port_var, "entry"),
            ("Speaker SIP Port", self.speaker_sip_port_var, "entry"),
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

        tk.Label(frame, text="播放音量", anchor="w").grid(row=2, column=0, sticky="ew", padx=(0, 4), pady=4)
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

        tk.Label(frame, text="Current SIP URI", anchor="w").grid(row=2, column=4, sticky="ew", padx=(0, 4), pady=4)
        tk.Label(frame, textvariable=self.sip_uri_text, anchor="w").grid(row=2, column=5, columnspan=3, sticky="ew", pady=4)
        tk.Button(frame, text="套用設定", command=self.apply_settings, height=2).grid(row=3, column=0, columnspan=8, sticky="ew", pady=(8, 0))

    def _build_live_section(self, parent):
        frame = tk.LabelFrame(parent, text="即時廣播", padx=12, pady=12, font=("Microsoft JhengHei UI", 10, "bold"))
        frame.pack(fill="x", pady=(0, 10))
        tk.Button(frame, text="開始即時廣播", command=self.start_live_broadcast, height=2).pack(fill="x", pady=(0, 8))
        tk.Button(frame, text="停止即時廣播", command=self.stop_live_broadcast, height=2).pack(fill="x")

    def _build_audio_section(self, parent):
        frame = tk.LabelFrame(parent, text="預錄語音廣播", padx=12, pady=12, font=("Microsoft JhengHei UI", 10, "bold"))
        frame.pack(fill="both", expand=True, pady=(0, 10))
        self.audio_frame = frame

    def _build_control_section(self, parent):
        frame = tk.Frame(parent)
        frame.pack(fill="x", pady=(0, 10))
        tk.Button(frame, text="停止播放 / 掛斷", command=self.stop_playback, height=2).pack(side="left", fill="x", expand=True, padx=(0, 8))
        tk.Button(frame, text="開啟音訊資料夾", command=self.open_audio_folder, height=2).pack(side="left", fill="x", expand=True)

    def _build_audio_manager(self, parent):
        frame = tk.LabelFrame(parent, text="音檔管理 / 錄音", padx=12, pady=12, font=("Microsoft JhengHei UI", 10, "bold"))
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1, minsize=210)
        frame.columnconfigure(1, weight=0, minsize=92)
        frame.columnconfigure(2, weight=2, minsize=260)
        frame.rowconfigure(0, weight=1)
        frame.rowconfigure(3, weight=1)

        tk.Label(frame, text="音檔清單", anchor="w", font=("Microsoft JhengHei UI", 9, "bold")).grid(row=0, column=0, sticky="new", padx=(0, 10))
        self.audio_list = tk.Listbox(frame, height=8)
        self.audio_list.grid(row=0, column=0, rowspan=8, sticky="nsew", padx=(0, 10), pady=(22, 0))
        self.audio_list.bind("<<ListboxSelect>>", self.on_audio_selected)
        order_frame = tk.Frame(frame)
        order_frame.grid(row=8, column=0, sticky="ew", padx=(0, 10), pady=(8, 0))
        order_frame.columnconfigure(0, weight=1)
        order_frame.columnconfigure(1, weight=1)
        tk.Button(order_frame, text="上移", command=lambda: self.move_audio_entry(-1)).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        tk.Button(order_frame, text="下移", command=lambda: self.move_audio_entry(1)).grid(row=0, column=1, sticky="ew", padx=(4, 0))

        self.audio_id_var = tk.StringVar()
        self.audio_display_var = tk.StringVar()
        self.audio_filename_var = tk.StringVar()

        fields = [
            ("音檔 ID", self.audio_id_var),
            ("顯示名稱", self.audio_display_var),
            ("檔名", self.audio_filename_var),
        ]
        for row, (label, var) in enumerate(fields):
            tk.Label(frame, text=label, anchor="e", width=10).grid(row=row, column=1, sticky="ew", padx=(0, 8), pady=3)
            tk.Entry(frame, textvariable=var).grid(row=row, column=2, sticky="ew", pady=3)

        tk.Label(frame, text="描述", anchor="ne", width=10).grid(row=3, column=1, sticky="new", padx=(0, 8), pady=3)
        self.audio_description_text = tk.Text(frame, height=6, wrap="word")
        self.audio_description_text.grid(row=3, column=2, sticky="nsew", pady=3)

        tk.Button(frame, text="新增 / 更新音檔設定", command=self.save_audio_entry).grid(row=4, column=1, columnspan=2, sticky="ew", pady=(8, 3))
        tk.Button(frame, text="刪除音檔設定", command=self.delete_audio_entry).grid(row=5, column=1, columnspan=2, sticky="ew", pady=3)
        tk.Button(frame, text="開始錄音", command=self.start_recording).grid(row=6, column=1, sticky="ew", pady=(10, 3), padx=(0, 4))
        tk.Button(frame, text="停止錄音並儲存", command=self.stop_recording).grid(row=6, column=2, sticky="ew", pady=(10, 3), padx=(4, 0))
        tk.Button(frame, text="重新整理音檔", command=self.refresh_all_audio_views).grid(row=7, column=1, columnspan=2, sticky="ew", pady=3)

    def _build_log_section(self):
        frame = tk.LabelFrame(self, text="事件紀錄", padx=8, pady=8, font=("Microsoft JhengHei UI", 10, "bold"))
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
        if not self.audio_frame:
            return
        for child in self.audio_frame.winfo_children():
            child.destroy()
        audio_files = normalize_audio_files(self.config_data.get("audio_files", {}))
        self.config_data["audio_files"] = audio_files
        self.audio_frame.columnconfigure(0, weight=1)
        tk.Label(
            self.audio_frame,
            text="請先在右側音檔清單選取要播放的音檔。",
            anchor="w",
            justify="left",
            wraplength=420,
        ).grid(row=0, column=0, sticky="ew", padx=4, pady=(0, 8))
        tk.Button(
            self.audio_frame,
            text="播放選取音檔",
            command=self.start_selected_audio_broadcast,
            height=3,
        ).grid(row=1, column=0, sticky="ew", padx=4, pady=4)

    def refresh_audio_list(self, selected_audio_id: str | None = None):
        if not self.audio_list:
            return
        self.audio_list.delete(0, "end")
        selected_index = None
        for index, (audio_id, info) in enumerate(self.config_data.get("audio_files", {}).items()):
            self.audio_list.insert("end", f"{audio_id} - {info['display_name']}")
            if audio_id == selected_audio_id:
                selected_index = index
        if selected_index is not None:
            self.audio_list.selection_set(selected_index)
            self.audio_list.activate(selected_index)
            self.audio_list.see(selected_index)

    def selected_audio_id(self) -> str | None:
        if not self.audio_list:
            return None
        selection = self.audio_list.curselection()
        if not selection:
            return None
        audio_ids = list(self.config_data.get("audio_files", {}).keys())
        if selection[0] >= len(audio_ids):
            return None
        return audio_ids[selection[0]]

    def start_selected_audio_broadcast(self):
        audio_id = self.selected_audio_id()
        if not audio_id:
            messagebox.showwarning(APP_TITLE, "請先在右側音檔清單選取要播放的音檔。")
            self.set_status("請先選取音檔")
            return
        self.start_audio_broadcast(audio_id)

    def move_audio_entry(self, direction: int):
        audio_id = self.selected_audio_id()
        if not audio_id:
            messagebox.showwarning(APP_TITLE, "請先選擇要調整順序的音檔。")
            return

        audio_items = list(self.config_data.get("audio_files", {}).items())
        current_index = next((index for index, item in enumerate(audio_items) if item[0] == audio_id), None)
        if current_index is None:
            return

        new_index = current_index + direction
        if new_index < 0 or new_index >= len(audio_items):
            return

        audio_items[current_index], audio_items[new_index] = audio_items[new_index], audio_items[current_index]
        self.config_data["audio_files"] = dict(audio_items)
        save_config(self.config_data)
        self.refresh_audio_buttons()
        self.refresh_audio_list(selected_audio_id=audio_id)
        self.on_audio_selected()
        self.set_status("音檔順序已更新")
        self.log(f"Audio order updated: {audio_id}")

    def refresh_all_audio_views(self):
        self.config_data["audio_files"] = normalize_audio_files(self.config_data.get("audio_files", {}))
        save_config(self.config_data)
        self.refresh_audio_buttons()
        self.refresh_audio_list()
        self.log("Audio list refreshed")

    def on_audio_selected(self, _event=None):
        audio_id = self.selected_audio_id()
        if not audio_id:
            return
        info = self.config_data["audio_files"][audio_id]
        self.audio_id_var.set(audio_id)
        self.audio_display_var.set(info.get("display_name", ""))
        self.audio_filename_var.set(info.get("filename", ""))
        self.audio_description_text.delete("1.0", "end")
        self.audio_description_text.insert("1.0", info.get("description", ""))

    def save_audio_entry(self):
        try:
            audio_id = validate_audio_id(self.audio_id_var.get())
        except AudioRecorderError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        filename = self.audio_filename_var.get().strip() or filename_from_audio_id(audio_id)
        if not filename.lower().endswith(".wav"):
            filename += ".wav"
        self.config_data.setdefault("audio_files", {})[audio_id] = {
            "display_name": self.audio_display_var.get().strip() or audio_id,
            "filename": filename,
            "description": self.audio_description_text.get("1.0", "end").strip(),
        }
        save_config(self.config_data)
        self.refresh_audio_buttons()
        self.refresh_audio_list()
        self.log(f"Saved audio entry: {audio_id} -> {filename}")

    def delete_audio_entry(self):
        audio_id = self.audio_id_var.get().strip()
        if not audio_id or audio_id not in self.config_data.get("audio_files", {}):
            messagebox.showerror(APP_TITLE, "請先選擇要刪除的音檔設定。")
            return
        if not messagebox.askyesno(APP_TITLE, f"確定刪除音檔設定？\n{audio_id}"):
            return
        self.config_data["audio_files"].pop(audio_id, None)
        save_config(self.config_data)
        self.refresh_audio_buttons()
        self.refresh_audio_list()
        self.log(f"Deleted audio entry: {audio_id}")

    def start_recording(self):
        try:
            audio_id = validate_audio_id(self.audio_id_var.get())
            filename = self.audio_filename_var.get().strip() or filename_from_audio_id(audio_id)
            if not filename.lower().endswith(".wav"):
                filename += ".wav"
            output_path = AUDIO_DIR / filename
            if output_path.exists() and not messagebox.askyesno(APP_TITLE, f"{filename} 已存在，是否覆蓋？"):
                return
            self.recorder.start_recording(output_path)
            self.recording_audio_id = audio_id
            self.audio_filename_var.set(filename)
            self.set_status("音檔錄音中...")
            self.log(f"Recording started: {output_path}")
        except AudioRecorderError as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def stop_recording(self):
        try:
            output_path = self.recorder.stop_recording()
        except AudioRecorderError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        self.save_audio_entry()
        self.set_status(f"錄音完成：{output_path.name}")
        self.log(f"Recording saved: {output_path}")

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

    def start_audio_broadcast(self, audio_id: str):
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showwarning(APP_TITLE, "A broadcast is already running. Please stop it first.")
            return
        if self.live_backend and self.live_backend.is_live_running():
            messagebox.showwarning(APP_TITLE, "即時廣播仍在執行中，請先停止即時廣播。")
            self.set_status("請先停止即時廣播")
            return
        if self.live_backend and not self.live_backend.is_live_running():
            self.live_backend = None
        if not self.apply_settings(silent=True):
            return
        info = self.config_data.get("audio_files", {}).get(audio_id)
        if not info:
            messagebox.showerror(APP_TITLE, f"找不到音檔設定：{audio_id}")
            return
        audio_path = AUDIO_DIR / info["filename"]
        if not audio_path.exists():
            messagebox.showerror(APP_TITLE, f"找不到音檔：\n{audio_path}")
            return
        backend_name = self.config_data.get("backend", "pjsua")
        self.set_status(f"準備播放：{info['display_name']}")
        self.log(f"Playing {info['display_name']} | {audio_path} | {info.get('description', '')}")
        self.worker_thread = threading.Thread(target=self._broadcast_worker, args=(backend_name, audio_path), daemon=True)
        self.worker_thread.start()

    def _broadcast_worker(self, backend_name: str, audio_path: Path):
        try:
            self.set_status_threadsafe(f"Starting {backend_name} backend")
            if backend_name == "pjsua":
                backend = PjsuaBackend(self.config_data, BASE_DIR, self.log_and_status_threadsafe)
            elif backend_name == "baresip":
                backend = BaresipBackend(self.config_data, BASE_DIR, self.log_and_status_threadsafe)
            else:
                raise RuntimeError(f"Unknown backend: {backend_name}")
            self.active_backend = backend
            backend.start_broadcast(audio_path)
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

    def start_live_broadcast(self):
        if not self.apply_settings(silent=True):
            return
        if self.config_data.get("backend") != "pjsua":
            messagebox.showerror(APP_TITLE, "即時廣播目前只支援 pjsua backend。")
            return
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showwarning(APP_TITLE, "預錄語音廣播仍在執行中，請先停止播放。")
            self.set_status("請先停止預錄語音廣播")
            return
        if self.active_backend and getattr(self.active_backend, "is_playback_running", lambda: False)():
            messagebox.showwarning(APP_TITLE, "預錄語音廣播仍在執行中，請先停止播放。")
            self.set_status("請先停止預錄語音廣播")
            return
        try:
            if not self.live_backend:
                self.live_backend = PjsuaBackend(self.config_data, BASE_DIR, self.log_and_status_threadsafe)
            self.live_backend.start_live_broadcast()
            self.set_status("即時廣播中")
            self.log("Live broadcast started")
        except PjsuaError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            self.log(f"Live broadcast error: {exc}")

    def stop_live_broadcast(self):
        try:
            if self.live_backend:
                self.live_backend.stop_live_broadcast()
        except Exception as exc:
            self.log(f"Stop live error: {exc}")
        self.live_backend = None
        self.set_status("即時廣播已停止")

    def stop_playback(self):
        try:
            if self.active_backend:
                self.active_backend.stop()
                self.active_backend = None
            if self.live_backend:
                self.live_backend.stop_live_broadcast()
                self.live_backend = None
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
