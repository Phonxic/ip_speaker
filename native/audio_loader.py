import struct
import wave
from pathlib import Path

CONVERT_HINT = "ffmpeg -i input.mp3 -ar 8000 -ac 1 -sample_fmt s16 audio/test_warning.wav"


class WavFormatError(ValueError):
    pass


def load_wav_samples(path: str | Path) -> list[int]:
    path = Path(path)
    try:
        with wave.open(str(path), "rb") as wav_file:
            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            frame_rate = wav_file.getframerate()
            compression = wav_file.getcomptype()
            if channels != 1 or sample_width != 2 or frame_rate != 8000 or compression != "NONE":
                raise WavFormatError(
                    "WAV format must be 8000 Hz, mono, 16-bit PCM. Convert with: " + CONVERT_HINT
                )
            frames = wav_file.readframes(wav_file.getnframes())
    except wave.Error as exc:
        raise WavFormatError(f"Invalid WAV file. Convert with: {CONVERT_HINT}") from exc

    sample_count = len(frames) // 2
    return list(struct.unpack("<" + "h" * sample_count, frames))


def get_wav_duration_sec(path: str | Path) -> float:
    path = Path(path)
    with wave.open(str(path), "rb") as wav_file:
        frame_rate = wav_file.getframerate()
        if frame_rate <= 0:
            raise WavFormatError("Invalid WAV frame rate")
        return wav_file.getnframes() / frame_rate
