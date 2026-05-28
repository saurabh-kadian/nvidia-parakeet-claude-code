"""
Parakeet PTT — Windows push-to-talk daemon.

Self-contained: reads config/corrections from JSON, no package imports needed.
Launch via:
    %LOCALAPPDATA%\\parakeet-ptt\\env\\Scripts\\python.exe listener.py

Windows-specific substitutions vs the Linux version:
  - pyperclip for clipboard  (replaces xclip)
  - pynput keyboard sim for paste  (replaces xdotool)
  - win32gui for window focus  (replaces xdotool getactivewindow)
  - plyer for notifications  (replaces notify-send)

ASR is identical to Linux: NVIDIA Parakeet TDT 0.6B v3 via NeMo (CUDA).
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

# ── Config paths ───────────────────────────────────────────────────────────────
_APPDATA      = Path(os.environ.get("APPDATA",      Path.home() / "AppData" / "Roaming"))
_LOCALAPPDATA = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
_CONFIG_DIR   = _APPDATA      / "parakeet-ptt"
_DATA_DIR     = _LOCALAPPDATA / "parakeet-ptt"
_TEL_FILE     = _DATA_DIR / "telemetry.jsonl"
_CONFIG_FILE  = _CONFIG_DIR / "config.json"
_CORR_FILE    = _CONFIG_DIR / "corrections.json"
_PID_FILE     = _DATA_DIR / "listener.pid"
_LOG_FILE     = _DATA_DIR / "listener.log"

SAMPLE_RATE      = 16000
MIN_DURATION_SEC = 0.3


def _load_config() -> dict:
    defaults = {
        "ptt_key": "f9",
        "paste_method": "ctrl+v",
        "model_cache": str(_DATA_DIR / "model_cache"),
        "venv_dir":    str(_DATA_DIR / "env"),
    }
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


cfg          = _load_config()
PTT_KEY      = cfg["ptt_key"]
PASTE_METHOD = cfg["paste_method"]
_MODEL_CACHE = Path(cfg.get("model_cache", str(_DATA_DIR / "model_cache")))

os.environ.setdefault("HF_HOME",    str(_MODEL_CACHE / "huggingface"))
os.environ.setdefault("TORCH_HOME", str(_MODEL_CACHE / "torch"))


# ── Telemetry ──────────────────────────────────────────────────────────────────
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
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _PID_FILE.write_text(str(os.getpid()))


def _remove_pid():
    try:
        _PID_FILE.unlink()
    except FileNotFoundError:
        pass


atexit.register(_remove_pid)
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
_write_pid()


# ── Notifications (best-effort) ────────────────────────────────────────────────
def _notify(title: str, body: str):
    try:
        from plyer import notification
        notification.notify(title=title, message=body, app_name="Parakeet PTT", timeout=4)
    except Exception:
        pass


# ── Model loading (Parakeet TDT via NeMo — same as Linux) ─────────────────────
MODEL_NAME = "nvidia/parakeet-tdt-0.6b-v3"

print("[parakeet] Loading model…", flush=True)
import nemo.collections.asr as nemo_asr

asr_model = nemo_asr.models.ASRModel.from_pretrained(MODEL_NAME)
asr_model.eval()
print(f"[parakeet] Ready — hold {PTT_KEY.upper()} to record.", flush=True)
_emit("session_start")
_notify("Parakeet ready", f"Hold {PTT_KEY.upper()} to record")


# ── Recording state ────────────────────────────────────────────────────────────
_recording     = False
_audio_chunks: list = []
_lock          = threading.Lock()
_record_thread = None
_active_window = ""
_press_ts      = 0.0
_release_ts    = 0.0


def _record_loop():
    import sounddevice as sd
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32") as stream:
        while _recording:
            chunk, _ = stream.read(1024)
            with _lock:
                _audio_chunks.append(chunk[:, 0].copy())


def _get_active_window() -> str:
    """Return the title of the currently focused window."""
    try:
        import win32gui
        return str(win32gui.GetForegroundWindow())
    except ImportError:
        return ""


def _focus_window(hwnd_str: str):
    """Re-focus the window that was active when the key was pressed."""
    if not hwnd_str:
        return
    try:
        import win32gui
        hwnd = int(hwnd_str)
        if win32gui.IsWindow(hwnd):
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.05)
    except Exception:
        pass


def _paste(method: str):
    """Simulate the paste keyboard shortcut."""
    from pynput.keyboard import Controller, Key
    kb = Controller()
    if method == "shift+insert":
        with kb.pressed(Key.shift):
            kb.press(Key.insert)
            kb.release(Key.insert)
    else:  # ctrl+v (default)
        with kb.pressed(Key.ctrl):
            kb.press("v")
            kb.release("v")


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

        t0 = time.perf_counter()
        output = asr_model.transcribe([tmp_path])
        text = (output[0].text if hasattr(output[0], "text") else str(output[0])).strip()
        inference_s = time.perf_counter() - t0

        if not text:
            print("[parakeet] Empty transcription.", flush=True)
            _emit("skipped", reason="empty_transcription")
            return

        raw = text
        text = _apply_corrections(text)
        total_s = time.perf_counter() - _release_ts
        print(f"[parakeet] {text}  [{inference_s:.2f}s / {total_s:.2f}s]", flush=True)

        _emit(
            "transcription_complete",
            inference_s=round(inference_s, 3), total_latency_s=round(total_s, 3),
            word_count=len(text.split()), char_count=len(text),
            corrections_applied=int(text != raw),
            gpu_mem_used_mb=0, gpu_mem_reserved_mb=0,
            text=text,
        )

        # Copy to clipboard
        import pyperclip
        pyperclip.copy(text)

        # Restore focus and paste
        _focus_window(_active_window)
        _paste(PASTE_METHOD)
        _emit("paste_result", exit_code=0)
        print("[parakeet] pasted.", flush=True)

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
    global _recording, _record_thread, _active_window, _press_ts
    if key == _PTT and not _recording:
        _press_ts      = time.perf_counter()
        _active_window = _get_active_window()
        _recording     = True
        with _lock:
            _audio_chunks.clear()
        _record_thread = threading.Thread(target=_record_loop, daemon=True)
        _record_thread.start()
        _emit("recording_start", window=_active_window)
        _notify("Recording", f"Release {PTT_KEY.upper()} to transcribe")


def on_release(key):
    global _recording, _release_ts
    if key == _PTT and _recording:
        _release_ts = time.perf_counter()
        _recording  = False
        duration_s  = _release_ts - _press_ts
        if _record_thread:
            _record_thread.join(timeout=3)
        _emit("recording_end", duration_s=round(duration_s, 3))
        _notify("Transcribing", "Parakeet is processing your audio…")
        threading.Thread(target=_transcribe_and_paste, daemon=True).start()


print(f"[parakeet] Listening. Hold {PTT_KEY.upper()} to record.", flush=True)
with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
    listener.join()
