#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/env"
CACHE_DIR="$SCRIPT_DIR/model_cache"
LOG="$SCRIPT_DIR/install.log"

echo "=== Parakeet TDT 0.6B v3 — Install Script ===" | tee "$LOG"
echo "  Virtualenv  : $VENV_DIR"
echo "  Model cache : $CACHE_DIR"
echo "  Log         : $LOG"

# ── Detect Ubuntu version ──────────────────────────────────────────────────────

UBUNTU_VERSION=$(lsb_release -rs 2>/dev/null || echo "0")
UBUNTU_MAJOR=$(echo "$UBUNTU_VERSION" | cut -d. -f1)

# ── Detect CUDA version from installed driver ──────────────────────────────────

echo ""
echo "→ Detecting NVIDIA driver / CUDA support..."
if command -v nvidia-smi &>/dev/null; then
    # Driver version → maximum supported CUDA version mapping
    DRIVER_VERSION=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1 | cut -d. -f1)
    if   [ "$DRIVER_VERSION" -ge 545 ]; then CUDA_TAG="cu124"
    elif [ "$DRIVER_VERSION" -ge 520 ]; then CUDA_TAG="cu121"
    elif [ "$DRIVER_VERSION" -ge 450 ]; then CUDA_TAG="cu118"
    else
        echo "  Driver $DRIVER_VERSION is too old (need 450+). Exiting."
        exit 1
    fi
    echo "  Driver $DRIVER_VERSION → using PyTorch index: $CUDA_TAG"
else
    echo "  nvidia-smi not found — falling back to CPU-only PyTorch."
    CUDA_TAG="cpu"
fi

# ── System dependencies ────────────────────────────────────────────────────────

echo ""
echo "→ Checking system packages..."

MISSING_APT=()
for pkg in xclip xdotool python3.10 python3.10-venv python3.10-dev libsndfile1 ffmpeg portaudio19-dev; do
    if ! dpkg -s "$pkg" &>/dev/null; then
        MISSING_APT+=("$pkg")
    fi
done

if [ ${#MISSING_APT[@]} -gt 0 ]; then
    echo "  Missing: ${MISSING_APT[*]}"
    # deadsnakes PPA only needed on Ubuntu < 22.04 (22.04+ ships Python 3.10 natively)
    if [ "$UBUNTU_MAJOR" -lt 22 ] && ! apt-cache show python3.10 &>/dev/null; then
        echo "  Adding deadsnakes PPA (Ubuntu $UBUNTU_VERSION does not ship Python 3.10)..."
        sudo add-apt-repository -y ppa:deadsnakes/ppa 2>>"$LOG"
        sudo apt-get update -qq 2>>"$LOG"
    fi
    sudo apt-get install -y "${MISSING_APT[@]}" 2>>"$LOG"
    echo "  Done."
else
    echo "  All system packages present."
fi

# ── Virtual environment ────────────────────────────────────────────────────────

echo ""
echo "→ Creating virtualenv at $VENV_DIR (Python 3.10)..."
if [ -d "$VENV_DIR" ]; then
    echo "  Already exists — skipping creation."
else
    python3.10 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
echo "  Python: $(python --version)"

# ── Cache directories ──────────────────────────────────────────────────────────

mkdir -p "$CACHE_DIR"

# Point HuggingFace and NeMo at our custom cache location
export HF_HOME="$CACHE_DIR/huggingface"
export NEMO_CACHE_DIR="$CACHE_DIR/nemo"
export TORCH_HOME="$CACHE_DIR/torch"
mkdir -p "$HF_HOME" "$NEMO_CACHE_DIR" "$TORCH_HOME"

# ── PyTorch (CUDA 12.1 — works with driver 520+) ──────────────────────────────

echo ""
echo "→ Installing PyTorch (index: $CUDA_TAG)..."
pip install --quiet --upgrade pip setuptools wheel 2>>"$LOG"

# PyTorch CUDA wheels are ~2.5 GB. pip extracts into TMPDIR before moving to
# the venv, so /tmp (root fs) fills up on space-constrained machines.
# Redirect both TMPDIR and pip's cache to the data drive.
export TMPDIR="$SCRIPT_DIR/tmp"
mkdir -p "$TMPDIR"

pip install \
    torch torchvision torchaudio \
    --index-url "https://download.pytorch.org/whl/$CUDA_TAG" \
    --cache-dir "$SCRIPT_DIR/tmp/pip-cache" \
    --log "$LOG"

python -c "
import torch
avail = torch.cuda.is_available()
gpu = torch.cuda.get_device_name(0) if avail else 'none'
print(f'  PyTorch {torch.__version__}  |  CUDA: {avail}  |  GPU: {gpu}')
"

# ── NeMo ASR ──────────────────────────────────────────────────────────────────

echo ""
echo "→ Installing NeMo ASR toolkit (this takes a few minutes)..."
pip install "nemo_toolkit[asr]" --log "$LOG"
echo "  Done."

# ── Audio + input libraries ───────────────────────────────────────────────────

echo ""
echo "→ Installing audio and keyboard libraries..."
pip install --quiet sounddevice soundfile pynput 2>>"$LOG"
echo "  Done."

# ── Pre-download model weights ────────────────────────────────────────────────

echo ""
echo "→ Pre-downloading nvidia/parakeet-tdt-0.6b-v3 (~2.4 GB)..."
HF_HOME="$HF_HOME" NEMO_CACHE_DIR="$NEMO_CACHE_DIR" python - <<'PYEOF'
import os
import nemo.collections.asr as nemo_asr
model = nemo_asr.models.ASRModel.from_pretrained("nvidia/parakeet-tdt-0.6b-v3")
print("  Model downloaded and cached successfully.")
PYEOF

# ── Launcher script ───────────────────────────────────────────────────────────

LAUNCHER="$SCRIPT_DIR/start_listener.sh"
cat > "$LAUNCHER" <<SHEOF
#!/bin/bash
# Start the Parakeet push-to-talk listener as a background daemon.
SCRIPT_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="\$SCRIPT_DIR/env"
CACHE_DIR="\$SCRIPT_DIR/model_cache"
PID_FILE="/tmp/parakeet_listener.pid"
LOG_FILE="/tmp/parakeet_listener.log"

if [ -f "\$PID_FILE" ] && kill -0 "\$(cat "\$PID_FILE")" 2>/dev/null; then
    echo "[parakeet] Already running (PID \$(cat "\$PID_FILE"))"
    exit 0
fi

echo "[parakeet] Starting listener..."
HF_HOME="\$CACHE_DIR/huggingface" \\
NEMO_CACHE_DIR="\$CACHE_DIR/nemo" \\
TORCH_HOME="\$CACHE_DIR/torch" \\
nohup "\$VENV_DIR/bin/python" "\$SCRIPT_DIR/listener.py" > "\$LOG_FILE" 2>&1 &
echo \$! > "\$PID_FILE"
echo "[parakeet] Started (PID \$(cat "\$PID_FILE")) — log: \$LOG_FILE"
SHEOF
chmod +x "$LAUNCHER"

echo ""
echo "=== Install complete ==="
echo ""
echo "  Virtualenv  : $VENV_DIR"
echo "  Model cache : $CACHE_DIR"
echo "  Launcher    : $LAUNCHER"
echo ""
echo "─────────────────────────────────────────────────────────────────────────────"
echo "Add this to ~/.claude/settings.json (merge into existing 'hooks' if present):"
echo "─────────────────────────────────────────────────────────────────────────────"
cat <<HOOKEOF
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "[ -f $LAUNCHER ] && $LAUNCHER 2>/dev/null || true",
            "async": true,
            "statusMessage": "Starting Parakeet listener..."
          }
        ]
      }
    ]
  }
}
HOOKEOF
echo "─────────────────────────────────────────────────────────────────────────────"
echo ""
echo "Hold '|' while Claude Code is focused to record; release to transcribe + paste."
