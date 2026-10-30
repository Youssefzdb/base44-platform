#!/usr/bin/env python3
"""AI website-builder e2e (API level): full React site via tool calls.

Flow:
1. login
2. create app from prompt containing website keywords → mode=website, gen_files≥6, entries include src/App.jsx + a .css
3. agent turn (SSE) "add a testimonials section" → file count grows, preview events present
4. publish → public /api/published/:slug exposes gen_files + mode
Exit 0 iff all pass. Long test (~1-2 min): real model calls.
"""
import json, sys, time, urllib.request
from collections import Counter

B = "http://localhost:8510"
PROMPT = "Website for a pizzeria called Napoli Bella, warm red and cream palette, menu with prices"
results = []

def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(("✓ " + name) if ok else ("✗ " + name + " — " + str(detail)[:160]))

def req(path, method="GET", body=None, token=None):
    h = {"Authorization": "Bearer " + token} if token else {}
    if body:
        h["Content-Type"] = "application/json"
    r = urllib.request.Request(B + path, data=(json.dumps(body).encode() if body else None),
                               method=method, headers=h)
    return json.loads(urllib.request.urlopen(r, timeout=300).read())

tok = req("/api/auth/login", "POST", {"email": "ai-site@x.io", "password": "p"})["access_token"]
t0 = time.time()
app = req("/api/apps", "POST", {"prompt": PROMPT}, token=tok)
gen = app.get("gen_files", {})
check(f"1. AI website create ({time.time()-t0:.0f}s, mode={app.get('mode')})", app.get("mode") == "website" and len(gen) >= 6,
      "files=" + ",".join(sorted(gen))[:110])
check("2. site entries", any("App.jsx" in p for p in gen) and any(p.endswith(".css") for p in gen))
app_id = app["id"]

# SSE turn: edit the generated site
r = urllib.request.Request(B + f"/api/apps/{app_id}/agent/stream",
                           data=json.dumps({"message": "Add a testimonials section with 3 customer reviews"}).encode(),
                           method="POST", headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
ev = []
with urllib.request.urlopen(r, timeout=300) as s:
    buf = ""
    while True:
        c = s.read(256)
        if not c:
            break
        buf += c.decode()
        while "\n\n" in buf:
            l, buf = buf.split("\n\n", 1)
            if l.startswith("data: "):
                ev.append(json.loads(l[6:]))
kinds = Counter(e["type"] for e in ev)
gen2 = req(f"/api/apps/{app_id}", token=tok).get("gen_files", {})
check(f"3. edit turn streamed ({kinds.get('file',0)} files written)", kinds.get("file", 0) >= 1 and kinds.get("done", 0) == 1, dict(kinds))
check("4. file count grows", len(gen2) >= len(gen), f"{len(gen)}→{len(gen2)}")

pub = req(f"/api/apps/{app_id}/publish", "POST", token=tok)
pubd = json.loads(urllib.request.urlopen(B + f"/api/published/{pub['sub_domain']}").read())
check("5. published public runtime has site", pubd.get("mode") == "website" and len(pubd.get("gen_files", {})) == len(gen2))

bad = [r for r in results if not r[1]]
print(json.dumps({"pass": len(results) - len(bad), "fail": len(bad)}, ensure_ascii=False))
sys.exit(1 if bad else 0)
