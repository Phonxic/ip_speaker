import json
import os
import re
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from native.audio_loader import CONVERT_HINT, WavFormatError, load_wav_samples
from native.rtp_streamer import RTPStreamer
from native.sip_client import SIPClient
from native.native_debug import LOG_PATH, debug_log

APP_TITLE = "Native SIP/RTP IP Speaker Demo"
BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
AUDIO_DIR = BASE_DIR / "audio"

LABELS = {
    "settings": "IP Speaker Settings",
    "local_ip": "Local IP",
    "speaker_ip": "Speaker IP",
    "sip_user": "SIP User",
    "local_sip_port": "Local SIP Port",
    "local_rtp_port": "Local RTP Port",
    "sip_uri": "Current SIP URI",
    "apply": "Apply Settings",
    "test": "Test Call / Play Test Audio",
    "live": "Live Broadcast",
    "live_disabled": "Native version currently supports pre-recorded audio only. Microphone live broadcast is not implemented yet.",
    "audio": "Pre-recorded Audio Broadcast",
    "stop": "Stop Playback",
    "open_audio": "Open Audio Folder",
    "ready": "Ready",
}


def default_config() -> dict:
    return {
        "local": {"ip": "", "advertise_ip": "", "sip_port": 5062, "rtp_port": 40000, "audio_gain": 3.0, "start_delay_ms": 500},
        "speaker": {"ip": "192.168.6.120", "sip_user": "4267", "sip_port": 5060},
        "audio_files": {
            "測試廣播": "testing.wav",
            "旅客跌倒": "fall_warning.wav",
            "行李滾落": "baggage_warning.wav",
            "輪椅進入": "wheelchair_warning.wav",
            "旅客逗留": "stay_warning.wav",
        },
    }


def sanitize_audio_files(audio_files: dict) -> dict:
    clean = {}
    for name, filename in audio_files.items():
        if isinstance(name, str) and isinstance(filename, str) and "?" not in name:
            clean[name] = filename
    return clean


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        config = default_config()
        save_config(config)
        return config
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        old = json.load(file)
    config = default_config()
    config.update(old)
    config["local"] = {**default_config()["local"], **old.get("local", {})}
    config["speaker"] = {**default_config()["speaker"], **old.get("speaker", {})}
    if "sip_uri" in old and ("speaker" not in old or not old.get("speaker")):
        user, ip = parse_sip_uri(old["sip_uri"])
        config["speaker"]["sip_user"] = user or config["speaker"]["sip_user"]
        config["speaker"]["ip"] = ip or config["speaker"]["ip"]
    merged_audio_files = {**default_config()["audio_files"], **old.get("audio_files", {})}
    config["audio_files"] = sanitize_audio_files(merged_audio_files)
    return config


def save_config(config: dict) -> None:
    with CONFIG_PATH.open("w", encoding="utf-8") as file:
        json.dump(config, file, ensure_ascii=False, indent=2)


def parse_sip_uri(uri: str) -> tuple[str | None, str | None]:
    match = re.match(r"sip:([^@]+)@([^:;]+)", uri or "")
    if not match:
        return None, None
    return match.group(1), match.group(2)


class NativeBroadcastApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("760x620")
        self.minsize(700, 560)
        self.configure(padx=16, pady=16)
        self.config_data = load_config()
        self.stop_event = threading.Event()
        self.current_client = None
        self.status_text = tk.StringVar(value=f"{LABELS['ready']} | Debug log: {LOG_PATH}")
        self.sip_uri_text = tk.StringVar()
        self.audio_buttons = []
        self._build_ui()
        self._load_config_to_vars()
        self.update_sip_uri()

    def _build_ui(self):
        title = tk.Label(self, text=APP_TITLE, font=("Microsoft JhengHei UI", 16, "bold"))
        title.pack(fill="x", pady=(0, 12))
        self._build_settings_section()
        self._build_live_section()
        self._build_audio_section()
        self._build_control_section()
        self._build_status_bar()

    def _build_settings_section(self):
        frame = tk.LabelFrame(self, text=LABELS["settings"], padx=12, pady=12, font=("Microsoft JhengHei UI", 10, "bold"))
        frame.pack(fill="x", pady=(0, 10))
        for col in range(6):
            frame.columnconfigure(col, weight=1)

        self.local_ip_var = tk.StringVar()
        self.advertise_ip_var = tk.StringVar()
        self.speaker_ip_var = tk.StringVar()
        self.sip_user_var = tk.StringVar()
        self.local_sip_port_var = tk.StringVar()
        self.local_rtp_port_var = tk.StringVar()
        self.speaker_sip_port_var = tk.StringVar()

        fields = [
            (LABELS["local_ip"], self.local_ip_var),
            ("Advertise IP", self.advertise_ip_var),
            (LABELS["speaker_ip"], self.speaker_ip_var),
            (LABELS["sip_user"], self.sip_user_var),
            (LABELS["local_sip_port"], self.local_sip_port_var),
            (LABELS["local_rtp_port"], self.local_rtp_port_var),
            ("Speaker SIP Port", self.speaker_sip_port_var),
        ]
        for index, (label, var) in enumerate(fields):
            row = index // 3
            col = (index % 3) * 2
            tk.Label(frame, text=label, anchor="w").grid(row=row, column=col, sticky="ew", padx=(0, 4), pady=4)
            entry = tk.Entry(frame, textvariable=var)
            entry.grid(row=row, column=col + 1, sticky="ew", padx=(0, 10), pady=4)
            var.trace_add("write", lambda *_args: self.update_sip_uri())

        tk.Label(frame, text=LABELS["sip_uri"], anchor="w").grid(row=3, column=0, sticky="ew", padx=(0, 4), pady=4)
        tk.Label(frame, textvariable=self.sip_uri_text, anchor="w").grid(row=3, column=1, columnspan=5, sticky="ew", pady=4)
        tk.Button(frame, text=LABELS["apply"], command=self.apply_settings, height=2).grid(row=4, column=0, columnspan=3, sticky="ew", padx=(0, 8), pady=(8, 0))
        tk.Button(frame, text=LABELS["test"], command=lambda: self.start_audio_broadcast("\u6e2c\u8a66\u5ee3\u64ad"), height=2).grid(row=4, column=3, columnspan=3, sticky="ew", pady=(8, 0))

    def _build_live_section(self):
        frame = tk.LabelFrame(self, text=LABELS["live"], padx=12, pady=12, font=("Microsoft JhengHei UI", 10, "bold"))
        frame.pack(fill="x", pady=(0, 10))
        tk.Label(frame, text=LABELS["live_disabled"], anchor="w", justify="left", wraplength=700).pack(fill="x")
        tk.Button(frame, text="Start Live Broadcast (Disabled)", state="disabled", height=2).pack(fill="x", pady=(8, 0))

    def _build_audio_section(self):
        frame = tk.LabelFrame(self, text=LABELS["audio"], padx=12, pady=12, font=("Microsoft JhengHei UI", 10, "bold"))
        frame.pack(fill="both", expand=True, pady=(0, 10))
        self.audio_frame = frame
        self.refresh_audio_buttons()

    def _build_control_section(self):
        frame = tk.Frame(self)
        frame.pack(fill="x", pady=(0, 10))
        tk.Button(frame, text=LABELS["stop"], command=self.stop_playback, height=2).pack(side="left", fill="x", expand=True, padx=(0, 8))
        tk.Button(frame, text=LABELS["open_audio"], command=self.open_audio_folder, height=2).pack(side="left", fill="x", expand=True)

    def _build_status_bar(self):
        frame = tk.Frame(self, bd=1, relief="sunken")
        frame.pack(fill="x", side="bottom")
        tk.Label(frame, textvariable=self.status_text, anchor="w", padx=8, pady=7).pack(fill="x")

    def _load_config_to_vars(self):
        local = self.config_data.get("local", {})
        speaker = self.config_data.get("speaker", {})
        self.local_ip_var.set(local.get("ip", ""))
        self.advertise_ip_var.set(local.get("advertise_ip", ""))
        self.local_sip_port_var.set(str(local.get("sip_port", 5062)))
        self.local_rtp_port_var.set(str(local.get("rtp_port", 40000)))
        self.speaker_ip_var.set(speaker.get("ip", "192.168.6.120"))
        self.sip_user_var.set(str(speaker.get("sip_user", "4267")))
        self.speaker_sip_port_var.set(str(speaker.get("sip_port", 5060)))

    def refresh_audio_buttons(self):
        for child in self.audio_frame.winfo_children():
            child.destroy()
        audio_files = sanitize_audio_files(self.config_data.get("audio_files", {}))
        self.config_data["audio_files"] = audio_files
        for audio_name in audio_files:
            tk.Button(
                self.audio_frame,
                text=f"Auto Play: {audio_name}",
                command=lambda name=audio_name: self.start_audio_broadcast(name),
                height=2,
            ).pack(fill="x", pady=4)

    def update_sip_uri(self):
        self.sip_uri_text.set(f"sip:{self.sip_user_var.get()}@{self.speaker_ip_var.get()}")

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
            "audio_gain": float(self.config_data.get("local", {}).get("audio_gain", 1.0)),
            "start_delay_ms": int(self.config_data.get("local", {}).get("start_delay_ms", 0)),
        }

    def apply_settings(self):
        try:
            settings = self.current_settings()
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        self.config_data["local"] = {
            "ip": settings["local_ip"],
            "advertise_ip": settings["advertise_ip"],
            "sip_port": settings["local_sip_port"],
            "rtp_port": settings["local_rtp_port"],
            "audio_gain": settings.get("audio_gain", 3.0),
            "start_delay_ms": settings.get("start_delay_ms", 500),
        }
        self.config_data["speaker"] = {
            "ip": settings["speaker_ip"],
            "sip_user": settings["speaker_sip_user"],
            "sip_port": settings["speaker_sip_port"],
        }
        self.config_data["audio_files"] = sanitize_audio_files(self.config_data.get("audio_files", {}))
        save_config(self.config_data)
        self.update_sip_uri()
        self.set_status("Settings applied")

    def start_audio_broadcast(self, audio_name: str):
        try:
            settings = self.current_settings()
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        self.config_data["audio_files"] = sanitize_audio_files(self.config_data.get("audio_files", {}))
        audio_file = self.config_data["audio_files"].get(audio_name)
        if not audio_file:
            messagebox.showerror(APP_TITLE, f"Audio setting not found: {audio_name}")
            return
        audio_path = AUDIO_DIR / audio_file
        if not audio_path.exists():
            messagebox.showerror(APP_TITLE, f"Audio file not found:\n{audio_path}")
            return
        self.apply_settings()
        self.stop_event.clear()
        thread = threading.Thread(target=self._broadcast_worker, args=(settings, audio_path), daemon=True)
        thread.start()

    def _broadcast_worker(self, settings: dict, audio_path: Path):
        client = None
        try:
            debug_log("=== Native broadcast started ===")
            debug_log(f"settings={settings}, audio_path={audio_path}")
            self.set_status_threadsafe("Loading WAV file")
            samples = load_wav_samples(audio_path)
            debug_log(f"WAV loaded: samples={len(samples)}")
            client = SIPClient(
                settings["local_ip"],
                settings["local_sip_port"],
                settings["local_rtp_port"],
                settings["speaker_ip"],
                settings["speaker_sip_user"],
                settings["speaker_sip_port"],
                settings["advertise_ip"],
            )
            self.current_client = client
            self.set_status_threadsafe("Calling IP Speaker")
            client.send_invite()
            rtp_ip, rtp_port, payload_type = client.wait_for_answer(status_callback=self.on_sip_status)
            codec_name = "PCMA" if payload_type == 8 else "PCMU"
            self.set_status_threadsafe(f"Connected, RTP target {rtp_ip}:{rtp_port}, codec {codec_name}")
            client.send_ack()
            self.set_status_threadsafe("Streaming RTP audio")
            streamer = RTPStreamer(settings["local_ip"], settings["local_rtp_port"], rtp_ip, rtp_port, self.stop_event, payload_type, client.rtp_ssrc, settings.get("audio_gain", 1.0), settings.get("start_delay_ms", 0))
            packet_count = streamer.stream_samples(samples)
            self.set_status_threadsafe(f"RTP packets sent: {packet_count}")
            if self.stop_event.is_set():
                self.set_status_threadsafe("Playback stopped")
            else:
                self.set_status_threadsafe("Playback completed")
            client.send_bye()
            self.set_status_threadsafe("Call ended")
        except WavFormatError as exc:
            debug_log(f"WAV format error: {exc}")
            self.show_error_threadsafe(str(exc))
            self.set_status_threadsafe("WAV format error")
        except Exception as exc:
            debug_log(f"ERROR: {type(exc).__name__}: {exc}")
            self.show_error_threadsafe(str(exc))
            self.set_status_threadsafe(f"Error: {exc}")
            try:
                if client:
                    client.send_bye()
            except Exception:
                pass
        finally:
            if client:
                client.close()
            self.current_client = None

    def on_sip_status(self, status: int):
        messages = {
            100: "Received 100 Trying",
            180: "Received 180 Ringing",
            183: "Received 183 Session Progress",
            200: "Connected",
        }
        self.set_status_threadsafe(messages.get(status, f"Received SIP {status}"))

    def stop_playback(self):
        self.stop_event.set()
        try:
            if self.current_client:
                self.current_client.send_bye()
        except Exception:
            pass
        self.set_status("Stop requested")

    def open_audio_folder(self):
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(AUDIO_DIR)

    def set_status(self, message: str):
        self.status_text.set(message)

    def set_status_threadsafe(self, message: str):
        self.after(0, lambda msg=message: self.set_status(msg))

    def show_error_threadsafe(self, message: str):
        self.after(0, lambda msg=message: messagebox.showerror(APP_TITLE, msg))


if __name__ == "__main__":
    app = NativeBroadcastApp()
    app.mainloop()
