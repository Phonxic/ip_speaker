import csv
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_PATH = LOG_DIR / "broadcast_log.csv"
HEADER = ["time", "task_id", "type", "target_group", "target_speakers", "audio_file", "status", "message"]


class BroadcastLogger:
    def __init__(self, log_path: Path | None = None):
        self.log_path = log_path or LOG_PATH
        self.ensure_log_file()

    def ensure_log_file(self) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_path.exists():
            with self.log_path.open("w", newline="", encoding="utf-8-sig") as file:
                csv.DictWriter(file, fieldnames=HEADER).writeheader()

    def write(self, task_id: str, task_type: str, target_group: str, target_speakers, audio_file: str, status: str, message: str) -> None:
        self.ensure_log_file()
        if isinstance(target_speakers, list):
            speakers = ";".join(target_speakers)
        else:
            speakers = str(target_speakers or "")
        row = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "task_id": task_id,
            "type": task_type,
            "target_group": target_group,
            "target_speakers": speakers,
            "audio_file": audio_file or "",
            "status": status,
            "message": message,
        }
        with self.log_path.open("a", newline="", encoding="utf-8-sig") as file:
            csv.DictWriter(file, fieldnames=HEADER).writerow(row)

    def read_recent_logs(self, limit: int = 50) -> list[dict[str, str]]:
        self.ensure_log_file()
        with self.log_path.open("r", newline="", encoding="utf-8-sig") as file:
            rows = list(csv.DictReader(file))
        return rows[-limit:][::-1]
