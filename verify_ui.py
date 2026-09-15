"""Drive the full UI flow end to end and screenshot each stage.

    # terminal 1
    python -m uvicorn pqfw_api.main:app --host 127.0.0.1 --port 8000
    # terminal 2
    cd web && npm run dev
    # terminal 3
    python verify_ui.py

Clicks through every tab the way a judge would, asserts what should appear,
and fails loudly if it does not. Screenshots land in spike/out/.

Requires: pip install playwright && python -m playwright install chromium
"""
from playwright.sync_api import sync_playwright
import pathlib, sys
out = pathlib.Path("spike/out"); out.mkdir(parents=True, exist_ok=True)
FAIL = []
def chk(ok, what):
    print(("  [PASS] " if ok else "  [FAIL] ") + what)
    if not ok: FAIL.append(what)

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width":1400,"height":900})
    errs = []
    pg.on("console", lambda m: errs.append(m.text) if m.type=="error" else None)
    pg.on("pageerror", lambda e: errs.append(str(e)))

    pg.goto("http://127.0.0.1:5173/", wait_until="networkidle")
    chk(pg.locator("text=PQ-FORENSIC").count() > 0, "app loads")

    # --- Distribute
    pg.click("text=Distribute")
    pg.wait_for_selector("input[type=checkbox]", timeout=15000)
    pg.wait_for_function("document.querySelectorAll('input[type=checkbox]:checked').length === 5",
                         timeout=15000)
    chk(pg.locator("input[type=checkbox]:checked").count() == 5,
        "Distribute lists and preselects 5 recipients")
    pg.click("button:has-text('Encrypt for')"); pg.wait_for_timeout(2500)
    chk(pg.locator("text=Bundle created").count() > 0, "Distribute: bundle created")
    pg.screenshot(path=str(out/"ui-1-distribute.png"), full_page=True)

    # --- Receive
    pg.click("text=Receive")
    pg.wait_for_function("document.querySelectorAll('select option').length >= 5", timeout=15000)
    pg.select_option("select", "dave")
    pg.click("button:has-text('Decrypt as')")
    pg.wait_for_selector("text=What happened", timeout=60000)
    steps = pg.locator("ol.steps li").count()
    chk(steps >= 6, f"Receive: {steps} pipeline steps shown")
    chk(pg.locator("text=ML-DSA-65").count() > 0, "Receive: signing step visible")
    pg.screenshot(path=str(out/"ui-2-receive.png"), full_page=True)

    # --- Investigate
    pg.click("text=Investigate"); pg.wait_for_timeout(500)
    pg.set_input_files("input[type=file]", "demo/LEAKED-DOCUMENT.pdf")
    pg.wait_for_selector(".verdict", timeout=120000)
    pg.wait_for_timeout(500)
    who = pg.locator(".verdict .who").inner_text()
    chk(who.strip() == "carol", f"Investigate: names carol (got '{who.strip()}')")
    seals = pg.locator('.seal .chk[data-ok="true"]').count()
    chk(seals == 4, f"Investigate: {seals}/4 evidence seals green")
    pg.screenshot(path=str(out/"ui-3-verdict.png"), full_page=True)

    # --- Ledger + tamper
    pg.click("text=Ledger"); pg.wait_for_timeout(800)
    rows = pg.locator("tbody tr").count()
    chk(rows >= 6, f"Ledger: {rows} records listed")
    pg.click("button:has-text('Check integrity')"); pg.wait_for_timeout(1200)
    chk(pg.locator("text=ledger intact").count() > 0, "Ledger: integrity check passes")

    pg.click("button:has-text('Tamper as administrator')"); pg.wait_for_timeout(2000)
    chk(pg.locator("text=/record #1 was modified/").count() > 0, "Ledger: tamper detected")
    pg.screenshot(path=str(out/"ui-4-tamper.png"), full_page=True)

    # --- Investigate again: must refuse
    pg.click("text=Investigate"); pg.wait_for_timeout(400)
    pg.set_input_files("input[type=file]", "demo/LEAKED-DOCUMENT.pdf")
    pg.wait_for_selector(".verdict", timeout=120000); pg.wait_for_timeout(400)
    tag = pg.locator(".verdict .tag").inner_text()
    chk("COMPROMISED" in tag, f"Investigate: refuses on tampered ledger ({tag})")
    red = pg.locator('.seal .chk[data-ok="false"]').count()
    chk(red == 4, f"Investigate: {red}/4 seals red")
    pg.screenshot(path=str(out/"ui-5-compromised.png"), full_page=True)

    # --- mobile
    pg.set_viewport_size({"width":390,"height":844}); pg.wait_for_timeout(600)
    chk(pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 2"),
        "mobile: no horizontal scroll at 390px")
    pg.screenshot(path=str(out/"ui-6-mobile.png"), full_page=True)

    real = [e for e in errs if "favicon" not in e.lower()]
    chk(not real, f"no console errors ({len(real)} found)")
    if real: print("   ", real[:2])
    b.close()

print(("\nALL UI CHECKS PASSED" if not FAIL else f"\n{len(FAIL)} UI CHECKS FAILED"))
