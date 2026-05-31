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

import os
import queue
import re
import threading
import traceback
import webbrowser
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from importers import load_pgn
from analyzer import analyze_pgn
from triage import annotate_with_tiers
from narrator import generate_narrative
from outputs import assemble_report, markdown_to_html, report_basename, default_reports_dir
from version import __version__


SPEED_LABELS = {"Fast (0.5s/move)": 0.5, "Normal (0.8s/move)": 0.8, "Deep (1.5s/move)": 1.5}
USE_CASES = ["companion", "coaching", "commentary"]
SIDES = ["White", "Black", "Neither"]

# Preferred place to look for PGNs (the E: library), with a sensible fallback.
PGN_LIBRARY = r"E:\Chess\PGNs"

# Greco app icon (window title bar + taskbar).
ICON_PATH = Path(__file__).resolve().parent / "assets" / "greco.ico"


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
    def __init__(self, root: tk.Tk):
        self.root = root
        self.q: "queue.Queue" = queue.Queue()
        self.running = False
        self._last_html = None   # path of the most recent report (for the buttons)
        self._last_dir = None
        root.title(f"Greco {__version__} — Chess Game Analyzer")
        root.geometry("760x640")
        root.minsize(640, 560)

        pad = {"padx": 8, "pady": 4}
        main = ttk.Frame(root, padding=10)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text="Greco", font=("Helvetica", 18, "bold")).pack(anchor="w")
        ttk.Label(
            main,
            text="Engine evaluation + AI narration for any chess game.",
            foreground="#555",
        ).pack(anchor="w", pady=(0, 8))

        # --- Game input ---
        game_box = ttk.LabelFrame(main, text="Game", padding=8)
        game_box.pack(fill="x", **pad)
        row = ttk.Frame(game_box)
        row.pack(fill="x")
        ttk.Label(row, text="PGN file:").pack(side="left")
        self.pgn_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.pgn_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row, text="Browse…", command=self._browse_pgn).pack(side="left")

        # --- Options ---
        opt = ttk.LabelFrame(main, text="Options", padding=8)
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

        # --- Advanced (engine path + API key, prefilled from environment) ---
        adv = ttk.LabelFrame(main, text="Setup (auto-filled from your environment)", padding=8)
        adv.pack(fill="x", **pad)
        erow = ttk.Frame(adv)
        erow.pack(fill="x", pady=2)
        ttk.Label(erow, text="Stockfish path:").pack(side="left")
        self.engine_var = tk.StringVar(value=os.environ.get("STOCKFISH_PATH", ""))
        ttk.Entry(erow, textvariable=self.engine_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(erow, text="Browse…", command=self._browse_engine).pack(side="left")
        krow = ttk.Frame(adv)
        krow.pack(fill="x", pady=2)
        ttk.Label(krow, text="Anthropic API key:").pack(side="left")
        self.key_var = tk.StringVar(value=os.environ.get("ANTHROPIC_API_KEY", ""))
        ttk.Entry(krow, textvariable=self.key_var, show="•").pack(side="left", fill="x", expand=True, padx=6)

        # --- Run ---
        runrow = ttk.Frame(main)
        runrow.pack(fill="x", **pad)
        self.analyze_btn = ttk.Button(runrow, text="Analyze game", command=self._on_analyze)
        self.analyze_btn.pack(side="left")
        self.progress = ttk.Progressbar(runrow, mode="determinate", length=260)
        self.progress.pack(side="left", padx=12, fill="x", expand=True)
        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(main, textvariable=self.status_var, foreground="#2b6cb0").pack(anchor="w", padx=8)

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

        # --- Log / live narrative ---
        self.log = scrolledtext.ScrolledText(main, height=14, wrap="word", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        self.log.configure(state="disabled")

    # ---------- input helpers ----------
    def _browse_pgn(self):
        initial = PGN_LIBRARY if os.path.isdir(PGN_LIBRARY) else str(Path.home())
        path = filedialog.askopenfilename(
            title="Choose a PGN file",
            initialdir=initial,
            filetypes=[("PGN files", "*.pgn"), ("All files", "*.*")],
        )
        if path:
            self.pgn_var.set(path)

    def _browse_engine(self):
        path = filedialog.askopenfilename(
            title="Locate the Stockfish executable",
            filetypes=[("Executable", "*.exe"), ("All files", "*.*")],
        )
        if path:
            self.engine_var.set(path)

    def _log(self, text: str):
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    # ---------- post-run actions ----------
    def _open_report(self):
        if self._last_html:
            try:
                webbrowser.open(Path(self._last_html).as_uri())
            except Exception:
                messagebox.showinfo("Greco", f"Report:\n{self._last_html}")

    def _open_folder(self):
        if self._last_dir:
            try:
                os.startfile(self._last_dir)  # Windows: reveal in File Explorer
            except Exception:
                messagebox.showinfo("Greco", f"Report folder:\n{self._last_dir}")

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
        os.environ["ANTHROPIC_API_KEY"] = key  # for this session

        self.running = True
        self.analyze_btn.configure(state="disabled")
        self.open_report_btn.configure(state="disabled")
        self.open_folder_btn.configure(state="disabled")
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)
        self.status_var.set("Starting…")
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

        side = self.side_var.get().lower()
        params = {
            "pgn_path": pgn_path,
            "engine": engine,
            "use_case": self.usecase_var.get(),
            "user_is": side if side in ("white", "black") else "neither",
            "note": self.note_var.get().strip() or None,
            "time_limit": SPEED_LABELS.get(self.speed_var.get(), 0.8),
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
                "white_player": None,
                "black_player": None,
                "user_is": p["user_is"],
                "player_named": False,
            }
            self.q.put(("status", "Assigning commentary tiers…"))
            tiers = annotate_with_tiers(game, user_context)
            self.q.put(("status", f"Writing the report with Claude ({p['use_case']} voice)…"))
            narrative = generate_narrative(
                game,
                tiers,
                user_context,
                use_case=p["use_case"],
                user_note=p["note"],
                live_stream_to=_QueueWriter(self.q),
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
            html_path = markdown_to_html(md_path)
            self.q.put(("done", str(html_path)))
        except Exception as exc:
            self.q.put(("error", f"{exc}\n\n{traceback.format_exc()}"))

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
        self.status_var.set("Done — report opened in your browser.")
        self._log(f"\n\n✅ Report saved to:\n{html_path}\nOpening in your browser…\n")
        try:
            webbrowser.open(Path(html_path).as_uri())
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
