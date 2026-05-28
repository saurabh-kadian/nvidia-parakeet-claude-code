"""
Telemetry logger for the Parakeet push-to-talk listener.

Appends one JSON line per event to TELEMETRY_FILE. Each line is a self-contained
record — easy to tail, grep, or feed into stats.py.
"""

import json
import os
import time

TELEMETRY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "telemetry.jsonl")


def _emit(event: str, **kwargs):
    record = {"event": event, "ts": time.time(), **kwargs}
    try:
        with open(TELEMETRY_FILE, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass  # never let telemetry crash the listener


def session_start():
    _emit("session_start")


def recording_start(window_id: str):
    _emit("recording_start", window_id=window_id)


def recording_end(duration_s: float):
    _emit("recording_end", duration_s=round(duration_s, 3))


def transcription_complete(
    inference_s: float,
    total_latency_s: float,
    word_count: int,
    char_count: int,
    corrections_applied: int,
    gpu_mem_used_mb: float,
    gpu_mem_reserved_mb: float,
    text: str,
):
    _emit(
        "transcription_complete",
        inference_s=round(inference_s, 3),
        total_latency_s=round(total_latency_s, 3),
        word_count=word_count,
        char_count=char_count,
        corrections_applied=corrections_applied,
        gpu_mem_used_mb=round(gpu_mem_used_mb, 1),
        gpu_mem_reserved_mb=round(gpu_mem_reserved_mb, 1),
        text=text,
    )


def paste_result(exit_code: int):
    _emit("paste_result", exit_code=exit_code)


def error(stage: str, message: str):
    _emit("error", stage=stage, message=message)


def skipped(reason: str):
    _emit("skipped", reason=reason)
