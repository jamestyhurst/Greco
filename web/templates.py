"""HTML pages for Greco Web (server-rendered with Jinja2).

Carried over from the Flask version's pages, with Flask `url_for(...)` calls
replaced by plain paths. Phase 4A formalises these into a `templates/` directory;
inlining them keeps Phase 1 a single dependency-light step.
"""
from __future__ import annotations

from jinja2 import Template

from version import __version__
from web.config import Settings, USE_CASES, MODELS

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

_FORM = Template("""<!doctype html><html lang="en"><head>
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
  <form class="card" method="post" action="/analyze" enctype="multipart/form-data"
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
  <p class="foot">Greco Online &middot; Phase 1 (local FastAPI). Interactive API docs at <a href="/docs">/docs</a>. Desktop app, CLI and Greco.exe are unaffected.</p>
</div>
<div id="overlay"><div><h2>Analyzing&hellip;</h2>
  <p class="sub">Stockfish is evaluating every move and Claude is writing the report.<br>This can take a minute or two &mdash; keep this tab open.</p></div></div>
</body></html>""")

_RESULT = Template("""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ base }} &mdash; Greco</title><style>{{ base_css|safe }}</style></head><body>
<div class="wrap">
  <div class="banner ok">&#10003; Report ready &mdash; {{ base }}</div>
  <div class="row">
    <div><a class="btn go" href="/report/{{ rid }}" target="_blank">Open report &#8599;</a></div>
    <div><a class="btn alt" href="/report/{{ rid }}/shareable">Download single file (email) &#11015;</a></div>
    <div><a class="btn alt" href="/">Analyze another game</a></div>
  </div>
  <p class="hint">Saved to: {{ saved_dir }}</p>
  <iframe src="/report/{{ rid }}" style="width:100%;height:78vh;border:1px solid var(--line);border-radius:12px;margin-top:16px;background:#fff;"></iframe>
</div></body></html>""")

_ERROR = Template("""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Greco &mdash; problem</title><style>{{ base_css|safe }}</style></head><body>
<div class="wrap">
  <div class="banner warn">{{ message }}</div>
  <p><a class="btn alt" href="/">&larr; Back</a></p>
  {% if detail %}<pre>{{ detail }}</pre>{% endif %}
</div></body></html>""")


def render_form(s: Settings) -> str:
    return _FORM.render(
        base_css=BASE_CSS, version=__version__, ready=s.ready,
        engine_ok=s.engine_ok, key_ok=s.key_ok, model=s.model,
        use_cases=USE_CASES, models=MODELS,
    )


def render_result(base: str, rid: int, saved_dir: str) -> str:
    return _RESULT.render(base_css=BASE_CSS, base=base, rid=rid, saved_dir=saved_dir)


def render_error(message: str, detail: str = "") -> str:
    return _ERROR.render(base_css=BASE_CSS, message=message, detail=detail)
