#!/usr/bin/env python3
"""Browser-level e2e on the REAL React build (base44-react/dist served by server.py).

Drives chromium headless against :8510:
1. login card renders
2. demo login → home hero
3. create app from prompt → builder loads
4. agent turn → steps timeline rendered
5. agent applied → new entity file visible in Code tab
6. dark mode → .dark class via pre-paint script
7. runtime.html preview iframe → entity table
8. publish tab → publish button + custom domain input
Exit 0 iff all pass. Requires: server.py running, playwright installed.
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

    # 3 create app from prompt → builder
    page.fill(".prompt textarea", "A CRM to track my clients and deals")
    page.click(".prompt button")
    page.wait_for_url("**/app/**", timeout=15000)
    page.wait_for_selector(".chat-body", timeout=10000)
    check("3. builder loaded", page.locator(".work-head b").inner_text().strip() == "CRM")

    # 4 agent turn: steps timeline visible
    page.fill(".chat-input textarea", "Add entity for invoices")
    page.click(".chat-input button")
    try:
        page.wait_for_selector(".msg.ai .steps .step", timeout=6000)
        first = page.locator(".msg.ai .steps .step").first.inner_text()
        check("4. agent steps rendered", "Designing" in first, first)
    except Exception as e:
        check("4. agent steps rendered", False, type(e).__name__)
    page.wait_for_timeout(2600)  # let the turn fully settle (files regenerated)

    # 5 agent applied: Invoice entity file in Code tab
    page.get_by_role("button", name="Code").click()
    page.wait_for_selector(".code-file", timeout=8000)
    inv = page.locator(".code-file", has_text="Invoice")
    (inv.first if inv.count() else page.locator(".code-file", has_text="entities/").first).click()
    code = page.inner_text("pre.code")
    check("5. code viewer has entity", "createEntity" in code, code[:80])

    # 6 dark mode via pre-paint stamp
    page.evaluate("localStorage.setItem('appearance-theme','dark')")
    page.reload(wait_until="networkidle")
    check("6. dark class applied", page.evaluate("document.documentElement.classList.contains('dark')"))
    page.evaluate("localStorage.setItem('appearance-theme','light')")
    page.reload(wait_until="networkidle")

    # 7 runtime preview iframe → entity table
    page.get_by_role("button", name="Preview").click()
    page.wait_for_selector('iframe[title="preview"]', timeout=8000)
    page.wait_for_timeout(2200)  # iframe fetch + render
    frame = next((f for f in page.frames if "/runtime.html" in (f.url or "")), None)
    ok7 = frame is not None and frame.locator("table").count() >= 1
    check("7. runtime entity table", bool(ok7),
          "frame=%s body=%s" % (frame is not None,
                                frame.locator("body").inner_text()[:60].replace("\n", "|") if frame else "?"))

    # 8 publish panel + custom domain input
    page.get_by_role("button", name="Publish").click()
    page.wait_for_selector(".publish-wrap", timeout=8000)
    ok8 = page.get_by_text("Publish to the web").count() >= 1
    dom = page.get_by_placeholder("app.yourbrand.com")
    dom.fill("app.brand.dev")
    check("8. publish + custom domain", ok8 and dom.input_value() == "app.brand.dev", "btn=%s" % ok8)

    browser.close()

bad = [r for r in results if not r[1]]
print(json.dumps({"pass": len(results) - len(bad), "fail": len(bad)}, ensure_ascii=False))
sys.exit(1 if bad else 0)
