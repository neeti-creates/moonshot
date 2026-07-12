"""JSON-file storage for MoonshotHunt submissions, drafts, and published cards."""
import os, json, threading, uuid, datetime

_lock = threading.Lock()
DATA_DIR = None
INDEX_PATH = None


def init(d):
    global DATA_DIR, INDEX_PATH
    DATA_DIR = d
    INDEX_PATH = os.path.join(d, "index.json")
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(INDEX_PATH):
        json.dump({}, open(INDEX_PATH, "w"))


def _read_index():
    return json.load(open(INDEX_PATH))


def _write_index(d):
    json.dump(d, open(INDEX_PATH, "w"), indent=2)


def now_iso():
    return datetime.datetime.utcnow().isoformat() + "Z"


def create_submission(raw):
    sid = uuid.uuid4().hex[:10]
    rec = {"id": sid, "status": "processing",
           "created_at": now_iso(), "raw": raw}
    with _lock:
        json.dump(rec, open(os.path.join(DATA_DIR, sid + ".json"), "w"), indent=2)
        idx = _read_index()
        idx[sid] = {"id": sid, "status": "processing",
                    "name": raw.get("startup_name", ""), "created_at": rec["created_at"]}
        _write_index(idx)
    return rec


def get(sid):
    p = os.path.join(DATA_DIR, sid + ".json")
    return json.load(open(p)) if os.path.exists(p) else None


def update(sid, patch):
    with _lock:
        rec = get(sid) or {}
        rec.update(patch)
        json.dump(rec, open(os.path.join(DATA_DIR, sid + ".json"), "w"), indent=2)
        idx = _read_index()
        if sid in idx:
            name = (rec.get("raw", {}).get("startup_name", "")
                    or rec.get("structured", {}).get("startup_name", "")
                    or rec.get("card", {}).get("startup_name", ""))
            idx[sid].update({"status": rec.get("status"), "name": name})
            _write_index(idx)


def published():
    idx = _read_index()
    return [s for s in idx.values() if s.get("status") == "published"]


def all_statuses():
    return list(_read_index().values())


# --- Upvotes + lightweight identification (no password, no verification email) ---
USERS_PATH = None


def _users_path():
    global USERS_PATH
    if USERS_PATH is None:
        USERS_PATH = os.path.join(DATA_DIR, "users.json")
    return USERS_PATH


def identify(name, email, role=None):
    """Record a lightweight identified user (name + email + role). Returns user dict."""
    email = (email or "").strip().lower()
    name = (name or "").strip()
    role = (role or "").strip()
    p = _users_path()
    users = json.load(open(p)) if os.path.exists(p) else {}
    if email in users:
        if name:
            users[email]["name"] = name
        if role:
            users[email]["role"] = role
    else:
        users[email] = {"email": email, "name": name, "role": role,
                        "created_at": now_iso()}
    json.dump(users, open(p, "w"), indent=2)
    return users[email]


def role_counts():
    """Distinct identified users by role. Returns {'founder': n, 'vc': n}."""
    p = _users_path()
    users = json.load(open(p)) if os.path.exists(p) else {}
    out = {"founder": 0, "vc": 0}
    for u in users.values():
        r = (u.get("role") or "").strip()
        if r == "founder":
            out["founder"] += 1
        elif r in ("vc", "VC / Investor", "investor"):
            out["vc"] += 1
    return out


def _norm_identity(name, linkedin):
    """Return a stable key for a founder: linkedin slug if present, else lowercased name."""
    if linkedin:
        slug = linkedin.rstrip("/").split("/")[-1].lower()
        if slug:
            return "li:" + slug
    if name:
        return "nm:" + name.strip().lower()
    return None


def builder_count():
    """Distinct builders = founders who actually submitted a startup.

    Derived from each submission's founder identity (founder_names / founder_linkedin),
    deduped by normalized linkedin slug or name. Login-modal 'founder' users are NOT
    added here: the modal is a voting identity, not a submission, and a founder who
    later votes would otherwise be double-counted. Builders = people who built something.
    """
    seen = set()
    with _lock:
        for s in all_statuses():
            rec = get(s["id"])
            if not rec:
                continue
            raw = rec.get("raw", {}) or {}
            names = raw.get("founder_names") or []
            if isinstance(names, str):
                names = [names]
            li = raw.get("founder_linkedin") or ""
            for n in names:
                key = _norm_identity(n, li if len(names) == 1 else "")
                if key:
                    seen.add(key)
    return len(seen)


def get_user(email):
    email = (email or "").strip().lower()
    p = _users_path()
    users = json.load(open(p)) if os.path.exists(p) else {}
    return users.get(email)


def vote(sid, email):
    """Cast one upvote per identified user per startup. Returns (ok, count, reason)."""
    email = (email or "").strip().lower()
    rec = get(sid)
    if not rec:
        return False, 0, "not_found"
    voters = rec.setdefault("voters", [])
    if email in voters:
        return False, len(voters), "already_voted"
    voters.append(email)
    update(sid, {"voters": voters})
    return True, len(voters), "ok"


def unvote(sid, email):
    email = (email or "").strip().lower()
    rec = get(sid)
    if not rec:
        return 0
    voters = rec.get("voters", [])
    if email in voters:
        voters.remove(email)
        update(sid, {"voters": voters})
    return len(voters)


def vote_count(sid):
    rec = get(sid)
    return len(rec.get("voters", [])) if rec else 0


# --- Visit / unique-visitor counter (same cookie approach as voting) ---
STATS_PATH = None


def _stats_path():
    global STATS_PATH
    if STATS_PATH is None:
        STATS_PATH = os.path.join(DATA_DIR, "stats.json")
    return STATS_PATH


def record_visit(visitor_id):
    """Bump total visits; track unique visitors by their session id. Returns stats."""
    p = _stats_path()
    with _lock:
        s = json.load(open(p)) if os.path.exists(p) else {"visits": 0, "uniques": []}
        s["visits"] = s.get("visits", 0) + 1
        if visitor_id and visitor_id not in s["uniques"]:
            s["uniques"].append(visitor_id)
        json.dump(s, open(p, "w"), indent=2)
    return {"visits": s["visits"], "uniques": len(s["uniques"])}


def get_stats():
    p = _stats_path()
    s = json.load(open(p)) if os.path.exists(p) else {"visits": 0, "uniques": []}
    return {"visits": s.get("visits", 0), "uniques": len(s.get("uniques", []))}

