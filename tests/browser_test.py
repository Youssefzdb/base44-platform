#!/usr/bin/env python3
"""Browser-level e2e on the REAL React build + AI agent backend (SSE).

Drives chromium headless against :8510:
1. login card renders
2. demo login → home hero
3. AI create app from prompt → builder loads (non-empty name)
4. agent turn → thinking row rendered (AI plan visible)
5. tool chips rendered (AI tool calls) + entity file in Code tab
6. live preview: iframe src gets bumped (rev param)
7. dark mode → .dark class via pre-paint script
8. runtime entity table in preview iframe
9. publish tab → publish button + custom domain input
Exit 0 iff all pass. Requires: server.py running (AI keys in /gpt.txt) + playwright.
"""
import json, sys
from playwright.sync_api import sync_playwright

B = "http://localhost:8510"
results = []

def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(("✓ " + name) if ok else ("✗ " + name + " — " + str(detail)[:160]))

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
    ctx = browser.new_context(viewport={"width": 1360, "height": 900})
    page = ctx.new_page()

    # 1 login screen
    page.goto(B, wait_until="networkidle")
    check("1. login card", page.locator(".auth-title").count() == 1)

    # 2 demo login → home hero
    page.get_by_role("button", name="Try the demo workspace").click()
    page.wait_for_url("**/#/", timeout=10000)
    page.wait_for_selector(".hero", timeout=10000)
    check("2. hero after demo login", "Build useful apps" in page.inner_text(".hero"))

    # 3 AI create app from prompt → builder
    page.fill(".prompt textarea", "A CRM to track my clients and deals")
    page.click(".prompt button")
    page.wait_for_url("**/app/**", timeout=30000)
    page.wait_for_selector(".chat-body", timeout=10000)
    name = page.locator(".work-head b").inner_text().strip()
    check("3. builder loaded (AI spec)", bool(name) and name.lower() != "untitled app", "name=%r" % name)

    # 4 agent turn: thinking row (AI plan streamed)
    page.fill(".chat-input textarea", "Add entity for invoices")
    page.click(".chat-input button")
    try:
        page.wait_for_selector(".msg.ai.live", timeout=8000)   # streaming bubble
        page.wait_for_selector(".think-row", timeout=25000)
        check("4. thinking streamed", True)
    except Exception as e:
        check("4. thinking streamed", False, type(e).__name__)
    page.wait_for_timeout(6000)                                # turn lands fully

    # 5 tool chips + code tab (entity file)
    chips = page.locator(".tool-chip b").all_inner_texts()
    check("5a. tool calls shown", len(chips) >= 1, "chips=%s" % chips)
    page.get_by_role("button", name="Code").click()
    page.wait_for_selector(".code-file", timeout=8000)
    inv = page.locator(".code-file", has_text="Invoice")
    (inv.first if inv.count() else page.locator(".code-file", has_text="entities/").first).click()
    code = page.inner_text("pre.code")
    check("5b. code viewer has entity", "createEntity" in code, code[:80])

    # 6 live preview bumped by backend preview event
    page.get_by_role("button", name="Preview").click()
    page.wait_for_selector('iframe[title="preview"]', timeout=8000)
    src = page.locator('iframe[title="preview"]').get_attribute("src") or ""
    check("6. live-preview rev bump", "rev=" in src and not src.endswith("rev=0"), src)

    # 7 dark mode via pre-paint stamp
    page.evaluate("localStorage.setItem('appearance-theme','dark')")
    page.reload(wait_until="networkidle")
    check("7. dark class applied", page.evaluate("document.documentElement.classList.contains('dark')"))
    page.evaluate("localStorage.setItem('appearance-theme','light')")
    page.reload(wait_until="networkidle")

    # 8 runtime preview iframe → entity table
    page.get_by_role("button", name="Preview").click()
    page.wait_for_selector('iframe[title="preview"]', timeout=8000)
    page.wait_for_timeout(2200)
    frame = next((f for f in page.frames if "/runtime.html" in (f.url or "")), None)
    ok8 = frame is not None and frame.locator("table").count() >= 1
    check("8. runtime entity table", bool(ok8),
          "frame=%s body=%s" % (frame is not None,
                                frame.locator("body").inner_text()[:60].replace("\n", "|") if frame else "?"))

    # 9 publish panel + custom domain input
    page.get_by_role("button", name="Publish").click()
    page.wait_for_selector(".publish-wrap", timeout=8000)
    ok9 = page.get_by_text("Publish to the web").count() >= 1 or page.get_by_text("Live").count() >= 1
    dom = page.get_by_placeholder("app.yourbrand.com")
    dom.fill("app.brand.dev")
    check("9. publish + custom domain", ok9 and dom.input_value() == "app.brand.dev", "btn=%s" % ok9)

    browser.close()

bad = [r for r in results if not r[1]]
print(json.dumps({"pass": len(results) - len(bad), "fail": len(bad)}, ensure_ascii=False))
sys.exit(1 if bad else 0)
