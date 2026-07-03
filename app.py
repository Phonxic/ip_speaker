import json
import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

import winsound


APP_TITLE = "IP Speaker Demo Control"
BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
AUDIO_DIR = BASE_DIR / "audio"
PLAY_AFTER_DIAL_DELAY_MS = 1000

DEFAULT_CONFIG = {
    "sip_uri": "sip:4267@192.168.6.120",
    "microsip_paths": [
        r"C:\Users\user\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\MicroSIP\MicroSIP.lnk",
        r"C:\Program Files\MicroSIP\microsip.exe",
        r"C:\Program Files (x86)\MicroSIP\microsip.exe",
    ],
    "audio_files": {
        "test_warning": "testing.wav",
        "fall_warning": "fall_warning.wav",
        "baggage_warning": "baggage_warning.wav",
        "wheelchair_warning": "wheelchair_warning.wav",
        "stay_warning": "stay_warning.wav",
    },
}

PRE_RECORDED_BUTTONS = [
    ("播放：測試廣播", "test_warning"),
    ("播放：旅客跌倒", "fall_warning"),
    ("播放：行李滾落", "baggage_warning"),
    ("播放：輪椅進入", "wheelchair_warning"),
    ("播放：旅客逗留", "stay_warning"),
]


def ensure_default_config():
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(
            json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def load_config():
    ensure_default_config()

    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as file:
            config = json.load(file)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"config.json 格式錯誤：{exc}") from exc

    if not isinstance(config, dict):
        raise RuntimeError("config.json 必須是 JSON object。")

    merged = DEFAULT_CONFIG.copy()
    merged.update(config)

    audio_files = DEFAULT_CONFIG["audio_files"].copy()
    audio_files.update(config.get("audio_files", {}))
    merged["audio_files"] = audio_files

    if not isinstance(merged.get("microsip_paths"), list):
        merged["microsip_paths"] = DEFAULT_CONFIG["microsip_paths"]

    return merged


class IPSpeakerDemoApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title(APP_TITLE)
        self.geometry("920x470")
        self.minsize(820, 430)
        self.configure(padx=18, pady=18)

        try:
            self.config_data = load_config()
        except RuntimeError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            self.config_data = DEFAULT_CONFIG.copy()

        self.status_text = tk.StringVar(value="準備就緒")

        self._build_ui()

    def _build_ui(self):
        title_label = tk.Label(
            self,
            text=APP_TITLE,
            font=("Microsoft JhengHei UI", 16, "bold"),
            anchor="center",
        )
        title_label.pack(fill="x", pady=(0, 14))

        content = tk.Frame(self)
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=1, uniform="main")
        content.columnconfigure(1, weight=1, uniform="main")
        content.rowconfigure(0, weight=1)

        left_column = tk.Frame(content)
        left_column.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        right_column = tk.Frame(content)
        right_column.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        self._build_connection_section(left_column)
        self._build_live_talk_section(left_column)
        self._build_pre_recorded_section(right_column)
        self._build_status_bar()

    def _build_connection_section(self, parent):
        frame = tk.LabelFrame(
            parent,
            text="連線控制",
            padx=12,
            pady=12,
            font=("Microsoft JhengHei UI", 10, "bold"),
        )
        frame.pack(fill="x", pady=(0, 12))

        self._add_button(frame, "連線 IP Speaker", self.dial_ip_speaker)
        self._add_button(frame, "開啟 MicroSIP", self.open_microsip)
        self._add_button(frame, "開啟音訊資料夾", self.open_audio_folder)

    def _build_live_talk_section(self, parent):
        frame = tk.LabelFrame(
            parent,
            text="人員通話廣播",
            padx=12,
            pady=12,
            font=("Microsoft JhengHei UI", 10, "bold"),
        )
        frame.pack(fill="x", pady=(0, 12))

        self._add_button(frame, "開始通話廣播", self.start_live_talk)
        self._add_button(frame, "結束通話廣播", self.end_live_talk)

        reminder = tk.Label(
            frame,
            text="通話廣播時，請確認 MicroSIP 麥克風來源為實體麥克風，或已將實體麥克風導入 CABLE Output。",
            wraplength=380,
            justify="left",
            anchor="w",
            fg="#444444",
            font=("Microsoft JhengHei UI", 9),
        )
        reminder.pack(fill="x", pady=(8, 0))

    def _build_pre_recorded_section(self, parent):
        frame = tk.LabelFrame(
            parent,
            text="預錄語音廣播",
            padx=12,
            pady=12,
            font=("Microsoft JhengHei UI", 10, "bold"),
        )
        frame.pack(fill="both", expand=True)

        for label, audio_key in PRE_RECORDED_BUTTONS:
            self._add_button(
                frame,
                label,
                lambda key=audio_key: self.connect_then_play_audio(key),
            )

        self._add_button(frame, "停止播放音檔", self.stop_audio)

        reminder = tk.Label(
            frame,
            text="預錄語音廣播時，請確認 MicroSIP 麥克風來源為 Stereo Mix 或 CABLE Output。",
            wraplength=380,
            justify="left",
            anchor="w",
            fg="#444444",
            font=("Microsoft JhengHei UI", 9),
        )
        reminder.pack(fill="x", pady=(8, 0))

    def _build_status_bar(self):
        status_frame = tk.Frame(self, bd=1, relief="sunken")
        status_frame.pack(fill="x", side="bottom", pady=(12, 0))

        status_label = tk.Label(
            status_frame,
            textvariable=self.status_text,
            anchor="w",
            padx=8,
            pady=7,
            font=("Microsoft JhengHei UI", 9),
        )
        status_label.pack(fill="x")

    def _add_button(self, parent, text, command):
        button = tk.Button(
            parent,
            text=text,
            command=command,
            height=2,
            font=("Microsoft JhengHei UI", 10),
        )
        button.pack(fill="x", pady=4)
        return button

    def set_status(self, message):
        self.status_text.set(message)

    def start_sip_call(self):
        sip_uri = self.config_data.get("sip_uri", DEFAULT_CONFIG["sip_uri"])

        try:
            subprocess.Popen(
                ["cmd", "/c", "start", "", sip_uri],
                shell=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"無法開啟 SIP URI：\n{sip_uri}\n\n{exc}")
            return False

        return True

    def dial_ip_speaker(self):
        if self.start_sip_call():
            self.set_status("已送出撥號請求")

    def start_live_talk(self):
        if self.start_sip_call():
            self.set_status("已啟動通話廣播，請開始說話")

    def end_live_talk(self):
        messagebox.showinfo(APP_TITLE, "請在 MicroSIP 中按下掛斷")
        self.set_status("請於 MicroSIP 中掛斷通話")

    def open_microsip(self):
        microsip_paths = self.config_data.get("microsip_paths", [])

        for microsip_path in microsip_paths:
            path = Path(microsip_path)
            if path.exists():
                try:
                    if path.suffix.lower() == ".lnk":
                        os.startfile(path)
                    else:
                        subprocess.Popen(
                            [str(path)],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                except OSError as exc:
                    self.set_status("無法開啟 MicroSIP")
                    messagebox.showerror(APP_TITLE, f"無法開啟 MicroSIP：\n{path}\n\n{exc}")
                    return

                self.set_status("已開啟 MicroSIP")
                return

        self.set_status("找不到 MicroSIP")
        messagebox.showerror(
            APP_TITLE,
            "找不到 MicroSIP，請自行開啟 MicroSIP。\n\n"
            "已檢查路徑：\n"
            + "\n".join(str(path) for path in microsip_paths),
        )

    def connect_then_play_audio(self, audio_key):
        audio_path = self.get_audio_path(audio_key)
        if audio_path is None:
            return

        if not self.start_sip_call():
            return

        self.set_status(f"已送出撥號請求，{PLAY_AFTER_DIAL_DELAY_MS // 1000} 秒後播放 {audio_path.name}")
        self.after(PLAY_AFTER_DIAL_DELAY_MS, lambda: self.play_audio_path(audio_path))

    def get_audio_path(self, audio_key):
        audio_files = self.config_data.get("audio_files", {})
        file_name = audio_files.get(audio_key)

        if not file_name:
            self.set_status("找不到音檔設定")
            messagebox.showerror(APP_TITLE, f"config.json 找不到音檔設定：{audio_key}")
            return None

        audio_path = AUDIO_DIR / file_name

        if not audio_path.exists():
            self.set_status("找不到音檔")
            messagebox.showerror(APP_TITLE, f"找不到音檔：\n{audio_path}")
            return None

        return audio_path

    def play_audio_path(self, audio_path):
        try:
            winsound.PlaySound(
                str(audio_path),
                winsound.SND_FILENAME | winsound.SND_ASYNC,
            )
        except RuntimeError as exc:
            self.set_status("播放音檔失敗")
            messagebox.showerror(APP_TITLE, f"播放音檔失敗：\n{audio_path}\n\n{exc}")
            return

        self.set_status(f"正在播放 {audio_path.name}")

    def stop_audio(self):
        winsound.PlaySound(None, winsound.SND_PURGE)
        self.set_status("已停止播放")

    def open_audio_folder(self):
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)

        try:
            os.startfile(AUDIO_DIR)
        except OSError as exc:
            self.set_status("無法開啟音訊資料夾")
            messagebox.showerror(APP_TITLE, f"無法開啟音訊資料夾：\n{AUDIO_DIR}\n\n{exc}")
            return

        self.set_status("已開啟音訊資料夾")


def main():
    if sys.platform != "win32":
        messagebox.showwarning(APP_TITLE, "此 Demo 使用 winsound 與 Windows SIP URI，請在 Windows 執行。")

    app = IPSpeakerDemoApp()
    app.mainloop()


if __name__ == "__main__":
    main()
