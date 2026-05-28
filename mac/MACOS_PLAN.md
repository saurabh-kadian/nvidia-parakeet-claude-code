# macOS Port — Implementation Plan

## Overview

The Linux version runs NVIDIA Parakeet TDT 0.6B v3 on CUDA via NeMo. Macs have no
NVIDIA GPU support, so the macOS port swaps the ASR backend for
[mlx-whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper) (Apple
Silicon) or [whisper.cpp](https://github.com/ggerganov/whisper.cpp) (Intel + Apple
Silicon fallback), and replaces the Linux-specific UI/system layer with macOS equivalents.

Everything else — corrections, config, telemetry, stats, the overall architecture — stays
the same.

---

## What changes, what stays the same

| Layer | Linux | macOS |
|---|---|---|
| ASR model | Parakeet TDT 0.6B v3 via NeMo (CUDA) | Whisper via mlx-whisper (MPS) or whisper.cpp |
| GUI framework | GTK3 + AppIndicator3 | rumps (menu bar) + PyQt5 (settings window) |
| Clipboard | `xclip` / `xsel` / `wl-copy` | `pbcopy` |
| Paste | `xdotool key ctrl+shift+v` | `pynput` keyboard simulation (`Cmd+V`) |
| Window focus | `xdotool getactivewindow` + `windowfocus` | `NSWorkspace` via PyObjC or `osascript` |
| Key listener | `pynput` | `pynput` (same, but needs Accessibility permission) |
| Audio capture | `sounddevice` (PortAudio) | `sounddevice` (PortAudio, works on Mac) |
| Packaging | `dpkg` `.deb` | `py2app` `.app` bundle |
| Notifications | `notify-send` | `rumps.notification()` |
| Config / corrections / telemetry | JSON files in `~/.config/parakeet-ptt/` | Same paths (XDG dirs work on Mac) |
| Stats | Python CLI + GUI window | Same |

---

## Repository structure (proposed)

```
parakeet/
├── parakeet_ptt/          ← Linux GUI app (current)
├── parakeet_mac/          ← macOS app (new)
│   ├── __init__.py
│   ├── main.py            entry point
│   ├── tray.py            rumps menu bar app
│   ├── settings_win.py    PyQt5 settings window
│   ├── wizard.py          first-run setup wizard (PyQt5)
│   ├── stats_win.py       PyQt5 stats window
│   ├── listener.py        push-to-talk daemon (macOS system calls)
│   └── asr/
│       ├── mlx_backend.py   mlx-whisper (Apple Silicon)
│       └── cpp_backend.py   whisper.cpp (Intel fallback)
├── parakeet_shared/       ← shared between both platforms (new)
│   ├── config.py          paths, defaults, r/w helpers
│   ├── corrections.py     apply corrections
│   ├── telemetry.py       event logger
│   └── stats.py           report generator
├── parakeet_ptt/          ← Linux app (refactored to import parakeet_shared)
├── listener.py            ← script mode (Linux, unchanged)
├── corrections.py         ← script mode (unchanged)
├── install.sh             ← Linux script install (unchanged)
└── packaging/
    ├── build_deb.sh       Linux .deb builder
    └── build_mac.sh       macOS .app builder (new)
```

---

## Phase 1 — Shared core

Extract `config.py`, `telemetry.py`, `stats.py`, and corrections logic from
`parakeet_ptt/` into a `parakeet_shared/` package that both the Linux and macOS
apps import. This avoids duplication and means bug fixes apply to both platforms.

**Effort:** ~2 hours. Mostly moving files and updating imports.

---

## Phase 2 — ASR backend

### Primary: mlx-whisper (Apple Silicon — M1/M2/M3/M4)

```bash
pip install mlx-whisper
```

Model: `mlx-community/whisper-large-v3-turbo` — best accuracy/speed balance on
Apple Silicon. Runs entirely on the Neural Engine / GPU via Apple's MLX framework.
Expected latency: similar to or faster than Parakeet on a mid-range NVIDIA GPU.

```python
# asr/mlx_backend.py
import mlx_whisper

def transcribe(wav_path: str) -> str:
    result = mlx_whisper.transcribe(wav_path, path_or_hf_repo="mlx-community/whisper-large-v3-turbo")
    return result["text"].strip()
```

### Fallback: whisper.cpp (Intel Macs)

Pre-built binary from [whisper.cpp releases](https://github.com/ggerganov/whisper.cpp/releases).
Called as a subprocess — no Python bindings needed.

```python
# asr/cpp_backend.py
import subprocess

WHISPER_BIN   = "~/.local/share/parakeet-ptt/whisper.cpp/main"
WHISPER_MODEL = "~/.local/share/parakeet-ptt/models/ggml-large-v3-turbo.bin"

def transcribe(wav_path: str) -> str:
    result = subprocess.run(
        [WHISPER_BIN, "-m", WHISPER_MODEL, "-f", wav_path, "--output-txt", "-"],
        capture_output=True, text=True,
    )
    return result.stdout.strip()
```

### Backend selection (auto-detect at runtime)

```python
import platform

def get_backend():
    if platform.processor() == "arm":   # Apple Silicon
        from .mlx_backend import transcribe
    else:                               # Intel
        from .cpp_backend import transcribe
    return transcribe
```

---

## Phase 3 — Listener (macOS system calls)

The listener logic is identical to Linux. Only the system-call layer changes:

### Clipboard

```python
# Linux
subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode())

# macOS
subprocess.run(["pbcopy"], input=text.encode())
```

### Paste

```python
# Linux
subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+shift+v"])

# macOS — pynput keyboard simulation
from pynput.keyboard import Controller, Key
kb = Controller()
with kb.pressed(Key.cmd):
    kb.press("v"); kb.release("v")
```

### Window focus

```python
# macOS — bring the previously active app back to front via osascript
import subprocess

def get_active_app() -> str:
    r = subprocess.run(
        ["osascript", "-e", 'tell application "System Events" to get name of first process whose frontmost is true'],
        capture_output=True, text=True,
    )
    return r.stdout.strip()

def focus_app(app_name: str):
    subprocess.run(["osascript", "-e", f'tell application "{app_name}" to activate'])
```

### Notifications

```python
# Linux
subprocess.run(["notify-send", "Recording", "Release to transcribe"])

# macOS — via rumps
import rumps
rumps.notification("Parakeet PTT", "Recording", "Release to transcribe")
```

---

## Phase 4 — Menu bar app (rumps)

[`rumps`](https://github.com/jaredks/rumps) is a minimal Python library for macOS
menu bar apps. It replaces GTK + AppIndicator3.

```bash
pip install rumps
```

```python
# tray.py
import rumps

class ParakeetApp(rumps.App):
    def __init__(self):
        super().__init__("Parakeet PTT", icon="data/icons/parakeet-ptt.png", quit_button=None)
        self.menu = [
            rumps.MenuItem("● Loading…", callback=None),
            None,  # separator
            rumps.MenuItem("Settings…",           callback=self.open_settings),
            rumps.MenuItem("Stats…",              callback=self.open_stats),
            rumps.MenuItem("View Log",            callback=self.open_log),
            None,
            rumps.MenuItem("Restart Listener",    callback=self.restart_listener),
            rumps.MenuItem("Re-run Setup Wizard", callback=self.open_wizard),
            None,
            rumps.MenuItem("Quit",                callback=rumps.quit_application),
        ]
        self._start_listener()

    @rumps.clicked("Settings…")
    def open_settings(self, _):
        # Launch PyQt5 settings window in a thread
        ...
```

`rumps` runs its own event loop, so PyQt5 windows need to run in a separate thread
or process. A simple approach: launch the settings window as a subprocess
(`python -m parakeet_mac.settings_win`).

---

## Phase 5 — Settings / wizard UI (PyQt5)

PyQt5 is cross-platform and well-supported on macOS. Replace GTK widgets 1-for-1:

| GTK widget | PyQt5 equivalent |
|---|---|
| `Gtk.Window` | `QMainWindow` / `QDialog` |
| `Gtk.Notebook` | `QTabWidget` |
| `Gtk.TreeView` + `Gtk.ListStore` | `QTableWidget` |
| `Gtk.ComboBoxText` | `QComboBox` |
| `Gtk.RadioButton` | `QRadioButton` |
| `Gtk.FileChooserDialog` | `QFileDialog.getExistingDirectory()` |
| `Gtk.ProgressBar` | `QProgressBar` |
| `Gtk.Assistant` | `QWizard` |

```bash
pip install PyQt5
```

---

## Phase 6 — Permissions (macOS-specific)

macOS requires explicit user permission for microphone and accessibility access.
The setup wizard needs to:

1. **Microphone** — trigger a permission request on first audio capture.
   `sounddevice` will prompt automatically on first use. If denied, show a dialog
   directing the user to System Settings → Privacy → Microphone.

2. **Accessibility** (for `pynput` key listening + keyboard simulation) — must be
   granted manually. The wizard should open the correct pane automatically:

   ```python
   import subprocess
   subprocess.run(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"])
   ```

3. **Input Monitoring** (for global key listener via `pynput`) — separate from
   Accessibility on macOS 10.15+. Same approach: open System Settings and guide
   the user.

---

## Phase 7 — Packaging

### `.app` bundle with `py2app`

```bash
pip install py2app
python setup_mac.py py2app
```

`setup_mac.py`:
```python
from setuptools import setup

APP      = ["parakeet_mac/main.py"]
OPTIONS  = {
    "iconfile": "data/icons/parakeet-ptt.icns",
    "packages": ["parakeet_mac", "parakeet_shared", "rumps", "PyQt5", "pynput", "sounddevice"],
    "plist": {
        "CFBundleName":        "Parakeet PTT",
        "CFBundleVersion":     "1.0.0",
        "LSUIElement":         True,   # hide from Dock (menu bar only app)
        "NSMicrophoneUsageDescription": "Parakeet PTT records audio for transcription.",
        "NSAppleEventsUsageDescription": "Parakeet PTT uses AppleScript to focus windows for paste.",
    },
}

setup(app=APP, options={"py2app": OPTIONS})
```

### Distribution without notarization (development / personal use)

Users right-click → Open → Open (bypasses Gatekeeper once). Document this clearly.

### Distribution with notarization (public release)

Requires Apple Developer account ($99/year). Steps:
1. Code-sign with Developer ID certificate
2. Submit to Apple notarization service (`xcrun notarytool`)
3. Staple the notarization ticket to the `.app`

This is a one-time setup per release. GitHub Actions can automate it.

---

## Phase 8 — Homebrew formula (optional, for wide distribution)

```ruby
class ParakeetPtt < Formula
  desc "Push-to-talk voice dictation powered by Whisper, running locally"
  homepage "https://github.com/your-repo/parakeet"
  url "https://github.com/your-repo/parakeet/releases/download/v1.0.0/parakeet-ptt-macos.tar.gz"
  sha256 "..."

  depends_on "python@3.11"
  depends_on :macos

  def install
    # install steps
  end
end
```

---

## Implementation order

1. **Extract `parakeet_shared/`** — decouple shared code from Linux-specific imports (Phase 1)
2. **Build `listener.py` for macOS** — wire up pbcopy, pynput paste, osascript focus (Phase 3)
3. **Integrate mlx-whisper backend** — get transcription working in a script first (Phase 2)
4. **Menu bar app with rumps** — minimal tray, hardcoded F9 key, no settings UI yet (Phase 4)
5. **Port settings/wizard to PyQt5** — corrections table, key picker, path pickers (Phase 5)
6. **Permissions wizard** — microphone + accessibility onboarding (Phase 6)
7. **py2app bundle** — test that it runs without a Python install (Phase 7)
8. **Homebrew formula** — only after the above is solid (Phase 8)

---

## Open questions (to resolve with a Mac to test)

- Does `pynput` key simulation reliably paste into all major macOS terminal emulators
  (Terminal.app, iTerm2, Warp, VS Code)?
- Does `rumps` play nicely with PyQt5 windows opened from menu callbacks? Or does
  the PyQt5 event loop conflict with rumps' NSApplication loop? (Likely need a
  subprocess approach.)
- What is the actual latency of `mlx-whisper large-v3-turbo` on M-series chips vs
  Parakeet TDT on an RTX 2070?
- Does `whisper.cpp` on Intel Mac hit acceptable latency for interactive PTT use?
- Is py2app the right bundler, or is PyInstaller more reliable for this dependency set?

---

## Estimated effort

| Phase | Effort |
|---|---|
| Phase 1 — shared core | ~2 h |
| Phase 2 — ASR backend | ~3 h |
| Phase 3 — listener (macOS calls) | ~2 h |
| Phase 4 — rumps menu bar | ~3 h |
| Phase 5 — PyQt5 settings/wizard | ~6 h |
| Phase 6 — permissions | ~2 h |
| Phase 7 — py2app bundle | ~3 h |
| Phase 8 — Homebrew (optional) | ~2 h |
| **Total** | **~23 h** |

Most of that time is in the PyQt5 port (Phase 5) and bundling/permissions (Phases 6–7).
The actual push-to-talk logic (Phase 3) is straightforward.
