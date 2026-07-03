import subprocess
from pathlib import Path


class MicroSIPDriver:
    def __init__(self, microsip_path: str):
        self.microsip_path = Path(microsip_path)

    def validate_path(self) -> None:
        if not self.microsip_path.exists():
            raise FileNotFoundError(f"MicroSIP path not found: {self.microsip_path}")

    def open_microsip(self) -> subprocess.Popen:
        self.validate_path()
        return subprocess.Popen([str(self.microsip_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def call(self, sip_uri: str) -> subprocess.Popen:
        self.validate_path()
        return subprocess.Popen([str(self.microsip_path), sip_uri], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def hangup_all(self) -> subprocess.Popen:
        self.validate_path()
        return subprocess.Popen([str(self.microsip_path), "/hangupall"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
