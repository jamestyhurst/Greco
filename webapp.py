"""
Greco Web — Phase 1 of the "Greco Online" roadmap.

A tiny local Flask server that runs the EXISTING Greco pipeline from your browser:
open a page on your own computer, upload a PGN (or paste one), click Analyze, and
get back the same self-contained HTML report the desktop app produces.

Why this is safe to add (it does not touch the rest of Greco):
  * It adds NO analysis logic. It imports and calls the very same functions
    gui.py and main.py use: importers -> analyzer -> triage -> narrator -> outputs.
  * It READS the same config.json the desktop settings panel WRITES (engine path,
    API key, model, reports folder) and never writes to it, so your settings are
    safe. If Greco already works on the desktop, this works with no extra setup.
  * It writes reports to the SAME "Greco Reports" folder as the desktop app.
  * It binds to 127.0.0.1 only, so it is reachable just from this machine and the
    API key stays server-side.
gui.py, main.py and Greco.exe keep working exactly as before.

Run it:    python webapp.py            (or double-click run_greco_web.bat)
Open it:   http://127.0.0.1:5000
Stop it:   Ctrl+C in the console window.

Roadmap note: Phase 1 runs the analysis synchronously — the page waits while
Stockfish + Claude work (a minute or two). Phase 2 ("async jobs + status page")
replaces that wait with a live progress page; Phase 7 swaps this localhost dev
server for a real host. See docs/ROADMAP.md.
"""
from __future__ import annotations

import json
import os
import tempfile
import traceback
from pathlib import Path

from flask import Flask, request, render_template_string, send_file, url_for, abort

# The Greco pipeline — identical to what the desktop GUI and CLI call.
from importers import load_pgn
from analyzer import analyze_pgn
from triage import annotate_with_tiers
from narrator import generate_narrative
from outputs import assemble_report, markdown_to_html, report_basename, default_reports_dir
from version import __version__

GRECO_DIR = Path(__file__).resolve().parent
CONFIG_PATH = GRECO_DIR / "config.json"

# Mirror the desktop GUI's option lists so both front-ends behave the same.
SPEED_LABELS = {"fast": 0.5, "normal": 0.8, "deep": 1.5}
USE_CASES = ["companion", "coaching", "commentary"]
MODELS = ["claude-sonnet-4-6", "claude-opus-4-8", "claude-fable-5"]

# Ephemeral map of report-id -> absolute .html path. Integer ids keep report
# links pure-ASCII (the reports folder path contains non-ASCII characters).
# Cleared on restart — fine for a single-user localhost tool; Phase 4 (database)
# is what makes reports durably addressable.
_REPORTS = {}
_NEXT_ID = [1]


def load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def resolve_settings() -> dict:
    """Read engine path, API key, model and reports folder from config.json — the
    same file the desktop settings panel writes — falling back to environment
    variables, exactly as tools/style_ab_test.py does. Applies the env vars the
    pipeline expects so reports land in the same folder as the desktop app."""
    cfg = load_config()
    engine = cfg.get("stockfish_path") or os.environ.get("STOCKFISH_PATH") or ""
    api_key = cfg.get("api_key") or os.environ.get("ANTHROPIC_API_KEY") or ""
    model = cfg.get("model") or "claude-sonnet-4-6"
    reports_dir = cfg.get("reports_dir") or os.environ.get("GRECO_REPORTS_DIR") or ""
    if api_key:
        os.environ["ANTHROPIC_API_KEY"] = api_key
    if reports_dir:
        # so outputs.default_reports_dir() writes to the same place as the GUI
        os.environ["GRECO_REPORTS_DIR"] = reports_dir
    return {
        "engine": engine,
        "api_key": api_key,
        "model": model if model in MODELS else (model or "claude-sonnet-4-6"),
        "reports_dir": reports_dir,
        "engine_ok": bool(engine) and os.path.isfile(engine),
        "key_ok": bool(api_key),
    }


def _save_uploaded_pgn(req) -> "Path | None":
    """Save the uploaded file or pasted text to a temp .pgn and return its path,
    or None if neither was provided. Caller deletes the temp file."""
    f = req.files.get("pgn_file")
    if f and f.filename:
        data = f.read()
        if data.strip():
            fd, tmp = tempfile.mkstemp(suffix=".pgn")
            os.close(fd)
            Path(tmp).write_bytes(data)
            return Path(tmp)
    text = (req.form.get("pgn_text") or "").strip()
    if text:
        fd, tmp = tempfile.mkstemp(suffix=".pgn")
        os.close(fd)
        Path(tmp).write_text(text, encoding="utf-8")
        return Path(tmp)
    return None


app = Flask(__name__)
resolve_settings()  # apply env vars once at startup


BASE_CSS = """
:root{--ink:#1a202c;--muted:#718096;--accent:#2b6cb0;--line:#e2e8f0;--bg:#f7fafc;}
*{box-sizing:border-box;}
body{margin:0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:var(--ink);background:var(--bg);line-height:1.5;}
.wrap{max-width:640px;margin:0 auto;padding:24px 16px 64px;}
h1{font-size:1.5rem;margin:0 0 4px;}
.sub{color:var(--muted);margin:0 0 20px;font-size:.95rem;}
.card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:18px;}
label{display:block;font-weight:600;margin:14px 0 6px;font-size:.9rem;}
input[type=file],textarea,select,input[type=text]{width:100%;padding:10px;border:1px solid var(--line);border-radius:8px;font-size:1rem;font-family:inherit;background:#fff;}
textarea{min-height:110px;resize:vertical;font-family:Consolas,monospace;font-size:.85rem;}
.row{display:flex;gap:12px;flex-wrap:wrap;}
.row>div{flex:1;min-width:140px;}
.or{text-align:center;color:var(--muted);margin:10px 0;font-size:.85rem;}
button{margin-top:20px;width:100%;padding:13px;font-size:1.05rem;font-weight:600;color:#fff;background:var(--accent);border:0;border-radius:8px;cursor:pointer;}
button:disabled{opacity:.6;cursor:progress;}
.btn{display:block;text-align:center;padding:12px;border-radius:8px;font-weight:600;text-decoration:none;}
.btn.go{color:#fff;background:var(--accent);}
.btn.alt{color:var(--accent);background:#fff;border:1px solid var(--accent);}
.banner{padding:10px 12px;border-radius:8px;font-size:.9rem;margin-bottom:16px;}
.ok{background:#f0fff4;border:1px solid #9ae6b4;color:#22543d;}
.warn{background:#fffaf0;border:1px solid #fbd38d;color:#7b341e;}
.hint{color:var(--muted);font-size:.82rem;margin-top:6px;}
.foot{color:var(--muted);font-size:.78rem;margin-top:18px;text-align:center;}
pre{white-space:pre-wrap;background:#1a202c;color:#e2e8f0;padding:14px;border-radius:8px;font-size:.8rem;overflow:auto;}
#overlay{display:none;position:fixed;inset:0;background:rgba(247,250,252,.94);align-items:center;justify-content:center;text-align:center;padding:24px;}
#overlay.show{display:flex;}
"""

FORM_PAGE = """<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Greco Web {{ version }}</title><style>{{ base_css|safe }}</style></head><body>
<div class="wrap">
  <h1>&#9823; Greco Web</h1>
  <p class="sub">Engine-backed, AI-narrated chess reports &mdash; in your browser. v{{ version }}</p>
  {% if ready %}
    <div class="banner ok">Ready &mdash; using your saved settings (model: {{ model }}). Reports save to your Greco Reports folder.</div>
  {% else %}
    <div class="banner warn">Not set up yet. Open the Greco <b>desktop app &rarr; settings</b> and set your Stockfish path and Anthropic API key once; this page reads the same settings.
      {% if not engine_ok %}<br>&bull; Stockfish path missing or invalid.{% endif %}
      {% if not key_ok %}<br>&bull; Anthropic API key missing.{% endif %}
    </div>
  {% endif %}
  <form class="card" method="post" action="{{ url_for('analyze') }}" enctype="multipart/form-data"
        onsubmit="document.getElementById('overlay').classList.add('show');document.getElementById('go').disabled=true;">
    <label>Upload a PGN file</label>
    <input type="file" name="pgn_file" accept=".pgn,.txt">
    <div class="or">&mdash; or &mdash;</div>
    <label>Paste PGN text</label>
    <textarea name="pgn_text" placeholder="[Event &quot;...&quot;]&#10;1. e4 e5 2. Nf3 Nc6 ..."></textarea>
    <div class="row">
      <div><label>Voice</label><select name="use_case">{% for u in use_cases %}<option value="{{ u }}">{{ u }}</option>{% endfor %}</select></div>
      <div><label>You played</label><select name="side"><option value="neither">neither</option><option value="white">white</option><option value="black">black</option></select></div>
    </div>
    <div class="row">
      <div><label>Engine depth</label><select name="speed"><option value="fast">Fast (0.5s/move)</option><option value="normal" selected>Normal (0.8s/move)</option><option value="deep">Deep (1.5s/move)</option></select></div>
      <div><label>Model</label><select name="model">{% for m in models %}<option value="{{ m }}"{% if m==model %} selected{% endif %}>{{ m }}</option>{% endfor %}</select></div>
    </div>
    <label>Note for Greco (optional)</label>
    <input type="text" name="note" placeholder="e.g. I'm proud of the queen sacrifice">
    <button id="go" type="submit">Analyze game</button>
    <p class="hint">Runs on your computer. Analysis takes ~1&ndash;3 minutes; keep this tab open.</p>
  </form>
  <p class="foot">Greco Online &middot; Phase 1 (local Flask). Desktop app, CLI and Greco.exe are unaffected.</p>
</div>
<div id="overlay"><div><h2>Analyzing&hellip;</h2>
  <p class="sub">Stockfish is evaluating every move and Claude is writing the report.<br>This can take a minute or two &mdash; keep this tab open.</p></div></div>
</body></html>"""

RESULT_PAGE = """<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ base }} &mdash; Greco</title><style>{{ base_css|safe }}</style></head><body>
<div class="wrap">
  <div class="banner ok">&#10003; Report ready &mdash; {{ base }}</div>
  <div class="row">
    <div><a class="btn go" href="{{ url_for('report', rid=rid) }}" target="_blank">Open report &#8599;</a></div>
    <div><a class="btn alt" href="{{ url_for('index') }}">Analyze another game</a></div>
  </div>
  <p class="hint">Saved to: {{ saved_dir }}</p>
  <iframe src="{{ url_for('report', rid=rid) }}" style="width:100%;height:78vh;border:1px solid var(--line);border-radius:12px;margin-top:16px;background:#fff;"></iframe>
</div></body></html>"""

ERROR_PAGE = """<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Greco &mdash; problem</title><style>{{ base_css|safe }}</style></head><body>
<div class="wrap">
  <div class="banner warn">{{ message }}</div>
  <p><a class="btn alt" href="{{ url_for('index') }}">&larr; Back</a></p>
  {% if detail %}<pre>{{ detail }}</pre>{% endif %}
</div></body></html>"""


@app.route("/")
def index():
    s = resolve_settings()
    return render_template_string(
        FORM_PAGE, base_css=BASE_CSS, version=__version__,
        ready=(s["engine_ok"] and s["key_ok"]),
        engine_ok=s["engine_ok"], key_ok=s["key_ok"],
        model=s["model"], use_cases=USE_CASES, models=MODELS,
    )


@app.route("/analyze", methods=["POST"])
def analyze():
    s = resolve_settings()
    if not (s["engine_ok"] and s["key_ok"]):
        return render_template_string(
            ERROR_PAGE, base_css=BASE_CSS, detail="",
            message="Stockfish path or API key not set. Open the desktop app's settings once, then reload.",
        ), 400

    pgn_path = _save_uploaded_pgn(request)
    if pgn_path is None:
        return render_template_string(
            ERROR_PAGE, base_css=BASE_CSS, detail="",
            message="Please upload a PGN file or paste PGN text.",
        ), 400

    use_case = request.form.get("use_case", "companion")
    if use_case not in USE_CASES:
        use_case = "companion"
    side = (request.form.get("side") or "neither").lower()
    user_is = side if side in ("white", "black") else "neither"
    flipped = user_is == "black"
    time_limit = SPEED_LABELS.get(request.form.get("speed", "normal"), 0.8)
    model = request.form.get("model") or s["model"]
    if model not in MODELS:
        model = s["model"]
    note = (request.form.get("note") or "").strip() or None

    try:
        # Identical pipeline to gui.py's _worker — no analysis logic added here.
        pgn_text, _src = load_pgn(str(pgn_path))
        game = analyze_pgn(pgn_text, engine_path=s["engine"], time_limit=time_limit)
        user_context = {"white_player": None, "black_player": None,
                        "user_is": user_is, "player_named": False}
        tiers = annotate_with_tiers(game, user_context)
        narrative = generate_narrative(
            game, tiers, user_context, use_case=use_case,
            user_note=note, model=model, live_stream_to=None,
        )
        base = report_basename(game)
        out_dir = default_reports_dir() / base
        out_dir.mkdir(parents=True, exist_ok=True)
        md_path = out_dir / f"{base}.md"
        assemble_report(game, tiers, narrative, output_md=md_path,
                        boards_at="tier3", render_eval_graph=True,
                        flipped_for_black=flipped)
        html_path = markdown_to_html(md_path, game=game, flipped=flipped)
    except Exception:
        return render_template_string(
            ERROR_PAGE, base_css=BASE_CSS, message="Analysis failed.",
            detail=traceback.format_exc(),
        ), 500
    finally:
        try:
            pgn_path.unlink()
        except Exception:
            pass

    rid = _NEXT_ID[0]
    _NEXT_ID[0] += 1
    _REPORTS[rid] = str(Path(html_path).resolve())
    return render_template_string(
        RESULT_PAGE, base_css=BASE_CSS, base=base, rid=rid, saved_dir=str(out_dir),
    )


@app.route("/report/<int:rid>")
def report(rid: int):
    path = _REPORTS.get(rid)
    if not path:
        abort(404)
    p = Path(path).resolve()
    reports_root = default_reports_dir().resolve()
    # Only ever serve a .html file that lives inside the reports folder.
    if p.suffix.lower() != ".html" or reports_root not in p.parents or not p.is_file():
        abort(404)
    return send_file(str(p))


if __name__ == "__main__":
    s = resolve_settings()
    print(f"Greco Web {__version__} — open http://127.0.0.1:5000 in your browser.")
    if not (s["engine_ok"] and s["key_ok"]):
        print("  Heads up: Stockfish path or API key not set — open the desktop app's settings once.")
    print("  Press Ctrl+C to stop.")
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
