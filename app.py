
import audioop
import json
import os
import subprocess
import sys
import tempfile
import wave
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

import winsound


APP_TITLE = "IP Speaker Demo Control"
BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
AUDIO_DIR = BASE_DIR / "audio"
PLAY_AFTER_DIAL_DELAY_MS = 1000
HANGUP_AFTER_AUDIO_MARGIN_MS = 2000

DEFAULT_CONFIG = {
    "sip_uri": "sip:4267@192.168.6.120",
    "microsip_paths": [
        r"C:\Users\user\Desktop\MicroSIP.lnk",
        r"C:\Users\user\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\MicroSIP\MicroSIP.lnk",
        r"C:\Users\user\AppData\Local\MicroSIP\MicroSIP.exe",
        r"C:\Program Files\MicroSIP\microsip.exe",
        r"C:\Program Files (x86)\MicroSIP\microsip.exe",
    ],
    "playback_volume": 100,
    "audio_files": {
        "test_warning": "testing.wav",
        "fall_warning": "fall_warning.wav",
        "baggage_warning": "baggage_warning.wav",
        "wheelchair_warning": "wheelchair_warning.wav",
        "stay_warning": "stay_warning.wav",
    },
}

PRE_RECORDED_BUTTONS = [
    ("\u64ad\u653e\uff1a\u6e2c\u8a66\u5ee3\u64ad", "test_warning"),
    ("\u64ad\u653e\uff1a\u65c5\u5ba2\u8dcc\u5012", "fall_warning"),
    ("\u64ad\u653e\uff1a\u884c\u674e\u6efe\u843d", "baggage_warning"),
    ("\u64ad\u653e\uff1a\u8f2a\u6905\u9032\u5165", "wheelchair_warning"),
    ("\u64ad\u653e\uff1a\u65c5\u5ba2\u9017\u7559", "stay_warning"),
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
        raise RuntimeError(f"config.json \u683c\u5f0f\u932f\u8aa4\uff1a{exc}") from exc

    if not isinstance(config, dict):
        raise RuntimeError("config.json \u5fc5\u9808\u662f JSON object\u3002")

    merged = DEFAULT_CONFIG.copy()
    merged.update(config)

    audio_files = DEFAULT_CONFIG["audio_files"].copy()
    audio_files.update(config.get("audio_files", {}))
    merged["audio_files"] = audio_files

    if not isinstance(merged.get("microsip_paths"), list):
        merged["microsip_paths"] = DEFAULT_CONFIG["microsip_paths"]

    try:
        merged["playback_volume"] = int(merged.get("playback_volume", 100))
    except (TypeError, ValueError):
        merged["playback_volume"] = 100
    merged["playback_volume"] = max(0, min(100, merged["playback_volume"]))

    return merged


class IPSpeakerDemoApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title(APP_TITLE)
        self.geometry("920x500")
        self.minsize(820, 460)
        self.configure(padx=18, pady=18)

        try:
            self.config_data = load_config()
        except RuntimeError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            self.config_data = DEFAULT_CONFIG.copy()

        self.status_text = tk.StringVar(value=f"\u6e96\u5099\u5c31\u7dd2\uff0c\u76ee\u524d\u57f7\u884c\u4f4d\u7f6e\uff1a{BASE_DIR}")
        self.volume_var = tk.IntVar(value=self.config_data.get("playback_volume", 100))
        self.volume_text = tk.StringVar(value=f"\u9810\u9304\u8a9e\u97f3\u97f3\u91cf\uff1a{self.volume_var.get()}%")
        self.pending_play_after_id = None
        self.pending_hangup_after_id = None
        self.current_temp_audio_path = None

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
        frame = tk.LabelFrame(parent, text="\u9023\u7dda\u63a7\u5236", padx=12, pady=12, font=("Microsoft JhengHei UI", 10, "bold"))
        frame.pack(fill="x", pady=(0, 12))

        self._add_button(frame, "\u9023\u7dda IP Speaker", self.dial_ip_speaker)
        self._add_button(frame, "\u958b\u555f MicroSIP", self.open_microsip)
        self._add_button(frame, "\u958b\u555f\u97f3\u8a0a\u8cc7\u6599\u593e", self.open_audio_folder)

    def _build_live_talk_section(self, parent):
        frame = tk.LabelFrame(parent, text="\u4eba\u54e1\u901a\u8a71\u5ee3\u64ad", padx=12, pady=12, font=("Microsoft JhengHei UI", 10, "bold"))
        frame.pack(fill="x", pady=(0, 12))

        self._add_button(frame, "\u958b\u59cb\u901a\u8a71\u5ee3\u64ad", self.start_live_talk)
        self._add_button(frame, "\u7d50\u675f\u901a\u8a71\u5ee3\u64ad", self.end_live_talk)

        reminder = tk.Label(
            frame,
            text="\u901a\u8a71\u5ee3\u64ad\u6642\uff0c\u8acb\u78ba\u8a8d MicroSIP \u9ea5\u514b\u98a8\u4f86\u6e90\u70ba\u5be6\u9ad4\u9ea5\u514b\u98a8\uff0c\u6216\u5df2\u5c07\u5be6\u9ad4\u9ea5\u514b\u98a8\u5c0e\u5165 CABLE Output\u3002",
            wraplength=380,
            justify="left",
            anchor="w",
            fg="#444444",
            font=("Microsoft JhengHei UI", 9),
        )
        reminder.pack(fill="x", pady=(8, 0))

    def _build_pre_recorded_section(self, parent):
        frame = tk.LabelFrame(parent, text="\u9810\u9304\u8a9e\u97f3\u5ee3\u64ad", padx=12, pady=12, font=("Microsoft JhengHei UI", 10, "bold"))
        frame.pack(fill="both", expand=True)

        volume_label = tk.Label(frame, textvariable=self.volume_text, anchor="w", font=("Microsoft JhengHei UI", 9))
        volume_label.pack(fill="x", pady=(0, 2))

        volume_slider = tk.Scale(
            frame,
            from_=0,
            to=100,
            orient="horizontal",
            variable=self.volume_var,
            command=self.update_volume_label,
            showvalue=False,
        )
        volume_slider.pack(fill="x", pady=(0, 8))

        for label, audio_key in PRE_RECORDED_BUTTONS:
            self._add_button(frame, label, lambda key=audio_key: self.connect_then_play_audio(key))

        self._add_button(frame, "\u505c\u6b62\u64ad\u653e\u97f3\u6a94", self.stop_audio)

        reminder = tk.Label(
            frame,
            text="\u9810\u9304\u8a9e\u97f3\u5ee3\u64ad\u6642\uff0c\u8acb\u78ba\u8a8d MicroSIP \u9ea5\u514b\u98a8\u4f86\u6e90\u70ba Stereo Mix \u6216 CABLE Output\u3002",
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

        status_label = tk.Label(status_frame, textvariable=self.status_text, anchor="w", padx=8, pady=7, font=("Microsoft JhengHei UI", 9))
        status_label.pack(fill="x")

    def _add_button(self, parent, text, command):
        button = tk.Button(parent, text=text, command=command, height=2, font=("Microsoft JhengHei UI", 10))
        button.pack(fill="x", pady=4)
        return button

    def set_status(self, message):
        self.status_text.set(message)

    def update_volume_label(self, _value=None):
        self.volume_text.set(f"\u9810\u9304\u8a9e\u97f3\u97f3\u91cf\uff1a{self.volume_var.get()}%")

    def start_sip_call(self):
        sip_uri = self.config_data.get("sip_uri", DEFAULT_CONFIG["sip_uri"])
        try:
            subprocess.Popen(["cmd", "/c", "start", "", sip_uri], shell=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"\u7121\u6cd5\u958b\u555f SIP URI\uff1a\n{sip_uri}\n\n{exc}")
            return False
        return True

    def dial_ip_speaker(self):
        if self.start_sip_call():
            self.set_status("\u5df2\u9001\u51fa\u64a5\u865f\u8acb\u6c42")

    def start_live_talk(self):
        if self.start_sip_call():
            self.set_status("\u5df2\u555f\u52d5\u901a\u8a71\u5ee3\u64ad\uff0c\u8acb\u958b\u59cb\u8aaa\u8a71")

    def end_live_talk(self):
        messagebox.showinfo(APP_TITLE, "\u8acb\u5728 MicroSIP \u4e2d\u6309\u4e0b\u639b\u65b7")
        self.set_status("\u8acb\u65bc MicroSIP \u4e2d\u639b\u65b7\u901a\u8a71")

    def open_microsip(self):
        microsip_paths = self.config_data.get("microsip_paths", [])
        for microsip_path in microsip_paths:
            path = Path(microsip_path)
            if path.exists():
                try:
                    if path.suffix.lower() == ".lnk":
                        os.startfile(path)
                    else:
                        subprocess.Popen([str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except OSError as exc:
                    self.set_status("\u7121\u6cd5\u958b\u555f MicroSIP")
                    messagebox.showerror(APP_TITLE, f"\u7121\u6cd5\u958b\u555f MicroSIP\uff1a\n{path}\n\n{exc}")
                    return
                self.set_status("\u5df2\u958b\u555f MicroSIP")
                return

        self.set_status("\u627e\u4e0d\u5230 MicroSIP")
        messagebox.showerror(APP_TITLE, "\u627e\u4e0d\u5230 MicroSIP\uff0c\u8acb\u81ea\u884c\u958b\u555f MicroSIP\u3002\n\n\u5df2\u6aa2\u67e5\u8def\u5f91\uff1a\n" + "\n".join(str(path) for path in microsip_paths))

    def connect_then_play_audio(self, audio_key):
        audio_path = self.get_audio_path(audio_key)
        if audio_path is None:
            return

        audio_duration_ms = self.get_wav_duration_ms(audio_path)
        if audio_duration_ms is None:
            return

        self.cancel_pending_timers()
        if not self.start_sip_call():
            return

        self.set_status(f"\u5df2\u9001\u51fa\u64a5\u865f\u8acb\u6c42\uff0c{PLAY_AFTER_DIAL_DELAY_MS // 1000} \u79d2\u5f8c\u64ad\u653e {audio_path.name}")
        self.pending_play_after_id = self.after(PLAY_AFTER_DIAL_DELAY_MS, lambda: self.play_audio_and_schedule_hangup(audio_path, audio_duration_ms))

    def get_audio_path(self, audio_key):
        audio_files = self.config_data.get("audio_files", {})
        file_name = audio_files.get(audio_key)
        if not file_name:
            self.set_status("\u627e\u4e0d\u5230\u97f3\u6a94\u8a2d\u5b9a")
            messagebox.showerror(APP_TITLE, f"config.json \u627e\u4e0d\u5230\u97f3\u6a94\u8a2d\u5b9a\uff1a{audio_key}")
            return None

        audio_path = AUDIO_DIR / file_name
        if not audio_path.exists():
            self.set_status("\u627e\u4e0d\u5230\u97f3\u6a94")
            messagebox.showerror(APP_TITLE, f"\u627e\u4e0d\u5230\u97f3\u6a94\uff1a\n{audio_path}")
            return None
        return audio_path

    def get_wav_duration_ms(self, audio_path):
        try:
            with wave.open(str(audio_path), "rb") as wav_file:
                frames = wav_file.getnframes()
                frame_rate = wav_file.getframerate()
                if frame_rate <= 0:
                    raise wave.Error("invalid frame rate")
                return int((frames / frame_rate) * 1000)
        except (wave.Error, OSError) as exc:
            self.set_status("\u7121\u6cd5\u8b80\u53d6\u97f3\u6a94\u9577\u5ea6")
            messagebox.showerror(APP_TITLE, f"\u7121\u6cd5\u8b80\u53d6\u97f3\u6a94\u9577\u5ea6\uff1a\n{audio_path}\n\n{exc}")
            return None

    def play_audio_and_schedule_hangup(self, audio_path, audio_duration_ms):
        self.pending_play_after_id = None
        if self.play_audio_path(audio_path):
            hangup_delay_ms = audio_duration_ms + HANGUP_AFTER_AUDIO_MARGIN_MS
            self.pending_hangup_after_id = self.after(hangup_delay_ms, self.auto_hangup_call)

    def play_audio_path(self, audio_path):
        playback_path = self.prepare_volume_adjusted_audio(audio_path)
        if playback_path is None:
            return False

        try:
            winsound.PlaySound(str(playback_path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        except RuntimeError as exc:
            self.set_status("\u64ad\u653e\u97f3\u6a94\u5931\u6557")
            messagebox.showerror(APP_TITLE, f"\u64ad\u653e\u97f3\u6a94\u5931\u6557\uff1a\n{playback_path}\n\n{exc}")
            return False

        self.set_status(f"\u6b63\u5728\u64ad\u653e {audio_path.name}\uff0c\u97f3\u91cf {self.volume_var.get()}%\uff0c\u64ad\u653e\u5b8c\u7562\u5f8c\u5c07\u81ea\u52d5\u639b\u65b7")
        return True

    def prepare_volume_adjusted_audio(self, audio_path):
        volume = max(0, min(100, self.volume_var.get()))
        self.cleanup_temp_audio()
        if volume == 100:
            return audio_path

        try:
            with wave.open(str(audio_path), "rb") as source:
                params = source.getparams()
                frames = source.readframes(source.getnframes())
                adjusted_frames = audioop.mul(frames, source.getsampwidth(), volume / 100)

            with tempfile.NamedTemporaryFile(prefix="ip_speaker_volume_", suffix=".wav", delete=False) as temp_file:
                temp_path = Path(temp_file.name)

            with wave.open(str(temp_path), "wb") as target:
                target.setparams(params)
                target.writeframes(adjusted_frames)
        except (audioop.error, wave.Error, OSError) as exc:
            self.set_status("\u97f3\u91cf\u8655\u7406\u5931\u6557")
            messagebox.showerror(APP_TITLE, f"\u97f3\u91cf\u8655\u7406\u5931\u6557\uff1a\n{audio_path}\n\n{exc}")
            return None

        self.current_temp_audio_path = temp_path
        return temp_path

    def cancel_pending_timers(self):
        for after_id in (self.pending_play_after_id, self.pending_hangup_after_id):
            if after_id is not None:
                try:
                    self.after_cancel(after_id)
                except tk.TclError:
                    pass
        self.pending_play_after_id = None
        self.pending_hangup_after_id = None

    def auto_hangup_call(self):
        self.pending_hangup_after_id = None
        winsound.PlaySound(None, winsound.SND_PURGE)
        self.cleanup_temp_audio()

        if self.try_microsip_hangup_command():
            self.set_status("\u97f3\u6a94\u64ad\u653e\u5b8c\u7562\uff0c\u5df2\u9001\u51fa\u81ea\u52d5\u639b\u65b7\u6307\u4ee4")
            return
        if self.try_send_escape_to_microsip():
            self.set_status("\u97f3\u6a94\u64ad\u653e\u5b8c\u7562\uff0c\u5df2\u5617\u8a66\u7528\u5feb\u6377\u9375\u639b\u65b7 MicroSIP")
            return
        self.set_status("\u97f3\u6a94\u64ad\u653e\u5b8c\u7562\uff0c\u8acb\u65bc MicroSIP \u4e2d\u624b\u52d5\u639b\u65b7\u901a\u8a71")

    def try_microsip_hangup_command(self):
        for microsip_path in self.config_data.get("microsip_paths", []):
            path = Path(microsip_path)
            if path.exists() and path.suffix.lower() == ".exe":
                try:
                    subprocess.Popen([str(path), "/hangupall"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return True
                except OSError:
                    continue
        return False

    def try_send_escape_to_microsip(self):
        command = (
            "$ws = New-Object -ComObject WScript.Shell; "
            "if ($ws.AppActivate('MicroSIP')) { Start-Sleep -Milliseconds 200; "
            "$ws.SendKeys('{ESC}'); exit 0 } else { exit 1 }"
        )
        try:
            result = subprocess.run(["powershell", "-NoProfile", "-Command", command], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0

    def stop_audio(self):
        self.cancel_pending_timers()
        winsound.PlaySound(None, winsound.SND_PURGE)
        self.cleanup_temp_audio()
        self.set_status("\u5df2\u505c\u6b62\u64ad\u653e")

    def cleanup_temp_audio(self):
        if self.current_temp_audio_path is None:
            return
        try:
            Path(self.current_temp_audio_path).unlink(missing_ok=True)
        except OSError:
            pass
        self.current_temp_audio_path = None

    def open_audio_folder(self):
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(AUDIO_DIR)
        except OSError as exc:
            self.set_status("\u7121\u6cd5\u958b\u555f\u97f3\u8a0a\u8cc7\u6599\u593e")
            messagebox.showerror(APP_TITLE, f"\u7121\u6cd5\u958b\u555f\u97f3\u8a0a\u8cc7\u6599\u593e\uff1a\n{AUDIO_DIR}\n\n{exc}")
            return
        self.set_status("\u5df2\u958b\u555f\u97f3\u8a0a\u8cc7\u6599\u593e")


def main():
    if sys.platform != "win32":
        messagebox.showwarning(APP_TITLE, "\u6b64 Demo \u4f7f\u7528 winsound \u8207 Windows SIP URI\uff0c\u8acb\u5728 Windows \u57f7\u884c\u3002")
    app = IPSpeakerDemoApp()
    app.mainloop()


if __name__ == "__main__":
    main()
