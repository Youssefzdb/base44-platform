#!/usr/bin/env python3
"""AI clone-from-URL extraction tests (no AI calls): SSRF guard + extractor + context block.

Run: python3 tests/clone_extract_test.py
Requires network to example.com + stripe.com (title/desc may vary; we check structure, not content).
"""
import importlib.util, json, os, sys

spec = importlib.util.spec_from_file_location("b44server",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server.py"))
srv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(srv)

results = []
def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(("✓ " + name) if ok else ("✗ " + name + " — " + str(detail)[:140]))

# 1. SSRF guard: private/loopback nets blocked, public allowed
priv = ["http://localhost:8510", "http://127.0.0.1/x", "http://192.168.1.7/",
        "http://172.16.0.3/", "http://10.0.0.1", "http://172.31.9.9", "http://169.254.1.1", "http://::1/"]
check("1. SSRF private blocked", all(srv._safe_url(u) is None for u in priv))
check("2. SSRF public allowed", srv._safe_url("https://example.com") == "https://example.com"
      and srv._safe_url("https://stripe.com,") == "https://stripe.com")

# 3. extractor shape on example.com
c = srv.extract_site_context("https://example.com")
ok = bool(c) and c["host"] == "example.com" and c["title"]
check("3. extract example.com", ok, c if c else "None")
blk = srv.clone_context_block(c)
check("4. context block", blk.startswith("REFERENCE SITE ANALYSIS — fetched example.com") and len(blk) > 120)

# 5. extraction of a real CSS-rich site (structure only — content varies)
c2 = srv.extract_site_context("https://stripe.com")
ok = bool(c2) and c2["title"]
check("5. extract stripe.com (title+desc)", ok, c2 if c2 else "None")
check("6. headings fallback", bool(c2 and c2["headings"]))

# 7. clone_reference caches on app dict
app = {}
blk7 = srv.clone_reference(app, "Build a site inspired by https://example.com")
check("7. clone_reference + cache", bool(blk7) and app.get("clone", {}).get("host") == "example.com"
      and srv.clone_reference(app, "Build a site inspired by https://example.com") == blk7)
check("8. no url → no block + cache cleared", srv.clone_reference(app, "plain request") == "" and "clone" not in app)

bad = [r for r in results if not r[1]]
print(json.dumps({"pass": len(results) - len(bad), "fail": len(bad)}))
sys.exit(1 if bad else 0)
