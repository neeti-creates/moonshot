"""
MoonshotHunt agents. Real LLM calls to the Nous Research inference endpoint
(reusing the Hermes agent_key from ~/.hermes/auth.json) plus real network checks.

VC Agent  -> structures raw Section-5 submission into Layer-1 card one-liners.
Verifier  -> runs checkable network/liveness checks, then an LLM turns the
             results into honest, lightweight verification badges.
"""
import os, json, time, threading, urllib.request, urllib.error

# --- Live LLM endpoint (same one Hermes uses) -------------------------------
# Prefer env vars (for cloud deploy e.g. Render); fall back to local Hermes auth.json.
def _load_creds():
    base = os.environ.get("NOUS_BASE_URL")
    key = os.environ.get("NOUS_API_KEY")
    if key:
        return (base or "https://inference-api.nousresearch.com/v1"), key
    try:
        auth = json.load(open(os.path.expanduser("~/.hermes/auth.json")))
        nous = auth["providers"]["nous"]
        return ((nous.get("inference_base_url") or "https://inference-api.nousresearch.com/v1"),
                nous.get("agent_key") or nous.get("access_token"))
    except Exception:
        return "https://inference-api.nousresearch.com/v1", None


BASE_URL, API_KEY = _load_creds()
BASE_URL = BASE_URL.rstrip("/")
DEF_MODEL = os.environ.get("MOONSHOT_MODEL", "tencent/hy3:free")


def _timed_request(req, cap):
    """Run urlopen in a worker thread and join with a hard wall-clock cap.

    On macOS the system urllib/ssl (LibreSSL) ignores the socket `timeout` for
    TLS connections, so a stalled free-tier call would hang forever. A worker
    thread + join(cap) guarantees we never block past `cap` seconds; on timeout
    we return None and let the caller retry.
    """
    box = {}
    def worker():
        try:
            box["r"] = urllib.request.urlopen(req, timeout=cap)
        except Exception as e:
            box["err"] = e
    th = threading.Thread(target=worker, daemon=True)
    th.start()
    th.join(cap + 2)
    if th.is_alive():
        return None  # hard timeout — caller retries
    if "err" in box:
        raise box["err"]
    return box.get("r")


def llm(messages, model=DEF_MODEL, json_mode=False, max_tokens=900, temperature=0.2):
    import urllib.error as _ue
    last_err = None
    CAP = 90  # hard wall-clock cap per attempt (free tier is slow but must not hang)
    for attempt in range(4):
        body = {"model": model, "messages": messages,
                "max_tokens": max_tokens, "temperature": temperature}
        req = urllib.request.Request(
            BASE_URL + "/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {API_KEY}"})
        t0 = time.time()
        try:
            r = _timed_request(req, CAP)
            if r is None:
                last_err = f"timeout after {CAP}s (attempt {attempt+1})"
                time.sleep(4 + attempt * 4)
                continue
            data = json.loads(r.read().decode())
        except _ue.HTTPError as e:
            last_err = f"HTTP {e.code}: {e.read().decode()[:160]}"
            time.sleep(3 + attempt * 3)
            continue
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)[:120]}"
            time.sleep(3 + attempt * 3)
            continue
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content")
        if content is None:
            last_err = f"empty completion (finish={(data.get('choices') or [{}])[0].get('finish_reason')})"
            time.sleep(2 + attempt * 2)
            continue
        usage = data.get("usage", {})
        return {"content": content,
                "model": data.get("model", model),
                "latency": round(time.time() - t0, 2),
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens")}
    return {"error": last_err or "all attempts failed",
            "model": model, "latency": None}


def _safe_json(text):
    """Extract the first JSON object from an LLM reply, tolerating prose/fences."""
    if not text:
        return {}
    if isinstance(text, dict):
        return text
    import re
    # strip ```json ... ``` fences if present
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except Exception:
            pass
    s = text.find("{")
    e = text.rfind("}")
    if s != -1 and e != -1 and e > s:
        try:
            return json.loads(text[s:e + 1])
        except Exception:
            pass
    return {"_raw": text}


# ---------------------------------------------------------------------------
# VC Agent — synthesis / structuring (NOT due diligence)
# ---------------------------------------------------------------------------
VC_SYSTEM = (
    "You are the MoonshotHunt VC Agent. A founder uploaded raw assets (deck, one-pager, "
    "tech spec, website, press) and you read them like a VC doing first-pass diligence, "
    "then draft a crisp discovery card. This is STRUCTURING / SYNTHESIS, never investment "
    "due diligence. You are organizing founder-provided material, NOT verifying its truth.\n\n"
    "You will receive IDENTITY fields the founder typed directly (treat as authoritative: "
    "startup_name, founder_names, founder_linkedin, founder_email) plus one or more SOURCE "
    "BLOCKS labelled [FROM: filename/url]. Each block is a different document or link about "
    "the same startup.\n\n"
    "Rules:\n"
    "1. Read the SPECIFIC sources. Do not use generic filler ('a promising startup'). Each "
    "line must reflect this founder's actual words/claims.\n"
    "2. Condense, don't invent. If a field is not supported by ANY provided source, write a "
    "short honest 'Not specified by founder' rather than fabricating.\n"
    "3. CONFLICTS: sources may disagree (e.g. deck says one market size, website says another). "
    "When they conflict, pick the more authoritative-seeming source, fill the field with that "
    "value, AND add an entry to 'conflicts' describing the discrepancy and the choice, so the "
    "founder sees it during review. Never silently pick one and hide the other.\n"
    "4. Infer STAGE from context (idea|prototype|pilot|early revenue|scaling) — founder can "
    "override in review.\n"
    "5. Infer SUBTHEME TAGS (2-4, lowercase, hyphenated, from: energy-storage, "
    "industrial-decarbonization, carbon-capture, resilience-adaptation, sustainable-agriculture, "
    "circular-economy, sustainable-mobility, built-environment, robotics-automation, "
    "advanced-materials, nanorobotics, ai-infrastructure, biotech, space-tech, semiconductors, "
    "quantum) — founder can override in review.\n"
    "6. Outcome-framed language where possible (what changes in the world), not feature-listing.\n"
    "7. Respect per-field length guidance.\n\n"
    "Return STRICT JSON with exactly these keys:\n"
    "  startup_name   : from identity (echo exactly)\n"
    "  tagline        : one line, outcome-framed. <= 14 words\n"
    "  problem        : one line, the problem in the founder's own domain. <= 22 words\n"
    "  opportunity_size: one line, the scale/number claim + its basis. <= 22 words\n"
    "  differentiator : one line, what makes this distinct. <= 22 words\n"
    "  solution       : one line, what they built. <= 18 words\n"
    "  stage          : exactly one of idea|prototype|pilot|early revenue|scaling\n"
    "  subtheme_tags  : array of 2-4 lowercase hyphenated tags (see allowed list)\n"
    "  ask            : one line, what they want (funding/partners/pilots/visibility). <= 18 words\n"
    "  impact_line    : ONE high-emotion sentence, mission-legible, starting 'If this wins, '. "
    "What changes in the world if this startup succeeds. <= 18 words. No metrics, no valuation.\n"
    "  conflicts      : array of {field, note} for any cross-source discrepancies you resolved "
    "(empty array if none)\n"
)


def _call_with_retry(build_messages, max_tokens, n=3):
    """Run an LLM call, retrying on empty/truncated completion (free-model flakiness)."""
    last = None
    for attempt in range(n):
        out = llm(build_messages(), max_tokens=max_tokens)
        if "error" not in out and out.get("content"):
            return out
        last = out
    return last or {"error": "all attempts returned empty"}


def run_vc_agent(raw, context=""):
    def msgs():
        parts = []
        if context:
            parts.append("SOURCE MATERIAL (uploaded by founder):\n" + context)
        parts.append("IDENTITY (founder typed directly — authoritative):\n" +
                     json.dumps({k: raw.get(k, "") for k in
                                 ["startup_name", "founder_names", "founder_linkedin",
                                  "founder_email"]}, indent=2, ensure_ascii=False))
        if not context:
            # legacy path: raw structured fields still present
            parts.append("SUBMISSION FIELDS:\n" + json.dumps(raw, indent=2, ensure_ascii=False))
        user = ("Return ONLY a JSON object (no markdown, no commentary) for this startup:\n"
                + "\n\n".join(parts))
        return [{"role": "system", "content": VC_SYSTEM},
                {"role": "user", "content": user}]
    out = _call_with_retry(msgs, max_tokens=2000)
    if "error" in out or not out.get("content"):
        return {"ok": False, "error": out.get("error", "empty"),
                "trace": out, "structured": {}}
    structured = _safe_json(out["content"])
    structured["startup_name"] = raw.get("startup_name", "")
    structured["founder_names"] = raw.get("founder_names", "")
    structured["founder_linkedin"] = raw.get("founder_linkedin", "")
    structured["founder_email"] = raw.get("founder_email", "")
    structured["subtheme_tags"] = structured.get("subtheme_tags", raw.get("subtheme_tags", []))
    return {"ok": True, "structured": structured, "llm": out}


# ---------------------------------------------------------------------------
# Verifier Agent — lightweight, checkable signals only
# ---------------------------------------------------------------------------
def _http_check(url, timeout=8):
    if not url:
        return {"checked": False, "reason": "not provided"}
    try:
        req = urllib.request.Request(url, method="HEAD",
                                     headers={"User-Agent": "MoonshotHunt-Verifier/1.0"})
        r = urllib.request.urlopen(req, timeout=timeout)
        return {"checked": True, "status": r.status, "live": 200 <= r.status < 400}
    except urllib.error.HTTPError as e:
        return {"checked": True, "status": e.code, "live": 200 <= e.code < 400}
    except Exception as e:
        return {"checked": True, "status": None, "live": False, "error": type(e).__name__}


def _linkedin_valid(url):
    if not url:
        return False, "no URL"
    u = url.lower()
    if "linkedin.com/in/" not in u:
        return False, "not a linkedin.com/in/ profile URL"
    slug = u.split("linkedin.com/in/")[1].strip("/").split("?")[0]
    if not slug or " " in slug:
        return False, "profile slug missing or malformed"
    return True, "well-formed linkedin.com/in/ URL"


def run_verifier(raw, structured):
    linkedin_ok, linkedin_note = _linkedin_valid(raw.get("founder_linkedin", ""))
    web = _http_check(raw.get("website", ""))

    checks = {
        "linkedin_format": {"ok": linkedin_ok, "note": linkedin_note,
                             "url": raw.get("founder_linkedin", "")},
        "website_live": web,
        "founder_name": {"present": bool((raw.get("founder_names") or "").strip())},
    }

    sys_p = (
        "You are the MoonshotHunt Verifier Agent. You ONLY assess what is "
        "mechanically checkable from public signals. You do NOT verify business "
        "claims (market size, traction, financials) — those stay self-reported.\n\n"
        "From the check results produce honest BADGES. Each badge is "
        "{\"label\": short text, \"status\": \"verified\"|\"unverified\", \"detail\": one line}.\n"
        "RULES:\n"
        "- All labels MUST be LOWERCASE, no spaces where possible (use e.g. "
        "'website', 'linkedin', 'founder identity', 'self-reported claims').\n"
        "- website: 'verified' only if live (HTTP 2xx/3xx), else 'unverified'.\n"
        "- linkedin: 'verified' if URL well-formed, else 'unverified'.\n"
        "- founder identity: 'verified' if a founder name is present, else 'unverified'.\n"
        "Always add one 'unverified' badge labeled 'self-reported claims' stating claims "
        "are self-reported and NOT independently verified. Never overstate.\n\n"
        "Return ONLY JSON: {\"badges\": [ ... ], \"disclaimer\": \"one sentence\"}"
    )
    def msgs():
        return [{"role": "system", "content": sys_p},
                {"role": "user", "content":
                 ("Return ONLY a JSON object (no markdown, no commentary):\n"
                  + json.dumps(checks, indent=2, ensure_ascii=False))}]
    out = _call_with_retry(msgs, max_tokens=1800)
    if "error" in out:
        badges = [{"label": "Verifier unavailable", "status": "unverified",
                   "detail": out.get("error", "error")}]
        disclaimer = "Automated lightweight check only — not due diligence."
    else:
        parsed = _safe_json(out["content"])
        badges = parsed.get("badges", [])
        disclaimer = parsed.get("disclaimer",
                                "Lightweight automated check only — not due diligence.")
    return {"checks": checks, "badges": badges,
            "disclaimer": disclaimer, "llm": out}


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------
def run_onepager_agent(raw, structured):
    """Synthesize the VC/Verifier one-pager body (rec["onepager"]).

    Produces the 11-field format the /onepager/<sid> page renders. The Verifier
    Agent's job here is to flag each Proof-of-Work line as verified vs founder-claimed
    where a checkable public signal exists; everything else is self-reported.
    Uses the same watchdog-capped llm() as the other agents (no foreground hang)."""
    arch = (structured.get("archetype")
            or raw.get("archetype")
            or _infer_archetype(structured, raw))
    sys_p = (
        "You are the MoonshotHunt VC Agent writing the startup's ONE-PAGER — a crisp, "
        "VC-legible discovery document generated from the founder's uploaded material "
        "(deck, site, docs). This is SYNTHESIS, never investment due diligence; you are "
        "organizing founder-provided claims, not certifying their truth.\n\n"
        "RULES:\n"
        "1. Every line must reflect THIS founder's actual words/claims from the sources. "
        "No generic filler. If a field isn't supported, write a short honest 'Not specified'.\n"
        "2. The masthead thesis is a BET, not a description: 'Betting that X becomes "
        "structurally necessary because Y.' <= 18 words.\n"
        "3. 'proof_work' is an array of {verdict, text}. verdict is 'verified' ONLY when a "
        "publicly checkable signal supports it (live site, granted patent number, published "
        "result, named pilot partner); otherwise 'claimed'. Be conservative — most lines are "
        "'claimed'. Each text <= 20 words.\n"
        "4. ARCHETYPE drives the proof block. The founder's archetype is: "
        f"'{arch}'.\n"
        "   - Hardware / Deep Tech: proof_note='TRL / IP / pilot / cost-down / capex'; "
        "proof_facts cover trl, patents, pilot result, cost-down target, capex to scale.\n"
        "   - Climate Infra: proof_note='bankability / project pipeline / offtake / policy'; "
        "proof_facts cover pipeline size, offtake/LOIs, unit economics at scale, policy dependency.\n"
        "   - Software / Platform: proof_note='distribution / usage / retention / data moat'; "
        "proof_facts cover users, retention, integration depth, data moat.\n"
        "   - Services-enabled: proof_note='team / repeatability / margin'; "
        "proof_facts cover founder authority, delivery track record, margin structure.\n"
        "5. Keep each analytical field to 2 sentences max. The Ask names amount, use of funds, "
        "and the milestone it unlocks.\n\n"
        "Return STRICT JSON with exactly these keys:\n"
        "  thesis, sector, archetype, trl, road_to_commercialisation, round_size,\n"
        "  bet, why_now, proof_note, proof_facts (array of {k,v}), proof_work (array of "
        "{verdict,text}), path_to_cash_flow, moat, market, team, the_ask, founder_line, "
        "founder_cite.\n"
        "sector/archetype/trl/road_to_commercialisation/round_size may be '' if unknown.\n"
    )
    def msgs():
        parts = []
        if raw.get("extracted_context"):
            parts.append("SOURCE MATERIAL:\n" + raw["extracted_context"])
        parts.append("STRUCTURED (from VC Agent):\n" +
                     json.dumps(structured, indent=2, ensure_ascii=False))
        parts.append("IDENTITY:\n" + json.dumps(
            {k: raw.get(k, "") for k in
             ["startup_name", "founder_names", "founder_linkedin", "founder_email"]},
            indent=2, ensure_ascii=False))
        user = ("Return ONLY a JSON object (no markdown) for this startup's one-pager:\n\n"
                + "\n\n".join(parts))
        return [{"role": "system", "content": sys_p},
                {"role": "user", "content": user}]
    out = _call_with_retry(msgs, max_tokens=2600)
    if "error" in out or not out.get("content"):
        return {"ok": False, "error": out.get("error", "empty"), "onepager": {}}
    op = _safe_json(out["content"])
    op["archetype"] = op.get("archetype") or arch
    op["name"] = structured.get("startup_name") or raw.get("startup_name", "")
    # normalise proof_work verdicts
    for pw in op.get("proof_work", []) or []:
        pw["verdict"] = "verified" if str(pw.get("verdict", "")).lower().startswith("ver") else "claimed"
    return {"ok": True, "onepager": op, "llm": out}


def _infer_archetype(structured, raw):
    """Best-effort archetype inference from available signals (agent can override)."""
    text = " ".join(str(v) for v in (list(structured.values()) + list(raw.values()))).lower()
    if any(w in text for w in ["saas", "platform", "software", "api", "app", "ml model"]):
        return "Software / Platform"
    if any(w in text for w in ["consult", "services", "retainer", "agency"]):
        return "Services-enabled"
    if any(w in text for w in ["grid", "plant", "infra", "generation", "pipeline", "offtake"]):
        return "Climate Infra"
    return "Hardware / Deep Tech"


def run_pipeline(sub):
    raw = sub["raw"]
    trace = []

    vc = run_vc_agent(raw, context=raw.get("extracted_context", ""))
    trace.append({
        "agent": "VC Agent (Synthesis)",
        "role": "Reads uploaded sources + identity, drafts card fields, infers stage/subthemes, flags conflicts",
        "model": vc.get("llm", {}).get("model"),
        "latency": vc.get("llm", {}).get("latency"),
        "prompt_tokens": vc.get("llm", {}).get("prompt_tokens"),
        "completion_tokens": vc.get("llm", {}).get("completion_tokens"),
        "input_summary": (_summarize(raw)
                          + f"; sources_chars={len(raw.get('extracted_context',''))}"),
        "raw_output": vc.get("llm", {}).get("content"),
        "ok": vc.get("ok", False),
        "error": vc.get("error"),
    })
    structured = vc.get("structured", {}) if vc.get("ok") else {}

    ver = run_verifier(raw, structured)
    trace.append({
        "agent": "Verifier Agent (Lightweight)",
        "role": "Checks what is mechanically checkable (LinkedIn, website liveness)",
        "model": ver.get("llm", {}).get("model"),
        "latency": ver.get("llm", {}).get("latency"),
        "input_summary": "Network checks: " + json.dumps(ver["checks"], ensure_ascii=False),
        "checks": ver["checks"],
        "raw_output": ver.get("llm", {}).get("content"),
        "badges": ver["badges"],
        "disclaimer": ver["disclaimer"],
    })

    # One-pager synthesis (VC Agent, archetype-conditional). Tolerant: a failure
    # here must NOT block review or publishing — the page degrades to placeholders.
    op = run_onepager_agent(raw, structured)
    trace.append({
        "agent": "VC Agent (One-pager)",
        "role": "Synthesizes the 11-field one-pager body + archetype-conditional proof block",
        "model": op.get("llm", {}).get("model"),
        "latency": op.get("llm", {}).get("latency"),
        "ok": op.get("ok", False),
        "error": op.get("error"),
        "raw_output": op.get("llm", {}).get("content"),
    })
    onepager = op.get("onepager", {}) if op.get("ok") else {}

    # If the VC agent failed or returned nothing usable, mark the submission as
    # errored so the founder sees a clear retry state instead of a blank review form.
    vc_ok = bool(vc.get("ok")) and bool(structured.get("startup_name"))
    status = "review" if vc_ok else "error"
    return {"status": status, "structured": structured,
            "badges": ver["badges"], "disclaimer": ver["disclaimer"],
            "onepager": onepager,
            "trace": trace, "vc_error": None if vc_ok else vc.get("error")}


def _summarize(raw):
    return (f"name={raw.get('startup_name','')}; stage={raw.get('stage','')}; "
            f"subthemes={raw.get('subtheme_tags',[])}; "
            f"problem={ (raw.get('problem','') or '')[:80] }")
