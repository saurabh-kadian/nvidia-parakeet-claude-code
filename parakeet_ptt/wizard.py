"""
First-run setup wizard.

Page 1 — Welcome
Page 2 — Venv location  (browse to existing or use default)
Page 3 — Model location (browse to existing or use default)
Page 4 — Install Python deps  (skipped if venv already has NeMo)
Page 5 — Download model       (skipped if model already present)
Page 6 — Done

All long-running pages use AssistantPageType.CONTENT (not PROGRESS) so the
Cancel button is never hidden during background work.
"""

import gi
import os
import subprocess
import sys
import threading
from pathlib import Path

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk

from .config import (
    DATA_DIR, MODEL_CACHE_DEFAULT, VENV_DIR,
    load_config, save_config,
)


def _hf_hub_has_model(cache_dir: Path) -> bool:
    hf_hub = cache_dir / "huggingface" / "hub"
    return hf_hub.exists() and any(hf_hub.glob("models--nvidia--parakeet*"))


def _venv_has_nemo(venv_path: Path) -> bool:
    python = venv_path / "bin" / "python"
    if not python.exists():
        return False
    try:
        r = subprocess.run(
            [str(python), "-c", "import nemo, sounddevice, pynput"],
            capture_output=True, timeout=15,
        )
        return r.returncode == 0
    except Exception:
        return False


class SetupWizard(Gtk.Assistant):
    def __init__(self, on_complete=None):
        super().__init__()
        self._on_complete    = on_complete
        self._install_active = False
        self._model_active   = False

        cfg = load_config()
        self._chosen_venv  = Path(VENV_DIR)
        self._chosen_cache = Path(cfg.get("model_cache", str(MODEL_CACHE_DEFAULT)))

        self.set_title("Parakeet PTT — First-Time Setup")
        self.set_default_size(660, 500)

        self._p_welcome  = self._add_welcome()
        self._p_venv     = self._add_venv_location()
        self._p_location = self._add_model_location()
        self._p_install  = self._add_install()
        self._p_model    = self._add_model()
        self._p_done     = self._add_done()

        self.connect("prepare", self._on_prepare)
        self.connect("cancel",  lambda _: Gtk.main_quit())
        self.connect("close",   self._on_close)

    # ── Pages ──────────────────────────────────────────────────────────────────

    def _add_welcome(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_border_width(24)
        lbl = Gtk.Label()
        lbl.set_markup(
            "<big><b>Welcome to Parakeet PTT</b></big>\n\n"
            "This wizard will set up everything needed for local voice-to-text:\n\n"
            "  1. Choose a Python virtualenv  <i>(or point to an existing one)</i>\n"
            "  2. Choose where model weights are stored  <i>(or use an existing download)</i>\n"
            "  3. Install PyTorch + NeMo ASR  <i>(skipped if venv is already ready)</i>\n"
            "  4. Download Parakeet TDT 0.6B v3  (~2.4 GB, skipped if already present)\n\n"
            "You can cancel at any time."
        )
        lbl.set_halign(Gtk.Align.START)
        lbl.set_line_wrap(True)
        lbl.set_use_markup(True)
        box.pack_start(lbl, False, False, 0)
        box.show_all()
        self.append_page(box)
        self.set_page_title(box, "Welcome")
        self.set_page_type(box, Gtk.AssistantPageType.INTRO)
        self.set_page_complete(box, True)
        return box

    def _add_venv_location(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_border_width(20)

        title = Gtk.Label()
        title.set_markup("<b>Python Virtualenv</b>")
        title.set_halign(Gtk.Align.START)
        box.pack_start(title, False, False, 0)

        hint = Gtk.Label(
            label="Parakeet PTT needs a virtualenv with PyTorch and NeMo ASR.\n"
                  "If you already have one set up, point here and the install step will be skipped."
        )
        hint.set_line_wrap(True)
        hint.set_halign(Gtk.Align.START)
        hint.get_style_context().add_class("dim-label")
        box.pack_start(hint, False, False, 0)

        row = Gtk.Box(spacing=8)
        self._venv_lbl = Gtk.Label(label=str(self._chosen_venv))
        self._venv_lbl.set_halign(Gtk.Align.START)
        self._venv_lbl.set_ellipsize(3)
        self._venv_lbl.set_xalign(0)
        row.pack_start(self._venv_lbl, True, True, 0)

        browse_btn = Gtk.Button(label="Browse…")
        browse_btn.connect("clicked", self._browse_venv)
        row.pack_start(browse_btn, False, False, 0)

        reset_btn = Gtk.Button(label="Reset to Default")
        reset_btn.connect("clicked", lambda _: self._set_venv(Path(VENV_DIR)))
        row.pack_start(reset_btn, False, False, 0)

        box.pack_start(row, False, False, 0)

        self._venv_status = Gtk.Label()
        self._venv_status.set_halign(Gtk.Align.START)
        self._venv_status.set_use_markup(True)
        box.pack_start(self._venv_status, False, False, 0)

        box.show_all()
        self.append_page(box)
        self.set_page_title(box, "Virtualenv")
        self.set_page_type(box, Gtk.AssistantPageType.CONTENT)
        self.set_page_complete(box, True)
        return box

    def _add_model_location(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_border_width(20)

        title = Gtk.Label()
        title.set_markup("<b>Model Cache Directory</b>")
        title.set_halign(Gtk.Align.START)
        box.pack_start(title, False, False, 0)

        hint = Gtk.Label(
            label="Where the ~2.4 GB Parakeet model weights will be stored.\n"
                  "Point to an existing download and the download step will be skipped."
        )
        hint.set_line_wrap(True)
        hint.set_halign(Gtk.Align.START)
        hint.get_style_context().add_class("dim-label")
        box.pack_start(hint, False, False, 0)

        row = Gtk.Box(spacing=8)
        self._loc_lbl = Gtk.Label(label=str(self._chosen_cache))
        self._loc_lbl.set_halign(Gtk.Align.START)
        self._loc_lbl.set_ellipsize(3)
        self._loc_lbl.set_xalign(0)
        row.pack_start(self._loc_lbl, True, True, 0)

        browse_btn = Gtk.Button(label="Browse…")
        browse_btn.connect("clicked", self._browse_model_dir)
        row.pack_start(browse_btn, False, False, 0)

        reset_btn = Gtk.Button(label="Reset to Default")
        reset_btn.connect("clicked", lambda _: self._set_model_cache(MODEL_CACHE_DEFAULT))
        row.pack_start(reset_btn, False, False, 0)

        box.pack_start(row, False, False, 0)

        self._loc_status = Gtk.Label()
        self._loc_status.set_halign(Gtk.Align.START)
        self._loc_status.set_use_markup(True)
        box.pack_start(self._loc_status, False, False, 0)

        box.show_all()
        self.append_page(box)
        self.set_page_title(box, "Model Location")
        self.set_page_type(box, Gtk.AssistantPageType.CONTENT)
        self.set_page_complete(box, True)
        return box

    def _add_install(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(12)

        self._install_lbl = Gtk.Label(label="Preparing…")
        self._install_lbl.set_halign(Gtk.Align.START)
        box.pack_start(self._install_lbl, False, False, 0)

        self._install_bar = Gtk.ProgressBar()
        self._install_bar.set_pulse_step(0.04)
        box.pack_start(self._install_bar, False, False, 0)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self._install_tv = Gtk.TextView()
        self._install_tv.set_editable(False)
        self._install_tv.set_cursor_visible(False)
        self._install_tv.set_monospace(True)
        sw.add(self._install_tv)
        box.pack_start(sw, True, True, 0)

        box.show_all()
        self.append_page(box)
        self.set_page_title(box, "Install Dependencies")
        # CONTENT (not PROGRESS) keeps Cancel visible during background work
        self.set_page_type(box, Gtk.AssistantPageType.CONTENT)
        self.set_page_complete(box, False)
        return box

    def _add_model(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_border_width(12)

        self._model_title = Gtk.Label(
            label="Downloading NVIDIA Parakeet TDT 0.6B v3 weights (~2.4 GB)…"
        )
        self._model_title.set_halign(Gtk.Align.START)
        self._model_title.set_line_wrap(True)
        box.pack_start(self._model_title, False, False, 0)

        self._model_bar = Gtk.ProgressBar()
        self._model_bar.set_pulse_step(0.02)
        box.pack_start(self._model_bar, False, False, 0)

        self._model_status = Gtk.Label(label="Waiting for previous step…")
        self._model_status.set_halign(Gtk.Align.START)
        self._model_status.get_style_context().add_class("dim-label")
        box.pack_start(self._model_status, False, False, 0)

        box.show_all()
        self.append_page(box)
        self.set_page_title(box, "Download Model")
        # CONTENT (not PROGRESS) keeps Cancel visible during background work
        self.set_page_type(box, Gtk.AssistantPageType.CONTENT)
        self.set_page_complete(box, False)
        return box

    def _add_done(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_border_width(24)
        lbl = Gtk.Label()
        lbl.set_markup(
            "<big><b>Setup complete!</b></big>\n\n"
            "Parakeet PTT is ready. The listener will start automatically.\n\n"
            "Hold your configured push-to-talk key to record, release to transcribe."
        )
        lbl.set_halign(Gtk.Align.START)
        lbl.set_line_wrap(True)
        box.pack_start(lbl, False, False, 0)
        box.show_all()
        self.append_page(box)
        self.set_page_title(box, "Done")
        self.set_page_type(box, Gtk.AssistantPageType.SUMMARY)
        self.set_page_complete(box, True)
        return box

    # ── Pickers ────────────────────────────────────────────────────────────────

    def _browse_venv(self, _):
        dialog = Gtk.FileChooserDialog(
            title="Choose Virtualenv Directory",
            transient_for=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
        )
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                           "Select", Gtk.ResponseType.OK)
        dialog.set_filename(str(self._chosen_venv))
        if dialog.run() == Gtk.ResponseType.OK:
            self._set_venv(Path(dialog.get_filename()))
        dialog.destroy()

    def _set_venv(self, path: Path):
        self._chosen_venv = path
        self._venv_lbl.set_text(str(path))
        self._update_venv_status()

    def _update_venv_status(self):
        if _venv_has_nemo(self._chosen_venv):
            self._venv_status.set_markup(
                "<span foreground='green'>✔ Virtualenv found with NeMo — install step will be skipped.</span>"
            )
        elif (self._chosen_venv / "bin" / "python").exists():
            self._venv_status.set_markup(
                "<span foreground='orange'>⚠ Virtualenv found but NeMo is missing — dependencies will be installed.</span>"
            )
        else:
            self._venv_status.set_markup(
                "<span foreground='gray'>No virtualenv here — one will be created and dependencies installed.</span>"
            )

    def _browse_model_dir(self, _):
        dialog = Gtk.FileChooserDialog(
            title="Choose Model Cache Directory",
            transient_for=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
        )
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                           "Select", Gtk.ResponseType.OK)
        dialog.set_filename(str(self._chosen_cache))
        if dialog.run() == Gtk.ResponseType.OK:
            self._set_model_cache(Path(dialog.get_filename()))
        dialog.destroy()

    def _set_model_cache(self, path: Path):
        self._chosen_cache = path
        self._loc_lbl.set_text(str(path))
        self._update_model_status()

    def _update_model_status(self):
        if _hf_hub_has_model(self._chosen_cache):
            self._loc_status.set_markup(
                "<span foreground='green'>✔ Model found here — download will be skipped.</span>"
            )
        else:
            self._loc_status.set_markup(
                "<span foreground='gray'>No model found here — it will be downloaded (~2.4 GB).</span>"
            )

    # ── Orchestration ──────────────────────────────────────────────────────────

    def _on_prepare(self, _assistant, page):
        if page is self._p_venv:
            self._update_venv_status()

        if page is self._p_location:
            self._update_model_status()

        if page is self._p_install and not self._install_active:
            # Persist chosen paths before doing any work
            cfg = load_config()
            cfg["model_cache"] = str(self._chosen_cache)
            cfg["venv_dir"]    = str(self._chosen_venv)
            save_config(cfg)

            if _venv_has_nemo(self._chosen_venv):
                GLib.idle_add(self._install_lbl.set_text,
                              "Virtualenv already has NeMo — skipping.")
                GLib.idle_add(self._install_bar.set_fraction, 1.0)
                GLib.idle_add(self.set_page_complete, self._p_install, True)
                GLib.idle_add(self.next_page)
            else:
                self._install_active = True
                threading.Thread(target=self._run_install, daemon=True).start()
                GLib.timeout_add(80, self._tick_install_bar)

        if page is self._p_model and not self._model_active:
            self._model_active = True
            if _hf_hub_has_model(self._chosen_cache):
                GLib.idle_add(self._model_title.set_text,
                              "Model already present — skipping download.")
                GLib.idle_add(self._model_status.set_text, "Using existing weights.")
                GLib.idle_add(self._model_bar.set_fraction, 1.0)
                GLib.idle_add(self.set_page_complete, self._p_model, True)
                GLib.idle_add(self.next_page)
            else:
                threading.Thread(target=self._run_model_download, daemon=True).start()
                GLib.timeout_add(200, self._tick_model_bar)

    def _on_close(self, _):
        self.destroy()
        if self._on_complete:
            self._on_complete()

    # ── Install thread ─────────────────────────────────────────────────────────

    def _log(self, text: str):
        GLib.idle_add(self._append_log, text)

    def _append_log(self, text: str):
        buf = self._install_tv.get_buffer()
        buf.insert(buf.get_end_iter(), text)
        mark = buf.create_mark(None, buf.get_end_iter(), False)
        self._install_tv.scroll_mark_onscreen(mark)
        buf.delete_mark(mark)

    def _tick_install_bar(self):
        if self._install_active:
            self._install_bar.pulse()
            return True
        self._install_bar.set_fraction(1.0)
        return False

    def _tick_model_bar(self):
        if self._model_active:
            self._model_bar.pulse()
            return True
        self._model_bar.set_fraction(1.0)
        return False

    def _run_install(self):
        ok = True
        venv = self._chosen_venv
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            self._chosen_cache.mkdir(parents=True, exist_ok=True)

            pip = str(venv / "bin" / "pip")

            if not venv.exists():
                GLib.idle_add(self._install_lbl.set_text, "Creating virtualenv…")
                self._log("Creating virtualenv…\n")
                subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
                self._log("Done.\n\n")

            GLib.idle_add(self._install_lbl.set_text, "Upgrading pip…")
            self._log("Upgrading pip…\n")
            subprocess.run([pip, "install", "--upgrade", "pip"],
                           check=True, capture_output=True)

            GLib.idle_add(self._install_lbl.set_text, "Installing PyTorch (CUDA 12.1)…")
            self._log("Installing PyTorch — this takes several minutes…\n")
            subprocess.run([
                pip, "install", "torch", "torchaudio",
                "--index-url", "https://download.pytorch.org/whl/cu121",
            ], check=True, capture_output=True)
            self._log("PyTorch installed.\n\n")

            GLib.idle_add(self._install_lbl.set_text, "Installing NeMo ASR…")
            self._log("Installing NeMo ASR — this takes several minutes…\n")
            subprocess.run([pip, "install", "nemo_toolkit[asr]"],
                           check=True, capture_output=True)
            self._log("NeMo installed.\n\n")

            GLib.idle_add(self._install_lbl.set_text, "Installing audio libraries…")
            self._log("Installing sounddevice, soundfile, pynput…\n")
            subprocess.run([pip, "install", "sounddevice", "soundfile", "pynput"],
                           check=True, capture_output=True)
            self._log("All dependencies installed.\n")
            GLib.idle_add(self._install_lbl.set_text, "Dependencies installed.")

        except subprocess.CalledProcessError as exc:
            ok = False
            self._log(f"\nERROR: {exc}\n\nCheck your internet connection and try again.\n")
            GLib.idle_add(self._install_lbl.set_text, "Installation failed — see log above.")

        self._install_active = False
        if ok:
            GLib.idle_add(self.set_page_complete, self._p_install, True)
            GLib.idle_add(self.next_page)

    # ── Model download thread ──────────────────────────────────────────────────

    def _run_model_download(self):
        GLib.idle_add(self._model_status.set_text, "Connecting to HuggingFace Hub…")
        ok = True
        try:
            venv_python = str(self._chosen_venv / "bin" / "python")
            env = os.environ.copy()
            env["HF_HOME"]        = str(self._chosen_cache / "huggingface")
            env["NEMO_CACHE_DIR"] = str(self._chosen_cache / "nemo")
            env["TORCH_HOME"]     = str(self._chosen_cache / "torch")
            subprocess.run([
                venv_python, "-c",
                "import nemo.collections.asr as nemo_asr; "
                "nemo_asr.models.ASRModel.from_pretrained('nvidia/parakeet-tdt-0.6b-v3')",
            ], env=env, check=True)
            GLib.idle_add(self._model_status.set_text, "Model downloaded successfully.")
        except subprocess.CalledProcessError as exc:
            ok = False
            GLib.idle_add(self._model_status.set_text, f"Download failed: {exc}")

        self._model_active = False
        if ok:
            GLib.idle_add(self.set_page_complete, self._p_model, True)
            GLib.idle_add(self.next_page)
