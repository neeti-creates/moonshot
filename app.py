"""MoonshotHunt — Flask app wiring the agent pipeline to a real submission form,
founder review, trace log, published directory, upvotes, and lightweight login.
Agents make REAL live LLM calls to the Nous Research inference endpoint.

Design system: light, Product-Hunt-style (see DESIGN_SPEC.md).
"""
import os, json, threading, uuid, tempfile, shutil
from flask import (Flask, request, render_template_string, redirect, url_for,
                   jsonify, session)
import store, agents, extract

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "moonshothunt-dev-key")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
store.init(DATA_DIR)

STAGES = ["idea", "prototype", "pilot", "early revenue", "scaling"]

# Layer-2 sub-sector SEGMENTS (granular). Founders pick these on review; agent tags at this level.
SUBTHEMES = [
    # Clean Energy & Grid
    "renewable-generation", "energy-storage", "grid-infrastructure",
    # Mobility & Transport
    "evs", "alt-fuels", "micromobility-logistics",
    # Built Environment & Industry
    "decarbonized-materials", "building-tech",
    # Food, Land Use & Agriculture
    "precision-ag", "alt-proteins", "soil-carbon",
    # Carbon Capture & Removal
    "carbon-removal", "carbon-accounting",
    # Circular Economy & Waste
    "waste-to-value", "recycling-tech",
    # Water & Climate Resilience
    "water-mgmt", "climate-fintech-risk",
    # Advanced Computing & Connectivity
    "quantum-computing", "next-gen-hardware",
    # AI & ML
    "advanced-ai",
    # Robotics, Machines & Space
    "autonomous-systems", "aerospace-spacetech",
    # Materials & Physical Sciences
    "advanced-materials", "photonics",
    # Biotechnology & Life Sciences
    "synthetic-biology", "healthcare-tech",
    # Web3 & DLT
    "blockchain-infra",
]

# Two-level taxonomy for the nucleated Directory.
# Layer 1 = sub-sector (the bubbles / theme tiles). Layer 2 = segments (expand under each).
THEME_ZONES = [
    {"key": "climate", "name": "Climate Tech", "groups": [
        {"key": "energy-grid", "name": "Clean Energy & Grid", "seg": ["renewable-generation", "energy-storage", "grid-infrastructure"]},
        {"key": "mobility", "name": "Mobility & Transport", "seg": ["evs", "alt-fuels", "micromobility-logistics"]},
        {"key": "built", "name": "Built Environment & Industry", "seg": ["decarbonized-materials", "building-tech"]},
        {"key": "food-ag", "name": "Food, Land Use & Agriculture", "seg": ["precision-ag", "alt-proteins", "soil-carbon"]},
        {"key": "carbon", "name": "Carbon Capture & Removal", "seg": ["carbon-removal", "carbon-accounting"]},
        {"key": "circular", "name": "Circular Economy & Waste", "seg": ["waste-to-value", "recycling-tech"]},
        {"key": "water", "name": "Water & Climate Resilience", "seg": ["water-mgmt", "climate-fintech-risk"]},
    ]},
    {"key": "deep", "name": "Deep Tech", "groups": [
        {"key": "compute", "name": "Advanced Computing & Connectivity", "seg": ["quantum-computing", "next-gen-hardware"]},
        {"key": "ai", "name": "Artificial Intelligence & ML", "seg": ["advanced-ai"]},
        {"key": "robotics", "name": "Robotics, Machines & Space", "seg": ["autonomous-systems", "aerospace-spacetech"]},
        {"key": "materials", "name": "Materials & Physical Sciences", "seg": ["advanced-materials", "photonics"]},
        {"key": "biotech", "name": "Biotechnology & Life Sciences", "seg": ["synthetic-biology", "healthcare-tech"]},
        {"key": "web3", "name": "Web3 & Distributed Ledger", "seg": ["blockchain-infra"]},
    ]},
]
_SEG_LABELS = {s: s.replace("-", " ").title() for z in THEME_ZONES for g in z["groups"] for s in g["seg"]}
_SUB_TO_GROUP = {s: g["key"] for z in THEME_ZONES for g in z["groups"] for s in g["seg"]}
_GROUP_NAME = {g["key"]: g["name"] for z in THEME_ZONES for g in z["groups"]}
# Forward-map legacy subtheme tags (pre-restructure) onto the new segment keys.
_LEGACY_MAP = {
    "waste-to-value": "waste-to-value", "industrial-decarbonization": "decarbonized-materials",
    "climate-ai": "advanced-ai", "energy-storage": "energy-storage", "green-hydrogen": "alt-fuels",
    "carbon-capture": "carbon-removal", "sustainable-mobility": "evs", "agritech-climate": "precision-ag",
    "water-tech": "water-mgmt", "circular-economy": "recycling-tech", "grid-tech": "grid-infrastructure",
    "robotics-in-healthcare": "autonomous-systems", "nanorobotics": "autonomous-systems",
    "space-tech": "aerospace-spacetech", "materials-science": "advanced-materials", "deep-tech-other": "advanced-materials",
}


def _norm_tags(c):
    pc = c.get("published_card") or {}
    tags = pc.get("subtheme_tags") or c.get("structured", {}).get("subtheme_tags") or c.get("raw", {}).get("subtheme_tags", []) or []
    out = []
    for t in tags:
        out.append(_LEGACY_MAP.get(t, t))
    return out


def group_counts(cards):
    """Count published startups per Layer-1 group key (stable counts)."""
    counts = {}
    for c in cards:
        seen = set()
        for t in _norm_tags(c):
            gk = _SUB_TO_GROUP.get(t)
            if gk and gk not in seen:
                counts[gk] = counts.get(gk, 0) + 1
                seen.add(gk)
    return counts


def segment_counts(cards):
    """Count published startups per Layer-2 segment key (stable counts)."""
    counts = {}
    for c in cards:
        seen = set()
        for t in _norm_tags(c):
            if t not in seen:
                counts[t] = counts.get(t, 0) + 1
                seen.add(t)
    return counts

# ---------------------------------------------------------------------------
# Design system (light, Product-Hunt-style) — applied to ALL templates
# ---------------------------------------------------------------------------
TPL_LAYOUT = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<title>{% block title %}MoonshotHunt{% endblock %}</title>
<style>
:root{
  --bg:#FFFFFF; --bg2:#F8F7F4; --txt:#1A1A1A; --txt2:#6B6B6B; --mut:#9B9B9B;
  --line:#EAEAEA; --coral:#5B3A8E; --coral-bg:#F1EBFA; --teal:#1D9E75; --teal2:#0F6E56;
  --amber-bg:#FAEEDA; --amber-tx:#854F0B; --black:#111111; --black2:#2B2B2B;
  --blue:#2F7FE0; --blue2:#1E5FB8; --beige:#F6F1E7; --red:#E5484D; --tan:#C9A36B;
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
.wrap-full{max-width:none;margin:0;padding:0}
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
.btnrow{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:14px}
.stats{display:flex;gap:34px;flex-wrap:wrap;margin-top:18px}
.stats .stat{display:flex;flex-direction:column;line-height:1.1}
.stats .stat b{font-size:30px;font-weight:800;color:var(--coral)}
.stats .stat span{font-size:12.5px;color:var(--txt2);margin-top:3px}

.card{background:var(--bg);border:1px solid var(--line);border-radius:12px;padding:16px;margin:0;
  box-shadow:0 1px 3px rgba(26,26,26,.06);transition:box-shadow .15s ease,border-color .15s ease,transform .15s ease}
.card:hover{box-shadow:0 6px 16px rgba(91,58,142,.12);border-color:var(--coral);transform:translateY(-2px)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:18px}

/* ===== TICKET CARD (blue / beige / coral) ===== */
.tk{background:var(--beige);border-radius:16px;overflow:hidden;box-shadow:0 10px 28px rgba(26,26,26,.16);
  border:1px solid #e7ddc9;position:relative;font-family:"Space Grotesk",-apple-system,BlinkMacSystemFont,sans-serif}
.tk .shot{height:120px;position:relative;overflow:hidden;display:flex;align-items:center;justify-content:center;
  background:linear-gradient(160deg,#3a342e,#211d18)}
.tk.light .shot{background:linear-gradient(160deg,#d9cfbd,#b6a890)}
.tk .shot .art{width:92px;height:92px;border-radius:50%;
  background:radial-gradient(circle at 38% 32%, rgba(255,255,255,.30), rgba(255,255,255,.02) 62%);
  box-shadow:inset 0 0 22px rgba(0,0,0,.4)}
.tk .dots{position:absolute;left:0;right:0;top:78px;height:54px;pointer-events:none}
.tk .dots i{position:absolute;width:10px;height:10px;border-radius:50%}
.tk .dots i:nth-child(1){left:20px;top:4px}
.tk .dots i:nth-child(2){left:50%;top:22px;transform:translateX(-50%)}
.tk .dots i:nth-child(3){right:20px;top:44px}
.info{padding:15px 16px 14px;color:#fff;position:relative}
.info.blue{background:linear-gradient(160deg,#4F9BF2,#1E5FB8)}
.info.coral{background:linear-gradient(160deg,#FA8A66,#F87060)}
.info.red{background:linear-gradient(160deg,#EE6A6E,#E5484D)}
.info.beige{background:linear-gradient(160deg,#E9DCC2,#D8C6A4);color:#1A1A1A}
.tk.blue .dots i{background:var(--blue)}
.tk.coral .dots i{background:#F87060}
.tk.red .dots i{background:#E5484D}
.tk.beige .dots i{background:#C9A36B}
.info .date{display:flex;align-items:center;gap:10px;font-weight:700;font-size:13px;opacity:.8}
.info .date .ln{flex:1;height:1.5px;background:currentColor;opacity:.45}
.info .title{font-weight:700;font-size:26px;letter-spacing:-.5px;text-transform:lowercase;margin:6px 0 4px;line-height:1}
.info .tagline{font-size:12.5px;line-height:1.3;margin:0 0 8px;opacity:.95}
.info .impact{font-size:11.5px;line-height:1.3;margin:0 0 9px;font-style:italic;opacity:.92}
.info .ticket{display:flex;align-items:center;gap:7px;font-size:9.5px;letter-spacing:.16em;text-transform:uppercase;font-weight:600}
.info .ticket .o{width:12px;height:12px;border-radius:50%;background:#1A1A1A;display:flex;align-items:center;justify-content:center}
.info .ticket .o::after{content:"";width:4px;height:4px;border-radius:50%;background:#fff}
.info .rows{margin-top:9px;border-top:1px solid rgba(255,255,255,.32);padding-top:8px}
.info.beige .rows{border-top-color:rgba(26,26,26,.22)}
.info .frow{display:flex;gap:8px;font-size:11px;padding:2px 0}
.info .fk{font-weight:700;text-transform:uppercase;letter-spacing:.06em;font-size:9px;min-width:48px;padding-top:1px;opacity:.85}
.info .fv{font-family:var(--mono);font-size:10.5px}
.info .vrow{display:flex;align-items:center;gap:6px;margin-top:10px;font-size:10px;flex-wrap:wrap}
.info .vdot{width:8px;height:8px;border-radius:50%;flex:none;background:rgba(255,255,255,.5)}
.info .vdot.verified{background:#0F6E56}
.info.beige .vdot.verified{background:#0F6E56}
.info .vtxt{opacity:.85;font-size:9.5px;text-transform:uppercase;letter-spacing:.04em}
.info .vote{margin-left:auto;display:flex;align-items:center;gap:5px;background:rgba(255,255,255,.2);
  color:#fff;border:none;border-radius:999px;padding:5px 11px;font-weight:700;font-size:12px;cursor:pointer;font-family:inherit}
.info.beige .vote{background:rgba(26,26,26,.12);color:#1A1A1A}
.info .vote.active{background:#fff;color:var(--blue)}
.info.beige .vote.active{background:#1A1A1A;color:#fff}
.info .vbar{height:26px;width:48px;margin-top:12px;
  background:repeating-linear-gradient(0deg,#1A1A1A 0 2px,transparent 2px 4px,#1A1A1A 4px 5px,transparent 5px 9px);opacity:.8}
.info.beige .vbar{opacity:.55}
.info .bcnum{font-family:var(--mono);font-size:7.5px;letter-spacing:.1em;margin-top:2px;opacity:.7}

/* ===== NUCLEATED DIRECTORY ===== */
.filterbar{display:flex;gap:8px;align-items:center;flex-wrap:nowrap;position:sticky;top:64px;z-index:15;
  background:#F4F5F7;border:1px solid var(--line);
  border-radius:14px;padding:8px 12px;margin:18px 0;box-shadow:0 1px 4px rgba(26,26,26,.05);max-width:100%;overflow:hidden}
.filterbar .search{flex:1 1 140px;min-width:0;display:flex;align-items:center;gap:8px;background:#fff;
  border:1px solid var(--line);border-radius:10px;padding:8px 14px}
.filterbar .search .sico{color:var(--mut);font-size:16px;flex:none}
.filterbar .search input{border:none;background:none;outline:none;flex:1;min-width:0;font:inherit;font-size:14px}
.filterbar .fsel{flex:0 1 auto;min-width:0;border:1px solid var(--line);border-radius:999px;padding:8px 28px 8px 13px;font:inherit;
  background:#fff url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%236B6B6B'/%3E%3C/svg%3E") no-repeat right 12px center;
  -webkit-appearance:none;appearance:none;color:var(--txt);cursor:pointer;max-width:170px;overflow:hidden;text-overflow:ellipsis}
.filterbar .cta{flex:none;padding:8px 16px}
.filterbar .pill{flex:none;white-space:nowrap}
@media(max-width:640px){.filterbar{flex-wrap:wrap}
  .filterbar .search{flex:1 1 100%}
  .filterbar .fsel{flex:1 1 auto;max-width:none}
  .filterbar .cta{flex:1 1 auto}}

.activepill{margin:6px 0 12px}
.nuc{position:relative;border-radius:16px;overflow:hidden;margin:8px 0 22px;border:1px solid var(--line)}
.nucbg{position:absolute;inset:0;
  background-color:#FBFBFD;
  background-image:linear-gradient(#F0F0F0 1px,transparent 1px),linear-gradient(90deg,#F0F0F0 1px,transparent 1px);
  background-size:28px 28px}
.nuctools{position:absolute;top:12px;right:14px;z-index:6;display:flex;gap:8px}
.nucbtn{border:1px solid var(--line);background:var(--bg);border-radius:999px;padding:6px 12px;font:inherit;font-size:12px;cursor:pointer;color:var(--txt)}
.nucbtn:hover{border-color:var(--blue);color:var(--blue)}
.showmap{margin:0 0 18px}
.nucinner{position:relative;display:flex;flex-wrap:wrap;gap:26px 30px;align-items:flex-start;justify-content:center;
  padding:34px 44px 44px;min-height:300px}
.zonetag{position:absolute;font-size:13px;letter-spacing:.14em;text-transform:uppercase;color:rgba(107,107,107,.28);font-weight:700;pointer-events:none;z-index:0}
.zonetag.zt-0{top:18px;left:24px}
.zonetag.zt-1{top:18px;right:24px;text-align:right}
/* organic, non-overlapping stagger (flow reserves space; expansion never collides) */
.bubwrap{display:flex;flex-direction:column;align-items:center;gap:10px;z-index:2}
.bubwrap.big .bub{width:150px;height:150px}
.bubwrap.mid .bub{width:118px;height:118px}
.bubwrap.sm .bub{width:92px;height:92px}
.bubwrap.big .bname{font-size:14px}
.bubwrap.sm .bname{font-size:11.5px}
.bubwrap.sm .bcount{font-size:15px}
.bubwrap:nth-child(3n+1){transform:translateY(18px)}
.bubwrap:nth-child(3n+2){transform:translateY(-10px)}
.bubwrap:nth-child(4n+3){transform:translateY(30px)}
.bubwrap:nth-child(5n){transform:translateY(-6px)}
.bub{width:118px;height:118px;border-radius:50%;display:flex;flex-direction:column;align-items:center;justify-content:center;
  text-decoration:none;color:#fff;font-family:"Space Grotesk",sans-serif;border:2px solid rgba(255,255,255,.6);cursor:pointer;
  box-shadow:0 6px 22px rgba(26,26,26,.12),inset 0 0 18px rgba(255,255,255,.18);
  transition:transform .15s ease,box-shadow .15s ease}
.bub:hover{transform:scale(1.06);box-shadow:0 10px 30px rgba(26,26,26,.18)}
.bub .bname{font-weight:600;font-size:13px;text-align:center;padding:0 8px;line-height:1.1}
.bub .bcount{font-family:var(--mono);font-size:18px;font-weight:700;margin-top:3px}
.bub-0{background:linear-gradient(150deg,#4F9BF2,#1E5FB8)}
.bub-1{background:linear-gradient(150deg,#E9DCC2,#C9A36B);color:#1A1A1A}
.bub-2{background:linear-gradient(150deg,#EE6A6E,#E5484D)}
/* sub-segments: smaller, lighter circles, revealed on click */
.segs{display:none;flex-wrap:wrap;gap:8px;justify-content:center;max-width:240px}
.segs.open{display:flex}
.segcircle{width:64px;height:64px;border-radius:50%;display:flex;flex-direction:column;align-items:center;justify-content:center;
  text-decoration:none;color:#1A1A1A;font-family:"Space Grotesk",sans-serif;border:1.5px solid rgba(255,255,255,.7);
  box-shadow:0 3px 12px rgba(26,26,26,.08);transition:transform .12s ease,box-shadow .12s ease}
.segcircle:hover{transform:scale(1.08)}
.segcircle .sname{font-weight:600;font-size:8.5px;text-align:center;padding:0 5px;line-height:1.05}
.segcircle .scount{font-family:var(--mono);font-size:11px;font-weight:700;margin-top:2px}
.segcircle.seg-0{background:linear-gradient(150deg,#BFDCF7,#9CC2EE)}
.segcircle.seg-1{background:linear-gradient(150deg,#F0E7D6,#E2D2B4)}
.segcircle.seg-2{background:linear-gradient(150deg,#F6C9CB,#F1B0B3)}
.segall{font-size:11px;color:var(--mut);text-decoration:none;align-self:center;white-space:nowrap}
.segall:hover{color:var(--blue)}

.gridwrap{margin-top:8px}
.gridhead{font-size:13px;color:var(--txt2);margin:6px 2px 12px;font-weight:600}
.disc{max-width:760px}
.hero.slim{padding:26px 0 10px}
.hero.slim h1{font-size:26px}
.thread{border:1px solid var(--line);border-radius:16px;padding:22px 24px;background:var(--bg);margin-bottom:18px}
.threadhead{display:flex;align-items:center;justify-content:space-between;gap:12px}
.threadhead h2{font-size:21px}
.threadbody{color:var(--txt2);line-height:1.55;margin:12px 0 4px;white-space:pre-wrap}
.replies{margin-top:18px;border-top:1px solid var(--line);padding-top:14px;display:flex;flex-direction:column;gap:14px}
.reply{border-left:3px solid var(--line);padding:2px 0 2px 14px}
.rhead{display:flex;align-items:center;gap:8px;font-size:14px}
.rolebadge{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;border-radius:999px;padding:2px 8px}
.rolebadge.founder{background:var(--coral-bg);color:var(--coral)}
.rolebadge.vc{background:#E3F1EC;color:var(--teal2)}
.reply p{margin:4px 0 0;color:var(--txt);line-height:1.5}
.topicform{max-width:620px;border:1px dashed var(--coral);border-radius:14px;padding:18px 20px;margin:6px 0 18px;background:var(--bg2)}
.replybox{max-width:620px;margin-top:8px}
.muted.small{color:var(--mut);font-size:13px}
.tinyerr{color:var(--coral);font-size:13px;margin-top:8px;min-height:16px}

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
.vbadge.unverified{border-color:var(--line);color:var(--gray);background:transparent;opacity:.7}

.tag{display:inline-block;background:var(--bg2);border:1px solid var(--line);color:var(--txt2);
  font-size:12px;padding:3px 9px;border-radius:10px;margin:2px}

/* Upvote control */
.vote{display:flex;flex-direction:column;align-items:center;justify-content:center;
  border:1px solid var(--line);border-radius:10px;padding:6px 10px;background:var(--bg);
  cursor:pointer;min-width:54px;user-select:none;color:var(--txt2)}
.vote:hover{border-color:var(--coral)}
.vote .arr{font-size:16px;line-height:1}
.vote .cnt{font-size:14px;font-weight:700;margin-top:2px}
.vote.active{color:var(--coral);border-color:var(--coral);background:var(--coral-bg)}

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
.hero{background:linear-gradient(135deg,#F3EDFB 0%,#EEF3FB 55%,#FBF1EE 100%);border:1px solid var(--line);border-radius:16px;padding:30px 30px 24px;margin-bottom:8px}
.hero h1{font-size:30px;line-height:1.15;margin:0 0 10px;letter-spacing:-.01em}
.lead{color:var(--txt2);max-width:680px}
.chips{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-top:18px}
.chiplbl{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--mut);font-weight:600;margin-right:2px}
.funpill{font-size:13px;text-decoration:none;color:var(--txt);background:var(--bg);border:1px solid var(--line);
  border-radius:999px;padding:6px 13px;transition:border-color .12s,color .12s,transform .12s}
.funpill:hover{border-color:var(--blue);color:var(--blue);transform:translateY(-1px)}

.fieldrow{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:640px){.fieldrow{grid-template-columns:1fr}}

/* Segmented stage control (all stages visible at once) */
.seg{display:flex;flex-wrap:wrap;gap:8px}
.seg label{margin:0;cursor:pointer}
.seg input{position:absolute;opacity:0;pointer-events:none}
.seg span{display:inline-block;padding:9px 14px;border:1px solid var(--line);border-radius:999px;
  font-size:13px;font-weight:600;color:var(--txt2);background:var(--bg)}
.seg input:checked + span{background:var(--black);color:#fff;border-color:var(--black)}
.seg span.on{background:var(--black);color:#fff;border-color:var(--black)}

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
<nav><a class="brand" href="/" style="text-decoration:none;color:inherit">⬡ MoonshotHunt</a>
<a href="/directory">Directory</a><a href="/whitespace">Whitespace</a><a href="/discussion">Discussion</a><a href="/submit">Submit</a>
<span class="navspacer"></span>
{% if user_email %}<span class="pill">Hi, {{ (user_name.split(' ')[0] if user_name else user_email.split('@')[0]) }}</span>
{% else %}<a class="pill" href="#" onclick="return openLogin()">sign in to vote</a>{% endif %}
</nav>
<div class="wrap">{% block body %}{% endblock %}</div>

<!-- Lightweight login modal (name + email + role, no password) -->
<div class="modal" id="loginModal">
  <div class="box">
    <span class="x" onclick="closeLogin()">×</span>
    <h3>One quick step</h3>
    <p class="hint">We need a name + email to record your vote. No password, no verification email.</p>
    <label>Name</label><input id="lm_name" placeholder="Your name">
    <label>Email</label><input id="lm_email" placeholder="you@email.com" type="email">
    <label>I am a…</label>
    <div class="seg" id="lm_role">
      <span class="on" data-role="founder" onclick="setRole('founder')">Founder</span>
      <span data-role="vc" onclick="setRole('vc')">VC / Investor</span>
    </div>
    <div class="err" id="lm_err"></div>
    <div class="btnrow"><button class="cta" onclick="submitLogin()">Continue <span class="arw">→</span></button></div>
  </div>
</div>
<script>
function openLogin(){document.getElementById('loginModal').classList.add('open');return false;}
function closeLogin(){document.getElementById('loginModal').classList.remove('open');}
let pendingSid=null, pendingRole='founder';
function setRole(r){ pendingRole=r;
  document.querySelectorAll('#lm_role span').forEach(s=>s.classList.toggle('on', s.dataset.role===r)); }
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
function hideMap(){ const n=document.getElementById('nuc'); if(n) n.style.display='none';
  const s=document.getElementById('showMap'); if(s) s.style.display='inline-block'; }
function showMap(){ const n=document.getElementById('nuc'); if(n) n.style.display='block';
  const s=document.getElementById('showMap'); if(s) s.style.display='none'; }
function toggleExpandAll(){
  const segs=[...document.querySelectorAll('.segs')];
  const anyOpen=segs.some(e=>e.classList.contains('open'));
  segs.forEach(e=>anyOpen?e.classList.remove('open'):e.classList.add('open'));
  const btn=document.getElementById('expandBtn');
  if(btn) btn.textContent = anyOpen ? 'Expand all' : 'Collapse all';
}
function toggleSeg(key){
  const el=document.getElementById('segs-'+key);
  if(!el) return;
  const open=el.classList.toggle('open');
  if(open) collapseAllExcept(el);
  syncExpandBtn();
}
function collapseAllExcept(keep){ document.querySelectorAll('.segs.open').forEach(o=>{ if(o!==keep) o.classList.remove('open'); }); }
function syncExpandBtn(){
  const segs=[...document.querySelectorAll('.segs')];
  const btn=document.getElementById('expandBtn');
  if(!btn||!segs.length) return;
  btn.textContent = segs.every(e=>e.classList.contains('open')) ? 'Collapse all' : 'Expand all';
}

async function submitLogin(){
  const name=document.getElementById('lm_name').value.trim();
  const email=document.getElementById('lm_email').value.trim();
  const err=document.getElementById('lm_err');
  if(!name||!email||!email.includes('@')){ err.textContent='Enter a name and a valid email.'; return; }
  const r=await fetch('/identify',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name:name,email:email,role:pendingRole})});
  const d=await r.json();
  if(d.ok){ closeLogin();
    if(pendingSid){ const s=pendingSid; pendingSid=null; await castVote(s,email); }
    else location.reload();
  } else { err.textContent=d.error||'Could not sign in.'; }
}
</script>
<!-- Cloudflare Web Analytics --><script type='module' src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{"token": "b74ce3e4fe6b442483b3551635d49c17"}'></script><!-- End Cloudflare Web Analytics -->
</body></html>"""


def _page(title, body, fullbleed=None):
    if fullbleed is None:
        fullbleed = 'id="wsroot"' in body  # whitespace map opts in automatically
    t = TPL_LAYOUT.replace("{% block title %}MoonshotHunt{% endblock %}",
                          "{% block title %}" + title + "{% endblock %}")
    t = t.replace('<div class="wrap">{% block body %}{% endblock %}</div>',
                  '<div class="wrap' + (' wrap-full' if fullbleed else '') + '">{% block body %}{% endblock %}</div>')
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



def _spec_code(sid, color):
    short = (sid or "0000000000")[:4].upper()
    prefix = {"blue": "BL", "red": "RE", "beige": "BE"}.get(color, "MH")
    return f"MH·{prefix}·2026·{short}"


def _abs_url(u):
    """Ensure an absolute http(s) URL so profile links don't resolve relative."""
    if not u:
        return ""
    u = u.strip()
    if u.startswith(("http://", "https://")):
        return u
    if u.startswith("//"):
        return "https:" + u
    return "https://" + u


def _logo_for(rec):
    """Best-effort logo from the startup website domain (Clearbit, no key).
    Falls back to None so the card keeps its generated motif."""
    raw = (rec.get("raw") or {}) if isinstance(rec, dict) else {}
    site = raw.get("website") or ""
    site = _abs_url(site)
    if not site:
        return None
    try:
        from urllib.parse import urlparse
        host = urlparse(site).netloc or ""
        if host.startswith("www."):
            host = host[4:]
        if not host:
            return None
        return f"https://logo.clearbit.com/{host}?size=128"
    except Exception:
        return None


TPL_HOME = _page("MoonshotHunt — Discovery for climate & deep tech", """
<div class="hero">
  <h1>Building the future of <span style="color:var(--coral)">climate</span> &amp; <span style="color:var(--blue)">deep tech</span> — pre-funding?</h1>
  <p class="lead">You're early. So are the people who should back you. MoonshotHunt is where pre-seed climate &amp; deep-tech founders get structured, VC-legible, and discovered — before the deck polish.</p>
  <span class="pill">{{ metrics.startups }} startups live</span>
  <span class="pill">{{ stats.visits }} visits · {{ stats.uniques }} unique visitors</span></div>
  <div class="stats" aria-label="platform metrics">
    <div class="stat"><b>{{ metrics.startups }}</b><span>startups tracked</span></div>
    <div class="stat"><b>{{ metrics.builders }}</b><span>builders on platform</span></div>
    <div class="stat"><b>{{ metrics.vcs }}</b><span>VCs on platform</span></div>
  </div>
  <div class="chips">
    <span class="chiplbl">Explore:</span>
    <a class="funpill" href="/directory?group=energy-grid">⚡ Clean Energy</a>
    <a class="funpill" href="/directory?group=carbon">🌍 Carbon Removal</a>
    <a class="funpill" href="/directory?group=circular">♻️ Circular Economy</a>
    <a class="funpill" href="/directory?group=robotics">🤖 Robotics</a>
    <a class="funpill" href="/directory?group=ai">🧠 AI &amp; ML</a>
    <a class="funpill" href="/directory?group=biotech">🧬 Biotech</a>
  </div>
</div>

<!-- Persistent search + filters (clean single bar, SS1 style) -->
<form class="filterbar" id="dirForm" method="get" action="/directory">
  <input type="hidden" name="group" value="{{ filters.group }}">
  <input type="hidden" name="segment" value="{{ filters.segment }}">
  <div class="search"><span class="sico">⌕</span><input name="q" value="{{ filters.q }}" placeholder="Search startups, problems, tags…" onkeydown="if(event.key==='Enter'){event.preventDefault();document.getElementById('dirForm').requestSubmit();}"></div>
  <select class="fsel" name="stage"><option value="">All stages</option>{% for s in stages %}<option value="{{ s }}" {% if s==filters.stage %}selected{% endif %}>{{ s }}</option>{% endfor %}</select>
  <select class="fsel" name="verify"><option value="">Any verification</option><option value="verified" {% if filters.verify=='verified' %}selected{% endif %}>Verified</option><option value="unverified" {% if filters.verify=='unverified' %}selected{% endif %}>Unverified</option></select>
  <button class="cta" type="submit">Apply</button>
  {% if filters.group or filters.segment or filters.q or filters.stage or filters.verify %}<a class="pill" href="/directory">Clear ✕</a>{% endif %}
</form>

<!-- Nucleated bubble map (single entry point; click a sub-sector to reveal its sub-segments) -->
{% if active_segment_name %}<div class="activepill"><span class="pill" style="background:var(--coral-bg);color:var(--coral)">Segment: {{ active_segment_name }} <a href="/directory?group={{ active_group }}" style="margin-left:6px;color:inherit">✕</a></span></div>
{% elif active_group_name %}<div class="activepill"><span class="pill" style="background:var(--coral-bg);color:var(--coral)">Sub-sector: {{ active_group_name }} <a href="/directory" style="margin-left:6px;color:inherit">✕</a></span></div>{% endif %}

<div class="nuc" id="nuc" style="display:{% if active_group or active_segment %}none{% else %}block{% endif %}">
  <div class="nucbg"></div>
  <div class="nuctools">
    <button class="nucbtn" type="button" id="expandBtn" onclick="toggleExpandAll()">Expand all</button>
    <button class="nucbtn" type="button" id="hideMap" onclick="hideMap()">Hide map</button>
  </div>
  <div class="nucinner" id="nucinner">
    {% for z in zones %}
    <span class="zonetag zt-{{ loop.index0 % 2 }}">{{ z.name }}</span>
    {% endfor %}
    {% for z in zones %}{% for g in z.groups %}
    {% set _n = counts.get(g.key, 0) %}
    <div class="bubwrap {% if _n>=6 %}big{% elif _n>=3 %}mid{% else %}sm{% endif %}">
      <button class="bub bub-{{ loop.index0 % 3 }}" type="button"
              onclick="toggleSeg('{{ g.key }}')">
        <span class="bname">{{ g.name }}</span><span class="bcount">{{ counts.get(g.key, 0) }}</span>
      </button>
      <div class="segs" id="segs-{{ g.key }}">
        {% for s in g.seg %}
        <a class="segcircle seg-{{ loop.index0 % 3 }}" title="{{ seg_labels.get(s, s) }}"
           href="/directory?segment={{ s }}{% if filters.stage %}&stage={{ filters.stage }}{% endif %}{% if filters.verify %}&verify={{ filters.verify }}{% endif %}{% if filters.q %}&q={{ filters.q }}{% endif %}">
          <span class="sname">{{ seg_labels.get(s, s) }}</span><span class="scount">{{ seg_counts.get(s, 0) }}</span>
        </a>
        {% endfor %}
        <a class="segall" href="/directory?group={{ g.key }}{% if filters.stage %}&stage={{ filters.stage }}{% endif %}{% if filters.verify %}&verify={{ filters.verify }}{% endif %}{% if filters.q %}&q={{ filters.q }}{% endif %}">view all →</a>
      </div>
    </div>
    {% endfor %}{% endfor %}
  </div>
</div>
<button class="nucbtn showmap" id="showMap" style="display:none" onclick="showMap()">Show map</button>

<div class="gridwrap">
  <div class="gridhead">
    <span>{% if active_segment_name %}{{ active_segment_name }} — {{ cards|length }} startup{{ '' if cards|length==1 else 's' }}
    {% elif active_group_name %}{{ active_group_name }} — {{ cards|length }} startup{{ '' if cards|length==1 else 's' }}
    {% else %}{{ cards|length }} startups{% endif %}</span>
  </div>
  <div class="grid">
{% for c in cards %}
  {% set pc = c.published_card if c.published_card else {} %}
  {% set badges = _lower_badges(c.published_card.badges if c.published_card else c.badges) %}
  {% set tcol = ['blue','beige','red'][loop.index0 % 3] %}
  {% set logo = _logo_for(c) %}
  <a class="tk {{ 'light' if tcol=='beige' else '' }} {{ tcol }}" href="/profile/{{ c.id }}" style="text-decoration:none;color:inherit;display:block">
    <div class="shot"{% if logo %} style="background-image:url('{{ logo }}');background-size:cover;background-position:center"{% endif %}><span class="art"></span></div>
    <div class="dots"><i></i><i></i><i></i></div>
    <div class="info {{ tcol }}">
      <div class="date"><span class="ln"></span><span class="yr">2026</span></div>
      <div class="title">{{ (pc.startup_name or c.raw.startup_name or 'untitled') | lower }}</div>
      <p class="tagline">{{ pc.tagline or c.structured.tagline or '' }}</p>
      {% if pc.impact_line %}<p class="impact">✦ {{ pc.impact_line }}</p>{% endif %}
      <div class="ticket"><span class="o"></span> TICKET</div>
      <div class="rows">
        <div class="frow"><span class="fk">Stage</span><span class="fv">{{ pc.stage or c.structured.stage or c.raw.stage or '—' }}</span></div>
        <div class="frow"><span class="fk">Theme</span><span class="fv">{{ (pc.subtheme_tags or c.structured.subtheme_tags or c.raw.subtheme_tags or [])|join(' · ') }}</span></div>
      </div>
      <div class="vrow">
        {% for b in badges %}<span class="vdot {{ b.status }}"></span>{% endfor %}
        <span class="vtxt">{% for b in badges %}{{ b.label }}{% if not loop.last %}, {% endif %}{% endfor %}</span>
        <span class="vote {% if c.id in voted %}active{% endif %}" onclick="event.stopPropagation();vote('{{ c.id }}')"
              title="{% if c.id in voted %}you upvoted this{% else %}upvote{% endif %}">
          <span class="arr">▲</span><span class="cnt">{{ c.voters|length }}</span></span>
      </div>
      <div class="vbar"></div><div class="bcnum">{{ _spec_code(c.id, tcol) }}</div>
    </div>
  </a>
{% endfor %}
  </div>
  {% if not cards %}<p class="muted">No startups match these filters. <a href="/directory">Reset</a></p>{% endif %}
</div>
""")


TPL_SUBMIT = _page("Submit — MoonshotHunt", """
<h2>Submit your startup</h2>
<p class="muted small">Upload whatever you have — deck, one-pager, tech spec, product doc. Our agent reads it like a VC would and drafts your listing. You'll review everything before it goes live.</p>
<form method="post" action="/submit" enctype="multipart/form-data" id="subForm">
  <div class="card">
    <div class="seclabel">Identity <span class="sub">you type these directly — they're authoritative</span></div>
    <label>Startup name *</label><input name="startup_name" required>
    <label>Founder name(s) *</label><input name="founder_names" required>
    <label>Founder LinkedIn * <span class="sub">needed for the mechanical verifier check</span></label><input name="founder_linkedin" placeholder="https://linkedin.com/in/..." required>
    <label>Founder email * <span class="sub">for your session; we won't spam</span></label><input name="founder_email" type="email" placeholder="you@startup.com" required>
    <label>Website / product link</label><input name="website" placeholder="https://">
  </div>

  <div class="card">
    <div class="seclabel">Uploads <span class="sub">PDF / PPTX / DOCX · max 5 files · 20MB each · the agent reads these</span></div>
    <div id="drop" style="border:2px dashed var(--coral);border-radius:12px;padding:28px;text-align:center;color:var(--txt2);
         background:var(--bg2);cursor:pointer;transition:background .15s">
      <div style="font-size:30px">⬆</div>
      <div style="font-weight:600;color:var(--txt)">Drag &amp; drop files here</div>
      <div class="small">or click to browse</div>
      <input id="fileInput" type="file" name="files" multiple accept=".pdf,.pptx,.docx" style="display:none">
    </div>
    <div id="chips" style="display:flex;flex-wrap:wrap;gap:8px;margin-top:10px"></div>
  </div>

  <div class="card">
    <div class="seclabel">Links <span class="sub">press / article / extra URLs</span></div>
    <div id="linkRows" style="display:flex;flex-direction:column;gap:8px">
      <input class="linkinp" name="url1" placeholder="https://article-or-press-link">
    </div>
    <button type="button" class="pill" id="addLink" style="cursor:pointer;margin-top:8px">+ add another link</button>
  </div>

  <div class="btnrow"><button type="submit" class="cta">Run agent pipeline <span class="arw">→</span></button></div>
</form>
<script>
const MAXF=5, MAXL=5, drop=document.getElementById('drop'), fi=document.getElementById('fileInput');
const chips=document.getElementById('chips'); let files=[];
function renderChips(){
  chips.innerHTML='';
  files.forEach((f,i)=>{
    const sz=(f.size/1024/1024).toFixed(1)+'MB';
    const c=document.createElement('div');
    c.style.cssText='display:flex;align-items:center;gap:8px;background:var(--bg2);border:1px solid var(--line);border-radius:999px;padding:5px 10px;font-size:13px';
    c.innerHTML='<span style="font-weight:600;color:var(--coral)">📎</span>'+f.name+' <span class="muted small">'+sz+'</span> <span style="cursor:pointer;color:var(--mut)" onclick="rmFile('+i+')">✕</span>';
    chips.appendChild(c);
  });
  const dt=new DataTransfer(); files.forEach(f=>dt.items.add(f)); fi.files=dt.files;
}
function rmFile(i){ files.splice(i,1); renderChips(); }
drop.onclick=()=>fi.click();
fi.onchange=e=>{ addFiles(e.target.files); };
['dragover','dragenter'].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.style.background='#F1EBFA';}));
['dragleave','drop'].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.style.background='var(--bg2)';}));
drop.addEventListener('drop',e=>{ addFiles(e.dataTransfer.files); });
function addFiles(list){
  for(const f of list){ if(files.length>=MAXF) break;
    const ext=f.name.rsplit('.',1)[-1].toLowerCase();
    if(['pdf','pptx','docx'].includes(ext) && f.size<=20*1024*1024) files.push(f); }
  files=files.slice(0,MAXF); renderChips();
}
let links=1;
document.getElementById('addLink').onclick=()=>{ if(links>=MAXL) return;
  links++; const inp=document.createElement('input'); inp.className='linkinp';
  inp.name='url'+links; inp.placeholder='https://article-or-press-link';
  document.getElementById('linkRows').appendChild(inp); };
</script>
""")


TPL_PROCESSING = _page("Processing — MoonshotHunt", """
<div class="card"><h2>Running the agent pipeline…</h2>
<p class="muted">This runs two real LLM agents on your uploads. Please wait, it takes ~30–60s.</p>
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
<p class="muted">Our agent drafted this card from your uploads. Fields marked <span style="color:var(--coral);font-weight:700">auto-drafted</span>
were inferred by the agent — edit anything before publishing. You — the human — are the approval gate.</p>
<form method="post" action="/publish/{{ sid }}">
  <div class="card">
    <div class="seclabel">Identity <span class="sub">what you typed — authoritative</span></div>
    <div class="fieldrow">
      <div><label>Startup name</label><input name="startup_name" value="{{ sc.startup_name }}"></div>
      <div><label>Stage <span style="color:var(--coral);font-weight:700">auto-drafted</span></label>
        <select name="stage">
          {% for s in ['idea','prototype','pilot','early revenue','scaling'] %}
          <option value="{{ s }}" {% if s==sc.stage %}selected{% endif %}>{{ s }}</option>{% endfor %}
        </select></div>
    </div>
  </div>

  <div class="card">
    <div class="seclabel">Agent-drafted card <span style="color:var(--coral);font-weight:700">auto-drafted</span> — review &amp; edit</div>
    <label>Tagline (outcome-framed)</label><input name="tagline" value="{{ sc.tagline }}">
    <label>Problem (one line)</label><textarea name="problem">{{ sc.problem }}</textarea>
    <label>Opportunity size (one line)</label><textarea name="opportunity_size">{{ sc.opportunity_size }}</textarea>
    <label>Differentiator (one line)</label><textarea name="differentiator">{{ sc.differentiator }}</textarea>
    <label>Solution (one line)</label><textarea name="solution">{{ sc.solution }}</textarea>
    <label>Ask (one line)</label><textarea name="ask">{{ sc.ask }}</textarea>
    <label>"If this wins" — impact line <span class="sub">one high-emotion sentence, mission-legible</span></label><textarea name="impact_line">{{ sc.impact_line }}</textarea>
    <label>Sub-theme tags <span class="sub">auto-inferred — adjust</span></label>
    <div class="seg">{% for s in subthemes %}
      <label><input type="checkbox" name="subtheme_tags" value="{{ s }}" {% if s in sc.subtheme_tags %}checked{% endif %}><span>{{ s }}</span></label>
    {% endfor %}</div>
  </div>

  {% if conflicts %}
  <div class="card" style="border-color:var(--coral)">
    <div class="seclabel" style="color:var(--coral)">⚠ Source conflicts the agent flagged</div>
    {% for c in conflicts %}
    <div class="disclaimer" style="margin:6px 0">• <b>{{ c.field }}</b>: {{ c.note }}</div>
    {% endfor %}
    <div class="small muted">The agent picked the more authoritative source for the field above — confirm or override.</div>
  </div>
  {% endif %}

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

TPL_REVIEW_ERR = _page("Draft failed — MoonshotHunt", """
<h2>Draft couldn't be generated</h2>
<p class="muted">Our agent didn't return a usable draft for your submission this time. This is usually
a transient model timeout — your uploads were received fine. You can retry, or submit again shortly.</p>
<div class="card">
  <div class="seclabel">What happened</div>
  <div class="disclaimer">{{ err }}</div>
</div>
<div class="btnrow">
  <a class="cta" href="/submit">Try again <span class="arw">→</span></a>
  <a class="pill" href="/trace/{{ sid }}" style="color:var(--txt2)">View agent trace</a>
</div>
""")


TPL_PROFILE = _page("VC profile — MoonshotHunt", """
<div style="max-width:760px;margin:0 auto">
  <a class="pill" href="/directory" style="color:var(--txt2)">← Directory</a>
  <div style="display:flex;align-items:center;gap:14px;margin:14px 0 6px">
    <div style="width:54px;height:54px;border-radius:10px;background:var(--bg2);border:1px solid var(--line);
      display:flex;align-items:center;justify-content:center;font-weight:700;font-size:22px;color:var(--coral);flex:none">
      {{ _monogram(pc.startup_name) }}</div>
    <div style="flex:1;min-width:0">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:10px">
        <h1 style="margin:0;font-size:26px">{{ pc.startup_name }}</h1>
        <span class="stage">{{ pc.stage }}</span>
      </div>
      <p style="margin:6px 0 0;color:var(--coral);font-size:16px;font-weight:600">{{ pc.tagline }}</p>
    </div>
  </div>

  <div style="display:flex;flex-wrap:wrap;gap:8px;margin:12px 0 4px">
    {% for t in subthemes %}<span class="tag">{{ t }}</span>{% endfor %}
  </div>
  <div style="display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 18px">
    {% for b in badges %}<span class="vbadge {{ b.status }}"><span class="ck">✓</span>{{ b.label }} · {{ b.status }}</span>{% endfor %}
  </div>

  <div class="memo">
    {% if pc.impact_line %}<div class="mrow" style="background:var(--coral-bg)"><div class="mlabel">If this wins</div><div class="mval"><b>{{ pc.impact_line }}</b></div></div>{% endif %}
    <div class="mrow"><div class="mlabel">Problem</div><div class="mval">{{ pc.problem or 'Not specified by founder' }}</div></div>
    <div class="mrow"><div class="mlabel">Opportunity size</div><div class="mval">{{ pc.opportunity_size or 'Not specified by founder' }}</div></div>
    <div class="mrow"><div class="mlabel">Differentiator</div><div class="mval">{{ pc.differentiator or 'Not specified by founder' }}</div></div>
    <div class="mrow"><div class="mlabel">Solution</div><div class="mval">{{ pc.solution or 'Not specified by founder' }}</div></div>
    <div class="mrow"><div class="mlabel">What they're looking for</div><div class="mval">{{ pc.ask or 'Not specified by founder' }}</div></div>
  </div>

  <div class="card" style="margin-top:18px">
    <div class="seclabel">Founder</div>
    <div class="small"><b>Name:</b> {{ rec.raw.founder_names or 'Not specified' }}</div>
    {% if rec.raw.founder_linkedin %}<div class="small"><b>LinkedIn:</b> <a href="{{ _abs_url(rec.raw.founder_linkedin) }}" target="_blank" rel="noopener" style="color:var(--coral)">{{ rec.raw.founder_linkedin }}</a></div>{% endif %}
    {% if rec.raw.website %}<div class="small"><b>Website:</b> <a href="{{ _abs_url(rec.raw.website) }}" target="_blank" rel="noopener" style="color:var(--coral)">{{ _abs_url(rec.raw.website) }}</a></div>{% endif %}
  </div>

  <div class="btnrow" style="margin-top:18px">
    <a class="pill" href="/trace/{{ sid }}" style="color:var(--txt2)">View agent trace →</a>
    <span class="muted small" style="margin-left:auto">Self-reported · not due diligence · drafted by the MoonshotHunt VC Agent</span>
  </div>
</div>
<style>
.memo{border:1px solid var(--line);border-radius:12px;overflow:hidden;background:var(--bg)}
.mrow{display:flex;gap:16px;padding:14px 16px;border-bottom:1px solid var(--line)}
.mrow:last-child{border-bottom:none}
.mlabel{width:160px;flex:none;font-weight:600;color:var(--txt2);font-size:13px;text-transform:uppercase;letter-spacing:.04em}
.mval{flex:1;color:var(--txt);line-height:1.5}
</style>
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
<div class="btnrow"><a class="pill" href="/directory" style="color:var(--txt2)">← Directory</a>
{% if rec.status=='review' %}<a class="cta" href="/review/{{ sid }}">Go to review <span class="arw">→</span></a>{% endif %}</div>
""")


TPL_WHITESPACE = _page("Whitespace — MoonshotHunt", """
<div id="wsroot" style="position:relative;padding:14px 16px">
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
      <a class="pill" href="/directory" style="color:var(--txt2)">← directory</a>
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

  <div id="stage" style="position:relative;height:calc(100vh - 150px);min-height:520px;border:none;border-radius:0;
       overflow:hidden;background:var(--bg);
       background-image:linear-gradient(#F0F0F0 1px,transparent 1px),linear-gradient(90deg,#F0F0F0 1px,transparent 1px);background-size:28px 28px">
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
let DATA=null, expanded=new Set(), manual={}, scale=1;
const W=()=>document.getElementById('stage').clientWidth, H=()=>document.getElementById('stage').clientHeight;

function bubbleR(count){ return count<=1 ? 15 : Math.min(15+count*4, 36); }

async function load(){
  const r=await fetch('/api/whitespace?stage='+encodeURIComponent(STAGE_FILTER()));
  DATA=await r.json(); render();
}

// Collision-aware, Prysm-style radial layout.
// Each zone's bubbles sit on concentric half-arcs facing outward from center.
// Ring radius is chosen so the arc length can hold each bubble's diameter + gap,
// and bubbles are evenly spaced along the arc -> no overlaps, no clipping.
function layout(){
  const cx=W()/2, cy=H()/2, positions={};
  const halfW = W()*0.46, halfH = H()*0.42;     // max ring radius bounds
  const pad = 52;                                // outer margin for labels
  const gap = 12;                                // min spacing between bubbles
  DATA.zones.forEach(z=>{
    const left=(z.side==='climate');
    const n=z.bubbles.length;
    const bs=[...z.bubbles].sort((a,b)=>b.count-a.count);
    const maxR=bubbleR(bs[0].count);
    // distribute across rings; bigger bubbles first claim outer rings
    const rings=Math.min(3, Math.max(1, Math.ceil(n/5)));
    // ring radii from inner to outer
    const r0=pad+maxR, r1=Math.min(halfW, halfH*2) - pad;
    const radii=[]; for(let k=0;k<rings;k++) radii.push(r0+(r1-r0)*(rings===1?0.6:k/(rings-1)));
    // how many each ring can hold (arc = PI*r)
    const cap=radii.map(rad=>Math.max(1, Math.floor(Math.PI*rad/(2*maxR+gap))));
    const per=[]; let assigned=0;
    // fill outer rings first (more capacity)
    for(let k=rings-1;k>=0;k--){
      let cnt=Math.min(cap[k], n-assigned);
      per[k]=cnt; assigned+=cnt;
    }
    while(assigned<n){ // spill remaining onto outer ring
      per[rings-1]++; assigned++;
    }
    let bi=0;
    for(let k=0;k<rings;k++){
      const rad=radii[k], cnt=per[k];
      // arc faces outward: left side spans 90..270 deg, right side spans -90..90 deg
      const a0 = left ? Math.PI*0.5 : -Math.PI*0.5;
      const a1 = left ? Math.PI*1.5 : Math.PI*0.5;
      for(let j=0;j<cnt;j++){
        const b=bs[bi++];
        const t = cnt===1 ? 0.5 : j/(cnt-1);
        const ang = a0 + (a1-a0)*t;
        let x = cx + Math.cos(ang)*rad;
        let y = cy + Math.sin(ang)*rad;
        const rr=bubbleR(b.count);
        x=Math.max(40, Math.min(W()-40, x));
        const ly=y+rr+6;
        y=Math.max(cy-H()/2+pad+rr, Math.min(cy+H()/2-pad-rr-14, y));
        // honor manual drag override (set live, not recomputed)
        if(manual[b.key]){ x=manual[b.key].x; y=manual[b.key].y; }
        positions[b.key]={x:x, y:y, r:rr};
      }
    }
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
      const p=positions[b.key], r=p.r||bubbleR(b.count), active=expanded.has(b.key);
      const px=p.x, py=p.y;  // live position (honors manual drag)
      // edge center->bubble
      line(svg,cx,cy,px,py, b.sparse?'var(--line)':'#E3E3E3', b.sparse);
      // bubble
      const border = active ? '2px solid var(--coral)'
                   : b.sparse ? '1.5px dashed var(--line)'
                   : b.verified_heavy ? '1.5px solid var(--teal)' : '1px solid #D9D9D9';
      const bg = active ? 'var(--coral-bg)' : b.sparse ? 'var(--bg)' : 'var(--bg2)';
      const op = b.sparse ? 'opacity:.7' : '';
      const el=node(px,py,
        '<div style="text-align:center;line-height:1.15">'+
        '<div style="font-size:'+(b.count>3?18:15)+'px;font-weight:700;color:'+
          (active?'var(--coral)':'var(--txt)')+'">'+b.count+'</div></div>',
        r*2, 'background:'+bg+';border:'+border+';cursor:grab;touch-action:none;'+op);
      // drag vs click: pointerdown -> move beyond threshold = drag (manual reposition);
      // release without move = toggle expand
      let drag=null;
      el.addEventListener('pointerdown',(e)=>{
        e.stopPropagation();
        const st=document.getElementById('stage').getBoundingClientRect();
        const sx=e.clientX, sy=e.clientY;
        drag={sx,sy,moved:false};
        const mv=(ev)=>{
          const dx=ev.clientX-sx, dy=ev.clientY-sy;
          if(!drag.moved && Math.hypot(dx,dy)>5) drag.moved=true;
          if(drag.moved){
            let nx=ev.clientX-st.left, ny=ev.clientY-st.top;
            nx=Math.max(r, Math.min(W()-r, nx)); ny=Math.max(r, Math.min(H()-r, ny));
            manual[b.key]={x:nx,y:ny}; render();
          }
        };
        const up=(ev)=>{
          el.releasePointerCapture && el.releasePointerCapture(ev.pointerId);
          document.removeEventListener('pointermove',mv);
          document.removeEventListener('pointerup',up);
          if(drag && !drag.moved){ if(expanded.has(b.key)) expanded.delete(b.key); else expanded.add(b.key); render(); }
        };
        el.setPointerCapture && el.setPointerCapture(e.pointerId);
        document.addEventListener('pointermove',mv);
        document.addEventListener('pointerup',up);
      });
      // floating cluster label near bubble (clamped inside canvas)
      const lab=document.createElement('div');
      lab.textContent=b.label+(b.sparse?' · whitespace':'');
      const lw=Math.min(b.label.length*6.2+ (b.sparse?54:0), W()-40);
      let lx=Math.max(40, Math.min(W()-40, px));
      let ly=py+r+6;
      lab.style.cssText='position:absolute;left:'+lx+'px;top:'+ly+'px;transform:translateX(-50%);'+
        'max-width:'+lw+'px;font-size:10px;color:'+(b.sparse?'var(--mut)':'var(--txt2)')+';'+
        'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;pointer-events:none';
      vp.appendChild(lab);

      // Level 2: orbit startup cards when expanded
      if(active && b.startups.length){
        b.startups.forEach((s,i)=>{
          const a=(i/b.startups.length)*Math.PI*2 - Math.PI/2;
          const orad=r+44;
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
    (s.impact_line?'<div class="small" style="font-style:italic;opacity:.9">✦ '+(s.impact_line||'')+'</div>':'')+
    '<div style="margin-top:10px">'+badges+'</div><div style="margin-top:6px">'+tags+'</div>'+
    '<div class="btnrow"><a class="cta" href="'+s.profile_url+'" style="color:#fff">VC profile →</a>'+
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
app.jinja_env.globals["_spec_code"] = _spec_code
app.jinja_env.globals["_abs_url"] = _abs_url
app.jinja_env.globals["_logo_for"] = _logo_for


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
def _current_user():
    email = session.get("email")
    if not email:
        return None
    u = store.get_user(email) or {}
    return {"email": email,
            "name": u.get("name") or session.get("name", ""),
            "role": u.get("role") or session.get("role", "")}


def _is_admin():
    """Manual Discussion admin = a single configured email (reuses login session)."""
    admin = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    return bool(admin) and session.get("email", "").strip().lower() == admin


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
    return redirect(url_for("whitespace"))


@app.route("/directory")
def directory():
    all_cards = [store.get(s["id"]) for s in store.published()]
    all_cards = [c for c in all_cards if c]
    # stable counts (over all published, independent of active filters)
    counts = group_counts(all_cards)
    seg_counts = segment_counts(all_cards)

    q = (request.args.get("q") or "").strip().lower()
    stage_f = (request.args.get("stage") or "").strip()
    verify_f = (request.args.get("verify") or "").strip()
    group_f = (request.args.get("group") or "").strip()
    seg_f = (request.args.get("segment") or "").strip()

    # map active group -> its segments; active segment -> exact key
    active_sub = set()
    active_group_name = None
    active_segment_name = None
    if seg_f:
        active_sub = {seg_f}
        active_segment_name = _SEG_LABELS.get(seg_f, seg_f)
        for z in THEME_ZONES:
            for g in z["groups"]:
                if seg_f in g["seg"]:
                    active_group_name = g["name"]
                    break
    elif group_f:
        for z in THEME_ZONES:
            for g in z["groups"]:
                if g["key"] == group_f:
                    active_sub = set(g["seg"])
                    active_group_name = g["name"]
                    break

    def matches(c):
        tags = _norm_tags(c)
        pc = c.get("published_card") or {}
        if active_sub and not (set(tags) & active_sub):
            return False
        if stage_f and (pc.get("stage") or c.get("structured", {}).get("stage") or c.get("raw", {}).get("stage", "")) != stage_f:
            return False
        if verify_f:
            badges = c.get("published_card", {}).get("badges", []) if c.get("published_card") else c.get("badges", [])
            ok = any(b.get("status") == "verified" for b in badges)
            if verify_f == "verified" and not ok:
                return False
            if verify_f == "unverified" and ok:
                return False
        if q:
            hay = " ".join(str(x) for x in [pc.get("startup_name"), pc.get("tagline"),
                                            pc.get("problem"), " ".join(tags)]).lower()
            if q not in hay:
                return False
        return True

    cards = [c for c in all_cards if matches(c)]
    cards.sort(key=lambda c: (len(c.get("voters", [])), c.get("created_at", "")), reverse=True)
    user = _current_user()
    stats = store.record_visit(_visitor_id())
    voted = set()
    if user:
        for c in cards:
            if user["email"] in c.get("voters", []):
                voted.add(c["id"])
    return render_template_string(TPL_HOME, cards=cards, voted=voted, stats=stats,
                                  zones=THEME_ZONES, counts=counts, seg_counts=seg_counts,
                                  seg_labels=_SEG_LABELS,
                                  active_group=group_f, active_group_name=active_group_name,
                                  active_segment=seg_f, active_segment_name=active_segment_name,
                                  filters={"q": q, "stage": stage_f, "verify": verify_f,
                                           "group": group_f, "segment": seg_f},
                                  metrics={"startups": len(all_cards),
                                           "builders": store.builder_count(),
                                           "vcs": store.role_counts()["vc"]},
                                  stages=STAGES, subthemes=SUBTHEMES,
                                  user_email=user["email"] if user else "",
                                  user_name=user["name"] if user else "")


@app.route("/submit", methods=["GET"])
def submit_get():
    user = _current_user()
    # reuse identified email/name from the upvote-gate session if present (don't duplicate capture)
    return render_template_string(TPL_SUBMIT,
                                  user_email=user["email"] if user else "",
                                  user_name=user["name"] if user else "")


ALLOWED_EXT = {"pdf", "pptx", "docx"}
MAX_FILE_BYTES = 20 * 1024 * 1024   # 20MB / file
MAX_FILES = 5
MAX_URLS = 5


@app.route("/submit", methods=["POST"])
def submit_post():
    # --- identity fields the founder types directly (authoritative) ---
    raw = {
        "startup_name": (request.form.get("startup_name") or "").strip(),
        "founder_names": (request.form.get("founder_names") or "").strip(),
        "founder_linkedin": (request.form.get("founder_linkedin") or "").strip(),
        "founder_email": (request.form.get("founder_email") or "").strip(),
        "website": (request.form.get("website") or "").strip(),
    }
    if not raw["startup_name"]:
        return "Startup name is required.", 400

    # --- uploaded files: save to a temp dir, extract text ---
    upload_dir = tempfile.mkdtemp(prefix="moonshot-up-")
    saved = []
    try:
        files = request.files.getlist("files")
        for f in files[:MAX_FILES]:
            if not f or not f.filename:
                continue
            ext = f.filename.rsplit(".", 1)[-1].lower()
            if ext not in ALLOWED_EXT:
                continue
            f.seek(0, 2)
            size = f.tell()
            f.seek(0)
            if size > MAX_FILE_BYTES:
                continue
            path = os.path.join(upload_dir, f.filename)
            f.save(path)
            saved.append({"filename": f.filename, "filepath": path})
    except Exception as e:
        shutil.rmtree(upload_dir, ignore_errors=True)
        return f"Upload error: {e}", 400

    # --- URL links (website already captured above; plus extra press/article links) ---
    urls = []
    if raw["website"]:
        urls.append(raw["website"])
    for i in range(1, MAX_URLS + 1):
        u = (request.form.get(f"url{i}") or "").strip()
        if u:
            urls.append(u)
    urls = urls[:MAX_URLS]

    # --- multi-source extraction ---
    context = extract.build_context(saved, urls)
    raw["extracted_context"] = context
    raw["source_files"] = [s["filename"] for s in saved]
    raw["source_urls"] = urls

    rec = store.create_submission(raw)
    store.update(rec["id"], {"log": "queued", "upload_dir": upload_dir})
    threading.Thread(target=_run_pipeline_bg, args=(rec["id"], upload_dir), daemon=True).start()
    return redirect(url_for("processing", sid=rec["id"]))


def _run_pipeline_bg(sid, upload_dir=None):
    rec = store.get(sid)
    store.update(sid, {"log": "VC Agent: reading uploads…"})
    res = agents.run_pipeline(rec)
    rec = store.get(sid)
    rec["structured"] = res["structured"]
    rec["badges"] = res["badges"]
    rec["disclaimer"] = res["disclaimer"]
    rec["trace"] = res["trace"]
    rec["status"] = res["status"]          # trust the pipeline's own ok/fail decision
    rec["vc_error"] = res.get("vc_error")
    rec["log"] = "done"
    store.update(sid, rec)
    # uploaded temp files are no longer needed once extracted
    if upload_dir:
        shutil.rmtree(upload_dir, ignore_errors=True)


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
    # VC agent failed to produce a usable card — show a clear retry state, not a blank form
    if rec.get("status") == "error":
        user = _current_user()
        return render_template_string(TPL_REVIEW_ERR, sid=sid,
                                      err=rec.get("vc_error") or "The agent didn't return a draft.",
                                      user_email=user["email"] if user else "",
                                      user_name=user["name"] if user else "")
    if not sc:
        return "Pipeline hasn't completed yet. <a href='/processing/" + sid + "'>Check status</a>", 202
    for k in ["startup_name", "tagline", "problem", "opportunity_size",
              "differentiator", "solution", "ask", "stage", "impact_line"]:
        sc.setdefault(k, "")
    sc.setdefault("subtheme_tags", [])
    sc.setdefault("conflicts", [])
    user = _current_user()
    # identity fields the founder typed directly; everything else is agent-inferred
    identity_fields = {"startup_name", "founder_names", "founder_linkedin", "founder_email"}
    inferred_fields = [k for k in ["tagline", "problem", "opportunity_size", "differentiator",
                                   "solution", "stage", "ask"] if k in sc]
    return render_template_string(TPL_REVIEW, sid=sid, sc=sc, raw=rec["raw"],
                                  badges=_lower_badges(rec.get("badges", [])),
                                  disclaimer=rec.get("disclaimer", ""),
                                  conflicts=sc.get("conflicts", []),
                                  identity_fields=identity_fields,
                                  inferred_fields=inferred_fields,
                                  subthemes=SUBTHEMES,
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
        "impact_line": (request.form.get("impact_line") or "").strip(),
        "subtheme_tags": request.form.getlist("subtheme_tags") or rec.get("raw", {}).get("subtheme_tags", []),
        "badges": rec.get("badges", []),
        "published_at": store.now_iso(),
    }
    rec["published_card"] = published_card
    rec["status"] = "published"
    store.update(sid, rec)
    return redirect(url_for("home"))


@app.route("/profile/<sid>")
def profile(sid):
    rec = store.get(sid)
    if not rec:
        return "not found", 404
    if rec.get("status") != "published":
        # not published yet — still let founders/preview see the draft memo
        if not rec.get("structured") and not rec.get("published_card"):
            return "Nothing to show yet. <a href='/processing/" + sid + "'>Check status</a>", 202
    user = _current_user()
    pc = rec.get("published_card") or rec.get("structured") or {}
    pc.setdefault("startup_name", rec.get("raw", {}).get("startup_name", ""))
    return render_template_string(TPL_PROFILE, sid=sid, rec=rec, pc=pc,
                                  badges=_lower_badges(rec.get("published_card", {}).get("badges")
                                                      if rec.get("published_card") else rec.get("badges", [])),
                                  subthemes=(pc.get("subtheme_tags") or rec.get("raw", {}).get("subtheme_tags", []) or []),
                                  user_email=user["email"] if user else "",
                                  user_name=user["name"] if user else "")


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
    role = (data.get("role") or "").strip()
    if not name or "@" not in email:
        return jsonify({"ok": False, "error": "name and valid email required"}), 400
    if role not in ("founder", "vc"):
        return jsonify({"ok": False, "error": "role must be 'founder' or 'vc'"}), 400
    store.identify(name, email, role)
    session["email"] = email
    session["name"] = name
    session["role"] = role
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
        "impact_line": pc.get("impact_line", ""),
        "votes": len(rec.get("voters", [])),
        "trace_url": "/trace/" + sid,
        "profile_url": "/profile/" + sid,
    })


@app.route("/whitespace")
def whitespace():
    user = _current_user()
    return render_template_string(TPL_WHITESPACE, stages=STAGES,
                                  user_email=user["email"] if user else "",
                                  user_name=user["name"] if user else "")


@app.route("/discussion", methods=["GET"])
def discussion():
    user = _current_user()
    thread = store.get_thread()
    return render_template_string(TPL_DISCUSSION, thread=thread, is_admin=_is_admin(),
                                  user_email=user["email"] if user else "",
                                  user_name=user["name"] if user else "",
                                  user_role=session.get("role", ""))


@app.route("/discussion/topic", methods=["POST"])
def discussion_topic():
    if not _is_admin():
        return jsonify({"ok": False, "error": "admin only"}), 403
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    body = (data.get("body") or "").strip()
    if not title or not body:
        return jsonify({"ok": False, "error": "title and body required"}), 400
    user = _current_user()
    store.set_thread(title, body, session.get("email", ""), user["name"] if user else "")
    return jsonify({"ok": True})


@app.route("/discussion/reply", methods=["POST"])
def discussion_reply():
    user = _current_user()
    if not user:
        return jsonify({"ok": False, "error": "login to reply"}), 401
    data = request.get_json(silent=True) or {}
    body = (data.get("body") or "").strip()
    if not body:
        return jsonify({"ok": False, "error": "reply body required"}), 400
    thread = store.get_thread()
    if not thread:
        return jsonify({"ok": False, "error": "no active thread"}), 404
    role = session.get("role", "")
    store.add_reply(thread, user["name"], role, body)
    return jsonify({"ok": True})


TPL_DISCUSSION = _page("Discussion — MoonshotHunt", """\
<div class="hero slim">
  <h1>Discussion</h1>
  <p class="lead">One active thread at a time. Founders and VCs weigh in. Manual for now — no automation.</p>
</div>

<div class="disc">
  {% if thread %}
    <div class="thread">
      <div class="threadhead">
        <h2 style="margin:0">{{ thread.title }}</h2>
        {% if is_admin %}<button class="pill" onclick="newTopic()">New topic</button>{% endif %}
      </div>
      <p class="threadbody">{{ thread.body }}</p>
      <div class="replies">
        {% for r in thread.replies %}
        <div class="reply">
          <div class="rhead"><b>{{ r.name or 'Anonymous' }}</b>
            <span class="rolebadge {{ r.role }}">{{ 'VC' if r.role=='vc' else 'Founder' if r.role=='founder' else r.role }}</span></div>
          <p>{{ r.body }}</p>
        </div>
        {% else %}
        <p class="muted small">No replies yet — be the first to weigh in.</p>
        {% endfor %}
      </div>
    </div>
  {% else %}
    <div class="thread empty">
      <p class="muted">No active thread right now.</p>
      {% if is_admin %}<button class="cta" onclick="newTopic()">Post the first topic</button>{% endif %}
    </div>
  {% endif %}

  <div class="topicform" id="topicForm" style="display:none">
    <h3>New topic</h3>
    <label>Title</label><input id="tp_title" placeholder="e.g. What's the hardest part of piloting climate hardware in India?">
    <label>Prompt / body</label><textarea id="tp_body" placeholder="Frame the question for founders and VCs…"></textarea>
    <div class="btnrow"><button class="cta" onclick="postTopic()">Post topic <span class="arw">→</span></button></div>
  </div>

  {% if user_email %}
  <div class="replybox">
    <label>Your reply <span class="sub">as {{ user_name }} · {{ 'VC' if user_role=='vc' else 'Founder' if user_role=='founder' else user_role }}</span></label>
    <textarea id="rp_body" placeholder="Share your take…"></textarea>
    <div class="btnrow"><button class="cta" onclick="postReply()">Reply <span class="arw">→</span></button></div>
  </div>
  {% else %}
  <p class="muted small"><a href="#" onclick="return openLogin()">Sign in</a> (founder or VC) to reply.</p>
  {% endif %}
</div>

<script>
function newTopic(){ document.getElementById('topicForm').style.display='block'; }
async function postTopic(){
  const title=document.getElementById('tp_title').value.trim();
  const body=document.getElementById('tp_body').value.trim();
  if(!title||!body){ alert('Title and body are required.'); return; }
  const r=await fetch('/discussion/topic',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({title:title,body:body})});
  const d=await r.json();
  if(d.ok){ location.reload(); } else { alert(d.error||'Failed to post.'); }
}
async function postReply(){
  const body=document.getElementById('rp_body').value.trim();
  if(!body){ alert('Write something first.'); return; }
  const r=await fetch('/discussion/reply',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({body:body})});
  const d=await r.json();
  if(d.ok){ location.reload(); } else { alert(d.error||'Failed to reply.'); }
}
</script>
""")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
