#!/usr/bin/env python3
"""
Parakeet TDT push-to-talk daemon.
Hold the '|' (pipe) key to record mic audio.
Release to transcribe via Parakeet TDT 0.6B v3 and paste into the focused window.
"""

import os
import sys
import signal
import tempfile
import threading
import subprocess
import atexit
import numpy as np

PID_FILE = "/tmp/parakeet_listener.pid"
SAMPLE_RATE = 16000          # Parakeet expects 16 kHz mono
MIN_DURATION_SEC = 0.3       # ignore accidental taps shorter than this
MODEL_NAME = "nvidia/parakeet-tdt-0.6b-v3"

# Push-to-talk key. Must be a pynput keyboard.Key constant (not a character)
# so it doesn't also type into the focused window. F9 is the default.
# Other options: keyboard.Key.f10, keyboard.Key.scroll_lock, keyboard.Key.pause
PTT_KEY = "f9"

# Resolve cache dirs relative to this script's location so the listener
# finds weights even when launched from a different working directory.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_CACHE_DIR = os.path.join(_SCRIPT_DIR, "model_cache")
os.environ.setdefault("HF_HOME", os.path.join(_CACHE_DIR, "huggingface"))
os.environ.setdefault("NEMO_CACHE_DIR", os.path.join(_CACHE_DIR, "nemo"))
os.environ.setdefault("TORCH_HOME", os.path.join(_CACHE_DIR, "torch"))


# ── PID file management ────────────────────────────────────────────────────────

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

print("[parakeet] Loading model — this takes ~10-20 s on first run...", flush=True)
import nemo.collections.asr as nemo_asr

asr_model = nemo_asr.models.ASRModel.from_pretrained(MODEL_NAME)
asr_model.eval()
print(f"[parakeet] Model ready. Hold {PTT_KEY.upper()} to record.", flush=True)
subprocess.run(
    ["notify-send", "-i", "audio-input-microphone", "Parakeet ready", f"Hold {PTT_KEY.upper()} to record"],
    capture_output=True,  # silently skip if notify-send is not installed
)


# ── Recording state ────────────────────────────────────────────────────────────

_recording = False
_audio_chunks: list = []
_lock = threading.Lock()
_record_thread: threading.Thread | None = None
_target_window: str = ""  # X11 window ID captured at press time, used for paste


def _record_loop():
    import sounddevice as sd
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32") as stream:
        while _recording:
            chunk, _ = stream.read(1024)
            with _lock:
                _audio_chunks.append(chunk[:, 0].copy())


def _transcribe_and_paste():
    import soundfile as sf

    with _lock:
        data = np.concatenate(_audio_chunks) if _audio_chunks else np.array([])

    if len(data) < SAMPLE_RATE * MIN_DURATION_SEC:
        print("[parakeet] Clip too short — ignored.", flush=True)
        return

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name
            sf.write(tmp_path, data, SAMPLE_RATE)

        output = asr_model.transcribe([tmp_path])
        # NeMo TDT output: list of Hypothesis objects with .text attribute
        text = (output[0].text if hasattr(output[0], "text") else str(output[0])).strip()

        if not text:
            print("[parakeet] Empty transcription.", flush=True)
            return

        print(f"[parakeet] Transcribed: {text}", flush=True)

        # ── Clipboard + paste ──────────────────────────────────────────────────
        # Choose the clipboard tool that matches your system, then choose the
        # paste shortcut that matches your terminal emulator. Only one of each
        # block should be active at a time.

        # --- Clipboard: xclip (default, most common on Ubuntu/Debian) ---
        proc = subprocess.run(
            ["xclip", "-selection", "clipboard"],
            input=text.encode(),
            capture_output=True,
        )
        if proc.returncode != 0:
            print(f"[parakeet] xclip error: {proc.stderr.decode()}", flush=True)
            return

        # --- Clipboard: xsel (alternative to xclip — install with: sudo apt install xsel) ---
        # subprocess.run(["xsel", "--clipboard", "--input"], input=text.encode(), check=True)

        # --- Clipboard: wl-copy (Wayland sessions — install with: sudo apt install wl-clipboard) ---
        # subprocess.run(["wl-copy"], input=text.encode(), check=True)

        # ── Paste shortcut ─────────────────────────────────────────────────────
        # Pick the line that matches your terminal emulator.

        # Re-focus the window that was active when F9 was pressed, then paste.
        # windowfocus --sync blocks until focus is confirmed before sending the key.
        if _target_window:
            subprocess.run(["xdotool", "windowfocus", "--sync", _target_window], capture_output=True)

        # Ctrl+Shift+V — standard for most Linux terminals (gnome-terminal, xterm, alacritty, kitty)
        result = subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+shift+v"], capture_output=True)
        print(f"[parakeet] paste exit={result.returncode}", flush=True)

        # Ctrl+V — works in some terminals (Windows-style, VS Code integrated terminal)
        # subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+v"])

        # Shift+Insert — works universally in almost all X11 terminals as a fallback
        # subprocess.run(["xdotool", "key", "--clearmodifiers", "shift+Insert"])

        # Type directly — bypasses clipboard entirely; safe for plain ASCII but
        # may mangle special characters (quotes, brackets, etc.).
        # --delay 12 is 12ms between keystrokes, not seconds — prevents terminal buffer overflow.
        # subprocess.run(["xdotool", "type", "--clearmodifiers", "--delay", "12", "--", text])

    except Exception as exc:
        print(f"[parakeet] Error during transcription: {exc}", flush=True)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ── Key listener ───────────────────────────────────────────────────────────────

from pynput import keyboard


_PTT = getattr(keyboard.Key, PTT_KEY)

def on_press(key):
    global _recording, _record_thread, _target_window
    if key == _PTT and not _recording:
        # Capture the focused window NOW so paste targets it even after a delay
        result = subprocess.run(["xdotool", "getactivewindow"], capture_output=True, text=True)
        _target_window = result.stdout.strip()
        _recording = True
        with _lock:
            _audio_chunks.clear()
        _record_thread = threading.Thread(target=_record_loop, daemon=True)
        _record_thread.start()
        print(f"[parakeet] Recording... (window {_target_window})", flush=True)
        subprocess.run(
            ["notify-send", "-i", "audio-input-microphone", "-t", "60000",
             "🎙 Recording", f"Release {PTT_KEY.upper()} to transcribe"],
            capture_output=True,
        )


def on_release(key):
    global _recording
    if key == _PTT and _recording:
        _recording = False
        if _record_thread:
            _record_thread.join(timeout=3)
        subprocess.run(
            ["notify-send", "-i", "system-run", "-t", "4000",
             "⏳ Transcribing", "Parakeet is processing your audio..."],
            capture_output=True,
        )
        threading.Thread(target=_transcribe_and_paste, daemon=True).start()


print(f"[parakeet] Keyboard listener active. Hold {PTT_KEY.upper()} to record.", flush=True)
with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
    listener.join()
