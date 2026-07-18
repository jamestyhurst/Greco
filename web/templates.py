"""HTML pages for Greco Web (server-rendered with Jinja2).

All templates inlined here; no separate template directory required for local
development. Phase 4 can formalise into a templates/ directory if needed.
"""
from __future__ import annotations

from typing import Optional

from jinja2 import Template

from version import __version__
from web.config import Settings, USE_CASES, MODELS

BASE_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;700&family=EB+Garamond:ital,wght@0,400;0,700;1,400;1,700&display=swap');
:root{--wine:#7A1C26;--wine-dark:#5E151D;--ivory:#F5EDD4;--parch:#FBF6E7;--gold:#C9A23A;--ink:#3A2A1A;--muted:#8a7a5c;--line:#d9c7a0;}
*{box-sizing:border-box;}
body{margin:0;font-family:'EB Garamond','Palatino Linotype',Palatino,Georgia,'Book Antiqua',serif;color:var(--ivory);background:var(--wine);line-height:1.6;}
.wrap{max-width:660px;margin:0 auto;padding:20px 16px 64px;}
h1{font-size:1.95rem;margin:0 0 4px;color:var(--ivory);font-weight:700;letter-spacing:.5px;font-family:'Cinzel','Palatino Linotype',Palatino,Georgia,serif;}
h2,h3{font-family:'EB Garamond','Palatino Linotype',Palatino,Georgia,serif;font-weight:700;color:var(--ivory);}
.sub{color:var(--gold);margin:0 0 20px;font-size:.95rem;font-style:italic;font-family:'EB Garamond','Palatino Linotype',Palatino,Georgia,serif;}
.card{background:var(--parch);border:1px solid var(--gold);border-radius:10px;padding:18px;color:var(--ink);box-shadow:0 2px 12px rgba(0,0,0,.28);}
label{display:block;font-weight:700;margin:14px 0 6px;font-size:.9rem;color:var(--wine-dark);}
input[type=file],textarea,select,input[type=text],input[type=email]{width:100%;padding:10px;border:1px solid var(--line);border-radius:8px;font-size:1rem;font-family:inherit;background:#fffdf6;color:var(--ink);}
textarea{min-height:110px;resize:vertical;font-family:Consolas,monospace;font-size:.85rem;}
.row{display:flex;gap:12px;flex-wrap:wrap;}
.row>div{flex:1;min-width:140px;}
.or{text-align:center;color:var(--muted);margin:10px 0;font-size:.85rem;}
button{margin-top:20px;width:100%;padding:13px;font-size:1.05rem;font-weight:700;color:var(--wine);background:var(--gold);border:0;border-radius:8px;cursor:pointer;font-family:inherit;}
button:hover{background:#d9b658;}
button:disabled{opacity:.6;cursor:progress;}
.btn{display:inline-block;text-align:center;padding:10px 18px;border-radius:8px;font-weight:700;text-decoration:none;font-family:inherit;}
.btn.go{color:var(--wine);background:var(--gold);}
.btn.alt{color:var(--wine-dark);background:var(--parch);border:1px solid var(--gold);}
.banner{padding:10px 12px;border-radius:8px;font-size:.9rem;margin-bottom:16px;}
.ok{background:#efe6c8;border:1px solid var(--gold);color:#5b4a1e;}
.warn{background:#f3d9b0;border:1px solid #b9742a;color:#6b3410;}
.hint{color:var(--muted);font-size:.82rem;margin-top:6px;}
.foot{color:#d8c9a0;font-size:.78rem;margin-top:18px;text-align:center;}
pre{white-space:pre-wrap;background:var(--wine-dark);color:var(--ivory);padding:14px;border-radius:8px;font-size:.8rem;overflow:auto;}
.tbl{width:100%;border-collapse:collapse;font-size:.9rem;}
.tbl th{text-align:left;padding:8px 10px;border-bottom:2px solid var(--gold);color:var(--wine-dark);font-size:.8rem;text-transform:uppercase;letter-spacing:.05em;}
.tbl td{padding:10px;border-bottom:1px solid var(--line);vertical-align:middle;}
.tbl tr:last-child td{border-bottom:none;}
.tbl a{color:var(--wine-dark);font-weight:700;text-decoration:none;}
.tbl a:hover{text-decoration:underline;}
.badge{display:inline-block;padding:2px 8px;border-radius:12px;font-size:.75rem;font-weight:700;}
.badge-admin{background:#d4af37;color:#3a2a1a;}
.badge-user{background:#d9c7a0;color:#5b4a1e;}
.del-btn{background:none;border:1px solid #b03030;color:#b03030;border-radius:6px;padding:4px 10px;cursor:pointer;font-size:.78rem;font-family:inherit;margin-top:0;}
.del-btn:hover{background:#b03030;color:#fff;}
.empty{color:var(--muted);font-size:.92rem;margin:20px 0;}
#overlay{display:none;position:fixed;inset:0;background:rgba(122,28,38,.95);color:var(--ivory);align-items:center;justify-content:center;text-align:center;padding:24px;}
#overlay.show{display:flex;}
.g-icon{width:36px;height:36px;vertical-align:middle;margin-right:8px;border-radius:6px;}
.top-nav{display:flex;align-items:center;justify-content:space-between;padding:10px 20px;background:var(--wine-dark);border-bottom:1px solid rgba(201,162,58,.4);flex-wrap:wrap;gap:8px;}
.nav-brand{display:flex;align-items:center;color:var(--gold);font-family:'Cinzel',serif;font-weight:700;font-size:1.1rem;text-decoration:none;gap:6px;}
.nav-brand img{width:28px;height:28px;border-radius:5px;}
.nav-links{display:flex;align-items:center;gap:6px;flex-wrap:wrap;}
.nav-btn{display:inline-block;padding:6px 13px;border-radius:7px;font-size:.83rem;font-weight:700;text-decoration:none;cursor:pointer;font-family:inherit;border:1px solid rgba(201,162,58,.5);color:var(--gold);background:none;line-height:1.4;}
.nav-btn:hover,.nav-btn:focus{background:rgba(201,162,58,.15);outline:none;}
.nav-btn.primary{background:var(--gold);color:var(--wine-dark);border-color:var(--gold);}
.nav-btn.primary:hover{background:#d9b658;}
.nav-user{color:var(--muted);font-size:.83rem;padding:6px 8px;}
.feature-grid{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0 24px;}
.feature-card{flex:1;min-width:160px;background:rgba(0,0,0,.18);border:1px solid rgba(201,162,58,.3);border-radius:10px;padding:14px 14px 12px;font-size:.88rem;line-height:1.45;}
.feature-card strong{display:block;color:var(--gold);margin-bottom:4px;font-size:.92rem;}
.progress-wrap{margin:16px 0 4px;}
.progress-bar{height:8px;background:rgba(0,0,0,.25);border-radius:4px;overflow:hidden;}
.progress-fill{height:100%;background:var(--gold);border-radius:4px;transition:width 1.5s ease;}
.log-box{background:var(--wine-dark);border:1px solid rgba(201,162,58,.3);border-radius:8px;padding:12px;font-size:.78rem;font-family:Consolas,monospace;min-height:60px;max-height:140px;overflow-y:auto;margin-top:10px;color:var(--gold);}
.result-cta{font-size:1rem;color:var(--ink);margin:0 0 14px;font-weight:700;}
.result-note{font-size:.85rem;color:var(--muted);margin:0 0 16px;}
.preview-toggle{background:none;border:1px solid var(--line);color:var(--ink);border-radius:6px;padding:6px 14px;cursor:pointer;font-size:.82rem;font-family:inherit;margin-top:8px;width:auto;}
.preview-toggle:hover{background:rgba(0,0,0,.05);}
"""


def _make_nav(user=None) -> str:
    """Return the HTML for the consistent top navigation bar."""
    brand = '<a href="/" class="nav-brand"><img src="/static/greco.png" alt="">Greco</a>'
    if user:
        admin = '<a class="nav-btn" href="/admin/users">Admin</a>' if getattr(user, 'is_admin', False) else ''
        links = (
            f'{admin}'
            f'<a class="nav-btn" href="/my-reports">My&nbsp;Reports</a>'
            f'<a class="nav-btn" href="/profile">{user.username}</a>'
            f'<form method="post" action="/auth/logout" style="margin:0;">'
            f'<button type="submit" class="nav-btn">Sign&nbsp;out</button></form>'
        )
    else:
        links = (
            '<a class="nav-btn" href="/auth/login">Sign&nbsp;in</a>'
            '<a class="nav-btn primary" href="/auth/register">Register</a>'
        )
    return f'<nav class="top-nav">{brand}<div class="nav-links">{links}</div></nav>'


# ---------------------------------------------------------------------------
# Home page (analysis form — guests and logged-in users)
# ---------------------------------------------------------------------------

_HOME = Template("""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Greco &mdash; Chess Report Generator</title><style>{{ base_css|safe }}</style></head><body>
{{ nav|safe }}
<div class="wrap">
{% if not user %}
  <div style="text-align:center;padding:8px 0 20px;">
    <h1 style="margin-bottom:6px;">Greco</h1>
    <p class="sub" style="margin-bottom:14px;">Engine-backed, AI-narrated chess reports &mdash; in your browser.</p>
    <div class="feature-grid">
      <div class="feature-card"><strong>Stockfish analysis</strong>Every move evaluated precisely. Blunders, mistakes, and brilliancies scored at engine depth.</div>
      <div class="feature-card"><strong>AI narration</strong>Claude writes a human-readable report &mdash; not just what went wrong, but why and what to do instead.</div>
      <div class="feature-card"><strong>Beautiful reports</strong>Self-contained HTML you can open offline, share by email, or publish online.</div>
    </div>
  </div>
{% endif %}
  {% if ready %}
    <div class="banner ok">Ready &mdash; using your saved settings (model: {{ model }}). Reports save to your Greco Reports folder.</div>
  {% else %}
    <div class="banner warn">Not set up yet. Open the Greco <b>desktop app &rarr; settings</b> and set your Stockfish path and Anthropic API key once; this page reads the same settings.
      {% if not engine_ok %}<br>&bull; Stockfish path missing or invalid.{% endif %}
      {% if not key_ok %}<br>&bull; Anthropic API key missing.{% endif %}
    </div>
  {% endif %}
{% if user and (lichess_username or chesscom_username) %}
  <div class="card" id="recent-card">
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
      <b>Your recent games</b>
      <span id="tc-chips"></span>
    </div>
    <div id="recent-list" style="margin-top:10px;"><p class="hint">Loading&hellip;</p></div>
  </div>
  <script>
  /* The home-page "play -> dwell -> analyze" flow. Time-control chips filter
     the merged Lichess + Chess.com list; Rapid is the doctrine default. The
     user's last choice sticks via localStorage (per-browser persistence — a
     per-account DB setting would be the upgrade if it should follow logins).

     Chip markers are ivory chess pieces, deliberately NOT the icons Lichess /
     Chess.com use (James: keep Greco's aesthetic distinct). The piece's
     weight grows with the time control's length — pawn for bullet up to
     queen for daily; the king stands for All (the whole game). */
  var _TCS=['rapid','blitz','bullet','classical','daily','all'];
  var _TC_PIECE={bullet:'\\u2659',blitz:'\\u2658',rapid:'\\u2657',classical:'\\u2656',daily:'\\u2655',all:'\\u2654'};
  var _TC_KEY='greco_recent_tc';
  function _tc(){try{var v=localStorage.getItem(_TC_KEY);return _TCS.indexOf(v)>=0?v:'rapid'}catch(e){return 'rapid'}}
  function _setTc(v){try{localStorage.setItem(_TC_KEY,v)}catch(e){} _drawChips(); _loadRecent();}
  function _drawChips(){
    var cur=_tc();
    document.getElementById('tc-chips').innerHTML=_TCS.map(function(t){
      var on=(t===cur);
      /* Both states set background AND color explicitly: inheriting the site
         button style gave gold-on-gold when selected (unreadable). */
      var style='margin:0 0 0 6px;width:auto;padding:3px 10px;font-size:.78rem;display:inline-block;cursor:pointer;border-radius:12px;'+
        (on?'background:rgba(0,0,0,.35);border:1px solid var(--gold);color:var(--gold);font-weight:700;'
           :'background:transparent;border:1px solid rgba(245,237,212,.25);color:rgba(245,237,212,.75);');
      return '<button type="button" onclick="_setTc(\\''+t+'\\')" style="'+style+'">'+
             '<span style="font-size:1rem;margin-right:4px;">'+_TC_PIECE[t]+'</span>'+
             t.charAt(0).toUpperCase()+t.slice(1)+'</button>';
    }).join('');
  }
  function _badge(you){
    if(you==='win')return '<span style="color:#7fbf7f;font-weight:bold;margin-right:8px;">W</span>';
    if(you==='loss')return '<span style="color:#d9776f;font-weight:bold;margin-right:8px;">L</span>';
    if(you==='draw')return '<span style="color:#999;font-weight:bold;margin-right:8px;">D</span>';
    return '';
  }
  /* Select fills the analyze form but does NOT submit — the user keeps full
     control of mode, model, and depth before launching (James's design
     decision: prefill, don't railroad). */
  function selectGame(url, side){
    var f=document.querySelector('form[action="/analyze"]');
    var urlField=f.querySelector('[name="game_url"]');
    urlField.value=url;
    var sideField=f.querySelector('[name="side"]');
    if(sideField)sideField.value=side||'neither';
    f.scrollIntoView({behavior:'smooth',block:'start'});
    f.style.transition='box-shadow .3s';
    f.style.boxShadow='0 0 0 2px var(--gold)';
    setTimeout(function(){f.style.boxShadow='';},1600);
  }
  function _loadRecent(){
    var el=document.getElementById('recent-list');
    el.innerHTML='<p class="hint">Loading&hellip;</p>';
    fetch('/recent-games?tc='+_tc())
      .then(function(r){return r.ok?r.json():Promise.reject(r)})
      .then(function(data){
        var note=(data.errors&&data.errors.length)?'<p class="hint">Could not reach: '+data.errors.join(', ')+'</p>':'';
        if(!data.games||!data.games.length){el.innerHTML=note+'<p class="hint">No recent '+data.tc+' games found.</p>';return;}
        el.innerHTML=note+data.games.map(function(g){
          var site=(g.site==='lichess')?'Lichess':'Chess.com';
          var thumb=g.fen?('<img src="/board-thumb?fen='+encodeURIComponent(g.fen)+'&orient='+(g.side==='black'?'black':'white')+'" '+
            'width="64" height="64" loading="lazy" alt="final position" '+
            'style="border-radius:4px;flex-shrink:0;margin-right:10px;vertical-align:middle;">'):'';
          return '<div class="game-row" style="display:flex;align-items:center;">'+thumb+
            '<div style="flex:1;min-width:0;">'+
              '<div class="game-players">'+_badge(g.you)+g.white+' vs '+g.black+'</div>'+
              '<div class="game-meta">'+site+' &middot; '+g.meta+'</div>'+
            '</div>'+
            '<button type="button" class="btn" onclick="selectGame(\\''+g.url+'\\',\\''+(g.side||'neither')+'\\')" '+
              'style="padding:5px 14px;font-size:.8rem;display:inline-block;width:auto;cursor:pointer;margin:0;">Select</button>'+
          '</div>';
        }).join('');
      })
      .catch(function(){el.innerHTML='<p class="hint">Could not load your recent games.</p>';});
  }
  document.addEventListener('DOMContentLoaded',function(){_drawChips();_loadRecent();});
  </script>
{% elif user %}
  <p class="hint" style="margin:4px 0 12px;">Link your Lichess or Chess.com account in
    <a href="/profile" style="color:var(--gold);">Profile</a> to see your recent games here for one-click analysis.</p>
{% endif %}
  <div id="s-restore-banner" class="banner ok" style="display:none;">
    Your previous inputs have been restored.
    <button type="button" onclick="document.getElementById('s-restore-banner').style.display='none'" style="margin:0;width:auto;padding:2px 10px;font-size:.82rem;display:inline-block;vertical-align:middle;margin-left:8px;">Dismiss</button>
  </div>
  <form class="card" method="post" action="/analyze" enctype="multipart/form-data"
        onsubmit="document.getElementById('overlay').classList.add('show');document.getElementById('go').disabled=true;saveFormState()">
    <label>Lichess or Chess.com game URL</label>
    <input type="text" name="game_url" placeholder="https://lichess.org/abcd1234 &mdash; or https://www.chess.com/game/live/123456789">
    <div class="or">&mdash; or &mdash;</div>
    <label>Upload a PGN file</label>
    <input type="file" name="pgn_file" accept=".pgn,.txt">
    <div class="or">&mdash; or &mdash;</div>
    <label>Paste PGN text</label>
    <textarea name="pgn_text" placeholder="[Event &quot;...&quot;]&#10;1. e4 e5 2. Nf3 Nc6 ..."></textarea>
    <div class="row">
      <div>
        <label title="Companion = personal tone. Coaching = analytical debrief. Commentary = broadcast-style. Essay = answer a chess question from the classical corpus.">Mode <span class="hint" style="display:inline;">(hover for info)</span></label>
        <select name="use_case" id="use_case_sel" onchange="toggleEssayFields()">{% for u in use_cases %}<option value="{{ u }}">{{ u }}</option>{% endfor %}</select>
      </div>
      <div id="side_row"><label>You played</label><select name="side"><option value="neither">neither</option><option value="white">white</option><option value="black">black</option></select></div>
    </div>
    <div id="essay_question_row" style="display:none;">
      <label>Your chess question</label>
      <textarea name="essay_question" id="essay_question" rows="2" placeholder="e.g. Does the Scandinavian Defense naturally lean toward queenside castling?"></textarea>
      <p class="hint" style="margin-top:4px;">Greco searches its classical corpus and synthesises an answer. The PGN/game above is optional — if provided, specific moves may be cited as examples.</p>
    </div>
    <div class="row" id="speed_row">
      <div>
        <label title="Fast = 0.5 s/move. Normal = 0.8 s/move. Deep = 1.5 s/move. Deep gives more precise evaluations for complex positions.">Engine depth <span class="hint" style="display:inline;">(hover)</span></label>
        <select name="speed"><option value="fast">Fast (0.5&thinsp;s/move)</option><option value="normal" selected>Normal (0.8&thinsp;s/move)</option><option value="deep">Deep (1.5&thinsp;s/move)</option></select>
      </div>
      <div><label>Model</label><select name="model">{% for m in models %}<option value="{{ m }}"{% if m==model %} selected{% endif %}>{{ m }}</option>{% endfor %}</select></div>
    </div>
    <label>Note for Greco (optional)</label>
    <input type="text" name="note" placeholder="e.g. I&rsquo;m proud of the queen sacrifice on move 18">
    <div class="row">
      <div>
        <label title="Calibrates how much Greco explains. Beginner = more context about basic ideas. Advanced = deeper tactical and strategic analysis.">Audience level <span class="hint" style="display:inline;">(hover)</span></label>
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
    <p class="hint">Analysis runs on your computer using Stockfish + Claude &mdash; takes 1&ndash;3 minutes. Keep this tab open.</p>
  </form>
{% if not user %}
  <p style="text-align:center;margin-top:14px;font-size:.87rem;color:rgba(245,237,212,.7);">
    <a href="/auth/register" style="color:var(--gold);">Create a free account</a> to save your report history and access past games.
  </p>
{% endif %}
  <p class="foot">Greco &middot; v{{ version }}{% if user %} &middot; <a href="/my-reports" style="color:var(--gold);">My Reports</a>{% endif %}</p>
</div>
<div id="overlay"><div>
  <h2 style="font-family:'Cinzel',serif;">Analyzing&hellip;</h2>
  <p class="sub">Stockfish is evaluating every move and Claude is writing the report.<br>This can take a minute or two &mdash; keep this tab open.</p>
</div></div>
<script>
function toggleEssayFields(){
  var sel=document.getElementById('use_case_sel');
  var isEssay=sel&&sel.value==='essay';
  var eqRow=document.getElementById('essay_question_row');
  var sideRow=document.getElementById('side_row');
  var speedRow=document.getElementById('speed_row');
  if(eqRow)eqRow.style.display=isEssay?'':'none';
  if(sideRow)sideRow.style.display=isEssay?'none':'';
  if(speedRow)speedRow.style.display=isEssay?'none':'';
}
document.addEventListener('DOMContentLoaded',toggleEssayFields);
var _FORM_KEY='greco_form_state';
var _FORM_FIELDS=['game_url','use_case','side','speed','model','note','audience_level','recipient','white_context','black_context','pgn_text','essay_question'];
function saveFormState(){
  try{
    var vals={};
    _FORM_FIELDS.forEach(function(f){
      var el=document.querySelector('[name="'+f+'"]');
      if(el)vals[f]=el.value;
    });
    localStorage.setItem(_FORM_KEY,JSON.stringify(vals));
  }catch(e){}
}
(function(){
  try{
    var saved=localStorage.getItem(_FORM_KEY);
    if(!saved)return;
    var vals=JSON.parse(saved);
    var restored=false;
    _FORM_FIELDS.forEach(function(f){
      if(vals[f]===undefined||vals[f]==='')return;
      var el=document.querySelector('[name="'+f+'"]');
      if(el){el.value=vals[f];restored=true;}
    });
    if(restored)document.getElementById('s-restore-banner').style.display='';
  }catch(e){}
})();
</script>
</body></html>""")


# ---------------------------------------------------------------------------
# Result page
# ---------------------------------------------------------------------------

_RESULT = Template("""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ base }} &mdash; Greco</title><style>{{ base_css|safe }}</style></head><body>
{{ nav|safe }}
<div class="wrap">
  <div class="banner ok">&#10003; Report ready &mdash; {{ base }}</div>
  <p class="result-cta">Your report is a self-contained HTML file.</p>
  <p class="result-note" style="color:var(--muted);">Open it in a new browser tab &mdash; it works offline and can be emailed as a single attachment.</p>
  <div class="row" style="margin-bottom:16px;">
    <div><a class="btn go" href="/report/{{ rid }}" target="_blank" style="width:100%;display:block;">Open report &#8599;</a></div>
    <div><a class="btn alt" href="/report/{{ rid }}/shareable" style="width:100%;display:block;">Download &#11015;</a></div>
    <div><a class="btn alt" href="/" style="width:100%;display:block;">Analyze another</a></div>
  </div>
  <div class="card" style="margin-bottom:16px;">
    <p style="font-weight:700;margin:0 0 8px;font-size:.9rem;color:var(--wine-dark);">Share this report</p>
    <div class="row">
      <div><button id="gv-copy"    class="btn alt" data-rid="{{ rid }}" type="button" style="width:100%;margin-top:0;">&#128279; Same WiFi</button></div>
      <div><button id="gv-ngrok"   class="btn alt" data-rid="{{ rid }}" type="button" style="width:100%;margin-top:0;">&#127760; Share anywhere</button></div>
      <div><button id="gv-publish" class="btn alt" data-rid="{{ rid }}" type="button" style="width:100%;margin-top:0;">&#9729; Publish</button></div>
    </div>
    <p class="hint" id="gv-share-hint" style="margin-top:8px;"></p>
  </div>
  <p class="hint">Saved&nbsp;to: {{ saved_dir }}</p>
  <div style="margin-top:16px;">
    <button class="preview-toggle" id="preview-btn" onclick="togglePreview()">&#9660; Show preview</button>
    <div id="preview-wrap" style="display:none;margin-top:8px;">
      <p class="hint" style="margin-bottom:6px;">This is a preview only. <a href="/report/{{ rid }}" target="_blank" style="color:var(--wine-dark);">Open the full report</a> for the best experience.</p>
      <iframe src="/report/{{ rid }}" style="width:100%;height:70vh;border:1px solid var(--line);border-radius:10px;background:#fff;"></iframe>
    </div>
  </div>
</div>
<script>
function togglePreview(){
  var w=document.getElementById('preview-wrap');
  var b=document.getElementById('preview-btn');
  if(w.style.display==='none'){w.style.display='';b.textContent='▲ Hide preview';}
  else{w.style.display='none';b.textContent='▼ Show preview';}
}
(function(){
  var hint=document.getElementById('gv-share-hint');
  function showHint(msg){hint.textContent=msg;}
  var btnCopy=document.getElementById('gv-copy');
  btnCopy.addEventListener('click',function(){
    var rid=btnCopy.getAttribute('data-rid');
    fetch('/lan-url').then(function(r){return r.json();}).then(function(d){
      var url=d.url+'/report/'+rid;
      navigator.clipboard.writeText(url).then(function(){
        btnCopy.textContent='✓ Copied!';
        showHint('Link: '+url+' — works for anyone on your WiFi.');
        setTimeout(function(){btnCopy.textContent='🔗 Same WiFi';},3000);
      });
    }).catch(function(){showHint('Could not copy — open the report and copy from the address bar.');});
  });
  var btnNgrok=document.getElementById('gv-ngrok');
  btnNgrok.addEventListener('click',function(){
    var rid=btnNgrok.getAttribute('data-rid');
    fetch('/ngrok-url').then(function(r){return r.json();}).then(function(d){
      if(!d.url){showHint('ngrok not running — add "ngrok_auth_token" to config.json and restart Greco Web.');return;}
      var url=d.url+'/report/'+rid;
      navigator.clipboard.writeText(url).then(function(){
        btnNgrok.textContent='✓ Copied!';
        showHint('Link: '+url+' — works anywhere while Greco Web is running.');
        setTimeout(function(){btnNgrok.textContent='🌐 Share anywhere';},3000);
      });
    }).catch(function(){showHint('Could not reach ngrok.');});
  });
  var btnPublish=document.getElementById('gv-publish');
  btnPublish.addEventListener('click',function(){
    var rid=btnPublish.getAttribute('data-rid');
    btnPublish.textContent='Uploading…';
    btnPublish.disabled=true;
    fetch('/report/'+rid+'/publish',{method:'POST'})
      .then(function(r){
        if(r.status===503){return r.json().then(function(d){throw new Error(d.detail);});}
        if(!r.ok){throw new Error('Upload failed ('+r.status+')');}
        return r.json();
      })
      .then(function(d){
        navigator.clipboard.writeText(d.url).then(function(){
          showHint('Published! Link copied: '+d.url);
        }).catch(function(){showHint('Published! Link: '+d.url);});
        btnPublish.textContent='✓ Published';
      })
      .catch(function(e){
        showHint(e.message||'Publish failed — check config.json for r2_* keys.');
        btnPublish.textContent='☁ Publish';
        btnPublish.disabled=false;
      });
  });
})();
</script>
</body></html>""")


# ---------------------------------------------------------------------------
# Error page
# ---------------------------------------------------------------------------

_ERROR = Template("""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Greco &mdash; Problem</title><style>{{ base_css|safe }}</style></head><body>
{{ nav|safe }}
<div class="wrap">
  <div class="banner warn">{{ message }}</div>
  <p><a class="btn alt" href="/">&larr; Back to home</a></p>
  {% if detail %}<pre>{{ detail }}</pre>{% endif %}
</div></body></html>""")


# ---------------------------------------------------------------------------
# Waiting / progress page
# ---------------------------------------------------------------------------

_WAITING = Template("""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Analysing&hellip; &mdash; Greco</title><style>{{ base_css|safe }}
.spinner{font-size:2.4rem;display:inline-block;animation:spin 2s linear infinite;}
@keyframes spin{from{transform:rotate(0deg);}to{transform:rotate(360deg);}}
.status-wrap{text-align:center;padding:28px 20px 20px;}
.stage-list{display:flex;justify-content:center;gap:0;margin:14px 0 4px;flex-wrap:wrap;}
.stage{font-size:.75rem;padding:4px 12px;border-radius:12px;color:rgba(245,237,212,.5);position:relative;}
.stage.active{color:var(--gold);font-weight:700;}
.stage.done{color:rgba(245,237,212,.7);}
</style></head><body>
{{ nav|safe }}
<div class="wrap">
  <div class="banner ok" id="s-banner">{% if essay_mode %}Searching the classical corpus&hellip;{% else %}Analysing your game&hellip;{% endif %}</div>
  <div class="card status-wrap">
    <div class="spinner"><img src="/static/greco.png" style="width:52px;height:52px;border-radius:8px;animation:spin 3s linear infinite;" alt=""></div>
    <p class="sub" id="s-text" style="margin-top:14px;">
      {% if essay_mode %}Greco is searching its classical corpus and writing your essay. This usually takes 10&ndash;20 seconds.{% else %}Stockfish is evaluating every move, then Claude writes the report. This usually takes 1&ndash;3 minutes.{% endif %}
    </p>
    <div class="progress-wrap">
      <div class="stage-list" id="s-stages">
        <span class="stage active" id="st-0">Queued</span>
        {% if essay_mode %}<span class="stage" id="st-1">&#8594; Corpus</span>
        <span class="stage" id="st-2">&#8594; Claude</span>{% else %}<span class="stage" id="st-1">&#8594; Stockfish</span>
        <span class="stage" id="st-2">&#8594; Claude</span>{% endif %}
        <span class="stage" id="st-3">&#8594; Done</span>
      </div>
      <div class="progress-bar"><div class="progress-fill" id="s-bar" style="width:5%;"></div></div>
    </div>
    <div class="log-box" id="s-log">Waiting to start&hellip;</div>
    <p id="s-move-text" style="display:none;font-size:.88rem;color:var(--gold);margin:8px 0 0;text-align:center;"></p>
    <div id="s-fail-box" style="display:none;background:#3d0d0d;border:2px solid #b03030;border-radius:8px;padding:16px;margin-top:12px;text-align:left;">
      <p style="color:#f87171;font-weight:700;font-size:1rem;margin:0 0 6px;">Analysis failed</p>
      <p id="s-fail-msg" style="color:#fca5a5;font-size:.9rem;margin:0 0 14px;line-height:1.5;"></p>
      <a class="btn alt" href="/" style="display:inline-block;width:auto;padding:8px 20px;font-size:.88rem;">Back to home &rarr;</a>
    </div>
  </div>
  <p class="hint" id="s-keep-open" style="text-align:center;margin-top:10px;">Keep this tab open &mdash; you&rsquo;ll be taken to your report automatically.</p>
  <p style="text-align:center;margin-top:8px;"><a class="btn alt" style="display:inline-block;width:auto;padding:8px 20px;" href="/">Cancel &amp; start over</a></p>
</div>
<script>
(function(){
  var jobId="{{ job_id }}";
  var done=false;
  var startTime=Date.now();
  var lastLogCount=0;
  var currentStage=0;

  function setStage(n){
    if(n<=currentStage) return;
    currentStage=n;
    for(var i=0;i<4;i++){
      var el=document.getElementById('st-'+i);
      if(!el) continue;
      el.className='stage'+(i<n?' done':i===n?' active':'');
    }
  }

  function setBar(pct){
    document.getElementById('s-bar').style.width=pct+'%';
  }

  function appendLog(lines){
    var box=document.getElementById('s-log');
    lines.forEach(function(l){box.textContent+='\n'+l;});
    box.scrollTop=box.scrollHeight;
  }

  function poll(){
    if(done) return;
    var elapsed=(Date.now()-startTime)/1000;
    fetch('/job/'+jobId)
      .then(function(r){
        /* Jobs live in the server's memory (Phase 2 design), so a server
           restart forgets them. Without this check a dead job 404s forever
           and the page spins silently — tell the user what happened. */
        if(r.status===404){
          done=true;
          var b=document.getElementById('s-banner');
          b.className='banner warn';b.textContent='This analysis is no longer running';
          document.getElementById('s-text').style.display='none';
          document.getElementById('s-move-text').style.display='none';
          document.getElementById('s-keep-open').style.display='none';
          setBar(0);
          var fb=document.getElementById('s-fail-box');
          fb.style.display='';
          document.getElementById('s-fail-msg').textContent=
            'The server was restarted while this analysis was in progress, so the job was lost. '+
            'Go back to the home page and start it again — your game is still one click away.';
          throw new Error('job gone');
        }
        return r.json();
      })
      .then(function(d){
        if(d.current_move && d.total_moves){
          var mt=document.getElementById('s-move-text');
          mt.style.display='';
          mt.textContent='Evaluating position '+d.current_move+' of '+d.total_moves+'…';
          if(currentStage<=1){
            setStage(1);
            setBar(5+Math.round(60*(d.current_move/d.total_moves)));
          }
        }
        if(d.logs && d.logs.length>lastLogCount){
          var newLines=d.logs.slice(lastLogCount);
          lastLogCount=d.logs.length;
          document.getElementById('s-log').textContent='';
          appendLog(d.logs);
          var last=d.logs[d.logs.length-1]||'';
          if(last.indexOf('Stockfish')!==-1||last.indexOf('evaluating')!==-1){setStage(1);}
          if(last.indexOf('Claude')!==-1||last.indexOf('writing')!==-1){
            setStage(2);setBar(65);
            document.getElementById('s-move-text').style.display='none';
          }
          if(last.indexOf('Saving')!==-1){setBar(88);}
        } else {
          if(d.status==='running'&&!d.current_move){
            if(elapsed<30){setStage(1);setBar(Math.min(25,5+elapsed*0.7));}
            else if(elapsed<90){setStage(2);setBar(Math.min(75,25+(elapsed-30)*0.8));}
            else{setBar(Math.min(92,75+(elapsed-90)*0.1));}
          }
        }
        if(d.status==='done'){
          done=true;
          setStage(3);setBar(100);
          document.getElementById('s-banner').textContent='✓ Report ready — redirecting…';
          document.getElementById('s-text').textContent='Taking you to your report now.';
          try{localStorage.removeItem('greco_form_state');}catch(e){}
          window.location.href='/result/'+jobId;
        } else if(d.status==='failed'){
          done=true;
          var b=document.getElementById('s-banner');
          b.className='banner warn';b.textContent='Something went wrong';
          document.getElementById('s-text').style.display='none';
          document.getElementById('s-move-text').style.display='none';
          document.getElementById('s-keep-open').style.display='none';
          setBar(0);
          var fb=document.getElementById('s-fail-box');
          fb.style.display='';
          document.getElementById('s-fail-msg').textContent=
            d.error||'An unexpected error occurred. Please go back and try again.';
        }
      })
      .catch(function(){});
  }
  poll();
  setInterval(poll,2000);
})();
</script>
</body></html>""")


# ---------------------------------------------------------------------------
# Auth pages
# ---------------------------------------------------------------------------

_AUTH = Template("""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Greco &mdash; {{ title }}</title><style>{{ base_css|safe }}</style></head><body>
{{ nav|safe }}
<div class="wrap" style="max-width:420px;">
  <h1 style="text-align:center;margin-bottom:4px;">Greco</h1>
  <p class="sub" style="text-align:center;">{{ subtitle }}</p>
  {% if error %}<div class="banner warn">{{ error }}</div>{% endif %}
  <form class="card" method="post" action="{{ action }}">
    {% if mode == 'register' %}
    <label>Username</label>
    <input type="text" name="username" value="{{ prefill.username }}" required
           pattern="[A-Za-z0-9_]{3,30}" title="3-30 characters: letters, digits, underscores"
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
  <p style="text-align:center;margin-top:8px;font-size:.84rem;">
    <a href="/" style="color:rgba(245,237,212,.6);">Continue without an account &rarr;</a>
  </p>
  <p class="foot">Greco &middot; v{{ version }}</p>
</div></body></html>""")


# ---------------------------------------------------------------------------
# Dashboard (my reports)
# ---------------------------------------------------------------------------

_DASHBOARD = Template("""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>My Reports &mdash; Greco</title><style>{{ base_css|safe }}</style></head><body>
{{ nav|safe }}
<div class="wrap">
  <h2>My Reports</h2>
  {% if reports %}
  <p style="margin-bottom:14px;">
    <a class="btn alt" href="/my-reports/export">&#11015; Export CSV</a>
    &nbsp;<a class="btn alt" href="/profile">&#128100; Profile</a>
  </p>
  <div class="card" style="padding:0;overflow:hidden;">
    <table class="tbl">
      <thead><tr><th>#</th><th>Game</th><th>Actions</th></tr></thead>
      <tbody>
        {% for r in reports %}
        <tr>
          <td style="color:var(--muted);font-size:.8rem;">{{ r.report_id }}</td>
          <td><a href="/report/{{ r.report_id }}" target="_blank">{{ r.base or "Report #" ~ r.report_id }}</a></td>
          <td>
            <a href="/report/{{ r.report_id }}" target="_blank" class="btn go" style="padding:5px 12px;font-size:.8rem;display:inline-block;width:auto;margin-top:0;">Open</a>
            &nbsp;<a href="/report/{{ r.report_id }}/shareable" class="btn alt" style="padding:5px 12px;font-size:.8rem;display:inline-block;width:auto;margin-top:0;">Download</a>
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
  <p class="foot">Greco &middot; v{{ version }}</p>
</div></body></html>""")


# ---------------------------------------------------------------------------
# Admin: users
# ---------------------------------------------------------------------------

_ADMIN_USERS = Template("""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Admin: Users &mdash; Greco</title><style>{{ base_css|safe }}</style></head><body>
{{ nav|safe }}
<div class="wrap">
  <h2>Admin &mdash; All Users</h2>
  <p style="margin-bottom:14px;">
    <a class="btn alt" href="/admin/reports/export">&#11015; Export all CSV</a>
  </p>
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
  <p class="foot">{{ users|length }} user(s) total &middot; Greco &middot; v{{ version }}</p>
</div></body></html>""")


# ---------------------------------------------------------------------------
# Profile page
# ---------------------------------------------------------------------------

_PROFILE = Template("""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Profile &mdash; Greco</title><style>{{ base_css|safe }}
#games-list{margin-top:16px;}
.game-row{display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid var(--line);font-size:.9rem;}
.game-row:last-child{border-bottom:none;}
.game-players{flex:1;color:var(--ink);}
.game-meta{color:var(--muted);font-size:.8rem;}
</style></head><body>
{{ nav|safe }}
<div class="wrap">
  <h2>Profile</h2>
  {% if saved %}
  <div class="banner ok">&#10003; Profile saved.</div>
  {% endif %}
  <form class="card" method="post" action="/profile">
    <label>Lichess username (optional)</label>
    <input type="text" name="lichess_username"
           value="{{ lichess_username or '' }}"
           placeholder="e.g. DrNykterstein">
    <label>Chess.com username (optional)</label>
    <input type="text" name="chesscom_username"
           value="{{ chesscom_username or '' }}"
           placeholder="e.g. Hikaru">
    <p class="hint">Link either account (or both) to see your recent games below for one-click analysis.</p>
    <button type="submit">Save profile</button>
  </form>
  {% if lichess_username %}
  <div class="card" style="margin-top:20px;">
    <b>Recent Lichess games for {{ lichess_username }}</b>
    <div id="games-list"><p class="hint">Loading&hellip;</p></div>
  </div>
  {% endif %}
  {% if chesscom_username %}
  <div class="card" style="margin-top:20px;">
    <b>Recent Chess.com games for {{ chesscom_username }}</b>
    <div id="cc-games-list"><p class="hint">Loading&hellip;</p></div>
  </div>
  {% endif %}
  {% if lichess_username or chesscom_username %}
  <script>
  function gameRow(g, meta, url){
    return `
      <div class="game-row">
        <div class="game-players">${g.white} vs ${g.black}</div>
        <div class="game-meta">${meta}</div>
        <form method="post" action="/analyze" style="margin:0;">
          <input type="hidden" name="game_url" value="${url}">
          <input type="hidden" name="use_case" value="companion">
          <input type="hidden" name="side" value="neither">
          <input type="hidden" name="speed" value="normal">
          <input type="hidden" name="model" value="">
          <button type="submit" class="btn go" style="padding:5px 14px;font-size:.8rem;display:inline-block;width:auto;cursor:pointer;margin-top:0;">Analyze</button>
        </form>
      </div>`;
  }
  function loadGames(endpoint, elId, rowFn){
    const el=document.getElementById(elId);
    if(!el)return;
    fetch(endpoint)
      .then(r=>r.ok?r.json():Promise.reject(r))
      .then(data=>{
        if(!data.games||!data.games.length){el.innerHTML='<p class="hint">No recent games found.</p>';return;}
        el.innerHTML=data.games.map(rowFn).join('');
      })
      .catch(()=>{el.innerHTML='<p class="hint">Could not load games &mdash; check the username saved above.</p>';});
  }
  loadGames('/profile/lichess-games','games-list',g=>gameRow(g,g.speed,g.lichess_url));
  loadGames('/profile/chesscom-games','cc-games-list',g=>gameRow(g,g.time_class,g.url));
  </script>
  {% endif %}
  <p class="foot">Greco &middot; v{{ version }}</p>
</div></body></html>""")


# ---------------------------------------------------------------------------
# Render functions
# ---------------------------------------------------------------------------

def render_home(s: Settings, user=None) -> str:
    return _HOME.render(
        base_css=BASE_CSS, version=__version__, ready=s.ready,
        engine_ok=s.engine_ok, key_ok=s.key_ok, model=s.model,
        use_cases=USE_CASES, models=MODELS,
        user=user,
        lichess_username=getattr(user, "lichess_username", None),
        chesscom_username=getattr(user, "chesscom_username", None),
        nav=_make_nav(user),
    )


def render_form(s: Settings, user=None) -> str:
    """Backwards-compatible alias for render_home."""
    return render_home(s, user=user)


def render_result(base: str, rid: int, saved_dir: str, user=None) -> str:
    return _RESULT.render(
        base_css=BASE_CSS, base=base, rid=rid, saved_dir=saved_dir,
        nav=_make_nav(user),
    )


def render_error(message: str, detail: str = "", user=None) -> str:
    return _ERROR.render(
        base_css=BASE_CSS, message=message, detail=detail,
        nav=_make_nav(user),
    )


def render_waiting(job_id: str, user=None, essay_mode: bool = False) -> str:
    return _WAITING.render(
        base_css=BASE_CSS, job_id=job_id, nav=_make_nav(user), essay_mode=essay_mode
    )


def render_dashboard(user, reports) -> str:
    return _DASHBOARD.render(
        base_css=BASE_CSS, version=__version__,
        username=user.username, is_admin=user.is_admin,
        reports=reports,
        nav=_make_nav(user),
    )


def render_admin_users(admin_user, users, counts: dict) -> str:
    return _ADMIN_USERS.render(
        base_css=BASE_CSS, version=__version__,
        admin_username=admin_user.username,
        users=users, counts=counts,
        nav=_make_nav(admin_user),
    )


def render_auth(
    mode: str,
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
        nav=_make_nav(None),
    )


def render_profile(user, saved: bool = False) -> str:
    return _PROFILE.render(
        base_css=BASE_CSS, version=__version__,
        username=user.username,
        lichess_username=getattr(user, "lichess_username", None),
        chesscom_username=getattr(user, "chesscom_username", None),
        saved=saved,
        nav=_make_nav(user),
    )
