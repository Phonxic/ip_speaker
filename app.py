import copy
import csv
import json
import os
import re
import subprocess
import threading
import time
import tkinter as tk
import winsound
from pathlib import Path
from tkinter import messagebox, ttk

from audio_recorder import AudioRecorder, AudioRecorderError, filename_from_audio_id, validate_audio_id
from sip_registrar import SipRegistrarServer
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

TRIGGER_AUDIO_IDS = [
    "testing",
    "fall_warning",
    "baggage_warning",
    "wheelchair_warning",
    "stay_warning",
]


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
        "audio": {"folder": "audio", "sample_rate": 8000, "channels": 1, "sample_width": 2},
        "audio_files": DEFAULT_AUDIO_FILES.copy(),
        "speakers": {
            "speaker_1": {
                "display_name": "IP Speaker 1",
                "ip": "192.168.6.120",
                "sip_user": "4267",
                "sip_port": 5060,
            }
        },
        "speaker_groups": {
            "all": {
                "display_name": "全部 Speaker",
                "speaker_ids": ["speaker_1"],
            }
        },
        "selected_speaker_group": "all",
        "registrar": {
            "host": "0.0.0.0",
            "port": 5060,
        },
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


def normalize_speakers(config: dict) -> dict:
    old_speaker = config.get("speaker", {})
    default_speaker = {
        "display_name": "IP Speaker 1",
        "ip": old_speaker.get("ip", "192.168.6.120"),
        "sip_user": old_speaker.get("sip_user", "4267"),
        "sip_port": old_speaker.get("sip_port", 5060),
        "audio_id": "testing",
        "event_audio_ids": {},
    }
    speakers = config.get("speakers")
    if not isinstance(speakers, dict) or not speakers:
        return {"speaker_1": default_speaker}

    result = {}
    for speaker_id, speaker in speakers.items():
        if not isinstance(speaker, dict):
            continue
        clean_id = re.sub(r"[^A-Za-z0-9_-]+", "_", str(speaker_id).strip()).strip("_")
        if not clean_id:
            continue
        result[clean_id] = {
            "display_name": str(speaker.get("display_name") or clean_id),
            "ip": str(speaker.get("ip") or "").strip(),
            "sip_user": str(speaker.get("sip_user") or "4267").strip(),
            "sip_port": int(speaker.get("sip_port", 5060)),
            "audio_id": str(speaker.get("audio_id") or "testing").strip(),
            "event_audio_ids": {
                str(event_id): str(event_audio_id)
                for event_id, event_audio_id in speaker.get("event_audio_ids", {}).items()
                if event_audio_id
            },
        }
    return result or {"speaker_1": default_speaker}


def normalize_speaker_groups(config: dict, speakers: dict) -> dict:
    speaker_ids = list(speakers.keys())
    groups = config.get("speaker_groups")
    if not isinstance(groups, dict) or not groups:
        return {"all": {"display_name": "全部 Speaker", "speaker_ids": speaker_ids}}

    result = {}
    for group_id, group in groups.items():
        if not isinstance(group, dict):
            continue
        clean_id = re.sub(r"[^A-Za-z0-9_-]+", "_", str(group_id).strip()).strip("_")
        if not clean_id:
            continue
        group_speaker_ids = [item for item in group.get("speaker_ids", []) if item in speakers]
        if not group_speaker_ids:
            continue
        result[clean_id] = {
            "display_name": str(group.get("display_name") or clean_id),
            "speaker_ids": group_speaker_ids,
        }
    return result or {"all": {"display_name": "全部 Speaker", "speaker_ids": speaker_ids}}


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
        config["audio"] = {**defaults["audio"], **old.get("audio", {})}
        config["registrar"] = {**defaults["registrar"], **old.get("registrar", {})}
        config["backend"] = "pjsua"
        if "sip_uri" in old and not old.get("speaker"):
            user, ip = parse_sip_uri(old["sip_uri"])
            config["speaker"]["sip_user"] = user or config["speaker"]["sip_user"]
            config["speaker"]["ip"] = ip or config["speaker"]["ip"]
        config["audio_files"] = normalize_audio_files(old.get("audio_files", {}))
        config["speakers"] = normalize_speakers(config)
        config["speaker_groups"] = normalize_speaker_groups(config, config["speakers"])
        if config.get("selected_speaker_group") not in config["speaker_groups"]:
            config["selected_speaker_group"] = next(iter(config["speaker_groups"]))
        first_group = config["speaker_groups"][config["selected_speaker_group"]]
        first_speaker_id = first_group["speaker_ids"][0]
        first_speaker = config["speakers"][first_speaker_id]
        config["speaker"] = {
            "ip": first_speaker["ip"],
            "sip_user": first_speaker["sip_user"],
            "sip_port": first_speaker["sip_port"],
        }
    else:
        config["speakers"] = normalize_speakers(config)
        config["speaker_groups"] = normalize_speaker_groups(config, config["speakers"])
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
        self.geometry("1280x820")
        self.minsize(1120, 720)
        self.configure(padx=16, pady=16)
        self.config_data = load_config()
        self.active_backend = None
        self.active_backends = []
        self.live_backend = None
        self.live_backends = []
        self.registrar_server = None
        self.worker_thread = None
        self.recorder = AudioRecorder(
            sample_rate=int(self.config_data.get("audio", {}).get("sample_rate", 8000)),
            channels=int(self.config_data.get("audio", {}).get("channels", 1)),
        )
        self.recording_audio_id = None

        self.status_text = tk.StringVar(value="準備就緒")
        self.sip_uri_text = tk.StringVar()
        self.volume_text = tk.StringVar()
        self.selected_group_var = tk.StringVar()
        self.group_combo = None
        self.registrar_status_var = tk.StringVar(value="IBS Server：未啟動")
        self.registration_list = None
        self.speaker_list = None
        self.group_list = None
        self.speaker_audio_combo = None
        self.audio_frame = None
        self.log_text = None
        self.audio_list = None
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self._load_config_to_vars()
        self.update_sip_uri()
        self.refresh_audio_buttons()
        self.refresh_audio_list()
        self.refresh_speaker_views()
        self.log("GUI ready")

    def _build_ui(self):
        tk.Label(self, text=APP_TITLE, font=("Microsoft JhengHei UI", 16, "bold")).pack(fill="x", pady=(0, 12))
        self._build_settings_section()

        main_pane = tk.PanedWindow(self, orient="horizontal", sashwidth=8, sashrelief="raised", bd=0)
        main_pane.pack(fill="both", expand=True, pady=(0, 10))

        notebook_area = tk.Frame(main_pane)
        log_area = tk.Frame(main_pane)
        main_pane.add(notebook_area, minsize=760, stretch="always")
        main_pane.add(log_area, minsize=280, stretch="never")

        notebook = ttk.Notebook(notebook_area)
        notebook.pack(fill="both", expand=True)

        broadcast_tab = tk.Frame(notebook, padx=12, pady=12)
        ibs_tab = tk.Frame(notebook, padx=12, pady=12)
        speakers_tab = tk.Frame(notebook, padx=12, pady=12)
        audio_tab = tk.Frame(notebook, padx=12, pady=12)
        notebook.add(broadcast_tab, text="廣播控制")
        notebook.add(ibs_tab, text="IBS Server")
        notebook.add(speakers_tab, text="Speaker 管理")
        notebook.add(audio_tab, text="音檔管理")

        self._build_registrar_section(ibs_tab)
        self._build_live_section(broadcast_tab)
        self._build_audio_section(broadcast_tab)
        self._build_control_section(broadcast_tab)
        self._build_speaker_manager(speakers_tab)
        self._build_audio_manager(audio_tab)
        self._build_log_section(log_area)
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
                widget = ttk.Combobox(frame, textvariable=var, values=("pjsua",), state="readonly")
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
        tk.Label(frame, text="目標群組", anchor="w").grid(row=3, column=0, sticky="ew", padx=(0, 4), pady=(8, 0))
        self.group_combo = ttk.Combobox(frame, textvariable=self.selected_group_var, state="readonly")
        self.group_combo.grid(row=3, column=1, columnspan=3, sticky="ew", padx=(0, 10), pady=(8, 0))
        self.group_combo.bind("<<ComboboxSelected>>", self.on_group_selected)
        tk.Button(frame, text="套用設定", command=self.apply_settings, height=2).grid(row=3, column=4, columnspan=4, sticky="ew", pady=(8, 0))

    def _build_live_section(self, parent):
        frame = tk.LabelFrame(parent, text="即時廣播", padx=12, pady=12, font=("Microsoft JhengHei UI", 10, "bold"))
        frame.pack(fill="x", pady=(0, 10))
        tk.Button(frame, text="開始即時廣播", command=self.start_live_broadcast, height=2).pack(fill="x", pady=(0, 8))
        tk.Button(frame, text="停止即時廣播", command=self.stop_live_broadcast, height=2).pack(fill="x")

    def _build_registrar_section(self, parent):
        frame = tk.LabelFrame(parent, text="IBS / IPB Server 註冊", padx=12, pady=12, font=("Microsoft JhengHei UI", 10, "bold"))
        frame.pack(fill="x", pady=(0, 10))
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        tk.Label(frame, textvariable=self.registrar_status_var, anchor="w").grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        tk.Button(frame, text="啟動 IBS Server", command=self.start_registrar_server, height=2).grid(row=1, column=0, sticky="ew", padx=(0, 4), pady=3)
        tk.Button(frame, text="停止 IBS Server", command=self.stop_registrar_server, height=2).grid(row=1, column=1, sticky="ew", padx=(4, 0), pady=3)
        self.registration_list = tk.Listbox(frame, height=4)
        self.registration_list.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 3))
        tk.Button(frame, text="重新整理註冊清單", command=self.refresh_registration_list).grid(row=3, column=0, sticky="ew", padx=(0, 4), pady=3)
        tk.Button(frame, text="匯入註冊 Speaker", command=self.import_registered_speakers).grid(row=3, column=1, sticky="ew", padx=(4, 0), pady=3)

    def _build_audio_section(self, parent):
        frame = tk.LabelFrame(parent, text="預錄語音廣播", padx=12, pady=12, font=("Microsoft JhengHei UI", 10, "bold"))
        frame.pack(fill="both", expand=True, pady=(0, 10))
        self.audio_frame = frame

    def _build_control_section(self, parent):
        frame = tk.Frame(parent)
        frame.pack(fill="x", pady=(0, 10))
        tk.Button(frame, text="停止播放 / 掛斷", command=self.stop_playback, height=2).pack(side="left", fill="x", expand=True, padx=(0, 8))
        tk.Button(frame, text="開啟音訊資料夾", command=self.open_audio_folder, height=2).pack(side="left", fill="x", expand=True)

    def _build_speaker_manager(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(0, weight=1)

        speaker_frame = tk.LabelFrame(parent, text="Speaker", padx=12, pady=12, font=("Microsoft JhengHei UI", 10, "bold"))
        speaker_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        speaker_frame.columnconfigure(0, weight=1)
        speaker_frame.columnconfigure(1, weight=2)
        speaker_frame.rowconfigure(1, weight=1)

        tk.Label(speaker_frame, text="Speaker 清單", anchor="w").grid(row=0, column=0, columnspan=2, sticky="ew")
        self.speaker_list = tk.Listbox(speaker_frame, height=10)
        self.speaker_list.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(4, 10))
        self.speaker_list.bind("<<ListboxSelect>>", self.on_speaker_selected)

        self.speaker_id_var = tk.StringVar()
        self.speaker_display_var = tk.StringVar()
        self.speaker_ip_edit_var = tk.StringVar()
        self.speaker_user_edit_var = tk.StringVar()
        self.speaker_port_edit_var = tk.StringVar()
        self.speaker_audio_var = tk.StringVar()
        self.speaker_event_var = tk.StringVar()
        self.speaker_event_audio_var = tk.StringVar()

        fields = [
            ("Speaker ID", self.speaker_id_var),
            ("名稱", self.speaker_display_var),
            ("IP", self.speaker_ip_edit_var),
            ("SIP User", self.speaker_user_edit_var),
            ("SIP Port", self.speaker_port_edit_var),
        ]
        for row, (label, var) in enumerate(fields, start=2):
            tk.Label(speaker_frame, text=label, anchor="e").grid(row=row, column=0, sticky="ew", padx=(0, 8), pady=3)
            tk.Entry(speaker_frame, textvariable=var).grid(row=row, column=1, sticky="ew", pady=3)

        tk.Label(speaker_frame, text="指定音檔", anchor="e").grid(row=7, column=0, sticky="ew", padx=(0, 8), pady=3)
        self.speaker_audio_combo = ttk.Combobox(speaker_frame, textvariable=self.speaker_audio_var, state="readonly")
        self.speaker_audio_combo.grid(row=7, column=1, sticky="ew", pady=3)

        tk.Label(speaker_frame, text="事件", anchor="e").grid(row=8, column=0, sticky="ew", padx=(0, 8), pady=3)
        self.speaker_event_combo = ttk.Combobox(speaker_frame, textvariable=self.speaker_event_var, state="readonly")
        self.speaker_event_combo.grid(row=8, column=1, sticky="ew", pady=3)
        self.speaker_event_combo.bind("<<ComboboxSelected>>", self.on_speaker_event_selected)

        tk.Label(speaker_frame, text="事件音檔", anchor="e").grid(row=9, column=0, sticky="ew", padx=(0, 8), pady=3)
        self.speaker_event_audio_combo = ttk.Combobox(speaker_frame, textvariable=self.speaker_event_audio_var, state="readonly")
        self.speaker_event_audio_combo.grid(row=9, column=1, sticky="ew", pady=3)

        tk.Button(speaker_frame, text="新增 / 更新 Speaker", command=self.save_speaker_entry).grid(row=10, column=0, columnspan=2, sticky="ew", pady=(10, 3))
        tk.Button(speaker_frame, text="刪除 Speaker", command=self.delete_speaker_entry).grid(row=11, column=0, columnspan=2, sticky="ew", pady=3)
        tk.Button(speaker_frame, text="測試此 Speaker 指定音檔", command=self.test_selected_speaker_audio).grid(row=12, column=0, columnspan=2, sticky="ew", pady=3)

        group_frame = tk.LabelFrame(parent, text="群組", padx=12, pady=12, font=("Microsoft JhengHei UI", 10, "bold"))
        group_frame.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        group_frame.columnconfigure(0, weight=1)
        group_frame.columnconfigure(1, weight=2)
        group_frame.rowconfigure(1, weight=1)

        tk.Label(group_frame, text="群組清單", anchor="w").grid(row=0, column=0, columnspan=2, sticky="ew")
        self.group_list = tk.Listbox(group_frame, height=10)
        self.group_list.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(4, 10))
        self.group_list.bind("<<ListboxSelect>>", self.on_group_manager_selected)

        self.group_id_var = tk.StringVar()
        self.group_display_var = tk.StringVar()
        self.group_members_var = tk.StringVar()

        group_fields = [
            ("群組 ID", self.group_id_var),
            ("群組名稱", self.group_display_var),
            ("Speaker IDs", self.group_members_var),
        ]
        for row, (label, var) in enumerate(group_fields, start=2):
            tk.Label(group_frame, text=label, anchor="e").grid(row=row, column=0, sticky="ew", padx=(0, 8), pady=3)
            tk.Entry(group_frame, textvariable=var).grid(row=row, column=1, sticky="ew", pady=3)

        tk.Button(group_frame, text="新增 / 更新群組", command=self.save_group_entry).grid(row=5, column=0, columnspan=2, sticky="ew", pady=(10, 3))
        tk.Button(group_frame, text="刪除群組", command=self.delete_group_entry).grid(row=6, column=0, columnspan=2, sticky="ew", pady=3)
        tk.Button(group_frame, text="使用此群組", command=self.select_group_from_manager).grid(row=7, column=0, columnspan=2, sticky="ew", pady=3)

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
        tk.Button(frame, text="本機測試播放", command=self.play_selected_audio_locally).grid(row=7, column=1, sticky="ew", pady=(10, 3), padx=(0, 4))
        tk.Button(frame, text="停止本機播放", command=self.stop_local_audio_preview).grid(row=7, column=2, sticky="ew", pady=(10, 3), padx=(4, 0))
        tk.Button(frame, text="重新整理音檔", command=self.refresh_all_audio_views).grid(row=8, column=1, columnspan=2, sticky="ew", pady=3)

    def _build_log_section(self, parent):
        frame = tk.LabelFrame(parent, text="事件紀錄", padx=8, pady=8, font=("Microsoft JhengHei UI", 10, "bold"))
        frame.pack(fill="both", expand=True)
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
        self.refresh_group_options()
        self.local_ip_var.set(local.get("ip", ""))
        self.advertise_ip_var.set(local.get("advertise_ip", ""))
        self.local_sip_port_var.set(str(local.get("sip_port", 64882)))
        self.local_rtp_port_var.set(str(local.get("rtp_port", 4004)))
        self.speaker_ip_var.set(speaker.get("ip", "192.168.6.120"))
        self.sip_user_var.set(str(speaker.get("sip_user", "4267")))
        self.speaker_sip_port_var.set(str(speaker.get("sip_port", 5060)))
        self.audio_gain_var.set(float(local.get("audio_gain", 100.0)))
        self.update_volume_text()

    def group_label(self, group_id: str) -> str:
        group = self.config_data.get("speaker_groups", {}).get(group_id, {})
        display_name = group.get("display_name", group_id)
        count = len(group.get("speaker_ids", []))
        return f"{display_name} ({count})"

    def group_id_from_label(self, label: str) -> str | None:
        for group_id in self.config_data.get("speaker_groups", {}):
            if self.group_label(group_id) == label:
                return group_id
        return None

    def selected_group_id(self) -> str:
        group_id = self.group_id_from_label(self.selected_group_var.get())
        if group_id:
            return group_id
        saved_group = self.config_data.get("selected_speaker_group")
        if saved_group in self.config_data.get("speaker_groups", {}):
            return saved_group
        return next(iter(self.config_data.get("speaker_groups", {"all": {}})))

    def refresh_group_options(self):
        self.config_data["speakers"] = normalize_speakers(self.config_data)
        self.config_data["speaker_groups"] = normalize_speaker_groups(self.config_data, self.config_data["speakers"])
        group_ids = list(self.config_data["speaker_groups"].keys())
        labels = [self.group_label(group_id) for group_id in group_ids]
        if self.group_combo:
            self.group_combo.configure(values=labels)
        selected_group = self.config_data.get("selected_speaker_group")
        if selected_group not in self.config_data["speaker_groups"]:
            selected_group = group_ids[0]
        self.selected_group_var.set(self.group_label(selected_group))
        self.config_data["selected_speaker_group"] = selected_group

    def on_group_selected(self, _event=None):
        group_id = self.selected_group_id()
        self.config_data["selected_speaker_group"] = group_id
        self.load_first_speaker_from_group(group_id)
        self.update_sip_uri()

    def load_first_speaker_from_group(self, group_id: str):
        group = self.config_data.get("speaker_groups", {}).get(group_id, {})
        speaker_ids = group.get("speaker_ids", [])
        if not speaker_ids:
            return
        speaker = self.config_data.get("speakers", {}).get(speaker_ids[0], {})
        self.speaker_ip_var.set(speaker.get("ip", ""))
        self.sip_user_var.set(str(speaker.get("sip_user", "4267")))
        self.speaker_sip_port_var.set(str(speaker.get("sip_port", 5060)))

    def refresh_speaker_views(self):
        self.config_data["audio_files"] = normalize_audio_files(self.config_data.get("audio_files", {}))
        self.config_data["speakers"] = normalize_speakers(self.config_data)
        self.config_data["speaker_groups"] = normalize_speaker_groups(self.config_data, self.config_data["speakers"])
        audio_labels = [self.audio_label(audio_id) for audio_id in self.config_data.get("audio_files", {})]
        trigger_labels = [
            self.audio_label(audio_id)
            for audio_id in TRIGGER_AUDIO_IDS
            if audio_id in self.config_data.get("audio_files", {})
        ]
        if self.speaker_audio_combo:
            self.speaker_audio_combo.configure(values=audio_labels)
        if hasattr(self, "speaker_event_combo"):
            self.speaker_event_combo.configure(values=trigger_labels)
        if hasattr(self, "speaker_event_audio_combo"):
            self.speaker_event_audio_combo.configure(values=audio_labels)
        self.refresh_speaker_list()
        self.refresh_group_list()
        self.refresh_group_options()

    def audio_label(self, audio_id: str) -> str:
        info = self.config_data.get("audio_files", {}).get(audio_id, {})
        return f"{audio_id} - {info.get('display_name', audio_id)}"

    def audio_id_from_label(self, label: str) -> str:
        return label.split(" - ", 1)[0].strip()

    def refresh_speaker_list(self, selected_speaker_id: str | None = None):
        if not self.speaker_list:
            return
        self.speaker_list.delete(0, "end")
        selected_index = None
        for index, (speaker_id, speaker) in enumerate(self.config_data.get("speakers", {}).items()):
            audio_id = speaker.get("audio_id", "testing")
            self.speaker_list.insert("end", f"{speaker_id} - {speaker.get('display_name', speaker_id)} [{audio_id}]")
            if speaker_id == selected_speaker_id:
                selected_index = index
        if selected_index is not None:
            self.speaker_list.selection_set(selected_index)
            self.speaker_list.activate(selected_index)

    def refresh_group_list(self, selected_group_id: str | None = None):
        if not self.group_list:
            return
        self.group_list.delete(0, "end")
        selected_index = None
        for index, (group_id, group) in enumerate(self.config_data.get("speaker_groups", {}).items()):
            self.group_list.insert("end", f"{group_id} - {group.get('display_name', group_id)} ({len(group.get('speaker_ids', []))})")
            if group_id == selected_group_id:
                selected_index = index
        if selected_index is not None:
            self.group_list.selection_set(selected_index)
            self.group_list.activate(selected_index)

    def selected_speaker_id_from_manager(self) -> str | None:
        if not self.speaker_list:
            return None
        selection = self.speaker_list.curselection()
        if not selection:
            return None
        speaker_ids = list(self.config_data.get("speakers", {}).keys())
        if selection[0] >= len(speaker_ids):
            return None
        return speaker_ids[selection[0]]

    def selected_group_id_from_manager(self) -> str | None:
        if not self.group_list:
            return None
        selection = self.group_list.curselection()
        if not selection:
            return None
        group_ids = list(self.config_data.get("speaker_groups", {}).keys())
        if selection[0] >= len(group_ids):
            return None
        return group_ids[selection[0]]

    def on_speaker_selected(self, _event=None):
        speaker_id = self.selected_speaker_id_from_manager()
        if not speaker_id:
            return
        speaker = self.config_data.get("speakers", {}).get(speaker_id, {})
        self.speaker_id_var.set(speaker_id)
        self.speaker_display_var.set(speaker.get("display_name", ""))
        self.speaker_ip_edit_var.set(speaker.get("ip", ""))
        self.speaker_user_edit_var.set(str(speaker.get("sip_user", "4267")))
        self.speaker_port_edit_var.set(str(speaker.get("sip_port", 5060)))
        audio_id = speaker.get("audio_id", "testing")
        self.speaker_audio_var.set(self.audio_label(audio_id))
        if not self.speaker_event_var.get() and self.config_data.get("audio_files"):
            first_event_id = next(
                (audio_id for audio_id in TRIGGER_AUDIO_IDS if audio_id in self.config_data["audio_files"]),
                next(iter(self.config_data["audio_files"])),
            )
            self.speaker_event_var.set(self.audio_label(first_event_id))
        self.on_speaker_event_selected()

    def on_speaker_event_selected(self, _event=None):
        speaker_id = self.selected_speaker_id_from_manager() or self.speaker_id_var.get().strip()
        speaker = self.config_data.get("speakers", {}).get(speaker_id, {})
        event_id = self.audio_id_from_label(self.speaker_event_var.get())
        event_audio_id = speaker.get("event_audio_ids", {}).get(event_id, event_id)
        if event_audio_id not in self.config_data.get("audio_files", {}):
            event_audio_id = event_id if event_id in self.config_data.get("audio_files", {}) else "testing"
        self.speaker_event_audio_var.set(self.audio_label(event_audio_id))

    def on_group_manager_selected(self, _event=None):
        group_id = self.selected_group_id_from_manager()
        if not group_id:
            return
        group = self.config_data.get("speaker_groups", {}).get(group_id, {})
        self.group_id_var.set(group_id)
        self.group_display_var.set(group.get("display_name", ""))
        self.group_members_var.set(", ".join(group.get("speaker_ids", [])))

    def save_speaker_entry(self):
        speaker_id = re.sub(r"[^A-Za-z0-9_-]+", "_", self.speaker_id_var.get().strip()).strip("_")
        if not speaker_id:
            messagebox.showerror(APP_TITLE, "Speaker ID 不可空白。")
            return
        try:
            sip_port = int(self.speaker_port_edit_var.get().strip() or "5060")
        except ValueError:
            messagebox.showerror(APP_TITLE, "SIP Port 必須是數字。")
            return
        audio_id = self.audio_id_from_label(self.speaker_audio_var.get() or "testing")
        if audio_id not in self.config_data.get("audio_files", {}):
            audio_id = "testing"
        existing_speaker = self.config_data.get("speakers", {}).get(speaker_id, {})
        event_audio_ids = dict(existing_speaker.get("event_audio_ids", {}))
        event_id = self.audio_id_from_label(self.speaker_event_var.get())
        event_audio_id = self.audio_id_from_label(self.speaker_event_audio_var.get())
        if event_id and event_audio_id in self.config_data.get("audio_files", {}):
            event_audio_ids[event_id] = event_audio_id
        self.config_data.setdefault("speakers", {})[speaker_id] = {
            "display_name": self.speaker_display_var.get().strip() or speaker_id,
            "ip": self.speaker_ip_edit_var.get().strip(),
            "sip_user": self.speaker_user_edit_var.get().strip() or "4267",
            "sip_port": sip_port,
            "audio_id": audio_id,
            "event_audio_ids": event_audio_ids,
        }
        self.config_data["speaker_groups"] = normalize_speaker_groups(self.config_data, self.config_data["speakers"])
        save_config(self.config_data)
        self.refresh_speaker_views()
        self.refresh_speaker_list(selected_speaker_id=speaker_id)
        self.set_status("Speaker 設定已更新")

    def delete_speaker_entry(self):
        speaker_id = self.speaker_id_var.get().strip()
        if speaker_id not in self.config_data.get("speakers", {}):
            messagebox.showerror(APP_TITLE, "請先選擇要刪除的 Speaker。")
            return
        if not messagebox.askyesno(APP_TITLE, f"確定刪除 Speaker？\n{speaker_id}"):
            return
        self.config_data["speakers"].pop(speaker_id, None)
        for group in self.config_data.get("speaker_groups", {}).values():
            group["speaker_ids"] = [item for item in group.get("speaker_ids", []) if item != speaker_id]
        self.config_data["speaker_groups"] = normalize_speaker_groups(self.config_data, self.config_data["speakers"])
        save_config(self.config_data)
        self.refresh_speaker_views()
        self.set_status("Speaker 已刪除")

    def save_group_entry(self):
        group_id = re.sub(r"[^A-Za-z0-9_-]+", "_", self.group_id_var.get().strip()).strip("_")
        if not group_id:
            messagebox.showerror(APP_TITLE, "群組 ID 不可空白。")
            return
        members = [item.strip() for item in self.group_members_var.get().split(",") if item.strip()]
        members = [item for item in members if item in self.config_data.get("speakers", {})]
        if not members:
            messagebox.showerror(APP_TITLE, "群組至少需要一台有效 Speaker。")
            return
        self.config_data.setdefault("speaker_groups", {})[group_id] = {
            "display_name": self.group_display_var.get().strip() or group_id,
            "speaker_ids": members,
        }
        save_config(self.config_data)
        self.refresh_speaker_views()
        self.refresh_group_list(selected_group_id=group_id)
        self.set_status("群組已更新")

    def delete_group_entry(self):
        group_id = self.group_id_var.get().strip()
        if group_id not in self.config_data.get("speaker_groups", {}):
            messagebox.showerror(APP_TITLE, "請先選擇要刪除的群組。")
            return
        if not messagebox.askyesno(APP_TITLE, f"確定刪除群組？\n{group_id}"):
            return
        self.config_data["speaker_groups"].pop(group_id, None)
        self.config_data["speaker_groups"] = normalize_speaker_groups(self.config_data, self.config_data["speakers"])
        if self.config_data.get("selected_speaker_group") == group_id:
            self.config_data["selected_speaker_group"] = next(iter(self.config_data["speaker_groups"]))
        save_config(self.config_data)
        self.refresh_speaker_views()
        self.set_status("群組已刪除")

    def select_group_from_manager(self):
        group_id = self.selected_group_id_from_manager() or self.group_id_var.get().strip()
        if group_id not in self.config_data.get("speaker_groups", {}):
            messagebox.showerror(APP_TITLE, "請先選擇有效群組。")
            return
        self.config_data["selected_speaker_group"] = group_id
        save_config(self.config_data)
        self.refresh_group_options()
        self.load_first_speaker_from_group(group_id)
        self.update_sip_uri()
        self.set_status(f"已切換目標群組：{self.config_data['speaker_groups'][group_id]['display_name']}")

    def test_selected_speaker_audio(self):
        speaker_id = self.selected_speaker_id_from_manager() or self.speaker_id_var.get().strip()
        speaker = self.config_data.get("speakers", {}).get(speaker_id)
        if not speaker:
            messagebox.showerror(APP_TITLE, "請先選擇 Speaker。")
            return
        audio_id = speaker.get("audio_id", "testing")
        self.start_audio_broadcast(audio_id=audio_id, targets=[self.target_from_speaker(speaker_id, speaker)], use_per_speaker_audio=False)

    def start_registrar_server(self):
        if self.registrar_server and self.registrar_server.is_running:
            self.set_status("IBS Server 已啟動")
            return
        registrar_config = self.config_data.get("registrar", {})
        host = str(registrar_config.get("host", "0.0.0.0"))
        port = int(registrar_config.get("port", 5060))
        self.cleanup_pjsua_processes()
        try:
            self.registrar_server = SipRegistrarServer(
                host=host,
                port=port,
                base_dir=BASE_DIR,
                on_event=self.log_threadsafe,
                on_registration=lambda: self.after(0, self.refresh_registration_list),
            )
            self.registrar_server.start()
        except OSError as exc:
            self.registrar_server = None
            owners = self.udp_port_owners(port)
            owner_text = self.format_port_owners(owners) if owners else "查不到占用程序，可能是系統服務或剛釋放中的 socket。"
            messagebox.showerror(APP_TITLE, f"無法啟動 IBS Server UDP {port}：\n{exc}\n\n目前占用 UDP {port} 的程序：\n{owner_text}")
            self.set_status("IBS Server 啟動失敗")
            return
        self.registrar_status_var.set(f"IBS Server：執行中 UDP {host}:{port}")
        self.set_status("IBS Server 已啟動，等待 Speaker REGISTER")
        self.log(f"IBS Server started on UDP {host}:{port}")

    def stop_registrar_server(self):
        if self.registrar_server:
            self.registrar_server.stop()
            self.registrar_server = None
        self.registrar_status_var.set("IBS Server：未啟動")
        self.set_status("IBS Server 已停止")

    def refresh_registration_list(self):
        if not self.registration_list:
            return
        self.registration_list.delete(0, "end")
        if not self.registrar_server:
            return
        registrations = self.registrar_server.registrations(online_only=False)
        now = time.time()
        for registration in registrations:
            status = "online" if registration.is_online else "expired"
            ttl = max(0, int(registration.expires_at - now))
            self.registration_list.insert(
                "end",
                f"{registration.user} @ {registration.contact_ip}:{registration.contact_port} [{status}, {ttl}s]",
            )

    def import_registered_speakers(self):
        if not self.registrar_server:
            messagebox.showwarning(APP_TITLE, "請先啟動 IBS Server，等待 Speaker 註冊。")
            return
        registrations = self.registrar_server.registrations(online_only=True)
        if not registrations:
            messagebox.showwarning(APP_TITLE, "目前沒有在線註冊的 Speaker。")
            return

        self.config_data["speakers"] = normalize_speakers(self.config_data)
        imported_ids = []
        for registration in registrations:
            speaker_id = self.speaker_id_from_registration(registration)
            self.config_data["speakers"][speaker_id] = {
                "display_name": f"Registered {registration.user}",
                "ip": registration.contact_ip,
                "sip_user": registration.user,
                "sip_port": registration.contact_port,
                "audio_id": "testing",
                "event_audio_ids": {},
            }
            imported_ids.append(speaker_id)

        self.config_data["speaker_groups"] = normalize_speaker_groups(self.config_data, self.config_data["speakers"])
        self.config_data["speaker_groups"]["registered"] = {
            "display_name": "已註冊 Speaker",
            "speaker_ids": imported_ids,
        }
        self.config_data["selected_speaker_group"] = "registered"
        first = self.config_data["speakers"][imported_ids[0]]
        self.config_data["speaker"] = {
            "ip": first["ip"],
            "sip_user": first["sip_user"],
            "sip_port": first["sip_port"],
        }
        save_config(self.config_data)
        self.refresh_speaker_views()
        self.refresh_group_options()
        self.load_first_speaker_from_group("registered")
        self.update_sip_uri()
        self.set_status(f"已匯入 {len(imported_ids)} 台註冊 Speaker")
        self.log(f"Imported registered speakers: {', '.join(imported_ids)}")

    @staticmethod
    def speaker_id_from_registration(registration) -> str:
        base = f"reg_{registration.user}_{registration.contact_ip}_{registration.contact_port}"
        return re.sub(r"[^A-Za-z0-9_-]+", "_", base).strip("_")

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
            text="選擇事件後，目標群組內每台 Speaker 會播放該事件各自設定的音檔。",
            anchor="w",
            justify="left",
            wraplength=420,
        ).grid(row=0, column=0, sticky="ew", padx=4, pady=(0, 8))

        trigger_items = [(audio_id, audio_files[audio_id]) for audio_id in TRIGGER_AUDIO_IDS if audio_id in audio_files]
        for index, (event_id, info) in enumerate(trigger_items, start=1):
            tk.Button(
                self.audio_frame,
                text=f"Trigger：{info.get('display_name', event_id)}",
                command=lambda item_id=event_id: self.start_event_trigger_broadcast(item_id),
                height=2,
            ).grid(row=index, column=0, sticky="ew", padx=4, pady=3)

        tk.Button(
            self.audio_frame,
            text="測試選取音檔到目標群組",
            command=self.start_selected_audio_broadcast,
            height=2,
        ).grid(row=len(trigger_items) + 1, column=0, sticky="ew", padx=4, pady=(10, 4))

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
            messagebox.showwarning(APP_TITLE, "請先在音檔管理頁選取要測試播放的音檔。")
            self.set_status("請先選取音檔")
            return
        self.start_audio_broadcast(audio_id)

    def play_selected_audio_locally(self):
        audio_id = self.selected_audio_id()
        if not audio_id:
            messagebox.showwarning(APP_TITLE, "請先在音檔管理頁選取要本機測試播放的音檔。")
            self.set_status("請先選取音檔")
            return

        info = self.config_data.get("audio_files", {}).get(audio_id)
        if not info:
            messagebox.showerror(APP_TITLE, f"找不到音檔設定：{audio_id}")
            self.set_status("找不到音檔設定")
            return

        audio_path = AUDIO_DIR / info.get("filename", "")
        if not audio_path.exists():
            messagebox.showerror(APP_TITLE, f"找不到音檔：\n{audio_path}")
            self.set_status("找不到音檔")
            return

        try:
            winsound.PlaySound(str(audio_path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        except RuntimeError as exc:
            messagebox.showerror(APP_TITLE, f"本機播放失敗：\n{exc}")
            self.set_status("本機播放失敗")
            return

        self.set_status(f"本機測試播放：{info.get('display_name', audio_id)}")
        self.log(f"Local audio preview started: {audio_path}")

    def stop_local_audio_preview(self):
        winsound.PlaySound(None, winsound.SND_PURGE)
        self.set_status("已停止本機測試播放")
        self.log("Local audio preview stopped")

    def start_event_trigger_broadcast(self, event_id: str):
        self.start_audio_broadcast(audio_id=event_id, use_per_speaker_audio=True)

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
        self.refresh_speaker_views()
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
        self.refresh_speaker_views()
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
        self.refresh_speaker_views()
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
            "selected_group": self.selected_group_id(),
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
        self.config_data["selected_speaker_group"] = settings["selected_group"]
        self.update_first_speaker_in_group(settings)
        self.config_data["audio_files"] = normalize_audio_files(self.config_data.get("audio_files", {}))
        save_config(self.config_data)
        self.update_sip_uri()
        self.update_volume_text()
        if not silent:
            self.set_status(f"設定已套用，音量 {settings['audio_gain']:.0f}%")
            self.log("Settings applied and saved")
        return True

    def update_first_speaker_in_group(self, settings: dict):
        group = self.config_data.get("speaker_groups", {}).get(settings["selected_group"], {})
        speaker_ids = group.get("speaker_ids", [])
        if not speaker_ids:
            return
        speaker_id = speaker_ids[0]
        self.config_data.setdefault("speakers", {}).setdefault(speaker_id, {})
        self.config_data["speakers"][speaker_id].update(
            {
                "display_name": self.config_data["speakers"][speaker_id].get("display_name", speaker_id),
                "ip": settings["speaker_ip"],
                "sip_user": settings["speaker_sip_user"],
                "sip_port": settings["speaker_sip_port"],
                "audio_id": self.config_data["speakers"][speaker_id].get("audio_id", "testing"),
                "event_audio_ids": self.config_data["speakers"][speaker_id].get("event_audio_ids", {}),
            }
        )

    def start_audio_broadcast(self, audio_id: str | None = None, targets: list[dict] | None = None, use_per_speaker_audio: bool = False):
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showwarning(APP_TITLE, "A broadcast is already running. Please stop it first.")
            return
        if self.is_any_live_running():
            messagebox.showwarning(APP_TITLE, "即時廣播仍在執行中，請先停止即時廣播。")
            self.set_status("請先停止即時廣播")
            return
        if self.live_backend and not self.live_backend.is_live_running():
            self.live_backend = None
        if not self.apply_settings(silent=True):
            return
        targets = targets or self.selected_speaker_targets()
        if not targets:
            messagebox.showerror(APP_TITLE, "目標群組沒有可用的 Speaker。")
            return

        jobs = self.build_broadcast_jobs(targets, audio_id, use_per_speaker_audio)
        if not jobs:
            return
        backend_name = self.config_data.get("backend", "pjsua")
        target_names = ", ".join(target["display_name"] for target in targets)
        mode_text = f"事件：{self.config_data.get('audio_files', {}).get(audio_id or '', {}).get('display_name', audio_id)}" if use_per_speaker_audio else "選取音檔"
        self.set_status(f"準備同步播放：{mode_text} -> {target_names}")
        self.log(f"Starting simultaneous broadcast | mode: {mode_text} | targets: {target_names}")
        self.worker_thread = threading.Thread(target=self._broadcast_worker, args=(backend_name, jobs), daemon=True)
        self.worker_thread.start()

    def selected_speaker_targets(self) -> list[dict]:
        group_id = self.selected_group_id()
        group = self.config_data.get("speaker_groups", {}).get(group_id, {})
        targets = []
        for speaker_id in group.get("speaker_ids", []):
            speaker = self.config_data.get("speakers", {}).get(speaker_id)
            if not speaker:
                continue
            targets.append(self.target_from_speaker(speaker_id, speaker))
        return targets

    def target_from_speaker(self, speaker_id: str, speaker: dict) -> dict:
        return {
            "id": speaker_id,
            "display_name": speaker.get("display_name", speaker_id),
            "ip": speaker.get("ip", ""),
            "sip_user": speaker.get("sip_user", "4267"),
            "sip_port": speaker.get("sip_port", 5060),
            "audio_id": speaker.get("audio_id", "testing"),
            "event_audio_ids": speaker.get("event_audio_ids", {}),
        }

    def build_broadcast_jobs(self, targets: list[dict], audio_id: str | None, use_per_speaker_audio: bool) -> list[dict]:
        jobs = []
        for index, target in enumerate(targets):
            if use_per_speaker_audio:
                target_audio_id = target.get("event_audio_ids", {}).get(audio_id or "", audio_id)
            else:
                target_audio_id = audio_id
            info = self.config_data.get("audio_files", {}).get(target_audio_id or "")
            if not info:
                messagebox.showerror(APP_TITLE, f"{target['display_name']} 找不到音檔設定：{target_audio_id}")
                return []
            audio_path = AUDIO_DIR / info["filename"]
            if not audio_path.exists():
                messagebox.showerror(APP_TITLE, f"{target['display_name']} 找不到音檔：\n{audio_path}")
                return []
            jobs.append(
                {
                    "index": index,
                    "target": target,
                    "audio_id": target_audio_id,
                    "audio_name": info.get("display_name", target_audio_id),
                    "audio_path": audio_path,
                }
            )
        return jobs

    def _broadcast_worker(self, backend_name: str, jobs: list[dict]):
        try:
            threads = []
            errors = []
            self.active_backends = []
            for job in jobs:
                thread = threading.Thread(target=self._single_broadcast_worker, args=(backend_name, job, len(jobs), errors), daemon=True)
                threads.append(thread)
                thread.start()
            for thread in threads:
                thread.join()
            if errors:
                raise RuntimeError("; ".join(errors))
            self.log_threadsafe("Broadcast completed")
            self.set_status_threadsafe("廣播完成")
        except PjsuaError as exc:
            self.log_threadsafe(f"{backend_name} error: {exc}")
            self.show_error_threadsafe(str(exc))
            self.set_status_threadsafe(f"{backend_name} setup error")
        except Exception as exc:
            self.log_threadsafe(f"Unexpected error: {exc}")
            self.show_error_threadsafe(str(exc))
            self.set_status_threadsafe(f"{backend_name} error: {exc}")
        finally:
            self.active_backend = None
            self.active_backends = []

    def _single_broadcast_worker(self, backend_name: str, job: dict, total: int, errors: list[str]):
        target = job["target"]
        backend = None
        try:
            backend_config = copy.deepcopy(self.config_data)
            local = backend_config.setdefault("local", {})
            base_sip_port = int(local.get("sip_port", 64882))
            base_rtp_port = int(local.get("rtp_port", 4004))
            port_offset = job["index"] * 2
            local["sip_port"] = base_sip_port + port_offset
            local["rtp_port"] = base_rtp_port + port_offset
            backend_config["speaker"] = {
                "ip": target["ip"],
                "sip_user": target["sip_user"],
                "sip_port": target["sip_port"],
            }
            backend_config.setdefault("pjsua", {})
            instance_id = re.sub(r"[^A-Za-z0-9_-]+", "_", target["id"]).strip("_")
            backend_config["pjsua"]["instance_id"] = instance_id
            backend_config["pjsua"]["playback_log_name"] = f"pjsua_gui_{instance_id}.log"
            if backend_name == "pjsua":
                backend = PjsuaBackend(backend_config, BASE_DIR, self.log_and_status_threadsafe)
            else:
                raise RuntimeError(f"Unknown backend: {backend_name}")
            self.active_backends.append(backend)
            self.active_backend = backend
            self.log_threadsafe(
                f"Broadcast {job['index'] + 1}/{total}: {target['display_name']} "
                f"{target['sip_user']}@{target['ip']}:{target['sip_port']} "
                f"audio={job['audio_name']} local_ports={local['sip_port']}/{local['rtp_port']}"
            )
            backend.start_broadcast(job["audio_path"])
            backend.wait_for_audio_then_hangup(job["audio_path"])
        except Exception as exc:
            message = f"{target['display_name']}: {exc}"
            errors.append(message)
            self.log_threadsafe(f"Broadcast error: {message}")
        finally:
            if backend:
                try:
                    self.active_backends.remove(backend)
                except Exception:
                    pass

    def start_live_broadcast(self):
        if not self.apply_settings(silent=True):
            return
        targets = self.selected_speaker_targets()
        if not targets:
            messagebox.showerror(APP_TITLE, "目標群組沒有可用的 Speaker。")
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
            self.stop_live_broadcast(silent=True)
            self.live_backends = []
            for index, target in enumerate(targets):
                backend_config = copy.deepcopy(self.config_data)
                local = backend_config.setdefault("local", {})
                base_sip_port = int(local.get("sip_port", 64882))
                base_rtp_port = int(local.get("rtp_port", 4004))
                port_offset = index * 2
                local["sip_port"] = base_sip_port + port_offset
                local["rtp_port"] = base_rtp_port + port_offset
                backend_config["speaker"] = {
                    "ip": target["ip"],
                    "sip_user": target["sip_user"],
                    "sip_port": target["sip_port"],
                }
                instance_id = re.sub(r"[^A-Za-z0-9_-]+", "_", target["id"]).strip("_")
                backend_config.setdefault("pjsua", {})
                backend_config["pjsua"]["instance_id"] = instance_id
                backend_config["pjsua"]["live_log_name"] = f"pjsua_live_{instance_id}.log"
                backend = PjsuaBackend(backend_config, BASE_DIR, self.log_and_status_threadsafe)
                backend.start_live_broadcast()
                self.live_backends.append(backend)
                if not self.live_backend:
                    self.live_backend = backend
                self.log(f"Live broadcast target {index + 1}/{len(targets)}: {target['display_name']} local_ports={local['sip_port']}/{local['rtp_port']}")
            self.set_status(f"即時群組廣播中：{len(self.live_backends)} 台")
            self.log("Live group broadcast started")
        except PjsuaError as exc:
            self.stop_live_broadcast(silent=True)
            messagebox.showerror(APP_TITLE, str(exc))
            self.log(f"Live broadcast error: {exc}")

    def stop_live_broadcast(self, silent: bool = False):
        try:
            backends = list(self.live_backends)
            for backend in backends:
                backend.stop_live_broadcast()
            self.live_backends = []
            if self.live_backend and self.live_backend not in backends:
                self.live_backend.stop_live_broadcast()
        except Exception as exc:
            self.log(f"Stop live error: {exc}")
        self.live_backend = None
        if not silent:
            self.set_status("即時廣播已停止")

    def is_any_live_running(self) -> bool:
        if self.live_backend and self.live_backend.is_live_running():
            return True
        return any(backend.is_live_running() for backend in self.live_backends)

    def stop_playback(self):
        try:
            backends = list(self.active_backends)
            for backend in backends:
                backend.stop()
            self.active_backends = []
            if self.active_backend and self.active_backend not in backends:
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

    def configured_pjsua_path(self) -> Path:
        pjsua_config = self.config_data.get("pjsua", {})
        configured = pjsua_config.get("path") or pjsua_config.get("exe_path") or "tools/pjsua/pjsua.exe"
        exe_path = Path(configured)
        if not exe_path.is_absolute():
            exe_path = BASE_DIR / exe_path
        return exe_path.resolve()

    def cleanup_pjsua_processes(self):
        target_path = self.configured_pjsua_path()
        try:
            result = subprocess.run(
                [
                    "wmic",
                    "process",
                    "where",
                    "name='pjsua.exe'",
                    "get",
                    "ProcessId,ExecutablePath",
                    "/format:csv",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception as exc:
            self.log(f"PJSUA cleanup skipped: {exc}")
            return

        if result.returncode != 0:
            self.log(f"PJSUA cleanup query failed: {result.stderr.strip()}")
            return

        killed = 0
        for row in csv.DictReader(line for line in result.stdout.splitlines() if line.strip()):
            exe_value = (row.get("ExecutablePath") or "").strip()
            pid = (row.get("ProcessId") or "").strip()
            if not exe_value or not pid:
                continue
            try:
                exe_path = Path(exe_value).resolve()
            except OSError:
                continue
            if exe_path != target_path:
                continue
            subprocess.run(
                ["taskkill", "/PID", pid, "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            killed += 1
            self.log(f"Closed bundled PJSUA process: PID {pid}")

        if killed:
            self.set_status(f"已關閉 PJSUA：{killed} 個程序")

    def udp_port_owners(self, port: int) -> list[dict]:
        script = (
            f"Get-NetUDPEndpoint -LocalPort {port} -ErrorAction SilentlyContinue | "
            "ForEach-Object { "
            "$p = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue; "
            "[PSCustomObject]@{PID=$_.OwningProcess;ProcessName=$p.ProcessName;Path=$p.Path;LocalAddress=$_.LocalAddress} "
            "} | ConvertTo-Csv -NoTypeInformation"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception as exc:
            self.log(f"UDP owner query skipped: {exc}")
            return []
        if result.returncode != 0 or not result.stdout.strip():
            return []
        return list(csv.DictReader(line for line in result.stdout.splitlines() if line.strip()))

    @staticmethod
    def format_port_owners(owners: list[dict]) -> str:
        lines = []
        for owner in owners:
            pid = owner.get("PID") or "unknown"
            name = owner.get("ProcessName") or "unknown"
            path = owner.get("Path") or "(no path)"
            address = owner.get("LocalAddress") or "*"
            lines.append(f"- {name} / PID {pid} / {address}\n  {path}")
        return "\n".join(lines)

    def on_close(self):
        self.set_status("正在關閉程式與 PJSUA...")
        try:
            self.stop_playback()
        except Exception as exc:
            self.log(f"Close stop playback error: {exc}")
        try:
            self.stop_live_broadcast(silent=True)
        except Exception as exc:
            self.log(f"Close stop live error: {exc}")
        try:
            self.stop_registrar_server()
        except Exception as exc:
            self.log(f"Close registrar error: {exc}")
        try:
            self.cleanup_pjsua_processes()
        except Exception as exc:
            self.log(f"Close PJSUA cleanup error: {exc}")
        self.destroy()


if __name__ == "__main__":
    app = BroadcastApp()
    app.mainloop()
