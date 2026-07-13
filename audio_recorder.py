import re
import wave
from pathlib import Path


class AudioRecorderError(RuntimeError):
    pass


class AudioRecorder:
    def __init__(self, sample_rate: int = 8000, channels: int = 1):
        self.sample_rate = sample_rate
        self.channels = channels
        self.stream = None
        self.wave_file = None
        self.output_path: Path | None = None

    def start_recording(self, output_path: Path) -> None:
        if self.stream:
            raise AudioRecorderError("Recording is already running.")

        try:
            import sounddevice as sd
        except ImportError as exc:
            raise AudioRecorderError("Missing dependency: please run `pip install sounddevice numpy`.") from exc

        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path = output_path
        self.wave_file = wave.open(str(output_path), "wb")
        self.wave_file.setnchannels(self.channels)
        self.wave_file.setsampwidth(2)
        self.wave_file.setframerate(self.sample_rate)

        def callback(indata, frames, time_info, status):
            if status:
                pass
            if self.wave_file:
                self.wave_file.writeframes(indata.copy().tobytes())

        self.stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
            callback=callback,
        )
        self.stream.start()

    def stop_recording(self) -> Path:
        if not self.stream:
            raise AudioRecorderError("Recording is not running.")
        self.stream.stop()
        self.stream.close()
        self.stream = None
        if self.wave_file:
            self.wave_file.close()
            self.wave_file = None
        if not self.output_path:
            raise AudioRecorderError("Recording output path is missing.")
        return self.output_path

    def is_recording(self) -> bool:
        return self.stream is not None


def validate_audio_id(audio_id: str) -> str:
    value = audio_id.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise AudioRecorderError("Audio ID can only contain letters, numbers, underscores, and hyphens.")
    return value


def filename_from_audio_id(audio_id: str) -> str:
    return f"{validate_audio_id(audio_id)}.wav"
