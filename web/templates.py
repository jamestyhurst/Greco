"""HTML pages for Greco Web (server-rendered with Jinja2).

Phase 4 will formalise these into a templates/ directory; inlining keeps
dependency count low for local development. Phase 3 adds login and register
forms plus a per-user header on the main analysis form.
"""
from __future__ import annotations

from typing import Optional

from jinja2 import Template

from version import __version__
from web.config import Settings, USE_CASES, MODELS

BASE_CSS = """
:root{--wine:#7A1C26;--wine-dark:#5E151D;--ivory:#F5EDD4;--parch:#FBF6E7;--gold:#C9A23A;--ink:#3A2A1A;--muted:#8a7a5c;--line:#d9c7a0;}
*{box-sizing:border-box;}
body{margin:0;font-family:'Palatino Linotype',Palatino,Georgia,'Book Antiqua',serif;color:var(--ivory);background:var(--wine);line-height:1.55;}
.wrap{max-width:640px;margin:0 auto;padding:24px 16px 64px;}
h1{font-size:1.95rem;margin:0 0 4px;color:var(--ivory);font-weight:700;letter-spacing:.5px;}
.sub{color:var(--gold);margin:0 0 20px;font-size:.95rem;font-style:italic;}
.card{background:var(--parch);border:1px solid var(--gold);border-radius:10px;padding:18px;color:var(--ink);box-shadow:0 2px 12px rgba(0,0,0,.28);}
label{display:block;font-weight:700;margin:14px 0 6px;font-size:.9rem;color:var(--wine-dark);}
input[type=file],textarea,select,input[type=text]{width:100%;padding:10px;border:1px solid var(--line);border-radius:8px;font-size:1rem;font-family:inherit;background:#fffdf6;color:var(--ink);}
textarea{min-height:110px;resize:vertical;font-family:Consolas,monospace;font-size:.85rem;}
.row{display:flex;gap:12px;flex-wrap:wrap;}
.row>div{flex:1;min-width:140px;}
.or{text-align:center;color:var(--muted);margin:10px 0;font-size:.85rem;}
button{margin-top:20px;width:100%;padding:13px;font-size:1.05rem;font-weight:700;color:var(--wine);background:var(--gold);border:0;border-radius:8px;cursor:pointer;font-family:inherit;}
button:hover{background:#d9b658;}
button:disabled{opacity:.6;cursor:progress;}
.btn{display:block;text-align:center;padding:12px;border-radius:8px;font-weight:700;text-decoration:none;}
.btn.go{color:var(--wine);background:var(--gold);}
.btn.alt{color:var(--wine-dark);background:var(--parch);border:1px solid var(--gold);}
.banner{padding:10px 12px;border-radius:8px;font-size:.9rem;margin-bottom:16px;}
.ok{background:#efe6c8;border:1px solid var(--gold);color:#5b4a1e;}
.warn{background:#f3d9b0;border:1px solid #b9742a;color:#6b3410;}
.hint{color:var(--muted);font-size:.82rem;margin-top:6px;}
.foot{color:#d8c9a0;font-size:.78rem;margin-top:18px;text-align:center;}
pre{white-space:pre-wrap;background:var(--wine-dark);color:var(--ivory);padding:14px;border-radius:8px;font-size:.8rem;overflow:auto;}
#overlay{display:none;position:fixed;inset:0;background:rgba(122,28,38,.95);color:var(--ivory);align-items:center;justify-content:center;text-align:center;padding:24px;}
#overlay.show{display:flex;}
"""

_FORM = Template("""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Greco Web {{ version }}</title><style>{{ base_css|safe }}</style></head><body>
<div class="wrap">
  <h1>&#9818; Greco Web</h1>
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
    <input type="text" name="note" placeholder="e.g. I&rsquo;m proud of the queen sacrifice">
    <div class="row">
      <div>
        <label>Audience level</label>
        <select name="audience_level">
          <option value="">Not specified</option>
          <option value="Beginner">Beginner</option>
          <option value="Casual">Casual</option>
          <option value="Club">Club player</option>
          <option value="Advanced">Advanced</option>
        </select>
      </div>
      <div>
        <label>This report is for (optional)</label>
        <input type="text" name="recipient" placeholder="e.g. my dad, a non-chess friend">
      </div>
    </div>
    <div class="row">
      <div>
        <label>White player context (optional)</label>
        <input type="text" name="white_context" placeholder="e.g. my son, an attacker">
      </div>
      <div>
        <label>Black player context (optional)</label>
        <input type="text" name="black_context" placeholder="e.g. positional style">
      </div>
    </div>
    <button id="go" type="submit">Analyze game</button>
    <p class="hint">Runs on your computer. Analysis takes ~1&ndash;3 minutes; keep this tab open.</p>
  </form>
  <p class="foot">Greco Online &middot; v{{ version }}. <a href="/my-reports" style="color:var(--gold);">My Reports</a> &middot; <a href="/docs" style="color:var(--gold);">API docs</a> &middot; Logged in as <b>{{ username }}</b> &middot; <form style="display:inline" method="post" action="/auth/logout"><button type="submit" style="background:none;border:none;color:var(--gold);cursor:pointer;font-size:.78rem;padding:0;text-decoration:underline;">Log out</button></form></p>
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
    <div><a class="btn alt" href="/report/{{ rid }}/shareable">Download &#11015;</a></div>
    <div><a class="btn alt" href="/">Analyze another game</a></div>
  </div>
  <div class="card" style="margin-top:1rem;">
    <p style="font-weight:700;margin:0 0 8px;font-size:.9rem;color:var(--wine-dark);">Share this report</p>
    <div class="row">
      <div><button id="gv-copy"    class="btn alt" data-rid="{{ rid }}" type="button">&#128279; Same WiFi</button></div>
      <div><button id="gv-ngrok"   class="btn alt" data-rid="{{ rid }}" type="button">&#127760; Share anywhere (ngrok)</button></div>
      <div><button id="gv-publish" class="btn alt" data-rid="{{ rid }}" type="button">&#9729; Publish permanently</button></div>
    </div>
    <p class="hint" id="gv-share-hint" style="margin-top:8px;"></p>
  </div>
  <p class="hint">Saved to: {{ saved_dir }}</p>
  <iframe src="/report/{{ rid }}" style="width:100%;height:78vh;border:1px solid var(--line);border-radius:12px;margin-top:16px;background:#fff;"></iframe>
</div>
<script>(function(){
  var hint = document.getElementById('gv-share-hint');
  function showHint(msg){ hint.textContent = msg; }

  // --- Same-WiFi link (LAN IP) ---
  var btnCopy = document.getElementById('gv-copy');
  btnCopy.addEventListener('click', function(){
    var rid = btnCopy.getAttribute('data-rid');
    fetch('/lan-url').then(function(r){ return r.json(); }).then(function(d){
      var url = d.url + '/report/' + rid;
      navigator.clipboard.writeText(url).then(function(){
        btnCopy.textContent = '✓ Copied!';
        showHint('Link: ' + url + ' — works for anyone on your WiFi.');
        setTimeout(function(){ btnCopy.textContent = '🔗 Same WiFi'; }, 3000);
      });
    }).catch(function(){ showHint('Could not copy — open the report and copy from the address bar.'); });
  });

  // --- Anywhere link (ngrok tunnel) ---
  var btnNgrok = document.getElementById('gv-ngrok');
  btnNgrok.addEventListener('click', function(){
    var rid = btnNgrok.getAttribute('data-rid');
    fetch('/ngrok-url').then(function(r){ return r.json(); }).then(function(d){
      if(!d.url){
        showHint('ngrok not running — add "ngrok_auth_token" to config.json and restart Greco Web.');
        return;
      }
      var url = d.url + '/report/' + rid;
      navigator.clipboard.writeText(url).then(function(){
        btnNgrok.textContent = '✓ Copied!';
        showHint('Link: ' + url + ' — works anywhere, as long as Greco Web is running.');
        setTimeout(function(){ btnNgrok.textContent = '🌐 Share anywhere (ngrok)'; }, 3000);
      });
    }).catch(function(){ showHint('Could not reach ngrok — check your auth token.'); });
  });

  // --- Publish permanently (R2) ---
  var btnPublish = document.getElementById('gv-publish');
  btnPublish.addEventListener('click', function(){
    var rid = btnPublish.getAttribute('data-rid');
    btnPublish.textContent = 'Uploading…';
    btnPublish.disabled = true;
    fetch('/report/' + rid + '/publish', {method: 'POST'})
      .then(function(r){
        if(r.status === 503){ return r.json().then(function(d){ throw new Error(d.detail); }); }
        if(!r.ok){ throw new Error('Upload failed (' + r.status + ')'); }
        return r.json();
      })
      .then(function(d){
        navigator.clipboard.writeText(d.url).then(function(){
          showHint('Published! Link copied: ' + d.url);
        }).catch(function(){ showHint('Published! Link: ' + d.url); });
        btnPublish.textContent = '✓ Published';
      })
      .catch(function(e){
        showHint(e.message || 'Publish failed — check config.json for r2_* keys.');
        btnPublish.textContent = '☁ Publish permanently';
        btnPublish.disabled = false;
      });
  });
})();</script>
</body></html>""")

_ERROR = Template("""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Greco &mdash; problem</title><style>{{ base_css|safe }}</style></head><body>
<div class="wrap">
  <div class="banner warn">{{ message }}</div>
  <p><a class="btn alt" href="/">&larr; Back</a></p>
  {% if detail %}<pre>{{ detail }}</pre>{% endif %}
</div></body></html>""")


_WAITING = Template("""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Analysing&hellip; &mdash; Greco</title><style>{{ base_css|safe }}
.spinner{font-size:2.8rem;display:inline-block;animation:spin 2s linear infinite;}
@keyframes spin{from{transform:rotate(0deg);}to{transform:rotate(360deg);}}
.status-wrap{text-align:center;padding:36px 20px;}
</style></head><body>
<div class="wrap">
  <div class="banner ok" id="s-banner">Analysing your game&hellip;</div>
  <div class="card status-wrap">
    <div class="spinner">&#9818;</div>
    <p class="sub" id="s-text" style="margin-top:18px;">
      Stockfish is evaluating every move, then Claude writes the report.
      This usually takes 1&ndash;3 minutes.
    </p>
    <p class="hint" id="s-err" style="display:none;color:#b03030;"></p>
  </div>
  <p class="hint" style="text-align:center;">Keep this tab open &mdash; you&rsquo;ll be taken to your report automatically.</p>
  <p style="text-align:center;margin-top:8px;"><a class="btn alt" style="display:inline-block;width:auto;padding:8px 20px;" href="/">Cancel &amp; start over</a></p>
</div>
<script>
(function(){
  var jobId = "{{ job_id }}";
  var done = false;
  function poll(){
    if(done) return;
    fetch("/job/" + jobId)
      .then(function(r){ return r.json(); })
      .then(function(d){
        if(d.status === "done"){
          done = true;
          document.getElementById("s-banner").textContent = "✓ Report ready — redirecting…";
          document.getElementById("s-text").textContent = "Taking you to your report now.";
          window.location.href = "/result/" + jobId;
        } else if(d.status === "failed"){
          done = true;
          var b = document.getElementById("s-banner");
          b.className = "banner warn"; b.textContent = "Analysis failed";
          document.getElementById("s-text").style.display = "none";
          var e = document.getElementById("s-err");
          e.style.display = ""; e.textContent = d.error || "An unexpected error occurred. Please try again.";
        }
      })
      .catch(function(){ /* transient network error — retry on next tick */ });
  }
  poll();
  setInterval(poll, 2000);
})();
</script>
</body></html>""")


def render_form(s: Settings, user=None) -> str:
    return _FORM.render(
        base_css=BASE_CSS, version=__version__, ready=s.ready,
        engine_ok=s.engine_ok, key_ok=s.key_ok, model=s.model,
        use_cases=USE_CASES, models=MODELS,
        username=user.username if user else "?",
    )


def render_result(base: str, rid: int, saved_dir: str) -> str:
    return _RESULT.render(base_css=BASE_CSS, base=base, rid=rid, saved_dir=saved_dir)


def render_error(message: str, detail: str = "") -> str:
    return _ERROR.render(base_css=BASE_CSS, message=message, detail=detail)


def render_waiting(job_id: str) -> str:
    return _WAITING.render(base_css=BASE_CSS, job_id=job_id)


# ---------------------------------------------------------------------------
# Auth pages (Phase 3)
# ---------------------------------------------------------------------------

_AUTH = Template("""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Greco &mdash; {{ title }}</title><style>{{ base_css|safe }}</style></head><body>
<div class="wrap" style="max-width:420px;">
  <h1>&#9818; Greco</h1>
  <p class="sub">{{ subtitle }}</p>
  {% if error %}<div class="banner warn">{{ error }}</div>{% endif %}
  <form class="card" method="post" action="{{ action }}">
    {% if mode == 'register' %}
    <label>Username</label>
    <input type="text" name="username" value="{{ prefill.username }}" required
           pattern="[A-Za-z0-9_]{3,30}" title="3–30 characters: letters, digits, underscores"
           autocomplete="username">
    <label>Email</label>
    <input type="email" name="email" value="{{ prefill.email }}" required autocomplete="email">
    {% else %}
    <label>Username or email</label>
    <input type="text" name="username" value="{{ prefill.username }}" required autocomplete="username">
    {% endif %}
    <label>Password</label>
    <input type="password" name="password" required autocomplete="{{ 'new-password' if mode == 'register' else 'current-password' }}" minlength="8">
    {% if mode == 'register' %}
    <label>Confirm password</label>
    <input type="password" name="confirm" required autocomplete="new-password" minlength="8">
    {% endif %}
    <button type="submit">{{ btn }}</button>
  </form>
  <p style="text-align:center;margin-top:12px;font-size:.88rem;color:var(--gold);">
    {% if mode == 'register' %}
    Already have an account? <a href="/auth/login" style="color:var(--gold);">Log in</a>
    {% else %}
    Don&rsquo;t have an account? <a href="/auth/register" style="color:var(--gold);">Register</a>
    {% endif %}
  </p>
  <p class="foot">Greco Online &middot; v{{ version }}</p>
</div></body></html>""")


_DASHBOARD = Template("""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>My Reports &mdash; Greco</title><style>{{ base_css|safe }}
.tbl{width:100%;border-collapse:collapse;font-size:.9rem;}
.tbl th{text-align:left;padding:8px 10px;border-bottom:2px solid var(--gold);color:var(--wine-dark);font-size:.8rem;text-transform:uppercase;letter-spacing:.05em;}
.tbl td{padding:10px;border-bottom:1px solid var(--line);vertical-align:middle;}
.tbl tr:last-child td{border-bottom:none;}
.tbl a{color:var(--wine-dark);font-weight:700;text-decoration:none;}
.tbl a:hover{text-decoration:underline;}
.empty{color:var(--muted);font-size:.92rem;margin:20px 0;}
.nav{display:flex;gap:10px;margin-bottom:20px;flex-wrap:wrap;}
.del-btn{background:none;border:1px solid #b03030;color:#b03030;border-radius:6px;padding:4px 10px;cursor:pointer;font-size:.78rem;font-family:inherit;}
.del-btn:hover{background:#b03030;color:#fff;}
</style></head><body>
<div class="wrap">
  <h1>&#9818; Greco</h1>
  <p class="sub">My Reports &mdash; logged in as <b>{{ username }}</b>
    {% if is_admin %}&nbsp;<span style="color:var(--gold);font-size:.78rem;">[admin]</span>{% endif %}
  </p>
  <div class="nav">
    <a class="btn go" href="/">&#43; Analyze a game</a>
    {% if reports %}<a class="btn alt" href="/my-reports/export">&#11015; Export CSV</a>{% endif %}
    {% if is_admin %}<a class="btn alt" href="/admin/users">&#128100; Admin: users</a>{% endif %}
    <form method="post" action="/auth/logout" style="margin:0;">
      <button type="submit" style="background:none;border:1px solid var(--gold);color:var(--gold);border-radius:8px;padding:10px 16px;cursor:pointer;font-size:.88rem;font-family:inherit;">Log out</button>
    </form>
  </div>
  {% if reports %}
  <div class="card" style="padding:0;overflow:hidden;">
    <table class="tbl">
      <thead><tr><th>#</th><th>Game</th><th>Actions</th></tr></thead>
      <tbody>
        {% for r in reports %}
        <tr>
          <td style="color:var(--muted);font-size:.8rem;">{{ r.report_id }}</td>
          <td><a href="/report/{{ r.report_id }}" target="_blank">{{ r.base or "Report #" ~ r.report_id }}</a></td>
          <td>
            <a href="/report/{{ r.report_id }}" target="_blank" class="btn go" style="padding:5px 12px;font-size:.8rem;display:inline-block;width:auto;">Open</a>
            &nbsp;<a href="/report/{{ r.report_id }}/shareable" class="btn alt" style="padding:5px 12px;font-size:.8rem;display:inline-block;width:auto;">Download</a>
            &nbsp;<form method="post" action="/my-reports/{{ r.report_id }}/delete" style="display:inline;" onsubmit="return confirm('Remove this report from your history?');">
              <button type="submit" class="del-btn">Remove</button>
            </form>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% else %}
  <div class="card"><p class="empty">No reports yet. <a href="/">Analyze a game</a> to get started.</p></div>
  {% endif %}
  <p class="foot">Greco Online &middot; v{{ version }}</p>
</div></body></html>""")


_ADMIN_USERS = Template("""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Admin: Users &mdash; Greco</title><style>{{ base_css|safe }}
.tbl{width:100%;border-collapse:collapse;font-size:.9rem;}
.tbl th{text-align:left;padding:8px 10px;border-bottom:2px solid var(--gold);color:var(--wine-dark);font-size:.8rem;text-transform:uppercase;letter-spacing:.05em;}
.tbl td{padding:10px;border-bottom:1px solid var(--line);vertical-align:middle;}
.tbl tr:last-child td{border-bottom:none;}
.badge{display:inline-block;padding:2px 8px;border-radius:12px;font-size:.75rem;font-weight:700;}
.badge-admin{background:#d4af37;color:#3a2a1a;}
.badge-user{background:#d9c7a0;color:#5b4a1e;}
.nav{display:flex;gap:10px;margin-bottom:20px;flex-wrap:wrap;}
</style></head><body>
<div class="wrap">
  <h1>&#9818; Greco Admin</h1>
  <p class="sub">All registered users &mdash; logged in as <b>{{ admin_username }}</b></p>
  <div class="nav">
    <a class="btn alt" href="/my-reports">&#8592; My Reports</a>
    <a class="btn alt" href="/admin/reports/export">&#11015; Export all CSV</a>
    <a class="btn go" href="/">&#43; Analyze a game</a>
    <form method="post" action="/auth/logout" style="margin:0;">
      <button type="submit" style="background:none;border:1px solid var(--gold);color:var(--gold);border-radius:8px;padding:10px 16px;cursor:pointer;font-size:.88rem;font-family:inherit;">Log out</button>
    </form>
  </div>
  <div class="card" style="padding:0;overflow:hidden;">
    <table class="tbl">
      <thead><tr><th>ID</th><th>Username</th><th>Email</th><th>Role</th><th>Reports</th></tr></thead>
      <tbody>
        {% for u in users %}
        <tr>
          <td style="color:var(--muted);font-size:.8rem;">{{ u.id }}</td>
          <td><b>{{ u.username }}</b></td>
          <td style="color:var(--muted);">{{ u.email }}</td>
          <td><span class="badge badge-{{ u.role }}">{{ u.role }}</span></td>
          <td>{{ counts.get(u.id, 0) }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  <p class="foot">{{ users|length }} user(s) total &middot; Greco Online v{{ version }}</p>
</div></body></html>""")


def render_dashboard(user, reports) -> str:
    return _DASHBOARD.render(
        base_css=BASE_CSS, version=__version__,
        username=user.username, is_admin=user.is_admin,
        reports=reports,
    )


def render_admin_users(admin_user, users, counts: dict) -> str:
    return _ADMIN_USERS.render(
        base_css=BASE_CSS, version=__version__,
        admin_username=admin_user.username,
        users=users, counts=counts,
    )


def render_auth(
    mode: str,  # 'login' or 'register'
    error: str = "",
    prefill: Optional[dict] = None,
) -> str:
    is_register = mode == "register"
    return _AUTH.render(
        base_css=BASE_CSS, version=__version__,
        mode=mode,
        title="Register" if is_register else "Log in",
        subtitle="Create your Greco account." if is_register else "Welcome back.",
        action=f"/auth/{mode}",
        btn="Create account" if is_register else "Log in",
        error=error,
        prefill=prefill or {},
    )
