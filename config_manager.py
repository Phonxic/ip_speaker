import json
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
AUDIO_DIR = BASE_DIR / "audio"
LOG_DIR = BASE_DIR / "logs"


class ConfigManager:
    def __init__(self, config_path: Path | None = None):
        self.config_path = config_path or CONFIG_PATH

    def load(self) -> dict[str, Any]:
        with self.config_path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def save(self, config: dict[str, Any]) -> None:
        with self.config_path.open("w", encoding="utf-8") as file:
            json.dump(config, file, ensure_ascii=False, indent=2)

    def get_server(self) -> dict[str, Any]:
        return self.load().get("server", {})

    def get_microsip(self) -> dict[str, Any]:
        return self.load().get("microsip", {})

    def get_speakers(self) -> list[dict[str, Any]]:
        return self.load().get("speakers", [])

    def get_groups(self) -> dict[str, list[str]]:
        return self.load().get("groups", {})

    def get_audio_files(self) -> dict[str, str]:
        return self.load().get("audio_files", {})
