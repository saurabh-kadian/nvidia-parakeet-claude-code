"""
First-run setup wizard — PyQt5 QWizard.
Pages: Welcome → Venv → Model location → Install → Download → Done
"""

import os
import subprocess
import sys
import threading
from pathlib import Path

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QWizard, QWizardPage, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QFileDialog,
    QProgressBar, QPlainTextEdit,
)

from .config import (
    DATA_DIR, MODEL_CACHE_DEFAULT, VENV_DIR,
    load_config, save_config,
)


def _hf_has_whisper(cache_dir: Path) -> bool:
    hf_hub = cache_dir / "huggingface" / "hub"
    return hf_hub.exists() and any(hf_hub.glob("models--*whisper*"))


def _venv_has_deps(venv_path: Path) -> bool:
    python = venv_path / "Scripts" / "python.exe"
    if not python.exists():
        return False
    try:
        r = subprocess.run(
            [str(python), "-c", "import nemo, sounddevice, pynput, pyperclip"],
            capture_output=True, timeout=15,
        )
        return r.returncode == 0
    except Exception:
        return False


# ── Worker threads ─────────────────────────────────────────────────────────────

class InstallWorker(QThread):
    log      = pyqtSignal(str)
    finished = pyqtSignal(bool)  # True = success

    def __init__(self, venv_path: Path, cache_path: Path):
        super().__init__()
        self.venv_path  = venv_path
        self.cache_path = cache_path

    def run(self):
        ok = True
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            self.cache_path.mkdir(parents=True, exist_ok=True)
            pip = str(self.venv_path / "Scripts" / "pip.exe")

            if not self.venv_path.exists():
                self.log.emit("Creating virtualenv…\n")
                subprocess.run([sys.executable, "-m", "venv", str(self.venv_path)], check=True)
                self.log.emit("Done.\n\n")

            self.log.emit("Upgrading pip…\n")
            subprocess.run([pip, "install", "--upgrade", "pip"],
                           check=True, capture_output=True)

            self.log.emit("Installing PyTorch (CUDA 12.1)…\n")
            subprocess.run([
                pip, "install", "torch", "torchaudio",
                "--index-url", "https://download.pytorch.org/whl/cu121",
            ], check=True, capture_output=True)
            self.log.emit("PyTorch installed.\n\n")

            self.log.emit("Installing NeMo ASR…\n")
            subprocess.run([pip, "install", "nemo_toolkit[asr]"],
                           check=True, capture_output=True)
            self.log.emit("NeMo installed.\n\n")

            self.log.emit("Installing audio + input libraries…\n")
            subprocess.run([pip, "install", "sounddevice", "soundfile",
                            "pynput", "pyperclip", "pywin32", "plyer"],
                           check=True, capture_output=True)
            self.log.emit("All dependencies installed.\n")

        except subprocess.CalledProcessError as exc:
            ok = False
            self.log.emit(f"\nERROR: {exc}\n")
        self.finished.emit(ok)


class DownloadWorker(QThread):
    status   = pyqtSignal(str)
    finished = pyqtSignal(bool)

    def __init__(self, venv_path: Path, cache_path: Path):
        super().__init__()
        self.venv_path  = venv_path
        self.cache_path = cache_path

    def run(self):
        ok = True
        try:
            python = str(self.venv_path / "Scripts" / "python.exe")
            env = os.environ.copy()
            env["HF_HOME"]        = str(self.cache_path / "huggingface")
            env["NEMO_CACHE_DIR"] = str(self.cache_path / "nemo")
            env["TORCH_HOME"]     = str(self.cache_path / "torch")
            self.status.emit("Downloading Parakeet TDT 0.6B v3 from HuggingFace…")
            subprocess.run([
                python, "-c",
                "import nemo.collections.asr as nemo_asr; "
                "nemo_asr.models.ASRModel.from_pretrained('nvidia/parakeet-tdt-0.6b-v3')",
            ], env=env, check=True)
            self.status.emit("Model downloaded.")
        except subprocess.CalledProcessError as exc:
            ok = False
            self.status.emit(f"Download failed: {exc}")
        self.finished.emit(ok)


# ── Wizard pages ───────────────────────────────────────────────────────────────

class WelcomePage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Welcome to Parakeet PTT")
        layout = QVBoxLayout(self)
        lbl = QLabel(
            "This wizard will set up everything needed for local voice-to-text:\n\n"
            "  1. Choose a Python virtualenv  (or point to an existing one)\n"
            "  2. Choose where model weights are stored  (or use an existing download)\n"
            "  3. Install faster-whisper + audio libraries  (skipped if already ready)\n"
            "  4. Download Whisper large-v3-turbo  (~3 GB, skipped if already present)\n\n"
            "You can cancel at any time."
        )
        lbl.setWordWrap(True)
        layout.addWidget(lbl)


class VenvPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Python Virtualenv")
        self._chosen = Path(VENV_DIR)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(
            "Parakeet PTT needs a virtualenv with faster-whisper and audio libraries.\n"
            "Point to an existing one to skip the install step."
        ))

        row = QHBoxLayout()
        self._edit = QLineEdit(str(self._chosen))
        self._edit.textChanged.connect(self._on_changed)
        row.addWidget(self._edit)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        reset = QPushButton("Default")
        reset.clicked.connect(lambda: self._edit.setText(str(VENV_DIR)))
        row.addWidget(reset)
        layout.addLayout(row)

        self._status = QLabel()
        layout.addWidget(self._status)

    def initializePage(self):
        self._update_status()

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, "Choose Virtualenv", self._edit.text())
        if path:
            self._edit.setText(path)

    def _on_changed(self, text):
        self._chosen = Path(text)
        self._update_status()

    def _update_status(self):
        if _venv_has_deps(self._chosen):
            self._status.setText("✔ Virtualenv found with all dependencies — install will be skipped.")
            self._status.setStyleSheet("color: green;")
        elif (self._chosen / "Scripts" / "python.exe").exists():
            self._status.setText("⚠ Virtualenv exists but dependencies are missing — will be installed.")
            self._status.setStyleSheet("color: orange;")
        else:
            self._status.setText("No virtualenv found here — one will be created.")
            self._status.setStyleSheet("color: gray;")

    def chosen(self) -> Path:
        return Path(self._edit.text())


class ModelLocationPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Model Cache Directory")
        cfg = load_config()
        self._chosen = Path(cfg.get("model_cache", str(MODEL_CACHE_DEFAULT)))
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(
            "Where the ~3 GB Whisper model weights will be stored.\n"
            "Point to an existing download and the download step will be skipped."
        ))

        row = QHBoxLayout()
        self._edit = QLineEdit(str(self._chosen))
        self._edit.textChanged.connect(self._on_changed)
        row.addWidget(self._edit)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        reset = QPushButton("Default")
        reset.clicked.connect(lambda: self._edit.setText(str(MODEL_CACHE_DEFAULT)))
        row.addWidget(reset)
        layout.addLayout(row)

        self._status = QLabel()
        layout.addWidget(self._status)

    def initializePage(self):
        self._update_status()

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, "Choose Model Cache", self._edit.text())
        if path:
            self._edit.setText(path)

    def _on_changed(self, text):
        self._chosen = Path(text)
        self._update_status()

    def _update_status(self):
        if _hf_has_whisper(self._chosen):
            self._status.setText("✔ Whisper model found — download will be skipped.")
            self._status.setStyleSheet("color: green;")
        else:
            self._status.setText("No model found here — it will be downloaded (~3 GB).")
            self._status.setStyleSheet("color: gray;")

    def chosen(self) -> Path:
        return Path(self._edit.text())


class InstallPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Install Dependencies")
        self._complete = False
        layout = QVBoxLayout(self)
        self._label = QLabel("Preparing…")
        layout.addWidget(self._label)
        self._bar = QProgressBar()
        self._bar.setRange(0, 0)  # indeterminate
        layout.addWidget(self._bar)
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(500)
        layout.addWidget(self._log)

    def initializePage(self):
        wizard = self.wizard()
        venv  = wizard.page(2).chosen()   # VenvPage
        cache = wizard.page(3).chosen()   # ModelLocationPage

        # Save chosen paths
        cfg = load_config()
        cfg["venv_dir"]    = str(venv)
        cfg["model_cache"] = str(cache)
        save_config(cfg)

        if _venv_has_deps(venv):
            self._label.setText("Dependencies already installed — skipping.")
            self._bar.setRange(0, 1); self._bar.setValue(1)
            self._done(True)
            return

        self._worker = InstallWorker(venv, cache)
        self._worker.log.connect(self._append_log)
        self._worker.finished.connect(self._done)
        self._worker.start()

    def _append_log(self, text):
        self._log.insertPlainText(text)
        self._log.ensureCursorVisible()

    def _done(self, ok: bool):
        self._bar.setRange(0, 1); self._bar.setValue(1)
        if ok:
            self._label.setText("Dependencies installed.")
            self._complete = True
            self.completeChanged.emit()
            self.wizard().next()

    def isComplete(self):
        return self._complete


class DownloadPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Download Model")
        self._complete = False
        layout = QVBoxLayout(self)
        self._label = QLabel("Downloading Whisper large-v3-turbo (~3 GB)…")
        self._label.setWordWrap(True)
        layout.addWidget(self._label)
        self._bar = QProgressBar()
        self._bar.setRange(0, 0)
        layout.addWidget(self._bar)
        self._status = QLabel("Waiting…")
        self._status.setStyleSheet("color: gray;")
        layout.addWidget(self._status)

    def initializePage(self):
        wizard = self.wizard()
        venv  = wizard.page(2).chosen()
        cache = wizard.page(3).chosen()

        if _hf_has_whisper(cache):
            self._label.setText("Model already present — skipping download.")
            self._status.setText("Using existing weights.")
            self._bar.setRange(0, 1); self._bar.setValue(1)
            self._done(True)
            return

        self._worker = DownloadWorker(venv, cache)
        self._worker.status.connect(self._status.setText)
        self._worker.finished.connect(self._done)
        self._worker.start()

    def _done(self, ok: bool):
        self._bar.setRange(0, 1); self._bar.setValue(1)
        if ok:
            self._complete = True
            self.completeChanged.emit()
            self.wizard().next()

    def isComplete(self):
        return self._complete


class DonePage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Setup Complete")
        layout = QVBoxLayout(self)
        lbl = QLabel(
            "Parakeet PTT is ready!\n\n"
            "The listener will start automatically.\n"
            "Hold your configured push-to-talk key to record, release to transcribe."
        )
        lbl.setWordWrap(True)
        layout.addWidget(lbl)


# ── Wizard ─────────────────────────────────────────────────────────────────────

class SetupWizard(QWizard):
    def __init__(self, on_complete=None, parent=None):
        super().__init__(parent)
        self._on_complete = on_complete
        self.setWindowTitle("Parakeet PTT — First-Time Setup")
        self.resize(660, 500)
        self.setWizardStyle(QWizard.ModernStyle)

        self.addPage(WelcomePage())       # page 1
        self.addPage(VenvPage())          # page 2
        self.addPage(ModelLocationPage()) # page 3
        self.addPage(InstallPage())       # page 4
        self.addPage(DownloadPage())      # page 5
        self.addPage(DonePage())          # page 6

        self.finished.connect(self._on_finished)

    def _on_finished(self, result):
        if result == QWizard.Accepted and self._on_complete:
            self._on_complete()
