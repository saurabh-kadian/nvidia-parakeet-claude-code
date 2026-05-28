"""
Paths, defaults, and config r/w helpers.
All user data lives under XDG directories so nothing touches the install prefix.
"""

import json
from pathlib import Path

# ── Directories ────────────────────────────────────────────────────────────────
CONFIG_DIR          = Path.home() / ".config"           / "parakeet-ptt"
DATA_DIR            = Path.home() / ".local" / "share"  / "parakeet-ptt"
VENV_DIR            = DATA_DIR / "env"
MODEL_CACHE_DEFAULT = DATA_DIR / "model_cache"   # used when config has no override
TELEMETRY_FILE      = DATA_DIR / "telemetry.jsonl"

CONFIG_FILE      = CONFIG_DIR / "config.json"
CORRECTIONS_FILE = CONFIG_DIR / "corrections.json"

# Keys that can be used as PTT key (pynput keyboard.Key names)
PTT_KEYS = [
    "f1","f2","f3","f4","f5","f6","f7","f8","f9","f10","f11","f12",
    "scroll_lock","pause","insert","home","end","page_up","page_down",
]

PASTE_METHODS = [
    ("ctrl+shift+v", "Ctrl+Shift+V  —  gnome-terminal, xterm, alacritty, kitty (default)"),
    ("ctrl+v",       "Ctrl+V  —  VS Code integrated terminal"),
    ("shift+Insert", "Shift+Insert  —  universal X11 fallback"),
]

CLIPBOARD_TOOLS = [
    ("xclip",   "xclip   —  default on Ubuntu/Debian (sudo apt install xclip)"),
    ("xsel",    "xsel    —  alternative (sudo apt install xsel)"),
    ("wl-copy", "wl-copy —  Wayland sessions (sudo apt install wl-clipboard)"),
]

DEFAULT_CONFIG = {
    "ptt_key":        "f9",
    "paste_method":   "ctrl+shift+v",
    "clipboard_tool": "xclip",
    "model_cache":    str(MODEL_CACHE_DEFAULT),
    "venv_dir":       str(VENV_DIR),
}

DEFAULT_CORRECTIONS = [
    # Model names
    [r"\bgemma\s+(?:4|four|for)\s*b\b",          "gemma:4b"],
    [r"\bgemma\s+(?:2|two)\s*b\b",               "gemma:2b"],
    [r"\bgemma\s+(?:7|seven)\s*b\b",             "gemma:7b"],
    [r"\bgemma\s+(?:9|nine)\s*b\b",              "gemma:9b"],
    [r"\bgemma\s+(?:27|twenty.?seven)\s*b\b",    "gemma:27b"],
    [r"\bllama\s+(?:3|three)\b",                 "llama3"],
    [r"\bllama\s+3\s*[.]\s*2\b",                "llama3.2"],
    [r"\bllama\s+(?:3|three)\s+(?:8|eight)\s*b\b",    "llama3:8b"],
    [r"\bllama\s+(?:3|three)\s+(?:70|seventy)\s*b\b",  "llama3:70b"],
    [r"\bmistral\s+(?:7|seven)\s*b\b",           "mistral:7b"],
    [r"\bphi\s+(?:3|three)\b",                   "phi3"],
    [r"\bphi\s+(?:4|four)\b",                    "phi4"],
    [r"\bdeep[\s-]seek\b",                       "deepseek"],
    [r"\b(?:queue|q)\s*wen\b",                   "qwen"],
    [r"\bol['\s-]?lama\b",                       "ollama"],
    # Tools & products
    [r"\bhugging\s+face\b",                      "HuggingFace"],
    [r"\b(?:pi|pie)\s*torch\b",                  "PyTorch"],
    [r"\btensor\s*flow\b",                       "TensorFlow"],
    [r"\bcuda\b",                                "CUDA"],
    # Notation
    [r"\b(\d+)\s*b\s+(?=param|model)",           r"\1B "],
    [r"\bdot\s+py\b",                            ".py"],
    [r"\bdot\s+json\b",                          ".json"],
    [r"\bdot\s+ya?ml\b",                         ".yaml"],
]


def _ensure():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    _ensure()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def save_config(cfg: dict):
    _ensure()
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


def load_corrections() -> list:
    _ensure()
    if CORRECTIONS_FILE.exists():
        try:
            with open(CORRECTIONS_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    # First run — persist defaults so the listener subprocess can find them
    corrections = [list(row) for row in DEFAULT_CORRECTIONS]
    save_corrections(corrections)
    return corrections


def save_corrections(corrections: list):
    _ensure()
    with open(CORRECTIONS_FILE, "w") as f:
        json.dump(corrections, f, indent=2)


def get_venv_dir() -> Path:
    cfg = load_config()
    return Path(cfg.get("venv_dir", str(VENV_DIR)))


def get_model_cache() -> Path:
    cfg = load_config()
    return Path(cfg.get("model_cache", str(MODEL_CACHE_DEFAULT)))


def venv_ready() -> bool:
    return (get_venv_dir() / "bin" / "python").exists()


def model_ready() -> bool:
    hf_hub = get_model_cache() / "huggingface" / "hub"
    return hf_hub.exists() and any(hf_hub.glob("models--nvidia--parakeet*"))
