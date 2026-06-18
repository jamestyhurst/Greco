"""
Greco desktop GUI (Phase 1) — a thin Tkinter front-end over the existing pipeline.

Pick a PGN, choose options, click Analyze; Greco runs Stockfish + Claude in a
background thread (so the window stays responsive), shows progress, then opens
the self-contained HTML report in your browser.

This file adds NO analysis logic — it only collects inputs and calls the same
functions the CLI uses: importers → analyzer → triage → narrator → outputs.

Run it with:   python gui.py     (or double-click run_greco.bat)
"""

from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import threading
import traceback
import webbrowser
from pathlib import Path
from typing import Optional

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from importers import load_pgn
from analyzer import analyze_pgn
from triage import annotate_with_tiers
from narrator import generate_narrative
from outputs import assemble_report, markdown_to_html, report_basename, default_reports_dir, export_shareable_html
from version import __version__


SPEED_LABELS = {"Fast (0.5s/move)": 0.5, "Normal (0.8s/move)": 0.8, "Deep (1.5s/move)": 1.5}
USE_CASES = ["companion", "coaching", "commentary"]
SIDES = ["White", "Black", "Neither"]
MODELS = ["claude-sonnet-4-6", "claude-opus-4-8", "claude-fable-5"]
AUDIENCE_LEVELS = ["(not specified)", "Beginner", "Casual", "Club", "Advanced"]

# Preferred place to look for PGNs (the E: library), with a sensible fallback.
PGN_LIBRARY = r"E:\Chess\PGNs"

# Greco app icon (window title bar + taskbar).
ICON_PATH = Path(__file__).resolve().parent / "assets" / "greco.ico"

# Persistent settings file — stores engine path, API key, model, reports folder.
CONFIG_PATH = Path(__file__).resolve().parent / "config.json"


def default_pgn_dir() -> str:
    """Best default folder to pick PGNs from: the user's 'Chess Game Files' under
    Documents (the C: source that sync_pgns.bat copies to E:), then the E: library,
    then the home folder. Used only when no folder is configured in settings."""
    for cand in (Path.home() / "Documents" / "Chess Game Files", Path(PGN_LIBRARY)):
        try:
            if cand.is_dir():
                return str(cand)
        except OSError:
            pass
    return str(Path.home())


def load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(cfg: dict) -> None:
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except Exception:
        pass


def _find_chrome() -> Optional[str]:
    """Locate chrome.exe — checks PATH, the standard install folders, and the
    'App Paths' registry. Returns the full path, or None if Chrome isn't found."""
    exe = shutil.which("chrome")
    if exe:
        return exe
    candidates = [
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    ]
    for c in candidates:
        try:
            if c.is_file():
                return str(c)
        except OSError:
            pass
    try:
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(
                    hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"
                ) as key:
                    val, _ = winreg.QueryValueEx(key, None)
                if val and Path(val).is_file():
                    return val
            except OSError:
                continue
    except Exception:
        pass
    return None


def open_report_in_browser(path: str) -> None:
    """Open the finished HTML report, preferring Chrome.

    Chrome is launched with the file path passed directly as an argument, which
    is robust for this machine's non-ASCII profile path (no file:// URI encoding
    to trip over). Falls back to the system default browser if Chrome is absent.
    """
    p = Path(path)
    chrome = _find_chrome()
    if chrome:
        try:
            subprocess.Popen([chrome, str(p)])
            return
        except Exception:
            pass  # fall through to the default browser
    webbrowser.open(p.as_uri())


def _safe_folder_name(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip() or "game"


class _QueueWriter:
    """File-like object: forwards written text to the GUI via the queue."""

    def __init__(self, q: "queue.Queue"):
        self._q = q

    def write(self, text: str) -> None:
        if text:
            self._q.put(("narrative", text))

    def flush(self) -> None:  # required for file-like protocol
        pass


class GrecoGUI:
    # Wine / ivory / gold palette, taken straight from the app icon
    # (assets/make_icon.py) so the window matches the desktop + title-bar king.
    WINE = "#7A1C26"; WINE_DARK = "#5E151D"; IVORY = "#F5EDD4"
    GOLD = "#C9A23A"; INK = "#3A2A1A"; PARCH = "#FBF6E7"  # INK = sepia, like aged manuscript ink

    def _apply_theme(self) -> None:
        """Recolour the ttk widgets to the icon's wine/ivory/gold aesthetic. Uses the
        'clam' theme because it is the built-in ttk theme that actually honours custom
        colours on Windows (the native theme ignores most of them)."""
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        W, WD, IV, G, INK, PA = self.WINE, self.WINE_DARK, self.IVORY, self.GOLD, self.INK, self.PARCH
        self.root.configure(bg=W)
        # The Combobox dropdown is a classic tk Listbox; colour it via the option DB.
        self.root.option_add("*TCombobox*Listbox.background", PA)
        self.root.option_add("*TCombobox*Listbox.foreground", INK)
        self.root.option_add("*TCombobox*Listbox.selectBackground", W)
        self.root.option_add("*TCombobox*Listbox.selectForeground", IV)
        style.configure(".", background=W, foreground=IV)
        style.configure("TFrame", background=W)
        style.configure("TLabel", background=W, foreground=IV)
        style.configure("TLabelframe", background=W, bordercolor=G, relief="solid", borderwidth=1)
        style.configure("TLabelframe.Label", background=W, foreground=G, font=("Constantia", 11, "bold"))
        style.configure("TButton", background=IV, foreground=W, bordercolor=G,
                        focuscolor=G, relief="raised", padding=6)
        style.map("TButton",
                  background=[("active", G), ("pressed", WD), ("disabled", WD)],
                  foreground=[("active", W), ("pressed", IV), ("disabled", "#9A8F78")])
        style.configure("TEntry", fieldbackground=PA, foreground=INK, bordercolor=G,
                        insertcolor=INK, relief="flat")
        style.configure("TCombobox", fieldbackground=PA, foreground=INK, background=IV,
                        bordercolor=G, arrowcolor=W, relief="flat")
        style.map("TCombobox", fieldbackground=[("readonly", PA)],
                  foreground=[("readonly", INK)], arrowcolor=[("active", WD)])
        style.configure("Horizontal.TProgressbar", background=G, troughcolor=WD, bordercolor=G)
        # Gold "primary" button for the main Analyze action.
        style.configure("Primary.TButton", background=G, foreground=W, bordercolor=WD,
                        font=("Georgia", 10, "bold"), padding=8)
        style.map("Primary.TButton", background=[("active", IV), ("pressed", WD)],
                  foreground=[("active", W), ("pressed", IV)])

    def _section(self, parent, glyph: str, title: str) -> ttk.LabelFrame:
        """A LabelFrame whose header is a large ivory chess piece + a gold title.
        Rendering the piece big (Segoe UI Symbol has clean, well-spaced chess glyphs)
        keeps the pawn/knight/rook clearly readable instead of compressing them to a
        blob the way an 11px header glyph did."""
        lf = ttk.LabelFrame(parent, padding=8)
        head = ttk.Frame(lf)
        ttk.Label(head, text=glyph, font=("Segoe UI Symbol", 18),
                  foreground=self.IVORY).pack(side="left")
        ttk.Label(head, text="  " + title, font=("Constantia", 12, "bold"),
                  foreground=self.GOLD).pack(side="left")
        lf.configure(labelwidget=head)
        return lf

    def __init__(self, root: tk.Tk):
        self.root = root
        self.q: "queue.Queue" = queue.Queue()
        self.running = False
        self._last_html = None   # path of the most recent report (for the buttons)
        self._last_dir = None
        root.title(f"Greco {__version__} — Chess Game Analyzer")
        root.geometry("760x700")
        root.minsize(640, 600)
        self._apply_theme()
        try:
            root.iconbitmap(default=str(ICON_PATH))  # king logo on the title bar + taskbar
        except Exception:
            pass

        cfg = load_config()

        pad = {"padx": 8, "pady": 4}
        main = ttk.Frame(root, padding=10)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text="♚  Greco", font=("Gabriola", 30),
                  foreground=self.IVORY).pack(anchor="w")
        ttk.Label(
            main,
            text="Engine evaluation + AI narration for any chess game.",
            foreground="#D8C9A0", font=("Constantia", 11, "italic"),
        ).pack(anchor="w", pady=(0, 8))

        # --- Game input ---
        game_box = self._section(main, "♟", "Game")
        game_box.pack(fill="x", **pad)
        row = ttk.Frame(game_box)
        row.pack(fill="x")
        ttk.Label(row, text="PGN file:").pack(side="left")
        self.pgn_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.pgn_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row, text="Browse…", command=self._browse_pgn).pack(side="left")

        # --- Options ---
        opt = self._section(main, "♞", "Options")
        opt.pack(fill="x", **pad)
        grid = ttk.Frame(opt)
        grid.pack(fill="x")
        ttk.Label(grid, text="Report style:").grid(row=0, column=0, sticky="w", pady=3)
        self.usecase_var = tk.StringVar(value="companion")
        ttk.Combobox(grid, textvariable=self.usecase_var, values=USE_CASES, state="readonly", width=16).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(grid, text="I played as:").grid(row=0, column=2, sticky="w", padx=(16, 0))
        self.side_var = tk.StringVar(value="Neither")
        ttk.Combobox(grid, textvariable=self.side_var, values=SIDES, state="readonly", width=10).grid(row=0, column=3, sticky="w", padx=6)
        ttk.Label(grid, text="Engine speed:").grid(row=1, column=0, sticky="w", pady=3)
        self.speed_var = tk.StringVar(value="Normal (0.8s/move)")
        ttk.Combobox(grid, textvariable=self.speed_var, values=list(SPEED_LABELS), state="readonly", width=16).grid(row=1, column=1, sticky="w", padx=6)
        noterow = ttk.Frame(opt)
        noterow.pack(fill="x", pady=(6, 0))
        ttk.Label(noterow, text="Note (optional):").pack(side="left")
        self.note_var = tk.StringVar()
        ttk.Entry(noterow, textvariable=self.note_var).pack(side="left", fill="x", expand=True, padx=6)

        ctxrow1 = ttk.Frame(opt)
        ctxrow1.pack(fill="x", pady=(4, 0))
        ttk.Label(ctxrow1, text="Audience level:").pack(side="left")
        self.audience_var = tk.StringVar(value=AUDIENCE_LEVELS[0])
        ttk.Combobox(ctxrow1, textvariable=self.audience_var, values=AUDIENCE_LEVELS,
                     state="readonly", width=14).pack(side="left", padx=6)
        ttk.Label(ctxrow1, text="Report is for (recipient):").pack(side="left", padx=(12, 0))
        self.recipient_var = tk.StringVar()
        ttk.Entry(ctxrow1, textvariable=self.recipient_var).pack(side="left", fill="x", expand=True, padx=6)

        ctxrow2 = ttk.Frame(opt)
        ctxrow2.pack(fill="x", pady=(4, 0))
        ttk.Label(ctxrow2, text="White context:").pack(side="left")
        self.white_ctx_var = tk.StringVar()
        ttk.Entry(ctxrow2, textvariable=self.white_ctx_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Label(ctxrow2, text="Black context:").pack(side="left", padx=(6, 0))
        self.black_ctx_var = tk.StringVar()
        ttk.Entry(ctxrow2, textvariable=self.black_ctx_var).pack(side="left", fill="x", expand=True, padx=6)

        # --- Setup (persistent config, falls back to environment variables) ---
        adv = self._section(main, "♜", "Setup")
        adv.pack(fill="x", **pad)

        LW = 16  # label column width (chars) — keeps entry fields aligned

        erow = ttk.Frame(adv)
        erow.pack(fill="x", pady=2)
        ttk.Label(erow, text="Stockfish path:", width=LW, anchor="w").pack(side="left")
        self.engine_var = tk.StringVar(
            value=cfg.get("stockfish_path") or os.environ.get("STOCKFISH_PATH", "")
        )
        ttk.Entry(erow, textvariable=self.engine_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(erow, text="Browse…", command=self._browse_engine).pack(side="left")

        krow = ttk.Frame(adv)
        krow.pack(fill="x", pady=2)
        ttk.Label(krow, text="Anthropic API key:", width=LW, anchor="w").pack(side="left")
        self.key_var = tk.StringVar(
            value=cfg.get("api_key") or os.environ.get("ANTHROPIC_API_KEY", "")
        )
        ttk.Entry(krow, textvariable=self.key_var, show="•").pack(side="left", fill="x", expand=True, padx=6)

        mrow = ttk.Frame(adv)
        mrow.pack(fill="x", pady=2)
        ttk.Label(mrow, text="Model:", width=LW, anchor="w").pack(side="left")
        self.model_var = tk.StringVar(value=cfg.get("model", MODELS[0]))
        ttk.Combobox(
            mrow, textvariable=self.model_var, values=MODELS, state="readonly", width=24
        ).pack(side="left", padx=6)

        rrow = ttk.Frame(adv)
        rrow.pack(fill="x", pady=2)
        ttk.Label(rrow, text="Reports folder:", width=LW, anchor="w").pack(side="left")
        self.reports_var = tk.StringVar(
            value=cfg.get("reports_dir") or os.environ.get("GRECO_REPORTS_DIR", "")
        )
        ttk.Entry(rrow, textvariable=self.reports_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(rrow, text="Browse…", command=self._browse_reports).pack(side="left")

        prow = ttk.Frame(adv)
        prow.pack(fill="x", pady=2)
        ttk.Label(prow, text="Pick PGNs from:", width=LW, anchor="w").pack(side="left")
        self.pgn_dir_var = tk.StringVar(value=cfg.get("pgn_dir") or default_pgn_dir())
        ttk.Entry(prow, textvariable=self.pgn_dir_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(prow, text="Browse…", command=self._browse_pgn_dir).pack(side="left")

        # --- Run ---
        runrow = ttk.Frame(main)
        runrow.pack(fill="x", **pad)
        self.analyze_btn = ttk.Button(runrow, text="Analyze game", command=self._on_analyze,
                                      style="Primary.TButton")
        self.analyze_btn.pack(side="left")
        self.progress = ttk.Progressbar(runrow, mode="determinate", length=260)
        self.progress.pack(side="left", padx=12, fill="x", expand=True)
        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(main, textvariable=self.status_var, foreground=self.GOLD).pack(anchor="w", padx=8)

        # --- Post-run actions (enabled once a report has been produced) ---
        actionrow = ttk.Frame(main)
        actionrow.pack(fill="x", **pad)
        self.open_report_btn = ttk.Button(
            actionrow, text="Open report", command=self._open_report, state="disabled"
        )
        self.open_report_btn.pack(side="left")
        self.open_folder_btn = ttk.Button(
            actionrow, text="Open report folder", command=self._open_folder, state="disabled"
        )
        self.open_folder_btn.pack(side="left", padx=6)
        self.export_btn = ttk.Button(
            actionrow, text="Export for email (single file)",
            command=self._export_shareable, state="disabled",
        )
        self.export_btn.pack(side="left", padx=6)

        # --- Log / live narrative ---
        self.log = scrolledtext.ScrolledText(
            main, height=14, wrap="word", font=("Constantia", 11),
            bg=self.PARCH, fg=self.INK, insertbackground=self.INK,
            selectbackground=self.WINE, selectforeground=self.IVORY,
            relief="solid", borderwidth=1,
        )
        self.log.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        self.log.configure(state="disabled")

    # ---------- input helpers ----------
    def _browse_pgn(self):
        chosen = self.pgn_dir_var.get().strip()
        initial = chosen if os.path.isdir(chosen) else default_pgn_dir()
        path = filedialog.askopenfilename(
            title="Choose a PGN file",
            initialdir=initial,
            filetypes=[("PGN files", "*.pgn"), ("All files", "*.*")],
        )
        if path:
            self.pgn_var.set(path)

    def _browse_pgn_dir(self):
        path = filedialog.askdirectory(
            title="Choose the default folder to pick PGNs from",
            initialdir=self.pgn_dir_var.get().strip() or default_pgn_dir(),
        )
        if path:
            self.pgn_dir_var.set(path)

    def _browse_engine(self):
        path = filedialog.askopenfilename(
            title="Locate the Stockfish executable",
            filetypes=[("Executable", "*.exe"), ("All files", "*.*")],
        )
        if path:
            self.engine_var.set(path)

    def _browse_reports(self):
        path = filedialog.askdirectory(title="Choose reports output folder")
        if path:
            self.reports_var.set(path)

    def _log(self, text: str):
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    # ---------- post-run actions ----------
    def _open_report(self):
        if self._last_html:
            try:
                open_report_in_browser(self._last_html)
            except Exception:
                messagebox.showinfo("Greco", f"Report:\n{self._last_html}")

    def _open_folder(self):
        if self._last_dir:
            try:
                os.startfile(self._last_dir)  # Windows: reveal in File Explorer
            except Exception:
                messagebox.showinfo("Greco", f"Report folder:\n{self._last_dir}")

    def _export_shareable(self):
        """Bundle the finished report into ONE self-contained .html for emailing.

        Reuses outputs.export_shareable_html (the shared core), so the desktop and
        web front-ends produce identical export files. The export sits next to the
        report, clearly named '<name> (shareable).html'; the originals are untouched.
        """
        if not self._last_html:
            return
        try:
            out = export_shareable_html(self._last_html)
        except Exception as exc:
            messagebox.showerror("Greco", f"Could not create the shareable file:\n{exc}")
            return
        self._log(f"\n\U0001F4E4 Shareable single-file report:\n{out}\n")
        try:
            os.startfile(str(out.parent))  # open the folder so the file is easy to attach
        except Exception:
            pass
        messagebox.showinfo(
            "Greco",
            "Created a single self-contained HTML you can email as one attachment:\n\n"
            f"{out.name}\n\n"
            "It's in the report folder that just opened — drag it straight into an email.",
        )

    # ---------- run ----------
    def _on_analyze(self):
        if self.running:
            return
        pgn_path = self.pgn_var.get().strip()
        engine = self.engine_var.get().strip()
        key = self.key_var.get().strip()
        if not pgn_path or not os.path.isfile(pgn_path):
            messagebox.showerror("Greco", "Please choose a valid PGN file.")
            return
        if not engine or not os.path.isfile(engine):
            messagebox.showerror("Greco", "Please set a valid Stockfish executable path.")
            return
        if not key:
            messagebox.showerror("Greco", "Please enter your Anthropic API key.")
            return

        model = self.model_var.get().strip() or MODELS[0]
        reports_dir = self.reports_var.get().strip()

        # Persist settings so they survive restarts.
        save_config({
            "stockfish_path": engine,
            "api_key": key,
            "model": model,
            "reports_dir": reports_dir,
            "pgn_dir": self.pgn_dir_var.get().strip(),
        })

        os.environ["ANTHROPIC_API_KEY"] = key
        if reports_dir:
            os.environ["GRECO_REPORTS_DIR"] = reports_dir

        self.running = True
        self.analyze_btn.configure(state="disabled")
        self.open_report_btn.configure(state="disabled")
        self.open_folder_btn.configure(state="disabled")
        self.export_btn.configure(state="disabled")
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)
        self.status_var.set("Starting…")
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

        side = self.side_var.get().lower()
        audience_raw = self.audience_var.get()
        params = {
            "pgn_path": pgn_path,
            "engine": engine,
            "use_case": self.usecase_var.get(),
            "user_is": side if side in ("white", "black") else "neither",
            "note": self.note_var.get().strip() or None,
            "time_limit": SPEED_LABELS.get(self.speed_var.get(), 0.8),
            "model": model,
            "audience_level": audience_raw if audience_raw != AUDIENCE_LEVELS[0] else None,
            "recipient": self.recipient_var.get().strip() or None,
            "white_context": self.white_ctx_var.get().strip() or None,
            "black_context": self.black_ctx_var.get().strip() or None,
        }
        threading.Thread(target=self._worker, args=(params,), daemon=True).start()
        self.root.after(100, self._poll)

    def _worker(self, p: dict):
        try:
            pgn_text, src = load_pgn(p["pgn_path"])
            self.q.put(("status", f"Loaded {src}"))
            self.q.put(("status", "Analyzing positions with Stockfish…"))
            game = analyze_pgn(
                pgn_text,
                engine_path=p["engine"],
                time_limit=p["time_limit"],
                progress_cb=lambda d, t: self.q.put(("progress", d, t)),
            )
            user_context = {
                "white_player": p.get("white_context"),
                "black_player": p.get("black_context"),
                "user_is": p["user_is"],
                "player_named": bool(p.get("white_context") or p.get("black_context")),
            }
            self.q.put(("status", "Assigning commentary tiers…"))
            tiers = annotate_with_tiers(game, user_context)
            self.q.put(("status", f"Writing the report ({p['use_case']} voice, {p['model']})…"))
            narrative = generate_narrative(
                game,
                tiers,
                user_context,
                use_case=p["use_case"],
                user_note=p["note"],
                model=p["model"],
                live_stream_to=_QueueWriter(self.q),
                source_path=p["pgn_path"],
                audience_level=p.get("audience_level"),
                recipient=p.get("recipient"),
            )
            # Name the report informatively ("White vs. Black, Blitz, 2024") and
            # save it under the E: reports library (falls back to Documents).
            base = report_basename(game)
            out_dir = default_reports_dir() / base
            md_path = out_dir / f"{base}.md"
            self.q.put(("status", "Rendering boards and assembling the report…"))
            assemble_report(
                game,
                tiers,
                narrative,
                output_md=md_path,
                boards_at="tier3",
                render_eval_graph=True,
                flipped_for_black=(p["user_is"] == "black"),
            )
            html_path = markdown_to_html(
                md_path, game=game, flipped=(p["user_is"] == "black")
            )
            self.q.put(("done", str(html_path)))
            # Developer-only (GRECO_DEV): quietly refill the test pool with a
            # similar game so the developer never runs out of games to test on.
            if os.environ.get("GRECO_DEV"):
                threading.Thread(target=self._dev_fetch_similar,
                                 args=(p["pgn_path"],), daemon=True).start()
        except Exception as exc:
            self.q.put(("error", f"{exc}\n\n{traceback.format_exc()}"))

    def _dev_fetch_similar(self, pgn_path):
        """Developer mode only: pull one similar game so the test pool refills.
        Silent and best-effort — never affects a normal run."""
        try:
            from tools.find_games import fetch_similar
            fetch_similar(pgn_path, max_games=1)
        except Exception:
            pass

    def _poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "progress":
                    done, total = msg[1], msg[2]
                    if self.progress["mode"] != "determinate":
                        self.progress.stop()
                        self.progress.configure(mode="determinate", maximum=total)
                    self.progress["value"] = done
                    self.status_var.set(f"Engine: analyzing position {done}/{total}")
                elif kind == "status":
                    self.status_var.set(msg[1])
                    self._log(f"• {msg[1]}\n")
                elif kind == "narrative":
                    self._log(msg[1])
                elif kind == "done":
                    self._finish_ok(msg[1])
                    return
                elif kind == "error":
                    self._finish_err(msg[1])
                    return
        except queue.Empty:
            pass
        if self.running:
            self.root.after(100, self._poll)

    def _reset_controls(self):
        self.running = False
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.progress["value"] = 0
        self.analyze_btn.configure(state="normal")

    def _finish_ok(self, html_path: str):
        self._reset_controls()
        self._last_html = html_path
        self._last_dir = str(Path(html_path).parent)
        self.open_report_btn.configure(state="normal")
        self.open_folder_btn.configure(state="normal")
        self.export_btn.configure(state="normal")
        self.status_var.set("Done — report opened in your browser.")
        self._log(f"\n\n✅ Report saved to:\n{html_path}\nOpening in Chrome…\n")
        try:
            open_report_in_browser(html_path)
        except Exception:
            messagebox.showinfo("Greco", f"Report saved to:\n{html_path}")

    def _finish_err(self, detail: str):
        self._reset_controls()
        self.status_var.set("Error — see the log below.")
        self._log(f"\n\n❌ Something went wrong:\n{detail}\n")
        messagebox.showerror("Greco — error", detail.splitlines()[0] if detail else "Unknown error")


def main():
    # Tell Windows this is its own app (a distinct AppUserModelID) so the taskbar
    # shows the Greco icon instead of grouping under the generic Python icon.
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Greco.ChessAnalyzer.1")
    except Exception:
        pass

    root = tk.Tk()
    try:
        root.iconbitmap(default=str(ICON_PATH))  # Greco logo: title bar + taskbar
    except Exception:
        pass
    GrecoGUI(root)
    root.mainloop()


if __name__ == "__main__":
    # Launched windowed (pythonw, no console), so make startup failures visible:
    # log them to a file and show a dialog instead of dying silently.
    try:
        main()
    except Exception:
        import traceback
        _err = traceback.format_exc()
        try:
            (Path(__file__).resolve().parent / "greco_startup_error.log").write_text(
                _err, encoding="utf-8"
            )
        except Exception:
            pass
        try:
            from tkinter import messagebox
            messagebox.showerror("Greco failed to start", _err)
        except Exception:
            pass
        raise
