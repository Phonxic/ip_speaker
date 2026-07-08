from datetime import datetime
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parents[1] / "logs" / "native_debug.log"


def debug_log(message: str) -> None:
    timestamp = datetime.now().isoformat(timespec="seconds")
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as file:
        file.write(f"[{timestamp}] {message}\n")
