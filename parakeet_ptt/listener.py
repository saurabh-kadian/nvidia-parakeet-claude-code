#!/usr/bin/env python3
"""
Parakeet TDT push-to-talk daemon.

Intentionally self-contained — reads config and corrections from JSON files
directly so it can be launched under the virtualenv Python without needing
the parakeet_ptt package on sys.path.

Launch via:
    ~/.local/share/parakeet-ptt/env/bin/python /usr/share/parakeet-ptt/parakeet_ptt/listener.py
"""

import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
import atexit
import numpy as np
from pathlib import Path

# ── Config paths (mirrored from config.py without importing it) ────────────────
_HOME       = Path.home()
_CONFIG_DIR = _HOME / ".config"          / "parakeet-ptt"
_DATA_DIR   = _HOME / ".local" / "share" / "parakeet-ptt"
_TEL_FILE   = _DATA_DIR / "telemetry.jsonl"
_CONFIG_FILE = _CONFIG_DIR / "config.json"
_CORR_FILE  = _CONFIG_DIR / "corrections.json"

PID_FILE    = "/tmp/parakeet_listener.pid"
SAMPLE_RATE = 16000
MIN_DURATION_SEC = 0.3
MODEL_NAME  = "nvidia/parakeet-tdt-0.6b-v3"


def _load_config() -> dict:
    defaults = {"ptt_key": "f9", "paste_method": "ctrl+shift+v", "clipboard_tool": "xclip"}
    if _CONFIG_FILE.exists():
        try:
            with open(_CONFIG_FILE) as f:
                return {**defaults, **json.load(f)}
        except Exception:
            pass
    return defaults


def _load_corrections() -> list:
    if _CORR_FILE.exists():
        try:
            with open(_CORR_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return []


cfg = _load_config()
PTT_KEY      = cfg["ptt_key"]
PASTE_CMD    = cfg["paste_method"]
CLIP_TOOL    = cfg["clipboard_tool"]
_MODEL_CACHE = Path(cfg.get("model_cache", str(_DATA_DIR / "model_cache")))

os.environ.setdefault("HF_HOME",        str(_MODEL_CACHE / "huggingface"))
os.environ.setdefault("NEMO_CACHE_DIR", str(_MODEL_CACHE / "nemo"))
os.environ.setdefault("TORCH_HOME",     str(_MODEL_CACHE / "torch"))


# ── Telemetry (inline to avoid import dependency) ──────────────────────────────
def _emit(event: str, **kwargs):
    record = {"event": event, "ts": time.time(), **kwargs}
    try:
        _TEL_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_TEL_FILE, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass


# ── Corrections ────────────────────────────────────────────────────────────────
def _apply_corrections(text: str) -> str:
    for pattern, replacement in _load_corrections():
        try:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        except re.error:
            pass
    return text


# ── PID file ───────────────────────────────────────────────────────────────────
def _write_pid():
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))


def _remove_pid():
    try:
        os.unlink(PID_FILE)
    except FileNotFoundError:
        pass


atexit.register(_remove_pid)
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
_write_pid()


# ── Model loading ──────────────────────────────────────────────────────────────
print("[parakeet] Loading model — ~10-20 s on first run…", flush=True)
import nemo.collections.asr as nemo_asr

asr_model = nemo_asr.models.ASRModel.from_pretrained(MODEL_NAME)
asr_model.eval()
print(f"[parakeet] Ready — hold {PTT_KEY.upper()} to record.", flush=True)
_emit("session_start")
subprocess.run(
    ["notify-send", "-i", "audio-input-microphone",
     "Parakeet ready", f"Hold {PTT_KEY.upper()} to record"],
    capture_output=True,
)


# ── Recording state ────────────────────────────────────────────────────────────
_recording      = False
_audio_chunks: list = []
_lock           = threading.Lock()
_record_thread  = None
_target_window  = ""
_press_ts       = 0.0
_release_ts     = 0.0


def _record_loop():
    import sounddevice as sd
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32") as stream:
        while _recording:
            chunk, _ = stream.read(1024)
            with _lock:
                _audio_chunks.append(chunk[:, 0].copy())


def _clipboard_copy(text: str) -> bool:
    if CLIP_TOOL == "xclip":
        proc = subprocess.run(["xclip", "-selection", "clipboard"],
                              input=text.encode(), capture_output=True)
    elif CLIP_TOOL == "xsel":
        proc = subprocess.run(["xsel", "--clipboard", "--input"],
                              input=text.encode(), capture_output=True)
    elif CLIP_TOOL == "wl-copy":
        proc = subprocess.run(["wl-copy"], input=text.encode(), capture_output=True)
    else:
        return False
    if proc.returncode != 0:
        print(f"[parakeet] clipboard error: {proc.stderr.decode()}", flush=True)
    return proc.returncode == 0


def _paste() -> int:
    if _target_window:
        subprocess.run(["xdotool", "windowfocus", "--sync", _target_window],
                       capture_output=True)
    result = subprocess.run(
        ["xdotool", "key", "--clearmodifiers", PASTE_CMD],
        capture_output=True,
    )
    return result.returncode


def _transcribe_and_paste():
    import soundfile as sf

    with _lock:
        data = np.concatenate(_audio_chunks) if _audio_chunks else np.array([])

    if len(data) < SAMPLE_RATE * MIN_DURATION_SEC:
        print("[parakeet] Clip too short — ignored.", flush=True)
        _emit("skipped", reason="clip_too_short")
        return

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name
            sf.write(tmp_path, data, SAMPLE_RATE)

        import torch
        gpu_before   = torch.cuda.memory_allocated() / 1024**2 if torch.cuda.is_available() else 0
        gpu_reserved = torch.cuda.memory_reserved()  / 1024**2 if torch.cuda.is_available() else 0

        t0 = time.perf_counter()
        output = asr_model.transcribe([tmp_path])
        inference_s = time.perf_counter() - t0

        text = (output[0].text if hasattr(output[0], "text") else str(output[0])).strip()
        if not text:
            print("[parakeet] Empty transcription.", flush=True)
            _emit("skipped", reason="empty_transcription")
            return

        raw = text
        text = _apply_corrections(text)
        total_s = time.perf_counter() - _release_ts
        print(f"[parakeet] {text}  [{inference_s:.2f}s infer / {total_s:.2f}s total]", flush=True)

        _emit(
            "transcription_complete",
            inference_s=round(inference_s, 3), total_latency_s=round(total_s, 3),
            word_count=len(text.split()), char_count=len(text),
            corrections_applied=int(text != raw),
            gpu_mem_used_mb=round(gpu_before, 1),
            gpu_mem_reserved_mb=round(gpu_reserved, 1),
            text=text,
        )

        if not _clipboard_copy(text):
            return

        rc = _paste()
        _emit("paste_result", exit_code=rc)
        print(f"[parakeet] paste exit={rc}", flush=True)

    except Exception as exc:
        print(f"[parakeet] Error: {exc}", flush=True)
        _emit("error", stage="transcription", message=str(exc))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ── Key listener ───────────────────────────────────────────────────────────────
from pynput import keyboard

_PTT = getattr(keyboard.Key, PTT_KEY)


def on_press(key):
    global _recording, _record_thread, _target_window, _press_ts
    if key == _PTT and not _recording:
        _press_ts = time.perf_counter()
        r = subprocess.run(["xdotool", "getactivewindow"], capture_output=True, text=True)
        _target_window = r.stdout.strip()
        _recording = True
        with _lock:
            _audio_chunks.clear()
        _record_thread = threading.Thread(target=_record_loop, daemon=True)
        _record_thread.start()
        _emit("recording_start", window_id=_target_window)
        subprocess.run(
            ["notify-send", "-i", "audio-input-microphone", "-t", "60000",
             "Recording", f"Release {PTT_KEY.upper()} to transcribe"],
            capture_output=True,
        )


def on_release(key):
    global _recording, _release_ts
    if key == _PTT and _recording:
        _release_ts = time.perf_counter()
        _recording  = False
        duration_s  = _release_ts - _press_ts
        if _record_thread:
            _record_thread.join(timeout=3)
        _emit("recording_end", duration_s=round(duration_s, 3))
        subprocess.run(
            ["notify-send", "-i", "system-run", "-t", "4000",
             "Transcribing", "Parakeet is processing your audio…"],
            capture_output=True,
        )
        threading.Thread(target=_transcribe_and_paste, daemon=True).start()


print(f"[parakeet] Keyboard listener active.", flush=True)
with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
    listener.join()
