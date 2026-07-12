"""MoonshotHunt — Flask app wiring the agent pipeline to a real submission form,
founder review, trace log, published directory, upvotes, and lightweight login.
Agents make REAL live LLM calls to the Nous Research inference endpoint.

Design system: light, Product-Hunt-style (see DESIGN_SPEC.md).
"""
import os, json, threading, uuid
from flask import (Flask, request, render_template_string, redirect, url_for,
                   jsonify, session)
import store, agents

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "moonshothunt-dev-key")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
store.init(DATA_DIR)

STAGES = ["idea", "prototype", "pilot", "early revenue", "scaling"]
SUBTHEMES = [
    "waste-to-value", "industrial-decarbonization", "climate-ai", "energy-storage",
    "green-hydrogen", "carbon-capture", "sustainable-mobility", "agritech-climate",
    "water-tech", "circular-economy", "grid-tech", "robotics-in-healthcare",
    "nanorobotics", "space-tech", "materials-science", "deep-tech-other",
]

# ---------------------------------------------------------------------------
# Design system (light, Product-Hunt-style) — applied to ALL templates
# ---------------------------------------------------------------------------
TPL_LAYOUT = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{% block title %}MoonshotHunt{% endblock %}</title>
<style>
:root{
  --bg:#FFFFFF; --bg2:#F8F7F4; --txt:#1A1A1A; --txt2:#6B6B6B; --mut:#9B9B9B;
  --line:#EAEAEA; --coral:#D85A30; --teal:#1D9E75; --teal2:#0F6E56;
  --amber-bg:#FAEEDA; --amber-tx:#854F0B; --black:#111111; --black2:#2A2A2A;
  --gray:#9B9B9B;
}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--txt);
  font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
h1,h2,h3{font-weight:600;color:var(--txt)}
h1{font-size:28px;line-height:1.25;margin:0 0 8px}
h2{font-size:22px;margin:0 0 10px}
h3{font-size:16px;margin:0 0 10px}
a{color:var(--coral);text-decoration:none}
a:hover{text-decoration:underline}
.wrap{max-width:1080px;margin:0 auto;padding:24px}
nav{display:flex;gap:20px;align-items:center;padding:14px 24px;border-bottom:1px solid var(--line);
  background:var(--bg);position:sticky;top:0;z-index:20}
nav .brand{font-weight:700;font-size:18px;color:var(--txt);letter-spacing:-.2px}
nav a{color:var(--txt2);font-weight:600}
nav a:hover{color:var(--coral);text-decoration:none}
.navspacer{flex:1}
.pill{font-size:11px;padding:3px 10px;border-radius:999px;background:var(--bg2);
  border:1px solid var(--line);color:var(--mut)}

/* CTA: the ONLY full-pill element in the system */
.cta{display:inline-flex;align-items:center;gap:8px;background:var(--black);color:#fff;
  border:none;border-radius:999px;padding:14px 28px;font-weight:600;font-size:15px;
  cursor:pointer;font-family:inherit;text-decoration:none}
.cta:hover{background:var(--black2);text-decoration:none}
.cta .arw{font-weight:700}
.btnrow{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin-top:18px}

.card{background:var(--bg);border:1px solid var(--line);border-radius:12px;padding:16px;margin:0}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px}
.section{background:var(--bg2)}

label{display:block;font-weight:600;margin:14px 0 5px;color:var(--txt);font-size:14px}
.seclabel{text-transform:uppercase;font-size:12px;letter-spacing:.5px;color:var(--mut);
  font-weight:600;margin:24px 0 8px}
.sub{color:var(--mut);font-weight:400;font-size:13px}
input,textarea,select{width:100%;background:var(--bg);border:1px solid var(--line);
  color:var(--txt);border-radius:10px;padding:10px 12px;font:inherit;font-size:14px}
input:focus,textarea:focus,select:focus{outline:none;border-color:var(--coral)}
textarea{min-height:72px;resize:vertical}

/* Stage badge — amber pill, EQUAL weight at every stage */
.stage{display:inline-block;font-size:12px;font-weight:600;padding:3px 10px;border-radius:999px;
  background:var(--amber-bg);color:var(--amber-tx);text-transform:lowercase;letter-spacing:.2px}

/* Verification badge — teal when verified, gray when unverified; all lowercase */
.vbadge{display:inline-flex;align-items:center;gap:5px;font-size:12px;font-weight:600;
  padding:3px 10px;border-radius:999px;border:1px solid var(--teal);color:var(--teal);
  margin:3px 4px 3px 0;text-transform:lowercase}
.vbadge .ck{font-size:11px}
.vbadge.unverified{border-color:var(--line);color:var(--gray);background:var(--bg2)}

.tag{display:inline-block;background:var(--bg2);border:1px solid var(--line);color:var(--txt2);
  font-size:12px;padding:3px 9px;border-radius:10px;margin:2px}

/* Upvote control */
.vote{display:flex;flex-direction:column;align-items:center;justify-content:center;
  border:1px solid var(--line);border-radius:10px;padding:6px 10px;background:var(--bg);
  cursor:pointer;min-width:54px;user-select:none;color:var(--txt2)}
.vote:hover{border-color:var(--coral)}
.vote .arr{font-size:16px;line-height:1}
.vote .cnt{font-size:14px;font-weight:700;margin-top:2px}
.vote.active{color:var(--coral);border-color:var(--coral);background:#FCEEE7}

/* Speech-bubble (teal gradient, tail bottom-left) — founder-voice ONLY */
.quote{position:relative;background:linear-gradient(135deg,var(--teal),var(--teal2));
  color:#fff;border-radius:16px;padding:14px 16px;font-size:15px;line-height:1.6;margin:12px 0}
.quote:after{content:"";position:absolute;left:20px;bottom:-9px;width:0;height:0;
  border-left:10px solid transparent;border-right:0 solid transparent;
  border-top:10px solid var(--teal2)}
.quote .who{display:block;margin-top:8px;font-size:12px;opacity:.85;font-weight:600}

.muted{color:var(--mut)}.small{font-size:13px}.meta{font-size:13px;color:var(--txt2)}
.disclaimer{background:var(--amber-bg);border:1px solid #EAD9BE;color:var(--amber-tx);
  border-radius:10px;padding:10px 12px;font-size:13px;margin:10px 0}
.hero{background:var(--bg2);border:1px solid var(--line);border-radius:12px;padding:28px;margin-bottom:8px}
.lead{color:var(--txt2);max-width:680px}
.fieldrow{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:640px){.fieldrow{grid-template-columns:1fr}}

/* Segmented stage control (all stages visible at once) */
.seg{display:flex;flex-wrap:wrap;gap:8px}
.seg label{margin:0;cursor:pointer}
.seg input{position:absolute;opacity:0;pointer-events:none}
.seg span{display:inline-block;padding:9px 14px;border:1px solid var(--line);border-radius:999px;
  font-size:13px;font-weight:600;color:var(--txt2);background:var(--bg)}
.seg input:checked + span{background:var(--black);color:#fff;border-color:var(--black)}
.seg input:focus-visible + span{border-color:var(--coral)}

.trace-step{background:var(--bg2);border:1px solid var(--line);border-radius:12px;padding:14px;margin:10px 0}
.trace-step h4{margin:0 0 6px;font-size:15px}
pre{white-space:pre-wrap;word-break:break-word;background:var(--bg2);border:1px solid var(--line);
  border-radius:10px;padding:10px;font-size:12px;color:var(--txt2);max-height:320px;overflow:auto}
.ok{color:var(--teal)}.err{color:var(--coral)}

/* Login modal */
.modal{position:fixed;inset:0;background:rgba(26,26,26,.45);display:none;
  align-items:center;justify-content:center;z-index:50;padding:16px}
.modal.open{display:flex}
.modal .box{background:var(--bg);border:1px solid var(--line);border-radius:12px;
  padding:24px;max-width:380px;width:100%}
.modal h3{margin-top:0}
.modal .hint{font-size:13px;color:var(--mut);margin:6px 0 14px}
.modal .err{color:var(--coral);font-size:13px;margin-top:8px;min-height:16px}
.x{float:right;cursor:pointer;color:var(--mut);font-size:20px;line-height:1}
</style></head><body>
<nav><span class="brand">⬡ MoonshotHunt</span>
<a href="/">Directory</a><a href="/whitespace">Whitespace</a><a href="/submit">Submit</a>
<span class="navspacer"></span>
{% if user_email %}<span class="pill">{{ user_name or user_email }}</span>
{% else %}<a class="pill" href="#" onclick="return openLogin()">sign in to vote</a>{% endif %}
</nav>
<div class="wrap">{% block body %}{% endblock %}</div>

<!-- Lightweight login modal (name + email, no password) -->
<div class="modal" id="loginModal">
  <div class="box">
    <span class="x" onclick="closeLogin()">×</span>
    <h3>One quick step</h3>
    <p class="hint">We need a name + email to record your vote. No password, no verification email.</p>
    <label>Name</label><input id="lm_name" placeholder="Your name">
    <label>Email</label><input id="lm_email" placeholder="you@email.com" type="email">
    <div class="err" id="lm_err"></div>
    <div class="btnrow"><button class="cta" onclick="submitLogin()">Continue <span class="arw">→</span></button></div>
  </div>
</div>
<script>
function openLogin(){document.getElementById('loginModal').classList.add('open');return false;}
function closeLogin(){document.getElementById('loginModal').classList.remove('open');}
let pendingSid=null;
async function vote(sid){
  const email="{{ user_email or '' }}";
  if(!email){ pendingSid=sid; openLogin(); return; }
  await castVote(sid,email);
}
async function castVote(sid,email){
  const r=await fetch('/vote/'+sid,{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({email:email})});
  const d=await r.json();
  if(d.ok!==undefined){ location.reload(); }
}
async function submitLogin(){
  const name=document.getElementById('lm_name').value.trim();
  const email=document.getElementById('lm_email').value.trim();
  const err=document.getElementById('lm_err');
  if(!name||!email||!email.includes('@')){ err.textContent='Enter a name and a valid email.'; return; }
  const r=await fetch('/identify',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name:name,email:email})});
  const d=await r.json();
  if(d.ok){ closeLogin();
    if(pendingSid){ const s=pendingSid; pendingSid=null; await castVote(s,email); }
    else location.reload();
  } else { err.textContent=d.error||'Could not sign in.'; }
}
</script>
</body></html>"""


def _page(title, body):
    t = TPL_LAYOUT.replace("{% block title %}MoonshotHunt{% endblock %}",
                          "{% block title %}" + title + "{% endblock %}")
    t = t.replace("{% block body %}{% endblock %}", body)
    return t


def _lower_badges(badges):
    out = []
    for b in badges or []:
        out.append({"label": (b.get("label") or "").lower(),
                    "status": b.get("status")})
    return out


def _monogram(name):
    return (name or "?")[0].upper()


TPL_HOME = _page("MoonshotHunt — Discovery for climate & deep tech", """
<div class="hero">
  <h1>India's <span style="color:var(--coral)">pre-funding</span> climate &amp; deep-tech radar</h1>
  <p class="lead">Founders submit raw. Our agents structure it into VC-legible cards, run a
  lightweight public-signal check, and the founder approves before anything goes live.
  Self-reported, not due diligence.</p>
  <div class="btnrow"><a class="cta" href="/submit">Submit your startup <span class="arw">→</span></a>
  <span class="pill">{{ cards|length }} startups live</span>
  <span class="pill">{{ stats.visits }} visits · {{ stats.uniques }} unique visitors</span></div>
</div>
<div class="grid">
{% for c in cards %}
  {% set pc = c.published_card if c.published_card else {} %}
  {% set badges = _lower_badges(c.published_card.badges if c.published_card else c.badges) %}
  <div class="card">
    <div style="display:flex;gap:12px;align-items:flex-start">
      <div style="width:48px;height:48px;border-radius:8px;background:var(--bg2);
        border:1px solid var(--line);display:flex;align-items:center;justify-content:center;
        font-weight:700;font-size:20px;color:var(--coral);flex:none">{{ _monogram(pc.startup_name or c.raw.startup_name) }}</div>
      <div style="flex:1;min-width:0">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px">
          <strong style="font-size:17px">{{ pc.startup_name or c.raw.startup_name }}</strong>
          <span class="stage">{{ pc.stage or c.structured.stage or c.raw.stage }}</span>
        </div>
        <p style="margin:4px 0 8px;color:var(--coral)">{{ pc.tagline or c.structured.tagline }}</p>
      </div>
      <div class="vote {% if c.id in voted %}active{% endif %}" onclick="vote('{{ c.id }}')"
           title="{% if c.id in voted %}you upvoted this{% else %}upvote{% endif %}">
        <span class="arr">▲</span><span class="cnt">{{ c.voters|length }}</span>
      </div>
    </div>
    <div class="small" style="margin-top:4px"><b>Problem:</b> {{ pc.problem or c.structured.problem }}</div>
    <div class="small"><b>Opportunity:</b> {{ pc.opportunity_size or c.structured.opportunity_size }}</div>
    <div class="small"><b>Differentiator:</b> {{ pc.differentiator or c.structured.differentiator }}</div>
    <div class="small"><b>Ask:</b> {{ pc.ask or c.structured.ask }}</div>
    <div style="margin-top:10px">
      {% for b in badges %}<span class="vbadge {{ b.status }}"><span class="ck">✓</span>{{ b.label }} · {{ b.status }}</span>{% endfor %}
    </div>
    <div style="margin-top:6px">
      {% for t in (pc.subtheme_tags or c.structured.subtheme_tags or c.raw.subtheme_tags or []) %}<span class="tag">{{ t }}</span>{% endfor %}
    </div>
    <div class="btnrow"><a class="pill" href="/trace/{{ c.id }}" style="color:var(--txt2)">View agent trace →</a></div>
  </div>
{% endfor %}
</div>
{% if not cards %}<p class="muted">No published startups yet. <a href="/submit">Submit one →</a></p>{% endif %}
""")


TPL_SUBMIT = _page("Submit — MoonshotHunt", """
<h2>Submit your startup</h2>
<p class="muted small">Section 5 fields. The VC Agent expands this into a structured card —
you approve the result before it's published. This is self-reported, not due diligence.</p>
<form method="post" action="/submit">
  <div class="card">
    <div class="seclabel">Identity</div>
    <label>Startup name *</label><input name="startup_name" required>
    <label>One-line tagline <span class="sub">outcome-framed, e.g. "cuts kiln emissions 40%"</span></label><input name="tagline">
    <label>Founder name(s) *</label><input name="founder_names" required>
    <label>Founder LinkedIn *</label><input name="founder_linkedin" placeholder="https://linkedin.com/in/..." required>
    <label>Website / product link</label><input name="website" placeholder="https://">
    <label>Sub-theme tag(s) <span class="sub">pick all that apply</span></label>
    <select name="subtheme_tags" multiple size="6">
      {% for s in subthemes %}<option value="{{ s }}">{{ s }}</option>{% endfor %}
    </select>
  </div>
  <div class="card">
    <div class="seclabel">Why this matters</div>
    <label>Problem (2–3 sentences) *</label><textarea name="problem" required></textarea>
    <label>Opportunity size (number/scale + basis) *</label><textarea name="opportunity_size" required></textarea>
    <label>Why now *</label><textarea name="why_now" required></textarea>
  </div>
  <div class="card">
    <div class="seclabel">Where you are</div>
    <div class="seclabel" style="margin-top:0">Stage *</div>
    <div class="seg">
      {% for s in stages %}
      <label><input type="radio" name="stage" value="{{ s }}" {% if loop.first %}checked{% endif %}><span>{{ s }}</span></label>
      {% endfor %}
    </div>
    <label>Proof-of-work (pilot data, LOIs, demo, patent)</label><textarea name="proof_of_work"></textarea>
    <label>Early adopters / customers</label><input name="early_adopters">
    <label>GTM (high-level)</label><textarea name="gtm"></textarea>
  </div>
  <div class="card">
    <div class="seclabel">Why bet on this</div>
    <label>Success scenario / what must be true</label><textarea name="success_scenario"></textarea>
    <label>Team's relevant edge</label><textarea name="team_edge"></textarea>
    <label>What you're looking for *</label>
    <select name="looking_for">
      <option>funding</option><option>pilot partners</option><option>co-founder</option>
      <option>visibility only</option><option>customers</option>
    </select>
  </div>
  <div class="btnrow"><button type="submit" class="cta">Run agent pipeline <span class="arw">→</span></button></div>
</form>
""")


TPL_PROCESSING = _page("Processing — MoonshotHunt", """
<div class="card"><h2>Running the agent pipeline…</h2>
<p class="muted">This runs two real LLM agents on your submission. Please wait, it takes ~30–60s.</p>
<pre id="log">Initializing…</pre></div>
<script>
const sid="{{ sid }}";
async function poll(){
  const r=await fetch("/api/status/"+sid); const d=await r.json();
  const log=document.getElementById("log");
  log.textContent="STATUS: "+d.status+"\n"+(d.log||"");
  if(d.status==="review"||d.status==="error"){ window.location="/review/"+sid; return; }
  setTimeout(poll,1500);
}
poll();
</script>
""")


TPL_REVIEW = _page("Founder review — MoonshotHunt", """
<h2>Founder review &amp; approve</h2>
<p class="muted">Our agents drafted this card from your submission. Edit any field, then publish.
You — the human — are the approval gate. Nothing goes live until you click publish.</p>
<form method="post" action="/publish/{{ sid }}">
  <div class="card">
    <div class="seclabel">VC Agent structured card</div>
    <div class="fieldrow">
      <div><label>Startup name</label><input name="startup_name" value="{{ sc.startup_name }}"></div>
      <div><label>Stage</label>
        <select name="stage">{% for s in stages %}
          <option value="{{ s }}" {% if s==sc.stage %}selected{% endif %}>{{ s }}</option>{% endfor %}
        </select></div>
    </div>
    <label>Tagline (outcome-framed)</label><input name="tagline" value="{{ sc.tagline }}">
    <label>Problem (one line)</label><textarea name="problem">{{ sc.problem }}</textarea>
    <label>Opportunity size (one line)</label><textarea name="opportunity_size">{{ sc.opportunity_size }}</textarea>
    <label>Differentiator (one line)</label><textarea name="differentiator">{{ sc.differentiator }}</textarea>
    <label>Solution (one line)</label><textarea name="solution">{{ sc.solution }}</textarea>
    <label>Ask (one line)</label><textarea name="ask">{{ sc.ask }}</textarea>
  </div>
  <div class="card">
    <div class="seclabel">Verification badges · lightweight public-signal check</div>
    {% for b in badges %}<span class="vbadge {{ b.status }}"><span class="ck">✓</span>{{ b.label | lower }} · {{ b.status }}</span>{% endfor %}
    <div class="disclaimer">⚠ {{ disclaimer }}<br>
    <span class="small">Verifier checks what's mechanically checkable (LinkedIn format, website liveness, founder identity).
    It does NOT verify market size, traction, or financial claims — those remain self-reported.</span></div>
  </div>
  <div class="card">
    <div class="seclabel">Honesty attestation</div>
    <div class="quote">"I'm submitting this as an accurate representation of {{ sc.startup_name or raw.startup_name }}'s
    current stage and work. I understand this listing is self-reported and visible to the community and to investors."
    <span class="who">— {{ raw.founder_names }}</span></div>
    <label style="margin-top:12px"><input type="checkbox" name="attest" required style="width:auto;margin-right:8px">
    I attest the above is accurate and self-reported.</label>
  </div>
  <div class="btnrow"><button type="submit" class="cta">Publish listing <span class="arw">→</span></button>
  <a class="pill" href="/trace/{{ sid }}" style="color:var(--txt2)">View agent trace</a></div>
</form>
""")


TPL_TRACE = _page("Agent trace — MoonshotHunt", """
<h2>Agent trace — <span style="color:var(--coral)">{{ rec.raw.startup_name or rec.structured.startup_name }}</span></h2>
<p class="meta">Submission {{ sid }} · status: <b>{{ rec.status }}</b> · created {{ rec.created_at }}</p>
{% for t in rec.trace %}
<div class="trace-step">
  <h4>{{ t.agent }}</h4>
  <div class="meta">{{ t.role }}</div>
  <div class="meta">model: <code>{{ t.model or '—' }}</code> · latency: {{ t.latency }}s
    · prompt tok: {{ t.prompt_tokens }} · completion tok: {{ t.completion_tokens }}
    · {% if t.ok %}<span class="ok">✓ ok</span>{% elif t.ok is sameas false %}<span class="err">✗ failed</span>{% else %}—{% endif %}</div>
  <div class="meta" style="margin-top:6px">input → {{ t.input_summary }}</div>
  {% if t.checks %}<div class="meta" style="margin-top:6px">checks →
    {% for k,v in t.checks.items() %}<span class="pill">{{ k }}: {{ v }}</span> {% endfor %}</div>{% endif %}
  {% if t.badges %}<div style="margin-top:6px">badges →
    {% for b in t.badges %}<span class="vbadge {{ b.status }}"><span class="ck">✓</span>{{ b.label | lower }} · {{ b.status }}</span>{% endfor %}</div>{% endif %}
  <details style="margin-top:8px"><summary class="small muted">raw agent output</summary>
  <pre>{{ t.raw_output or '(none)' }}</pre></details>
</div>
{% endfor %}
<div class="btnrow"><a class="pill" href="/" style="color:var(--txt2)">← Directory</a>
{% if rec.status=='review' %}<a class="cta" href="/review/{{ sid }}">Go to review <span class="arw">→</span></a>{% endif %}</div>
""")


TPL_WHITESPACE = _page("Whitespace — MoonshotHunt", """
<div id="wsroot" style="position:relative">
  <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:8px">
    <div>
      <h2 style="margin-bottom:2px">Whitespace map</h2>
      <p class="muted small" style="margin:0">Bubble size = startups tagged in a sub-theme. Faint dashed bubbles = sparse / open whitespace for VCs.</p>
    </div>
    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
      <select id="stageFilter" style="width:auto">
        <option value="">all stages</option>
        {% for s in stages %}<option value="{{ s }}">{{ s }}</option>{% endfor %}
      </select>
      <button class="pill" style="cursor:pointer" onclick="toggleAll()">collapse / expand all</button>
      <button class="pill" style="cursor:pointer" onclick="fitView()">fit view</button>
      <button class="pill" style="cursor:pointer" onclick="zoom(0.1)">+</button>
      <button class="pill" style="cursor:pointer" onclick="zoom(-0.1)">−</button>
      <button class="pill" style="cursor:pointer" onclick="toggleHelp()">how to</button>
      <a class="pill" href="/" style="color:var(--txt2)">← directory</a>
    </div>
  </div>

  <div id="helpBox" class="card" style="display:none;position:absolute;top:60px;right:0;z-index:30;max-width:280px">
    <div class="seclabel" style="margin-top:0">how to read this</div>
    <ul class="small" style="margin:0;padding-left:18px;line-height:1.7;color:var(--txt2)">
      <li><b>Left/top</b> = Climate · <b>right/bottom</b> = Deep Tech</li>
      <li>Bigger bubble = more startups in that sub-theme</li>
      <li>Dashed faint bubble = <b>whitespace</b> (0–1 startups)</li>
      <li>Click a sub-theme to orbit its startups</li>
      <li>Click a startup to open its detail panel</li>
    </ul>
  </div>

  <div id="stage" style="position:relative;height:640px;border:1px solid var(--line);border-radius:12px;
       overflow:hidden;background:var(--bg)">
    <div id="zoneTint" style="position:absolute;inset:0;pointer-events:none;
      background:linear-gradient(105deg, rgba(216,90,48,.05) 0%, rgba(216,90,48,.02) 42%, rgba(29,158,117,.02) 58%, rgba(29,158,117,.05) 100%)"></div>
    <div id="divider" style="position:absolute;top:6%;bottom:6%;left:50%;width:1px;
      background:repeating-linear-gradient(var(--line),var(--line) 6px,transparent 6px,transparent 12px)"></div>
    <div id="zoneClimate" style="position:absolute;top:14px;left:18px;font-size:12px;font-weight:700;
      color:var(--coral);letter-spacing:.5px">CLIMATE</div>
    <div id="zoneDeep" style="position:absolute;top:14px;right:18px;font-size:12px;font-weight:700;
      color:var(--teal);letter-spacing:.5px">DEEP TECH</div>
    <svg id="edges" style="position:absolute;inset:0;width:100%;height:100%;pointer-events:none"></svg>
    <div id="viewport" style="position:absolute;inset:0;transform-origin:center center"></div>
  </div>
</div>

<!-- Right-side detail panel (reuses founder-card layout) -->
<div id="panelOverlay" onclick="closePanel(event)" style="display:none;position:fixed;inset:0;
     background:rgba(26,26,26,.25);z-index:60">
  <aside id="panel" style="position:absolute;top:0;right:0;height:100%;width:min(420px,92vw);
     background:var(--bg);border-left:1px solid var(--line);padding:22px;overflow:auto"></aside>
</div>

<script>
const STAGE_FILTER=()=>document.getElementById('stageFilter').value;
let DATA=null, expanded=new Set(), scale=1;
const W=()=>document.getElementById('stage').clientWidth, H=()=>document.getElementById('stage').clientHeight;

function bubbleR(count){ return count<=1 ? 24 : Math.min(24+count*7, 54); }

async function load(){
  const r=await fetch('/api/whitespace?stage='+encodeURIComponent(STAGE_FILTER()));
  DATA=await r.json(); render();
}

function layout(){
  // Climate bubbles fan out on the left semicircle, Deep Tech on the right.
  const cx=W()/2, cy=H()/2, positions={};
  const xrad=W()*0.29, yrad=H()*0.36;   // separate radii; leaves margin for labels
  DATA.zones.forEach(z=>{
    const n=z.bubbles.length, left=(z.side==='climate');
    z.bubbles.forEach((b,i)=>{
      const t=(i+0.5)/n;                  // 0..1 top->bottom
      const ang=(-0.4+t*0.8)*Math.PI;     // arc ~ -72deg .. +72deg
      positions[b.key]={
        x: cx + (left?-1:1)*Math.cos(ang)*xrad,
        y: cy + Math.sin(ang)*yrad
      };
    });
  });
  return {cx,cy,positions};
}

function render(){
  const vp=document.getElementById('viewport'); vp.innerHTML='';
  const svg=document.getElementById('edges'); svg.innerHTML='';
  const {cx,cy,positions}=layout();

  // center
  vp.appendChild(node(cx,cy,'<div style="text-align:center;font-weight:700;font-size:13px;color:var(--txt)">'+
    DATA.center+'</div>', 70, 'background:var(--bg2);border:1px solid var(--line)'));

  DATA.zones.forEach(z=>{
    z.bubbles.forEach(b=>{
      const p=positions[b.key], r=bubbleR(b.count), active=expanded.has(b.key);
      // edge center->bubble
      line(svg,cx,cy,p.x,p.y, b.sparse?'var(--line)':'#E3E3E3', b.sparse);
      // bubble
      const border = active ? '2px solid var(--coral)'
                   : b.sparse ? '1.5px dashed var(--line)'
                   : b.verified_heavy ? '1.5px solid var(--teal)' : '1px solid #D9D9D9';
      const bg = active ? '#FCEEE7' : b.sparse ? 'var(--bg)' : 'var(--bg2)';
      const op = b.sparse ? 'opacity:.7' : '';
      const el=node(p.x,p.y,
        '<div style="text-align:center;line-height:1.15">'+
        '<div style="font-size:'+(b.count>3?18:15)+'px;font-weight:700;color:'+
          (active?'var(--coral)':'var(--txt)')+'">'+b.count+'</div></div>',
        r*2, 'background:'+bg+';border:'+border+';cursor:pointer;'+op);
      el.onclick=()=>{ if(expanded.has(b.key)) expanded.delete(b.key); else expanded.add(b.key); render(); };
      // floating cluster label near bubble
      const lab=document.createElement('div');
      lab.textContent=b.label+(b.sparse?' · whitespace':'');
      lab.style.cssText='position:absolute;left:'+p.x+'px;top:'+(p.y+r+6)+'px;transform:translateX(-50%);'+
        'font-size:10.5px;color:'+(b.sparse?'var(--mut)':'var(--txt2)')+';white-space:nowrap;pointer-events:none';
      vp.appendChild(lab);

      // Level 2: orbit startup cards when expanded
      if(active && b.startups.length){
        b.startups.forEach((s,i)=>{
          const a=(i/b.startups.length)*Math.PI*2 - Math.PI/2;
          const orad=r+58;
          const sx=p.x+Math.cos(a)*orad, sy=p.y+Math.sin(a)*orad;
          line(svg,p.x,p.y,sx,sy,'#ECECEC',false);
          const card=node(sx,sy,
            '<div style="display:flex;align-items:center;gap:6px">'+
            '<div style="width:22px;height:22px;border-radius:6px;background:var(--bg2);border:1px solid var(--line);'+
              'display:flex;align-items:center;justify-content:center;font-weight:700;font-size:11px;color:var(--coral);flex:none">'+s.initial+'</div>'+
            '<div style="text-align:left;min-width:0"><div style="font-size:11px;font-weight:600;white-space:nowrap;'+
              'max-width:92px;overflow:hidden;text-overflow:ellipsis">'+s.name+'</div>'+
            '<span class="stage" style="font-size:9px;padding:1px 7px">'+s.stage+'</span></div></div>',
            null,'background:var(--bg);border:1px solid var(--line);cursor:pointer;padding:6px 9px;border-radius:10px;width:auto');
          card.onclick=(e)=>{ e.stopPropagation(); openPanel(s.id); };
        });
      }
    });
  });
}

function node(x,y,html,d,extra){
  const el=document.createElement('div');
  const size = d? 'width:'+d+'px;height:'+d+'px;border-radius:50%;' : '';
  el.style.cssText='position:absolute;left:'+x+'px;top:'+y+'px;transform:translate(-50%,-50%);'+
    'display:flex;align-items:center;justify-content:center;'+size+(extra||'');
  el.innerHTML=html;
  document.getElementById('viewport').appendChild(el);
  return el;
}
function line(svg,x1,y1,x2,y2,color,dash){
  const l=document.createElementNS('http://www.w3.org/2000/svg','line');
  l.setAttribute('x1',x1);l.setAttribute('y1',y1);l.setAttribute('x2',x2);l.setAttribute('y2',y2);
  l.setAttribute('stroke',color);l.setAttribute('stroke-width',dash?1:1.3);
  if(dash) l.setAttribute('stroke-dasharray','4 5');
  svg.appendChild(l);
}

async function openPanel(id){
  const r=await fetch('/api/startup/'+id); const s=await r.json();
  const badges=(s.badges||[]).map(b=>'<span class="vbadge '+b.status+'"><span class="ck">✓</span>'+b.label+' · '+b.status+'</span>').join('');
  const tags=(s.subtheme_tags||[]).map(t=>'<span class="tag">'+t+'</span>').join('');
  document.getElementById('panel').innerHTML=
    '<span class="x" style="float:right;cursor:pointer;color:var(--mut);font-size:22px" onclick="closePanel()">×</span>'+
    '<div style="display:flex;gap:12px;align-items:center"><div style="width:48px;height:48px;border-radius:8px;'+
      'background:var(--bg2);border:1px solid var(--line);display:flex;align-items:center;justify-content:center;'+
      'font-weight:700;font-size:20px;color:var(--coral)">'+(s.startup_name||'?')[0]+'</div>'+
    '<div><h3 style="margin:0">'+s.startup_name+'</h3><span class="stage">'+s.stage+'</span></div></div>'+
    '<p style="color:var(--coral);margin:10px 0 4px">'+(s.tagline||'')+'</p>'+
    '<div class="small"><b>Problem:</b> '+(s.problem||'')+'</div>'+
    '<div class="small"><b>Opportunity:</b> '+(s.opportunity_size||'')+'</div>'+
    '<div class="small"><b>Differentiator:</b> '+(s.differentiator||'')+'</div>'+
    '<div class="small"><b>Ask:</b> '+(s.ask||'')+'</div>'+
    '<div style="margin-top:10px">'+badges+'</div><div style="margin-top:6px">'+tags+'</div>'+
    '<div class="btnrow"><a class="pill" style="color:var(--txt2)" href="'+s.trace_url+'">view agent trace →</a>'+
    '<span class="pill">▲ '+s.votes+' upvotes</span></div>';
  document.getElementById('panelOverlay').style.display='block';
}
function closePanel(e){ if(!e||e.target.id==='panelOverlay'||e.type==='click'){ if(e&&e.target&&e.target.id==='panel')return;
  document.getElementById('panelOverlay').style.display='none'; } }

function toggleAll(){ const all=DATA.zones.flatMap(z=>z.bubbles.filter(b=>b.count>0).map(b=>b.key));
  if(expanded.size>=all.length){ expanded.clear(); } else { all.forEach(k=>expanded.add(k)); } render(); }
function zoom(d){ scale=Math.max(0.5,Math.min(1.8,scale+d));
  document.getElementById('viewport').style.transform='scale('+scale+')';
  document.getElementById('edges').style.transform='scale('+scale+')';
  document.getElementById('edges').style.transformOrigin='center center'; }
function fitView(){ scale=1; zoom(0); }
function toggleHelp(){ const h=document.getElementById('helpBox'); h.style.display=h.style.display==='none'?'block':'none'; }
document.getElementById('stageFilter').onchange=load;
window.addEventListener('resize',()=>DATA&&render());
load();
</script>
""")


# Register template helpers (defined above)
app.jinja_env.globals["_lower_badges"] = _lower_badges
app.jinja_env.globals["_monogram"] = _monogram


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
def _current_user():
    email = session.get("email")
    if not email:
        return None
    u = store.get_user(email) or {}
    return {"email": email, "name": u.get("name", "")}


def _visitor_id():
    """Stable per-browser id in the signed session cookie (same approach as login)."""
    vid = session.get("vid")
    if not vid:
        vid = uuid.uuid4().hex
        session["vid"] = vid
        session.permanent = True
    return vid


@app.route("/")
def home():
    cards = []
    for s in store.published():
        rec = store.get(s["id"])
        if rec:
            cards.append(rec)
    # default sort: most-upvoted first, then newest
    cards.sort(key=lambda c: (len(c.get("voters", [])), c.get("created_at", "")), reverse=True)
    user = _current_user()
    stats = store.record_visit(_visitor_id())
    voted = set()
    if user:
        for c in cards:
            if user["email"] in c.get("voters", []):
                voted.add(c["id"])
    return render_template_string(TPL_HOME, cards=cards, voted=voted, stats=stats,
                                  user_email=user["email"] if user else "",
                                  user_name=user["name"] if user else "")


@app.route("/submit", methods=["GET"])
def submit_get():
    user = _current_user()
    return render_template_string(TPL_SUBMIT, stages=STAGES, subthemes=SUBTHEMES,
                                  user_email=user["email"] if user else "",
                                  user_name=user["name"] if user else "")


@app.route("/submit", methods=["POST"])
def submit_post():
    keys = ["startup_name", "tagline", "founder_names", "founder_linkedin", "website",
            "problem", "opportunity_size", "why_now", "stage", "proof_of_work",
            "early_adopters", "gtm", "success_scenario", "team_edge", "looking_for"]
    raw = {k: (request.form.get(k) or "").strip() for k in keys}
    raw["subtheme_tags"] = request.form.getlist("subtheme_tags")
    rec = store.create_submission(raw)
    store.update(rec["id"], {"log": "queued"})
    threading.Thread(target=_run_pipeline_bg, args=(rec["id"],), daemon=True).start()
    return redirect(url_for("processing", sid=rec["id"]))


def _run_pipeline_bg(sid):
    rec = store.get(sid)
    store.update(sid, {"log": "VC Agent: reading submission…"})
    res = agents.run_pipeline(rec)
    rec = store.get(sid)
    rec["structured"] = res["structured"]
    rec["badges"] = res["badges"]
    rec["disclaimer"] = res["disclaimer"]
    rec["trace"] = res["trace"]
    rec["status"] = "review" if res["structured"] and "_raw" not in res["structured"] else "error"
    rec["log"] = "done"
    store.update(sid, rec)


@app.route("/processing/<sid>")
def processing(sid):
    user = _current_user()
    return render_template_string(TPL_PROCESSING, sid=sid,
                                  user_email=user["email"] if user else "",
                                  user_name=user["name"] if user else "")


@app.route("/api/status/<sid>")
def api_status(sid):
    rec = store.get(sid) or {}
    return jsonify({"status": rec.get("status"), "log": rec.get("log", "")})


@app.route("/review/<sid>", methods=["GET"])
def review(sid):
    rec = store.get(sid)
    if not rec:
        return "not found", 404
    sc = rec.get("structured", {})
    if not sc:
        return "Pipeline hasn't completed yet. <a href='/processing/" + sid + "'>Check status</a>", 202
    for k in ["startup_name", "tagline", "problem", "opportunity_size",
              "differentiator", "solution", "ask", "stage"]:
        sc.setdefault(k, "")
    user = _current_user()
    return render_template_string(TPL_REVIEW, sid=sid, sc=sc, raw=rec["raw"],
                                  badges=_lower_badges(rec.get("badges", [])),
                                  disclaimer=rec.get("disclaimer", ""),
                                  stages=STAGES,
                                  user_email=user["email"] if user else "",
                                  user_name=user["name"] if user else "")


@app.route("/publish/<sid>", methods=["POST"])
def publish(sid):
    rec = store.get(sid)
    if not rec:
        return "not found", 404
    if not request.form.get("attest"):
        return "Attestation required.", 400
    published_card = {
        "startup_name": request.form.get("startup_name", ""),
        "tagline": request.form.get("tagline", ""),
        "stage": request.form.get("stage", ""),
        "problem": request.form.get("problem", ""),
        "opportunity_size": request.form.get("opportunity_size", ""),
        "differentiator": request.form.get("differentiator", ""),
        "solution": request.form.get("solution", ""),
        "ask": request.form.get("ask", ""),
        "subtheme_tags": rec.get("raw", {}).get("subtheme_tags", []),
        "badges": rec.get("badges", []),
        "published_at": store.now_iso(),
    }
    rec["published_card"] = published_card
    rec["status"] = "published"
    store.update(sid, rec)
    return redirect(url_for("home"))


@app.route("/trace/<sid>")
def trace(sid):
    rec = store.get(sid)
    if not rec:
        return "not found", 404
    user = _current_user()
    return render_template_string(TPL_TRACE, sid=sid, rec=rec,
                                  user_email=user["email"] if user else "",
                                  user_name=user["name"] if user else "")


# --- Lightweight login + voting (no password, no verification email) ---
@app.route("/identify", methods=["POST"])
def identify():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    if not name or "@" not in email:
        return jsonify({"ok": False, "error": "name and valid email required"}), 400
    store.identify(name, email)
    session["email"] = email
    session["name"] = name
    return jsonify({"ok": True})


@app.route("/vote/<sid>", methods=["POST"])
def do_vote(sid):
    user = _current_user()
    if not user:
        return jsonify({"ok": False, "error": "not_identified"}), 401
    # toggle: if already voted, remove; else add
    rec = store.get(sid)
    voters = rec.get("voters", []) if rec else []
    if user["email"] in voters:
        count = store.unvote(sid, user["email"])
        return jsonify({"ok": True, "voted": False, "count": count})
    ok, count, reason = store.vote(sid, user["email"])
    return jsonify({"ok": ok, "voted": True, "count": count, "reason": reason})


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/health")
def health():
    return jsonify({"ok": True, "model": agents.DEF_MODEL})


# ---------------------------------------------------------------------------
# Whitespace clustered view (radial bubble map)
# ---------------------------------------------------------------------------
# Map our real sub-theme tags onto the spec's zone taxonomy. Bubbles with no
# mapped startups (built-environment, biotech, semiconductors, quantum) stay
# empty on purpose — that empty space IS the whitespace signal for VCs.
WS_TAG_MAP = {
    # Climate
    "energy-storage": "energy-storage", "grid-tech": "energy-storage",
    "industrial-decarbonization": "industrial-decarbonization",
    "carbon-capture": "carbon-capture", "agritech-climate": "sustainable-agriculture",
    "circular-economy": "circular-economy", "waste-to-value": "circular-economy",
    "sustainable-mobility": "sustainable-mobility", "water-tech": "resilience-adaptation",
    # Deep Tech
    "climate-ai": "ai-infrastructure", "deep-tech-other": "ai-infrastructure",
    "materials-science": "advanced-materials",
    "robotics-in-healthcare": "robotics-automation", "nanorobotics": "nanorobotics",
    "space-tech": "space-tech",
}
WS_ZONES = [
    {"name": "Climate", "side": "climate", "bubbles": [
        "energy-storage", "industrial-decarbonization", "carbon-capture",
        "resilience-adaptation", "sustainable-agriculture", "circular-economy",
        "sustainable-mobility", "built-environment"]},
    {"name": "Deep Tech", "side": "deeptech", "bubbles": [
        "robotics-automation", "advanced-materials", "nanorobotics",
        "ai-infrastructure", "biotech", "space-tech", "semiconductors", "quantum"]},
]


def _whitespace_data(stage_filter=""):
    """Build the two-zone bubble graph from published startups."""
    buckets = {b: [] for z in WS_ZONES for b in z["bubbles"]}
    for s in store.published():
        rec = store.get(s["id"])
        if not rec:
            continue
        pc = rec.get("published_card", {})
        stage = pc.get("stage") or rec.get("raw", {}).get("stage", "")
        if stage_filter and stage != stage_filter:
            continue
        name = pc.get("startup_name") or rec.get("raw", {}).get("startup_name", "")
        tags = pc.get("subtheme_tags") or rec.get("raw", {}).get("subtheme_tags", []) or []
        badges = pc.get("badges", [])
        verified = sum(1 for b in badges if b.get("status") == "verified")
        seen = set()
        for t in tags:
            bubble = WS_TAG_MAP.get(t)
            if bubble and bubble not in seen:
                seen.add(bubble)
                buckets[bubble].append({"id": rec["id"], "name": name, "stage": stage,
                                        "initial": (name or "?")[0].upper(),
                                        "verified": verified})
    zones = []
    for z in WS_ZONES:
        bubbles = []
        for b in z["bubbles"]:
            sl = buckets[b]
            vsum = sum(x["verified"] for x in sl)
            bubbles.append({"key": b, "label": b, "count": len(sl),
                            "sparse": len(sl) <= 1,
                            "verified_heavy": len(sl) >= 2 and (vsum / len(sl)) > 2.0,
                            "startups": sl})
        zones.append({"name": z["name"], "side": z["side"], "bubbles": bubbles})
    return {"center": "MoonshotHunt Whitespace", "zones": zones}


@app.route("/api/whitespace")
def api_whitespace():
    return jsonify(_whitespace_data(request.args.get("stage", "").strip()))


@app.route("/api/startup/<sid>")
def api_startup(sid):
    rec = store.get(sid)
    if not rec:
        return jsonify({"error": "not_found"}), 404
    pc = rec.get("published_card", {}) or rec.get("structured", {})
    return jsonify({
        "id": sid,
        "startup_name": pc.get("startup_name") or rec.get("raw", {}).get("startup_name", ""),
        "tagline": pc.get("tagline", ""), "stage": pc.get("stage", ""),
        "problem": pc.get("problem", ""), "opportunity_size": pc.get("opportunity_size", ""),
        "differentiator": pc.get("differentiator", ""), "ask": pc.get("ask", ""),
        "subtheme_tags": pc.get("subtheme_tags") or rec.get("raw", {}).get("subtheme_tags", []),
        "badges": _lower_badges(pc.get("badges", [])),
        "votes": len(rec.get("voters", [])),
        "trace_url": "/trace/" + sid,
    })


@app.route("/whitespace")
def whitespace():
    user = _current_user()
    return render_template_string(TPL_WHITESPACE, stages=STAGES,
                                  user_email=user["email"] if user else "",
                                  user_name=user["name"] if user else "")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
