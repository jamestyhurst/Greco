# Screenshots

This folder holds the screenshots linked from the top-level `README.md` Quick Start.
They are captured by hand on a machine with Stockfish + an API key configured (CI and
an autonomous agent can't take real app screenshots), so the capture is a quick manual
step. Drop the two PNGs below in here, then add the image links to `README.md`.

## What to capture

1. **`desktop-gui.png`** — the Tkinter desktop app with a game loaded.
   - Launch: double-click the desktop **Greco** icon, or run
     `venv\Scripts\pythonw.exe gui.py` from the repo root.
   - Load a PGN, pick a voice, and capture the main window (the wine/ivory/gold
     manuscript theme + the Setup/Options panel are the things worth showing).

2. **`web-ui.png`** — Greco Web in a browser.
   - Launch: `run_greco_web.bat` (or `venv\Scripts\python.exe -m web.main`), then open
     <http://127.0.0.1:5000>.
   - Capture the upload form, and optionally a second shot of a finished report
     (with a board diagram + the interactive replay viewer).

## Then link them from README.md

Under the Quick Start section, add:

```markdown
![Greco desktop app](screenshots/desktop-gui.png)
![Greco Web](screenshots/web-ui.png)
```

Tracked as roadmap item #15. Keep the images reasonably sized (≲300 KB each); PNG is fine.
