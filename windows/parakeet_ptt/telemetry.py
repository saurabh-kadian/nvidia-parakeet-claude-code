"""Telemetry logger — identical logic to Linux version, uses Windows DATA_DIR."""

import json
import time

from .config import TELEMETRY_FILE


def _emit(event: str, **kwargs):
    record = {"event": event, "ts": time.time(), **kwargs}
    try:
        TELEMETRY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(TELEMETRY_FILE, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass


def session_start():                _emit("session_start")
def recording_start(window: str):   _emit("recording_start", window=window)
def recording_end(duration_s):      _emit("recording_end", duration_s=round(duration_s, 3))
def paste_result(exit_code: int):   _emit("paste_result", exit_code=exit_code)
def error(stage: str, msg: str):    _emit("error", stage=stage, message=msg)
def skipped(reason: str):           _emit("skipped", reason=reason)


def transcription_complete(
    inference_s, total_latency_s, word_count, char_count,
    corrections_applied, gpu_mem_used_mb, gpu_mem_reserved_mb, text,
):
    _emit(
        "transcription_complete",
        inference_s=round(inference_s, 3),
        total_latency_s=round(total_latency_s, 3),
        word_count=word_count, char_count=char_count,
        corrections_applied=corrections_applied,
        gpu_mem_used_mb=round(gpu_mem_used_mb, 1),
        gpu_mem_reserved_mb=round(gpu_mem_reserved_mb, 1),
        text=text,
    )
