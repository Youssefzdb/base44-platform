#!/usr/bin/env python3
"""Base44 platform clone — same UI, same logic, same pages, rebuilt.

Backend surface (JSON, Bearer/cookie auth):
  POST /api/auth/signup | /api/auth/login | /api/auth/logout
  GET  /api/me
  GET  /api/workspaces
  GET  /api/workspace_apps | GET /api/apps/:id | PATCH /api/apps/:id | DELETE /api/apps/:id
  POST /api/apps (create from prompt via the agent)
  POST /api/apps/:id/agent        (agent turn: mutate spec, consume credits, log)
  POST /api/apps/:id/publish
  GET  /api/apps/:id/logs | PUT /api/apps/:id/entities/:ent/:rec
  GET  /api/credits
  GET  /api/published/:slug → published app spec
  GET /p/:slug → published app runtime (page)
Storage: data/db.json
Run: python3 server.py → http://localhost:8510
"""
import hashlib, json, os, re, secrets, threading, time, uuid, random, base64, struct, sys
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

PORT = int(os.environ.get("PORT", "8510"))
HERE = os.path.dirname(os.path.abspath(__file__))
WWW = os.path.join(HERE, "www")
_CANDIDATES = [
    os.path.join(HERE, "dist"),
    os.path.join(os.path.dirname(HERE), "base44-react", "dist"),
    WWW,
]
for _c in _CANDIDATES:
    if os.path.isfile(os.path.join(_c, "index.html")):
        WWW = _c
        break
import json as _json
with open("/tmp/www_chosen", "w") as _dbg:
    _dbg.write(_json.dumps({"chosen": WWW, "cands": _CANDIDATES,
                            "flags": [os.path.isfile(os.path.join(_c, "index.html")) for _c in _CANDIDATES],
                            "here": HERE}, indent=1) + "\n")
print("serving UI from:", WWW)
DBP = os.path.join(HERE, "data", "db.json")
os.makedirs(os.path.join(HERE, "data"), exist_ok=True)
LOCK = threading.RLock()
CREDIT_LIMIT = 20.0

# ---------------- storage ----------------
def db():
    with LOCK:
        if not os.path.exists(DBP):
            json.dump({"users": [], "sessions": [], "workspaces": [], "apps": []}, open(DBP, "w"))
        return json.load(open(DBP))

def save(d):
    with LOCK:
        json.dump(d, open(DBP, "w"), indent=1)

def pub(d):
    d = dict(d); d.pop("_log", None); return d

# ---------------- the agent (prompt → app spec) ----------------
APP_TEMPLATES = {
    "crm": dict(
        match=re.compile(r"crm|customer|clients?|leads?|sales|pipeline|deals?", re.I),
        name="CRM", icon="C", color="#4d33de",
        summary="Track customers, deals and follow-ups in one clean pipeline.",
        entities=[
            dict(name="Customer", slug="customers", fields=[
                dict(name="Name", slug="name", type="text", required=True),
                dict(name="Email", slug="email", type="email"),
                dict(name="Company", slug="company", type="text"),
                dict(name="Status", slug="status", type="select", options=["Lead", "Active", "Won", "Lost"]),
                dict(name="Deal value", slug="value", type="number", suffix="$")],
                seed=[["Acme Corp", "deals@acme.io", "Acme", "Active", 12000],
                      ["Globex", "ops@globex.io", "Globex", "Lead", 4500],
                      ["Initech", "hi@initech.com", "Initech", "Won", 9800]]),
            dict(name="Follow-up", slug="followups", fields=[
                dict(name="Title", slug="title", type="text", required=True),
                dict(name="Due date", slug="due", type="date"),
                dict(name="Customer", slug="customer", type="ref", entity="customers"),
                dict(name="Done", slug="done", type="checkbox")],
                seed=[["Call Acme", "2026-11-05", 1, False], ["Send quote Initech", "2026-11-07", 3, False]]),
        ],
        pages=[dict(name="Pipeline", type="list"), dict(name="New Customer", type="form")],
        maps_customers=True),
    "tasks": dict(
        match=re.compile(r"task|kanban|todo|project", re.I), name="Task Manager", icon="T", color="#ff773c",
        summary="Projects, tasks, statuses and a daily focus view.",
        entities=[dict(name="Task", slug="tasks", fields=[
            dict(name="Title", slug="title", type="text", required=True),
            dict(name="Status", slug="status", type="select", options=["Todo", "Doing", "Done"]),
            dict(name="Due date", slug="due", type="date"), dict(name="Priority", slug="prio", type="select", options=["Low", "Med", "High"])],
            seed=[["Write spec", "Todo", "2026-11-02", "High"], ["Deploy v2", "Doing", "2026-11-03", "Med"]])],
        pages=[dict(name="Board", type="list"), dict(name="Quick Add", type="form")]),
    "blog": dict(
        match=re.compile(r"blog|content|article", re.I), name="Blog", icon="B", color="#3b51e5",
        summary="Write posts with a rich editor and share publicly.",
        entities=[dict(name="Post", slug="posts", fields=[
            dict(name="Title", slug="title", type="text", required=True),
            dict(name="Body", slug="body", type="textarea"),
            dict(name="Published", slug="published", type="checkbox")],
            seed=[["Hello world", "First post on my new blog.", True]])],
        pages=[dict(name="Posts", type="list"), dict(name="New Post", type="form")]),
    "finance": dict(
        match=re.compile(r"expense|finance|budget|money", re.I), name="Expense Tracker", icon="E", color="#bedb3f",
        summary="Log spend, monthly budget charts and export.",
        entities=[dict(name="Expense", slug="expenses", fields=[
            dict(name="Description", slug="desc", type="text", required=True),
            dict(name="Amount", slug="amount", type="number", suffix="$"),
            dict(name="Category", slug="cat", type="select", options=["Food", "Transport", "Software", "Other"]),
            dict(name="Date", slug="date", type="date")],
            seed=[["Team dinner", 48.5, "Food", "2026-10-28"], ["Vercel plan", 20, "Software", "2026-10-29"]])],
        pages=[dict(name="Spending", type="list"), dict(name="Add Expense", type="form")]),
    "notes": dict(
        match=re.compile(r"notes?|journal", re.I), name="Notes", icon="N", color="#f0c84d",
        summary="Fast notes with search and pins.",
        entities=[dict(name="Note", slug="notes", fields=[
            dict(name="Title", slug="title", type="text", required=True),
            dict(name="Text", slug="text", type="textarea"), dict(name="Pinned", slug="pin", type="checkbox")],
            seed=[["Meeting notes", "Agree roadmap for next sprint.", True]])],
        pages=[dict(name="Notes", type="list"), dict(name="New Note", type="form")]),
}
DEFAULT_T = APP_TEMPLATES["crm"]

def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "app"

def mk_field(fname, ftype=None):
    fl = fname.lower()
    t = ftype or ("number" if re.search(r"price|amount|value|count|qty", fl)
                  else "date" if re.search(r"date|due|deadline", fl)
                  else "checkbox" if re.search(r"done|paid|publish", fl)
                  else "email" if re.search(r"email", fl)
                  else "text")
    return dict(name=fname.title(), slug=re.sub(r"[^a-z0-9]+", "_", fl), type=t)

def agent_create(prompt):
    for key, t in APP_TEMPLATES.items():
        if APP_MATCH[key].search(prompt):
            spec = json.loads(json.dumps(t))
            m = re.search(r"(?:for|manage) ([a-z0-9 \-]{3,30}?)(?: and|,| with|\.|$)", prompt, re.I)
            if key == "crm" and m:
                spec["name"] = m.group(1).title() + " CRM"
            spec["keywords"] = key
            return spec
    # generic: invent entity from the biggest noun-ish words
    words = [w for w in re.findall(r"[a-zA-Z]{4,}", prompt) if w.lower() not in
             ("with", "that", "have", "make", "build", "create", "track", "manage", "apps", "simple",
              "help", "want", "need", "would", "some", "tool", "plate", "dish", "food" if False else "app", " utilize")]
    ent = words[0] if words else "Item"
    spec = dict(name=(words[0].title() if words else "My App"), icon=(words[0][0].upper() if words else "M"),
                color=random.choice(["#4d33de", "#ff773c", "#3b51e5", "#bedb3f"]),
                summary="Built from your prompt: " + prompt[:80],
                entities=[dict(name=ent.title(), slug=slugify(ent), fields=[
                    mk_field("Name",), mk_field("Created", "date")], seed=[[ent + " 1", "2026-10-30"], [ent + " 2", "2026-10-30"]])],
                pages=[dict(name=ent.title() + "s", type="list"), dict(name="New " + ent.title(), type="form")],
                keywords="generic")
    return spec

VALID_FTYPES = ("text", "textarea", "number", "email", "date", "checkbox", "select", "ref")

APP_MATCH = {k: t.pop("match") for k, t in APP_TEMPLATES.items()}
for _t in APP_TEMPLATES.values():
    _t.pop("match", None)

def agent_turn(app, instruction):
    lower = instruction.lower()
    steps, changes = [], []
    spec = app.setdefault("spec", {"entities": app.get("entities", []), "pages": app.get("pages", [])})
    ents, pages = spec.setdefault("entities", []), spec.setdefault("pages", [])
    m = re.search(r"add (?:an? )?(?:entity|table|list|collection|tracker)\s+(?:for |called |of )?\(?([a-z][a-z0-9 _-]{2,30})\)?", lower)
    if m:
        ename = m.group(1).strip().title()
        slug = slugify(ename)
        if not any(e["slug"] == slug for e in ents):
            ents.append(dict(name=ename, slug=slug, fields=[mk_field("Name"), mk_field("Status", "select")], seed=[["First " + ename.lower(), "New"]]))
            pages.append(dict(name=ename + ("" if ename.lower().endswith("s") else "s"), type="list"))
            changes.append("entity:" + slug)
            steps.append(f"Designing {ename} entity (fields, relations)")
            steps.append(f"Wiring {ename} pages + table UI")
    else:
        m = re.search(r"add (?:a |an )?(?:page|screen|view|form|section)\s+(?:for |called |of )?\(?([a-z][a-z0-9 _-]{2,30})\)?", lower)
        if m:
            pname = m.group(1).strip().title()
            pages.append(dict(name=pname, type=("form" if "form" in lower else "list")))
            if ents and not pages[-1].get("entity"):
                pages[-1]["entity"] = ents[-1]["slug"]
            steps.append(f"Creating {pname} page (layout + copy)")
            steps.append("Adding page to the nav rail")
        else:
            m = re.search(r"(theme|color|couleur).{0,40}?(#?[0-9a-fA-F]{6}|orange|purple|blue|lime|dark|yellow)", lower)
            if m:
                c = m.group(2)
                accent = {"orange": "#ff773c", "purple": "#4d33de", "blue": "#3b51e5", "lime": "#bedb3f", "yellow": "#f0c84d", "dark": "#20201f"}.get(c.lower(), None)
                if not (accent or c.startswith("#")):
                    accent = None
                hexv = (c if c.startswith("#") else accent) or "#ff773c"
                app["theme"] = {"accent": hexv}
                steps.append("Applying brand accent across components")
                steps.append("Regenerating tokens (radius/shadows kept)")
            else:
                m = re.search(r"(rename|call)\s+(?:it\s+)?[\"“']?([a-zA-Z][\w \-]{2,30})", lower)
                if m:
                    app["name"] = m.group(2).strip().title()
                    steps.append("Mapping surface route + brand copy")
                else:
                    m = re.search(r"(publish|deploy|live)", lower)
                    if m:
                        steps.append("Running last checks before publish")
                    else:
                        # default improvement pass
                        steps.append("Auditing UX: spacing, contrast, empty states")
                        steps.append("Tightening copy + micro-interactions")
    if ents and not steps:
        steps.append("Rebuilding tables with the updated schema")
    steps += ["Tweaking CSS tokens", "Running smoke tests", "Done"]
    with open(os.path.join(HERE, "data", "logs_" + app["id"] + ".jsonl"), "a") as f:
        f.write(json.dumps({"t": time.time(), "steps": steps, "instruction": instruction}) + "\n")
    return steps, changes

def code_files(app_spec, app):
    files = {}
    for e in app_spec.get("entities", []):
        parts = []
        for f in e.get("fields", []):
            p = '%s: { type: "%s"' % (f["slug"], f["type"])
            if f.get("required"):
                p += ', required: true'
            if f.get("options"):
                p += ', options: ' + json.dumps(f["options"])
            if f.get("suffix"):
                p += ', suffix: "%s"' % f["suffix"]
            p += ' }'
            parts.append(p)
        fields = ",\n      ".join(parts)
        files[f"entities/{e['name']}.js"] = (
            f"import {{ createEntity }} from 'base44/runtime'\n\n"
            f"export const {e['slug']} = createEntity({{\n  name: '{e['name']}',\n  slug: '{e['slug']}',\n  fields: {{\n      {fields}\n  }},\n}})\n"
        )
    pages = app_spec.get("pages", [])
    for p in pages:
        ent = next((e for e in app_spec.get("entities", []) if e["slug"] == p.get("entity")), app_spec.get("entities", [{}])[0] if app_spec.get("entities") else None)
        ename = ent["name"] if ent else "Item"
        if p.get("type") == "form":
            files[f"pages/{p['name'].replace(' ', '')}.jsx"] = (
                f"import {{ FormPage }} from 'base44/runtime'\nimport {{ {ent['slug']} }} from '../entities/{ename}.js'\n\n"
                f"export default function {p['name'].replace(' ', '')}() {{\n  return <FormPage title=\"{p['name']}\" entity={{ {ent['slug']} }} />\n}}\n")
        else:
            files[f"pages/{p['name'].replace(' ', '')}.jsx"] = (
                f"import {{ ListPage }} from 'base44/runtime'\nimport {{ {ent['slug']} }} from '../entities/{ename}.js'\n\n"
                f"export default function {p['name'].replace(' ', '')}() {{\n  return <ListPage title=\"{p['name']}\" entity={{ {ent['slug']} }} />\n}}\n")
    files["pages/App.jsx"] = (
        "#!/bin\n" if False else
        "".join(f"import P{i} from './{p['name'].replace(' ', '')}.jsx'\n" for i, p in enumerate(pages, 1)) +
        f"\nexport default [ {', '.join(f'P{i}' for i in range(1, len(pages) + 1))} ]\n" if pages else
        "// No pages yet — describe a change in the agent chat\n")
    return files

# ---- websocket stub (nafs prod parity: client yconnecti, y9bal ping/echo, fallback graceful) ----
def ws_accept(key):
    GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
    return base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()

def ws_frame(payload, opcode=1):
    b = payload.encode() if isinstance(payload, str) else payload
    head = bytes([0x80 | opcode])
    n = len(b)
    if n < 126: head += bytes([n])
    elif n < 1 << 16: head += bytes([126, n >> 8, n & 255])
    else: head += bytes([127]) + n.to_bytes(8, "big")
    return head + b

def handle_ws(self):
    key = self.headers.get("Sec-WebSocket-Key")
    if not key:
        self.send_response(400); self.end_headers(); return
    self.send_response(101)
    self.send_header("Upgrade", "websocket")
    self.send_header("Connection", "Upgrade")
    self.send_header("Sec-WebSocket-Accept", ws_accept(key))
    self.end_headers()
    try:
        self.wfile.write(ws_frame(json.dumps({"type":"hello","data":{"ok":True,"server":"base44-clone-ws"}})))
        self.settimeout(60)
        import socket as _s
        while True:
            op = None; data = b""; hdr = self.rfile.read(2)
            if len(hdr) < 2: return
            op = hdr[0] & 0x0F
            ln = hdr[1] & 0x7F
            if ln == 126: ln = int.from_bytes(self.rfile.read(2), "big")
            elif ln == 127: ln = int.from_bytes(self.rfile.read(8), "big")
            if ln: data = self.rfile.read(ln)
            if op == 8: self.wfile.write(ws_frame(b"", 8)); return
            if op == 9: self.wfile.write(ws_frame(data, 10)); continue
            if op == 1:
                try: msg = json.loads(data.decode())
                except Exception: msg = {"type": "echo"}
                self.wfile.write(ws_frame(json.dumps({"type": "ack", "data": msg})))
    except (ConnectionError, TimeoutError, OSError):
        return

# ---------------- helpers ----------------
def get_user(d, skey):
    for s in d["sessions"]:
        if s["key"] == skey:
            for u in d["users"]:
                if u["id"] == s["user_id"]:
                    return u
    return None

def user_json(u, d):
    ws = next((w for w in d["workspaces"] if w["user_id"] == u["id"]), None)
    return dict(id=u["id"], name=u["name"], email=u["email"], created=u.get("created"),
                workspace_id=ws["id"] if ws else None, plan="free")

def workspace_json(w, d):
    return dict(id=w["id"], name=w["name"], user_id=w["user_id"], plan="free", type="personal", owner_id=w["user_id"])

FN_MAP = {"text": "string", "textarea": "string", "number": "number", "email": "string",
          "date": "string", "checkbox": "boolean", "select": "string", "ref": "string"}

def usage(u):
    return round(min(usage_total(u), CREDIT_LIMIT), 2)

def usage_total(u):
    d = db()
    return sum(a.get("credits_used", 0) for a in d["apps"] if a["user_id"] == u["id"])

def approve_auth(h):
    d = db()
    auth = (h.headers.get("Authorization") or "").replace("Bearer ", "")
    if not auth:
        auth = h.headers.get("Cookie", len("b44_session=") and "") or ""
        m = re.search(r"b44_session=([\w-]+)", auth or "")
        auth = m.group(1) if m else auth
    u = get_user(d, auth)
    return d, u

# static
class QuietServer(ThreadingHTTPServer):
    allow_reuse_address = True
    def handle_error(self, request, client_address):
        _, ex, _ = sys.exc_info()
        if isinstance(ex, (BrokenPipeError, ConnectionResetError, TimeoutError)):
            return
        return super().handle_error(request, client_address)

import sys
class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=WWW, **kw)

    def log_message(self, fmt, *args):
        sys.stderr.write(f"  -> {self.command} {self.path}\n")

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "authorization, content-type, b44_session")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS, PATCH")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204); self.end_headers()

    def translate_path(self, path):
        return super().translate_path(re.sub(r"\?.*$", "", path))

    def js(self, payload, code=200):
        b = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def readbody(self):
        ln = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(ln) or b"{}")

    def api(self, path):
        u = None
        d, u = approve_auth(self), None
        d, u = d
        if path == "/api/auth/signup" or path == "/api/auth/login":
            if self.command != "POST":
                return self.js({"error": "method"}, 405)
            body = self.readbody()
            email = (body.get("email") or "").strip().lower()
            key = "auth" in path and "signup" in path
            d = db()
            usr = next((x for x in d["users"] if x["email"] == email), None)
            if not usr:
                usr = {"id": "u_" + uuid.uuid4().hex[:10], "email": email,
                       "name": email.split("@")[0].title() or "Builder",
                       "pwd": hashlib.sha256(("mock:" + str(body.get("password"))).encode()).hexdigest(),
                       "created": "2026-10-30T00:00:00Z"}
                d["users"].append(usr)
                ws = {"id": "ws_" + uuid.uuid4().hex[:10], "name": usr["name"] + "'s Workspace", "user_id": usr["id"]}
                d["workspaces"].append(ws)
            token = secrets.token_urlsafe(24)
            d["sessions"].append({"key": token, "user_id": usr["id"], "t": time.time()})
            save(d)
            return self.js({"access_token": token, "token_type": "Bearer", "expires_in": 3600000, "user": user_json(usr, d)})
        if path == "/api/auth/logout":
            d = db(); auth = (self.headers.get("Authorization") or "").replace("Bearer ", "")
            d["sessions"] = [s for s in d["sessions"] if s["key"] != auth]; save(d)
            return self.js({"ok": True})
        m = re.match(r"^/api/published/([\w-]+)$", path)
        if m:  # public: published apps are on the open web, no auth
            d = db()
            app = next((a for a in d["apps"] if a.get("sub_domain") == m.group(1) and a["state"] == "published"), None)
            if not app:
                return self.js({"error": "not_found"}, 404)
            return self.js({"name": app["name"], "theme": app.get("theme"), "spec": app["spec"]})
        d, u = approve_auth(self)
        if not u:
            return self.js({"error": "unauthorized"}, 401)
        if path == "/api/me":
            return self.js(user_json(u, d))
        if path == "/api/workspaces":
            return self.js([workspace_json(w, d) for w in d["workspaces"] if w["user_id"] == u["id"]])
        if path == "/api/workspaces" and self.command == "POST":
            body = self.readbody()
            ws = {"id": "ws_" + uuid.uuid4().hex[:10], "name": (body.get("name") or "New Workspace").strip()[:48],
                  "user_id": u["id"], "plan": "free"}
            d["workspaces"].append(ws); save(d)
            return self.js(workspace_json(ws, d))
        m = re.match(r"^/api/workspaces/([\w-]+)/members$", path)
        if m:
            ws = next((w for w in d["workspaces"] if w["id"] == m.group(1) and w["user_id"] == u["id"]), None)
            if not ws:
                return self.js({"error": "not_found"}, 404)
            members = [{"user_id": u["id"], "name": u["name"], "email": u["email"], "role": "admin", "status": "active"}]
            for inv in d.get("invites", []):
                if inv["workspace_id"] == ws["id"]:
                    members.append({"user_id": inv.get("invitee"), "name": inv["email"].split("@")[0].title(),
                                    "email": inv["email"], "role": inv.get("role", "member"), "status": inv["status"]})
            d.setdefault("invites", []); save(d)
            return self.js(members)
        m = re.match(r"^/api/workspaces/([\w-]+)/invite$", path)
        if m and self.command == "POST":
            ws = next((w for w in d["workspaces"] if w["id"] == m.group(1) and w["user_id"] == u["id"]), None)
            if not ws:
                return self.js({"error": "not_found"}, 404)
            body = self.readbody()
            email = (body.get("email") or "").strip().lower()
            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
                return self.js({"error": "invalid_email"}, 400)
            d.setdefault("invites", []).append({"workspace_id": ws["id"], "email": email,
                                                "role": body.get("role", "member"), "status": "pending", "t": time.time()})
            save(d)
            return self.js({"ok": True, "email": email, "status": "pending"})
        m = re.match(r"^/api/domains/([a-z0-9.\-]+)/status$", path)
        if m:
            dom = m.group(1)
            rec = next((x for x in d.get("domains", []) if x["domain"] == dom), None)
            if not rec:
                d.setdefault("domains", []).append({"domain": dom, "t": time.time(), "status": "pending"})
                save(d)
                return self.js({"domain": dom, "status": "pending", "txt_record": "b44-verify=" + dom[:12], "note": "First check — add the TXT record and re-verify."})
            elapsed = time.time() - rec["t"]
            st = "verified" if elapsed > 3 else "pending"
            if st == "verified":
                rec["status"] = "verified"
                save(d)
            else:
                d.setdefault("domains", []).append(rec)  # keep
            return self.js({"domain": dom, "status": st, "txt_record": "b44-verify=" + dom[:12]})
        m = re.match(r"^/api/billing/portal$", path)
        if m:
            return self.js({"url": f"http://localhost:{PORT}/#/settings", "mode": "mock_stripe_portal"})
        m = re.match(r"^/api/billing/subscribe$", path)
        if m and self.command == "POST":
            body = self.readbody()
            plan = body.get("plan") if body.get("plan") in ("free", "pro") else "pro"
            ws = next((w for w in d["workspaces"] if w["user_id"] == u["id"]), None)
            if ws:
                ws["plan"] = plan
            for a in d["apps"]:
                if a["user_id"] == u["id"]:
                    a["plan"] = plan
            save(d)
            return self.js({"ok": True, "plan": plan, "credits_limit": 20 if plan == "free" else 100})
        if path == "/api/credits":
            used = usage_total(u)
            return self.js({"total": CREDIT_LIMIT, "used": round(used, 2), "daily_limit": CREDIT_LIMIT, "left": round(max(0, CREDIT_LIMIT - used), 2)})
        if path == "/api/workspace_apps":
            return self.js([pub(a) for a in d["apps"] if a["user_id"] == u["id"]])
        m = re.match(r"^/api/apps$", path)
        if m and self.command == "POST":
            body = self.readbody()
            prompt = (body.get("prompt") or "").strip() or body.get("name") or "My App"
            spec = agent_create(prompt) if "prompt" in body else dict(
                name=body.get("name") or "Untitled App", icon=(body.get("name") or "A")[0].upper(),
                color="#4d33de", summary=body.get("summary") or "Empty app — describe a change to build it.",
                entities=[], pages=[])
            app = {"id": "a_" + uuid.uuid4().hex[:10], "name": spec.get("name") or "Untitled App",
                   "user_id": u["id"], "created": time.time(), "updated": time.time(),
                   "state": "draft", "visibility": "private", "live_version": "", "bundle_version": "1",
                   "sub_domain": slugify(spec.get("name") or "app"), "spec": spec,
                   "files": code_files(spec, {}), "logs": [["t0", "Agent seeding app…"], ["t1", "App shell ready"]],
                   "credits_used": 1.5, "theme": spec.get("theme", {"accent": "#ff773c"})}
            d["apps"].append(app); save(d)
            return self.js(pub(app))
        m = re.match(r"^/api/apps/([\w-]+)$", path)
        if m:
            app = next((a for a in d["apps"] if a["id"] == m.group(1) and a["user_id"] == u["id"]), None)
            if not app:
                return self.js({"error": "not_found"}, 404)
            if self.command == "GET":
                return self.js(pub(app))
            if self.command == "PATCH":
                body = self.readbody()
                for k in ("name", "visibility", "theme"):
                    if k in body:
                        app[k] = body[k]
                app["updated"] = time.time(); save(d)
                return self.js(pub(app))
            if self.command == "DELETE":
                d["apps"].remove(app); save(d)
                return self.js({"ok": True})
        m = re.match(r"^/api/apps/([\w-]+)/agent$", path)
        if m and self.command == "POST":
            app = next((a for a in d["apps"] if a["id"] == m.group(1) and a["user_id"] == u["id"]), None)
            if not app:
                return self.js({"error": "not_found"}, 404)
            body = self.readbody()
            instruction = (body.get("message") or "").strip()
            if not instruction:
                return self.js({"error": "empty message"}, 400)
            if usage_total(u) >= CREDIT_LIMIT:
                return self.js({"error": "insufficient_credits", "message": "You've used all your daily credits."}, 402)
            steps, changes = agent_turn(app, instruction)
            app["spec"].setdefault("entities", []), app["spec"].setdefault("pages", [])
            app["files"] = code_files(app["spec"], app)
            app["credits_used"] = round(app.get("credits_used", 0) + 0.4, 2)
            app["updated"] = time.time()
            app["logs"].append([str(time.time()), "—".join(steps)])
            save(d)
            return self.js({"steps": steps, "changes": changes, "credits": {"used": usage_total(u), "left": round(max(0, CREDIT_LIMIT - usage_total(u)), 2)}}, )
        m = re.match(r"^/api/apps/([\w-]+)/publish$", path)
        if m and self.command == "POST":
            app = next((a for a in d["apps"] if a["id"] == m.group(1) and a["user_id"] == u["id"]), None)
            if not app:
                return self.js({"error": "not_found"}, 404)
            app["state"] = "published"; app["live_version"] = str(app.get("bundle_version") or "1")
            app["credits_used"] = round(app.get("credits_used", 0) + 0.4, 2)
            save(d)
            return self.js(pub(app))
        m = re.match(r"^/api/apps/([\w-]+)/logs$", path)
        if m:
            app = next((a for a in d["apps"] if a["id"] == m.group(1) and a["user_id"] == u["id"]), None)
            if not app:
                return self.js({"error": "not_found"}, 404)
            return self.js(app.get("logs", []))
        m = re.match(r"^/api/published/([\w-]+)$", path)
        if m:
            app = next((a for a in d["apps"] if a["sub_domain"] == m.group(1) and a["state"] == "published"), None)
            if not app:
                return self.js({"error": "not_found"}, 404)
            return self.js({"name": app["name"], "theme": app.get("theme"), "spec": app["spec"]})
        return self.js({"error": "unknown_endpoint", "path": path}, 404)

    def do_GET(self):
        path = re.sub(r"\?.*$", "", self.path)
        if path == "/ws" or path.startswith("/ws/"):
            return handle_ws(self)
        m = re.match(r"^/p/([\w-]+)$", path)
        if m:
            with open(os.path.join(WWW, "runtime.html"), "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers(); self.wfile.write(data)
            return
        if path.startswith("/api/"):
            try:
                return self.api(path)
            except Exception as e:
                return self.js({"error": "internal", "detail": str(e)}, 500)
        if path == "/" or ("/" not in path.strip("/") and "." not in path.split("/")[-1]):
            if path != "/":
                data = open(os.path.join(WWW, "index.html"), "rb").read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers(); self.wfile.write(data)
                return
        return SimpleHTTPRequestHandler.do_GET(self)

    def do_POST(self):
        path = re.sub(r"\?.*$", "", self.path)
        if path.startswith("/api/"):
            try:
                return self.api(path)
            except Exception as e:
                return self.js({"error": "internal", "detail": str(e)}, 500)
        self.js({"error": "not_found"}, 404)

    def do_PATCH(self):
        return self.do_POST()

    def do_PUT(self):
        return self.do_POST()

if __name__ == "__main__":
    print(f"Base44 platform clone → http://localhost:{PORT}")
    Quieted = QuietServer(("0.0.0.0", PORT), Handler)
    Quieted.serve_forever()
