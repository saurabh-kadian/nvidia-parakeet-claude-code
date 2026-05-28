# parakeet-ptt

Push-to-talk voice dictation powered by NVIDIA's [Parakeet TDT 0.6B v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) — a state-of-the-art open-source ASR model running fully locally on your GPU.

Hold **F9** → speak → release → transcribed text is pasted directly into your focused window.

No API calls. No audio leaves your machine. ~3,000× real-time on a mid-range GPU.

---

## Requirements

| | |
|---|---|
| **OS** | Ubuntu 20.04+ or Debian-based Linux, X11 session |
| **GPU** | NVIDIA GPU with 4 GB+ VRAM |
| **Driver** | NVIDIA driver 520+ (CUDA 12.1 compatible) |
| **Disk** | ~6 GB for virtualenv + model weights |

---

## Two ways to install

| | GUI App | Script |
|---|---|---|
| Install | `sudo dpkg -i parakeet-ptt.deb` | `bash install.sh` |
| Configure | Settings window in the tray | Edit `listener.py` and `corrections.py` |
| Autostart | Tray app or `.desktop` autostart | Claude Code hook |
| Best for | Everyday use | Headless / server / CI |

---

## Option A — GUI App (recommended)

A system tray app that manages the listener, lets you edit the corrections dictionary, change the push-to-talk key, and pick where the model lives — all without touching a config file.

### 1. Build the package

```bash
git clone <repo>
cd parakeet
bash packaging/build_deb.sh
```

This produces `parakeet-ptt_1.0.0_amd64.deb` in the repo root.

### 2. Install

```bash
sudo dpkg -i parakeet-ptt_1.0.0_amd64.deb
sudo apt-get install -f          # resolves any missing dependencies
```

### 3. First run — setup wizard

```bash
parakeet-ptt
```

On first launch a setup wizard opens:

| Step | What happens |
|---|---|
| **Virtualenv** | Browse to an existing venv or let the wizard create one at `~/.local/share/parakeet-ptt/env/` |
| **Model location** | Browse to an existing model download or choose where to save it (~2.4 GB) |
| **Install deps** | PyTorch + NeMo ASR installed into the venv (skipped if already present) |
| **Download model** | Parakeet TDT 0.6B v3 downloaded from HuggingFace (skipped if already present) |

You can cancel at any time. On subsequent launches the wizard is skipped and the tray icon appears immediately.

### 4. Usage

| Action | Result |
|---|---|
| Hold **F9** | Mic starts recording |
| Release **F9** | Audio transcribed → text pasted into focused window |
| **Tray icon → Settings** | Edit corrections dictionary, change PTT key, change paste method |
| **Tray icon → Stats** | View latency, word count, GPU memory, paste success rate |
| **Tray icon → Re-run Setup Wizard** | Change venv or model location, re-download |
| **Tray icon → Restart Listener** | Pick up config changes immediately |

> [!NOTE]
> **First transcription may not paste automatically.** After the listener starts, the very first recording sometimes lands in the clipboard but does not get pasted into your window — paste it manually with **Ctrl+Shift+V** (or your terminal's paste shortcut). Every recording after that works without any manual step. This is a one-time `xdotool` warm-up quirk and does not recur until the next time the listener process starts.

### 5. Autostart with GNOME

```bash
cp data/parakeet-ptt.desktop ~/.config/autostart/
```

The app will start automatically when you log in.

### 6. Autostart with Claude Code

Add to `~/.claude/settings.json` (merge into any existing `hooks` block):

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "parakeet-ptt &",
            "async": true,
            "statusMessage": "Starting Parakeet PTT..."
          }
        ]
      }
    ]
  }
}
```

---

## Option B — Script (headless / no GUI)

The original shell-script approach. No GTK, no tray — just the listener running in the background. Ideal for headless setups, SSH sessions with X forwarding, or if you prefer editing config files directly.

### 1. Install

```bash
git clone <repo>
cd parakeet
bash install.sh
```

The script handles everything:

- Detects your CUDA version from the installed driver
- Installs Python 3.10, `xclip`, `xdotool`, and audio libraries via `apt`
- Creates a virtualenv at `parakeet/env/`
- Downloads Parakeet TDT 0.6B v3 weights into `parakeet/model_cache/` (~2.4 GB)
- Generates `start_listener.sh`

### 2. Start the listener

```bash
bash start_listener.sh
```

You'll see a live counter while the model loads (~20 s), then:

```
[parakeet] Ready — hold F9 to record.
```

### 3. Autostart with Claude Code

At the end of `install.sh`, the exact hook snippet is printed for you. Paste it into `~/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "[ -f /path/to/parakeet/start_listener.sh ] && /path/to/parakeet/start_listener.sh 2>/dev/null || true",
            "async": true,
            "statusMessage": "Starting Parakeet listener..."
          }
        ]
      }
    ]
  }
}
```

### 4. Manage the listener

```bash
# Check status
ps -p $(cat /tmp/parakeet_listener.pid)

# View live log
tail -f /tmp/parakeet_listener.log

# Stop
kill $(cat /tmp/parakeet_listener.pid)
```

---

## Customising the vocabulary (both modes)

### GUI App

Open **Tray → Settings → Dictionary**. Add, edit, remove, or reorder regex rules. Changes take effect on the next recording — no restart needed.

### Script

Edit `corrections.py` directly:

```python
CORRECTIONS = [
    (r'\bgemma\s+(?:4|four|for)\s*b\b', 'gemma:4b'),
    (r'\bdeep[\s-]seek\b',              'deepseek'),
    # add your own...
]
```

Each entry is `(regex_pattern, replacement)`, matched case-insensitively in order. Changes are picked up on the next recording without restarting.

---

## Changing the push-to-talk key

### GUI App

**Tray → Settings → Key Binding** — choose from a dropdown.

### Script

Edit `PTT_KEY` near the top of `listener.py`:

```python
PTT_KEY = "f9"          # default
PTT_KEY = "f10"
PTT_KEY = "scroll_lock"
PTT_KEY = "pause"
```

Must be a [pynput `keyboard.Key`](https://pynput.readthedocs.io/en/latest/keyboard.html#pynput.keyboard.Key) name (not a character key, or it will also type into your terminal). Restart the listener to apply.

---

## Changing the paste method

### GUI App

**Tray → Settings → System** — radio buttons for paste shortcut and clipboard tool.

### Script

Find the `── Paste shortcut ──` section in `listener.py`:

```python
# Ctrl+Shift+V  — gnome-terminal, xterm, alacritty, kitty (default)
# Ctrl+V        — VS Code integrated terminal
# Shift+Insert  — universal X11 fallback
# xdotool type  — types directly, no clipboard
```

For Wayland, switch the clipboard block from `xclip` to `wl-copy`.

---

## View usage stats

### GUI App

**Tray → Stats** — shows latency, word count, GPU memory, and paste success rate in a window.

### Script

```bash
# Full report
env/bin/python stats.py

# Live tail
env/bin/python stats.py --tail
```

---

## How it works

```
Key held
  └─ sounddevice captures mic at 16 kHz
Key released
  └─ audio saved to temp WAV
      └─ NeMo loads Parakeet TDT on GPU
          └─ corrections applied (regex post-processing)
              └─ xclip copies to clipboard
                  └─ xdotool focuses original window + pastes
```

The listener runs as a background process. Logs go to `/tmp/parakeet_listener.log`.

---

## Repository layout

```
parakeet/
│
│  ── GUI app ──────────────────────────────────────────────
├── parakeet_ptt/
│   ├── main.py          entry point; wizard on first run, tray otherwise
│   ├── tray.py          AppIndicator3 system tray + listener lifecycle
│   ├── wizard.py        first-run setup wizard (venv, model, install)
│   ├── settings_win.py  settings window (dictionary, key binding, system)
│   ├── stats_win.py     stats popup
│   ├── config.py        config r/w, path constants
│   ├── listener.py      push-to-talk daemon (reads JSON config)
│   ├── telemetry.py     event logger
│   └── stats.py         report generator
│
│  ── Script / headless ─────────────────────────────────────
├── listener.py          push-to-talk daemon (standalone, reads corrections.py)
├── corrections.py       vocabulary corrections (edit this file)
├── telemetry.py         event logger
├── stats.py             CLI stats report
├── install.sh           one-shot setup script
└── start_listener.sh    generated by install.sh — launches the daemon
│
│  ── Packaging ─────────────────────────────────────────────
├── packaging/
│   ├── build_deb.sh     builds parakeet-ptt_*.deb
│   └── debian/          dpkg control files (control, postinst, prerm)
├── data/
│   ├── icons/           bundled tray icon (SVG)
│   └── parakeet-ptt.desktop
│
├── env/                 virtualenv (gitignored)
└── model_cache/         model weights (gitignored)
```

---

## Why NeMo and not Hugging Face Transformers?

The official `nvidia/parakeet-tdt-0.6b-v3` weights ship in NeMo's native checkpoint format. The TDT decoder — which gives accurate word-level timestamps and handles noisy/long-form audio better than CTC — is not yet in the stable Transformers release. NeMo is the only way to run it with the official weights.

If you want to avoid NeMo, swap in `nvidia/parakeet-ctc-0.6b` with standard `transformers` — accuracy is comparable for clean audio, and no NeMo install is needed.

---

## Troubleshooting

**Model loads but no audio is recorded**
- Check your default mic: `arecord -l`
- Set the correct device index: `sd.InputStream(device=N, ...)` in `listener.py`

**Paste does not land in the focused window**
- Verify `xdotool` is installed: `which xdotool`
- Try the `shift+Insert` fallback (works in all X11 terminals)
- On Wayland: switch clipboard block to `wl-copy` in Settings or `listener.py`

**`pynput` fails to listen for key events**
- On some systems pynput needs `/dev/input` access. Run once with `sudo` to verify, then add your user to the `input` group:
  ```bash
  sudo usermod -aG input $USER   # logout required
  ```

**NeMo install fails**
- Ensure Python 3.10 is active: `env/bin/python --version`
- Check the install log: `cat install.log`
- Try: `pip install "nemo_toolkit[asr]" --no-deps` then install missing deps manually

**Tray icon not visible (GNOME)**
- Enable the AppIndicator extension:
  ```bash
  sudo apt install gnome-shell-extension-appindicator
  gnome-extensions enable ubuntu-appindicators@ubuntu.com
  ```
  Then log out and back in.

---

## License

Model weights: [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) (NVIDIA)  
This repo: MIT

---

## Code and Readme courtesy ClaudeCode
