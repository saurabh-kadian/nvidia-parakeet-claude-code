# parakeet-ptt

Push-to-talk voice dictation powered by NVIDIA's [Parakeet TDT 0.6B v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) — a state-of-the-art open-source ASR model running fully locally on your GPU.

Hold **F9** → speak → release → transcribed text is pasted directly into your focused window.

No API calls. No audio leaves your machine. ~3,000× real-time on a mid-range GPU.

---

## Repository layout

```
parakeet/
├── linux/
│   ├── gui/                    GTK3 tray app (Ubuntu / Debian)
│   │   ├── parakeet_ptt/       Python package
│   │   │   ├── main.py         entry point
│   │   │   ├── tray.py         AppIndicator3 system tray
│   │   │   ├── wizard.py       first-run setup wizard
│   │   │   ├── settings_win.py corrections, key binding, system settings
│   │   │   ├── stats_win.py    usage stats popup
│   │   │   ├── listener.py     push-to-talk daemon
│   │   │   ├── config.py       config r/w, path constants
│   │   │   ├── telemetry.py    event logger
│   │   │   └── stats.py        report generator
│   │   ├── data/
│   │   │   ├── icons/          tray icon (SVG)
│   │   │   └── parakeet-ptt.desktop
│   │   └── packaging/
│   │       ├── build_deb.sh    builds .deb package
│   │       └── debian/         dpkg control files
│   └── terminal/               Headless / script mode
│       ├── listener.py         push-to-talk daemon (standalone)
│       ├── corrections.py      vocabulary corrections (edit this)
│       ├── telemetry.py        event logger
│       ├── stats.py            CLI stats report
│       ├── install.sh          one-shot setup script
│       ├── start_listener.sh   generated launcher
│       └── INSTALL.md          detailed setup & troubleshooting
├── windows/                    Windows GUI app (PyQt5 + pystray)
│   ├── parakeet_ptt/           same structure as linux/gui/parakeet_ptt/
│   ├── data/icons/
│   ├── packaging/
│   │   └── build_exe.ps1       PyInstaller .exe builder
│   └── requirements.txt
├── mac/
│   └── MACOS_PLAN.md           implementation plan (not yet built)
├── README.md
└── LICENSE
```

---

## Requirements

| | |
|---|---|
| **OS** | Ubuntu 20.04+ / Debian-based Linux (GUI), Windows 10+ (Windows app) |
| **GPU** | NVIDIA GPU with 4 GB+ VRAM |
| **Driver** | NVIDIA driver 520+ (CUDA 12.1 compatible) |
| **Disk** | ~6 GB for virtualenv + model weights |
| **Display** | X11 session (Linux GUI); Wayland requires substituting `wl-copy` |

---

## Linux — GUI App (recommended)

A system tray app that manages the listener, lets you edit the corrections dictionary, change the push-to-talk key, and pick where the model lives — without touching a config file.

### Install

```bash
git clone <repo>
cd parakeet
bash linux/gui/packaging/build_deb.sh
sudo dpkg -i linux/gui/parakeet-ptt_1.0.0_amd64.deb
sudo apt-get install -f          # resolve any missing deps
```

### First run — setup wizard

```bash
parakeet-ptt
```

On first launch a setup wizard opens:

| Step | What happens |
|---|---|
| **Virtualenv** | Browse to an existing venv or create one at `~/.local/share/parakeet-ptt/env/` |
| **Model location** | Browse to an existing download or choose where to save (~2.4 GB) |
| **Install deps** | PyTorch + NeMo ASR installed into the venv (skipped if already present) |
| **Download model** | Parakeet TDT 0.6B v3 downloaded from HuggingFace (skipped if already present) |

You can cancel at any time. Subsequent launches skip the wizard and go straight to the tray.

### Usage

| Action | Result |
|---|---|
| Hold **F9** | Mic starts recording |
| Release **F9** | Audio transcribed → text pasted into focused window |
| **Tray → Settings** | Edit corrections dictionary, change PTT key, paste method |
| **Tray → Stats** | Latency, word count, GPU memory, paste success rate |
| **Tray → Re-run Setup Wizard** | Change venv or model location |
| **Tray → Restart Listener** | Pick up config changes immediately |

> [!NOTE]
> **First transcription may not paste automatically.** After the listener starts, the very first recording sometimes lands in the clipboard but does not get pasted into your window — paste it manually with **Ctrl+Shift+V**. Every recording after that works without any manual step. This is a one-time `xdotool` warm-up quirk.

### Autostart with GNOME

```bash
cp linux/gui/data/parakeet-ptt.desktop ~/.config/autostart/
```

### Autostart with Claude Code

```json
{
  "hooks": {
    "SessionStart": [{
      "hooks": [{
        "type": "command",
        "command": "parakeet-ptt &",
        "async": true,
        "statusMessage": "Starting Parakeet PTT..."
      }]
    }]
  }
}
```

---

## Linux — Terminal / Headless

The original script-based approach — no GTK, no tray, just the listener running in the background. Ideal for SSH sessions, headless servers, or if you prefer editing config files directly.

### Install

```bash
cd parakeet
bash linux/terminal/install.sh
```

The script detects your CUDA version, installs system deps, creates a virtualenv at `linux/terminal/env/`, downloads the model weights (~2.4 GB), and generates `start_listener.sh`.

### Start

```bash
bash linux/terminal/start_listener.sh
```

```
[parakeet] Ready — hold F9 to record.
```

### Autostart with Claude Code

The exact hook snippet is printed at the end of `install.sh`. Paste it into `~/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [{
      "hooks": [{
        "type": "command",
        "command": "[ -f /path/to/linux/terminal/start_listener.sh ] && bash /path/to/linux/terminal/start_listener.sh 2>/dev/null || true",
        "async": true,
        "statusMessage": "Starting Parakeet listener..."
      }]
    }]
  }
}
```

### Manage the listener

```bash
# Check status
ps -p $(cat /tmp/parakeet_listener.pid)

# Live log
tail -f /tmp/parakeet_listener.log

# Stop
kill $(cat /tmp/parakeet_listener.pid)
```

---

## Windows

Same Parakeet TDT 0.6B v3 model, same accuracy. Replaces the Linux-specific layer (GTK, xclip, xdotool) with Windows equivalents (PyQt5, pystray, pyperclip, pynput + win32gui).

### Requirements

- Windows 10 or 11
- Python 3.10+ from [python.org](https://python.org)
- NVIDIA GPU with CUDA 12.1 support (driver 520+)

### Run from source

```bash
# In a Python 3.10+ environment:
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install -r windows/requirements.txt

python windows/parakeet_ptt/main.py
```

The setup wizard handles the NeMo install and model download on first run.

### Build a standalone `.exe`

```powershell
cd windows
powershell -ExecutionPolicy Bypass -File packaging\build_exe.ps1
# produces dist\Parakeet PTT.exe — no Python install required on target machine
```

---

## macOS

Not yet implemented. See [`mac/MACOS_PLAN.md`](mac/MACOS_PLAN.md) for the full implementation plan.

The port would use `mlx-whisper` (Apple Silicon) or `whisper.cpp` (Intel), `rumps` for the menu bar, and PyQt5 for settings windows. Estimated ~23 hours of work once a Mac is available for testing.

---

## Customising the vocabulary

### Linux GUI app

**Tray → Settings → Dictionary** — add, edit, remove, or reorder regex rules. Changes take effect on the next recording.

### Linux terminal / Windows

Edit `linux/terminal/corrections.py` (terminal) or `~/.config/parakeet-ptt/corrections.json` (GUI apps):

```python
# corrections.py
CORRECTIONS = [
    (r'\bgemma\s+(?:4|four|for)\s*b\b', 'gemma:4b'),
    (r'\bdeep[\s-]seek\b',              'deepseek'),
    # add your own...
]
```

Each entry is `(regex_pattern, replacement)`, matched case-insensitively in order. No restart needed.

---

## Changing the push-to-talk key

### GUI apps

**Tray → Settings → Key Binding** — dropdown, applies after listener restart.

### Terminal

Edit `PTT_KEY` near the top of `linux/terminal/listener.py`:

```python
PTT_KEY = "f9"          # default
PTT_KEY = "f10"
PTT_KEY = "scroll_lock"
PTT_KEY = "pause"
```

Must be a [pynput `keyboard.Key`](https://pynput.readthedocs.io/en/latest/keyboard.html#pynput.keyboard.Key) name. Restart the listener to apply.

---

## How it works

```
Key held
  └─ sounddevice captures mic at 16 kHz
Key released
  └─ audio saved to temp WAV
      └─ NeMo loads Parakeet TDT on GPU
          └─ corrections applied (regex post-processing)
              └─ text copied to clipboard
                  └─ focused window restored → paste shortcut sent
```

Logs go to `/tmp/parakeet_listener.log` (Linux) or `%LOCALAPPDATA%\parakeet-ptt\listener.log` (Windows).

---

## Troubleshooting

**Model loads but no audio is recorded**
Check your default mic: `arecord -l` (Linux) or Settings → Sound (Windows). Set the correct device index in `listener.py`: `sd.InputStream(device=N, ...)`.

**Paste does not land in the focused window**
- Linux: verify `xdotool` is installed. Try `Shift+Insert` fallback in Settings.
- Windows: verify `pywin32` is installed (`pip install pywin32`).
- Wayland: switch clipboard tool to `wl-copy` in **Tray → Settings → System**.

**`pynput` fails to listen for key events (Linux)**
Add your user to the `input` group:
```bash
sudo usermod -aG input $USER   # logout required
```

**NeMo install fails**
- Ensure Python 3.10 is active: `env/bin/python --version`
- Try: `pip install "nemo_toolkit[asr]" --no-deps` then install missing deps manually
- Check install log in the wizard's log view

**Tray icon not visible (GNOME)**
Enable the AppIndicator extension:
```bash
sudo apt install gnome-shell-extension-appindicator
gnome-extensions enable ubuntu-appindicators@ubuntu.com
```
Then log out and back in.

---

## Why NeMo and not Hugging Face Transformers?

The official `nvidia/parakeet-tdt-0.6b-v3` weights ship in NeMo's native checkpoint format. The TDT decoder — which gives accurate word-level timestamps and handles noisy audio better than CTC — is not yet in the stable Transformers release. NeMo is the only way to run it with the official weights.

If you want to avoid NeMo, `nvidia/parakeet-ctc-0.6b` works with standard `transformers` and has comparable accuracy for clean audio.

---

## License

Model weights: [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) (NVIDIA)  
This repo: MIT

---

## Code and Readme courtesy ClaudeCode
