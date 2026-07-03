import queue
import threading
import time
import uuid
import wave
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import winsound

from logger_manager import BroadcastLogger
from microsip_driver import MicroSIPDriver

BASE_DIR = Path(__file__).resolve().parent
AUDIO_DIR = BASE_DIR / "audio"


@dataclass
class BroadcastTask:
    task_id: str
    created_time: str
    type: str
    target_group: str
    target_speakers: list[dict[str, Any]]
    audio_name: str
    audio_file: str
    status: str = "queued"
    message: str = "queued"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["target_speaker_ids"] = [speaker.get("id", "") for speaker in self.target_speakers]
        return data


class AudioPlayer:
    def play(self, path: Path) -> None:
        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)

    def stop(self) -> None:
        winsound.PlaySound(None, winsound.SND_PURGE)

    def duration_sec(self, path: Path) -> float:
        with wave.open(str(path), "rb") as wav_file:
            frame_rate = wav_file.getframerate()
            if frame_rate <= 0:
                raise ValueError("invalid wav frame rate")
            return wav_file.getnframes() / frame_rate


class TaskManager:
    def __init__(self, config: dict[str, Any], driver: MicroSIPDriver, logger: BroadcastLogger):
        self.config = config
        self.driver = driver
        self.logger = logger
        self.audio_player = AudioPlayer()
        self.tasks: dict[str, BroadcastTask] = {}
        self.queue: queue.Queue[BroadcastTask] = queue.Queue()
        self.worker = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker.start()

    def create_audio_task(self, target_group: str, target_speakers: list[dict[str, Any]], audio_name: str, audio_file: str) -> BroadcastTask:
        task = BroadcastTask(
            task_id=str(uuid.uuid4()),
            created_time=datetime.now().isoformat(timespec="seconds"),
            type="audio",
            target_group=target_group,
            target_speakers=target_speakers,
            audio_name=audio_name,
            audio_file=audio_file,
        )
        self.tasks[task.task_id] = task
        self.queue.put(task)
        self._log(task, "queued", "task queued")
        return task

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        task = self.tasks.get(task_id)
        return task.to_dict() if task else None

    def stop_all(self) -> None:
        self.audio_player.stop()
        self.driver.hangup_all()

    def _worker_loop(self) -> None:
        while True:
            task = self.queue.get()
            try:
                self._execute_audio_task(task)
            finally:
                self.queue.task_done()

    def _execute_audio_task(self, task: BroadcastTask) -> None:
        try:
            task.status = "running"
            task.message = "running"
            self._log(task, "running", "task started")

            microsip_config = self.config.get("microsip", {})
            multi_call_interval_sec = float(microsip_config.get("multi_call_interval_sec", 0.8))
            call_connect_delay_sec = float(microsip_config.get("call_connect_delay_sec", 1.5))
            hangup_after_playback = bool(microsip_config.get("hangup_after_playback", True))

            for speaker in task.target_speakers:
                self.driver.call(speaker["sip_uri"])
                time.sleep(multi_call_interval_sec)

            time.sleep(call_connect_delay_sec)

            audio_path = AUDIO_DIR / task.audio_file
            duration_sec = self.audio_player.duration_sec(audio_path)
            self.audio_player.play(audio_path)
            time.sleep(duration_sec + 0.5)

            if hangup_after_playback:
                self.driver.hangup_all()

            task.status = "completed"
            task.message = "completed"
            self._log(task, "completed", "task completed")
        except Exception as exc:
            task.status = "failed"
            task.message = str(exc)
            self._log(task, "failed", str(exc))
            try:
                self.audio_player.stop()
                self.driver.hangup_all()
            except Exception:
                pass

    def _log(self, task: BroadcastTask, status: str, message: str) -> None:
        speaker_ids = [speaker.get("id", "") for speaker in task.target_speakers]
        self.logger.write(task.task_id, task.type, task.target_group, speaker_ids, task.audio_file, status, message)
