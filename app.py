
import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import requests

from config_manager import AUDIO_DIR, ConfigManager

APP_TITLE = "Windows Broadcast Management Client"
REQUEST_TIMEOUT = 3


class BroadcastClientApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("980x620")
        self.minsize(900, 560)
        self.configure(padx=16, pady=16)

        self.config_manager = ConfigManager()
        server_config = self.config_manager.get_server()
        self.base_url = f"http://{server_config.get('host', '127.0.0.1')}:{server_config.get('port', 8000)}"

        self.server_status_text = tk.StringVar(value="Offline")
        self.status_text = tk.StringVar(value="Please run: python broadcast_server.py")
        self.group_var = tk.StringVar()
        self.speaker_text = tk.StringVar(value="")

        self.groups = {}
        self.speakers = []
        self.audio_files = {}

        self._build_ui()
        self.load_local_config_data()
        self.check_server()

    def _build_ui(self):
        title = tk.Label(self, text=APP_TITLE, font=("Microsoft JhengHei UI", 16, "bold"))
        title.pack(fill="x", pady=(0, 12))

        content = tk.Frame(self)
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=1, uniform="main")
        content.columnconfigure(1, weight=1, uniform="main")

        left = tk.Frame(content)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        right = tk.Frame(content)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        self._build_server_section(left)
        self._build_group_section(left)
        self._build_live_section(left)
        self._build_audio_section(right)
        self._build_control_section(right)
        self._build_status_bar()

    def _build_server_section(self, parent):
        frame = tk.LabelFrame(parent, text="Server Status", padx=12, pady=12, font=("Microsoft JhengHei UI", 10, "bold"))
        frame.pack(fill="x", pady=(0, 12))
        tk.Label(frame, textvariable=self.server_status_text, anchor="w", font=("Microsoft JhengHei UI", 11)).pack(fill="x", pady=(0, 8))
        self._button(frame, "Start Local Server", self.start_local_server)
        self._button(frame, "Check Server Again", self.check_server)

    def _build_group_section(self, parent):
        frame = tk.LabelFrame(parent, text="Target Group", padx=12, pady=12, font=("Microsoft JhengHei UI", 10, "bold"))
        frame.pack(fill="x", pady=(0, 12))
        self.group_combo = ttk.Combobox(frame, textvariable=self.group_var, state="readonly")
        self.group_combo.pack(fill="x", pady=(0, 8))
        self.group_combo.bind("<<ComboboxSelected>>", lambda _event: self.update_group_speakers())
        tk.Label(frame, textvariable=self.speaker_text, justify="left", anchor="w", wraplength=420).pack(fill="x")

    def _build_live_section(self, parent):
        frame = tk.LabelFrame(parent, text="Live Broadcast", padx=12, pady=12, font=("Microsoft JhengHei UI", 10, "bold"))
        frame.pack(fill="x", pady=(0, 12))
        self._button(frame, "Start Live Broadcast", self.start_live)
        self._button(frame, "Stop Live Broadcast", self.stop_live)

    def _build_audio_section(self, parent):
        self.audio_frame = tk.LabelFrame(parent, text="One-Click Audio Broadcast", padx=12, pady=12, font=("Microsoft JhengHei UI", 10, "bold"))
        self.audio_frame.pack(fill="both", expand=True, pady=(0, 12))
        tk.Label(self.audio_frame, text="Audio buttons will appear when server is online.", anchor="w").pack(fill="x")

    def _build_control_section(self, parent):
        frame = tk.LabelFrame(parent, text="Control", padx=12, pady=12, font=("Microsoft JhengHei UI", 10, "bold"))
        frame.pack(fill="x", pady=(0, 12))
        self._button(frame, "Stop Broadcast", self.stop_broadcast)
        self._button(frame, "Open Audio Folder", self.open_audio_folder)
        self._button(frame, "View Recent Logs", self.show_recent_logs)

    def _build_status_bar(self):
        frame = tk.Frame(self, bd=1, relief="sunken")
        frame.pack(fill="x", side="bottom", pady=(12, 0))
        tk.Label(frame, textvariable=self.status_text, anchor="w", padx=8, pady=7).pack(fill="x")

    def _button(self, parent, text, command):
        button = tk.Button(parent, text=text, command=command, height=2, font=("Microsoft JhengHei UI", 10))
        button.pack(fill="x", pady=4)
        return button

    def start_local_server(self):
        def worker():
            try:
                subprocess.Popen(
                    [sys.executable, "broadcast_server.py"],
                    cwd=Path(__file__).resolve().parent,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self.after(0, lambda: self.status_text.set("Starting local Broadcast Server..."))
                self.after(1500, self.check_server)
            except OSError as exc:
                message = str(exc)
                self.after(0, lambda msg=message: self.status_text.set(f"Start server error: {msg}"))
        self.run_background(worker)

    def check_server(self):
        self.run_background(self._check_server)

    def _check_server(self):
        try:
            response = requests.get(f"{self.base_url}/api/health", timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            self.after(0, lambda: self.server_status_text.set("Online"))
            self.after(0, lambda: self.status_text.set("Broadcast Server Online"))
            self.load_server_data()
        except requests.RequestException:
            self.after(0, lambda: self.server_status_text.set("Offline"))
            self.after(0, lambda: self.status_text.set("Please run: python broadcast_server.py"))

    def load_local_config_data(self):
        try:
            config = self.config_manager.load()
            self.groups = config.get("groups", {})
            self.speakers = config.get("speakers", [])
            self.audio_files = config.get("audio_files", {})
            self.refresh_ui_data()
        except Exception as exc:
            self.status_text.set(f"Local config error: {exc}")

    def load_server_data(self):
        try:
            self.groups = requests.get(f"{self.base_url}/api/groups", timeout=REQUEST_TIMEOUT).json()
            self.speakers = requests.get(f"{self.base_url}/api/speakers", timeout=REQUEST_TIMEOUT).json()
            self.audio_files = requests.get(f"{self.base_url}/api/audio-files", timeout=REQUEST_TIMEOUT).json()
            self.after(0, self.refresh_ui_data)
        except requests.RequestException as exc:
            message = str(exc)
            self.after(0, lambda msg=message: self.status_text.set(f"API error: {msg}"))

    def refresh_ui_data(self):
        group_names = list(self.groups.keys())
        self.group_combo["values"] = group_names
        if group_names and not self.group_var.get():
            self.group_var.set(group_names[0])
        self.update_group_speakers()
        self.refresh_audio_buttons()

    def update_group_speakers(self):
        group = self.group_var.get()
        speaker_ids = set(self.groups.get(group, []))
        lines = []
        for speaker in self.speakers:
            if speaker.get("id") in speaker_ids:
                enabled = "enabled" if speaker.get("enabled") else "disabled"
                lines.append(f"{speaker.get('id')} - {speaker.get('name')} ({enabled})")
        self.speaker_text.set("\n".join(lines) if lines else "No speakers")

    def refresh_audio_buttons(self):
        for child in self.audio_frame.winfo_children():
            child.destroy()
        if not self.audio_files:
            tk.Label(self.audio_frame, text="No audio files from server.", anchor="w").pack(fill="x")
            return
        for audio_name in self.audio_files.keys():
            self._button(self.audio_frame, f"Auto Play: {audio_name}", lambda name=audio_name: self.broadcast_audio(name))

    def selected_group(self):
        group = self.group_var.get()
        if not group:
            messagebox.showwarning(APP_TITLE, "Please select a target group first.")
            return None
        return group

    def post_api(self, endpoint: str, payload: dict | None = None):
        def worker():
            try:
                response = requests.post(f"{self.base_url}{endpoint}", json=payload, timeout=REQUEST_TIMEOUT)
                try:
                    data = response.json()
                except ValueError:
                    data = {}
                response.raise_for_status()
                message = data.get("message", "ok")
                if "task_id" in data:
                    message += f" | task_id={data['task_id']}"
                self.after(0, lambda: self.status_text.set(message))
            except requests.RequestException as exc:
                message = str(exc)
                self.after(0, lambda msg=message: self.status_text.set(f"API error: {msg}"))
        self.run_background(worker)

    def broadcast_audio(self, audio_name: str):
        group = self.selected_group()
        if group:
            self.post_api("/api/broadcast/audio", {"target_group": group, "audio_name": audio_name})

    def start_live(self):
        group = self.selected_group()
        if group:
            self.post_api("/api/broadcast/live/start", {"target_group": group})

    def stop_live(self):
        self.post_api("/api/broadcast/live/stop")

    def stop_broadcast(self):
        self.post_api("/api/broadcast/stop")

    def open_audio_folder(self):
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(AUDIO_DIR)

    def show_recent_logs(self):
        def worker():
            try:
                rows = requests.get(f"{self.base_url}/api/logs", timeout=REQUEST_TIMEOUT).json()
                text = "\n".join(f"{row.get('time')} | {row.get('type')} | {row.get('status')} | {row.get('message')}" for row in rows)
                self.after(0, lambda: messagebox.showinfo("Recent Logs", text or "No logs"))
            except requests.RequestException as exc:
                message = str(exc)
                self.after(0, lambda msg=message: self.status_text.set(f"API error: {msg}"))
        self.run_background(worker)

    def run_background(self, target):
        threading.Thread(target=target, daemon=True).start()


if __name__ == "__main__":
    app = BroadcastClientApp()
    app.mainloop()
