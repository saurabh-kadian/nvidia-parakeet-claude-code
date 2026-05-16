# Parakeet Push-to-Talk for Claude Code

A push-to-talk voice dictation tool that uses NVIDIA's Parakeet TDT 0.6B v3 ASR model to transcribe speech and paste it directly into Claude Code (or any focused terminal window).

Hold `|` (pipe key) → speak → release → text appears in Claude Code.

## Requirements

- **OS**: Ubuntu 20.04+ (or Debian-based Linux)
- **GPU**: NVIDIA GPU with 4 GB+ VRAM (tested on RTX 2070 SUPER / 8 GB)
- **Driver**: NVIDIA driver 520+ (supports CUDA 12.1)
- **Display**: X11 session (Wayland requires substituting `wl-copy` — see customization below)
- **Disk**: ~6 GB free for virtualenv + model weights

## Install

Run the install script once. It will ask for `sudo` to install system packages.

```bash
bash /path/to/parakeet/install.sh
```

The script will:
1. Add the deadsnakes PPA and install Python 3.10 (NeMo requires 3.10+; Ubuntu 20.04 ships 3.8)
2. Install `xclip` and `xdotool` for clipboard and paste automation
3. Create a Python virtualenv at `parakeet/env/`
4. Install PyTorch (CUDA 12.1), NeMo ASR, and audio libraries
5. Download the `nvidia/parakeet-tdt-0.6b-v3` model weights (~2.4 GB) into `parakeet/model_cache/`
6. Generate `parakeet/start_listener.sh`

Model weights and the virtualenv are stored inside the `parakeet/` directory, not in your home directory or on the OS drive.

## Claude Code Hook Setup

Add this hook to `~/.claude/settings.json` so the listener starts automatically at the beginning of every Claude Code session:

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

Replace `/path/to/parakeet/` with the actual path to where you cloned or placed this directory.

If you already have other hooks in `settings.json`, merge the `SessionStart` block into your existing `hooks` object — do not replace the whole file.

## How It Works

Once the listener is running:

1. **Hold `|`** while Claude Code is focused → mic starts recording
2. **Speak** your prompt
3. **Release `|`** → audio is transcribed by Parakeet TDT → text is pasted into the focused window

The listener runs as a background daemon. Logs go to `/tmp/parakeet_listener.log`. To check if it is running:

```bash
cat /tmp/parakeet_listener.pid | xargs ps -p
```

To stop it:

```bash
kill $(cat /tmp/parakeet_listener.pid)
```

## Customization

### Terminal paste shortcut

Open `listener.py` and find the `── Paste shortcut ──` section. Comment out the active line and uncomment the one that matches your terminal:

| Terminal | Shortcut |
|---|---|
| gnome-terminal, xterm, alacritty, kitty | `ctrl+shift+v` (default) |
| VS Code integrated terminal | `ctrl+v` |
| Any X11 terminal (universal fallback) | `shift+Insert` |
| Bypass clipboard, type directly | `xdotool type` |

### Clipboard tool

Find the `── Clipboard ──` section in `listener.py`:

| Tool | When to use |
|---|---|
| `xclip` (default) | X11, Ubuntu/Debian |
| `xsel` | X11 alternative (`sudo apt install xsel`) |
| `wl-copy` | Wayland sessions (`sudo apt install wl-clipboard`) |

### Push-to-talk key

Change the key by editing the two `key.char == "|"` checks in `listener.py` to any single character. For a non-character key (e.g. F9), use pynput's `keyboard.Key` constants instead:

```python
# Example: use F9 instead of |
if key == keyboard.Key.f9 and not _recording:
```

## Why NeMo (not Hugging Face Transformers)?

The official `nvidia/parakeet-tdt-0.6b-v3` weights are released in NeMo's native format. The TDT decoder (which gives precise word-level timestamps and better accuracy on noisy/long audio) is not yet supported in the stable HuggingFace Transformers release. NeMo is the only way to run TDT v3 with the official weights without relying on community-converted checkpoints.

If you prefer to avoid NeMo, `nvidia/parakeet-ctc-0.6b` works with standard Transformers (`pip install transformers`) and has comparable accuracy for clean audio — swap it in by changing `MODEL_NAME` in `listener.py` and replacing the NeMo inference call with the Transformers pipeline.

## Troubleshooting

**Model loads but no audio is recorded**
- Check your default mic: `arecord -l`
- Set the correct device index in `listener.py`: `sd.InputStream(device=N, ...)`

**Paste does not land in Claude Code**
- Verify `xdotool` is installed: `which xdotool`
- Try the `shift+Insert` fallback (works in all X11 terminals)
- If on Wayland, switch the clipboard block to `wl-copy`

**`pynput` fails to listen for key events**
- On some systems, pynput needs access to `/dev/input`. Run once with `sudo` to verify, then add your user to the `input` group: `sudo usermod -aG input $USER` (logout required)

**NeMo install fails**
- Ensure Python 3.10 is active in the venv: `env/bin/python --version`
- Check the install log: `cat install.log`
- NeMo occasionally has pip resolver conflicts; try `pip install "nemo_toolkit[asr]" --no-deps` then install missing deps manually
