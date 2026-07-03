from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from config_manager import AUDIO_DIR, ConfigManager
from logger_manager import BroadcastLogger
from microsip_driver import MicroSIPDriver
from task_manager import AudioPlayer, TaskManager

config_manager = ConfigManager()
config = config_manager.load()
logger = BroadcastLogger()
driver = MicroSIPDriver(config.get("microsip", {}).get("path", ""))
task_manager = TaskManager(config, driver, logger)
audio_player = AudioPlayer()

app = FastAPI(title="Windows Broadcast Management Server")


class AudioBroadcastRequest(BaseModel):
    target_group: str
    audio_name: str


class LiveBroadcastRequest(BaseModel):
    target_group: str


def reload_config() -> dict[str, Any]:
    global config
    config = config_manager.load()
    task_manager.config = config
    driver.microsip_path = Path(config.get("microsip", {}).get("path", ""))
    return config


def enabled_speakers_for_group(target_group: str) -> list[dict[str, Any]]:
    cfg = reload_config()
    groups = cfg.get("groups", {})
    if target_group not in groups:
        raise HTTPException(status_code=404, detail=f"target_group not found: {target_group}")

    speaker_ids = set(groups[target_group])
    speakers = [speaker for speaker in cfg.get("speakers", []) if speaker.get("id") in speaker_ids and speaker.get("enabled")]
    if not speakers:
        raise HTTPException(status_code=400, detail="no enabled speakers in target group")
    return speakers


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/speakers")
def speakers():
    return reload_config().get("speakers", [])


@app.get("/api/groups")
def groups():
    return reload_config().get("groups", {})


@app.get("/api/audio-files")
def audio_files():
    return reload_config().get("audio_files", {})


@app.get("/api/logs")
def logs():
    return logger.read_recent_logs(limit=50)


@app.post("/api/broadcast/audio")
def broadcast_audio(request: AudioBroadcastRequest):
    cfg = reload_config()
    target_speakers = enabled_speakers_for_group(request.target_group)
    audio_map = cfg.get("audio_files", {})
    if request.audio_name not in audio_map:
        raise HTTPException(status_code=404, detail=f"audio_name not found: {request.audio_name}")

    audio_file = audio_map[request.audio_name]
    audio_path = AUDIO_DIR / audio_file
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail=f"audio file not found: {audio_file}")

    task = task_manager.create_audio_task(request.target_group, target_speakers, request.audio_name, audio_file)
    return {"accepted": True, "task_id": task.task_id, "message": "task queued"}


@app.post("/api/broadcast/live/start")
def live_start(request: LiveBroadcastRequest):
    cfg = reload_config()
    target_speakers = enabled_speakers_for_group(request.target_group)
    interval = float(cfg.get("microsip", {}).get("multi_call_interval_sec", 0.8))

    import time
    for speaker in target_speakers:
        driver.call(speaker["sip_uri"])
        time.sleep(interval)

    speaker_ids = [speaker["id"] for speaker in target_speakers]
    logger.write("live", "live_start", request.target_group, speaker_ids, "", "completed", "live broadcast started")
    return {"accepted": True, "message": "live broadcast started"}


@app.post("/api/broadcast/live/stop")
def live_stop():
    driver.hangup_all()
    logger.write("live", "live_stop", "", [], "", "completed", "live broadcast stopped")
    return {"accepted": True, "message": "live broadcast stopped"}


@app.post("/api/broadcast/stop")
def stop_broadcast():
    audio_player.stop()
    driver.hangup_all()
    logger.write("manual", "stop", "", [], "", "completed", "broadcast stopped")
    return {"accepted": True, "message": "broadcast stopped"}


if __name__ == "__main__":
    server = config.get("server", {})
    uvicorn.run("broadcast_server:app", host=server.get("host", "127.0.0.1"), port=int(server.get("port", 8000)), reload=False)
