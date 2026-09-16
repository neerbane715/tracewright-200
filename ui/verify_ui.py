"""Drive the new UI in a real browser and assert what each Act must show."""
import sys, pathlib
from playwright.sync_api import sync_playwright
OUT = pathlib.Path("spike/out"); OUT.mkdir(parents=True, exist_ok=True)
FAIL = []
def chk(ok, what, extra=""):
    print(("  [PASS] " if ok else "  [FAIL] ") + what + (f"  {extra}" if extra else ""))
    if not ok: FAIL.append(what)

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1340, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)

    print("\nAct 0 — Brief")
    pg.goto("http://127.0.0.1:5174/", wait_until="networkidle")
    chk(pg.locator("text=Tracewright").count() > 0, "wordmark is Tracewright")
    chk(pg.locator("text=PQ-FORENSIC").count() == 0, "no PQ-FORENSIC anywhere")
    chk("Who did it?" in pg.inner_text("h1"), "leads with the question")
    chk(pg.locator("svg[role=img]").count() >= 1, "problem diagram present")
    pg.screenshot(path=str(OUT / "tw-act0.png"), full_page=True)

    # limits: present but not shouted
    chk(pg.locator("text=A screenshot or photograph cannot be traced").count() == 0,
        "limits hidden by default")
    pg.click("text=What this does not do"); pg.wait_for_timeout(300)
    chk(pg.locator("text=A screenshot or photograph cannot be traced").count() > 0,
        "limits open on demand")

    print("\nDepth toggle")
    pg.click("text=Start the walkthrough"); pg.wait_for_timeout(500)
    pg.goto("http://127.0.0.1:5174/", wait_until="networkidle")
    chk(pg.locator("text=ML-KEM-768 (FIPS 203) key encapsulation").count() == 0,
        "technical layer hidden by default")
    pg.click("text=Technical detail"); pg.wait_for_timeout(400)
    chk(pg.locator("text=ML-KEM-768 (FIPS 203) key encapsulation").count() > 0,
        "technical layer reveals on toggle")
    pg.screenshot(path=str(OUT / "tw-act0-deep.png"), full_page=True)

    print("\nAct 1 — Seal")
    pg.click("text=Start the walkthrough")
    # Identity cards are toggle buttons (aria-pressed), not checkboxes -- they
    # present key material, so a bare checkbox row would undersell them.
    pg.wait_for_selector("button[aria-pressed]", timeout=15000)
    pg.wait_for_function(
        "document.querySelectorAll('button[aria-pressed=true]').length===5",
        timeout=15000)
    chk(pg.locator("button[aria-pressed=true]").count() == 5,
        "5 recipient identity cards, all preselected")
    chk(pg.locator("text=fingerprint").count() >= 5, "each shows a key fingerprint")
    pg.screenshot(path=str(OUT / "tw-act1-before.png"), full_page=True)

    pg.click("button:has-text('Encrypt for 5')")
    pg.wait_for_selector("text=Sealed for 5 recipients", timeout=60000)
    pg.wait_for_timeout(600)
    chk(True, "encryption completed against the live backend")
    body = pg.inner_text("body")
    chk("bits available" in body and "required" in body, "capacity vs requirement shown")
    pg.screenshot(path=str(OUT / "tw-act1-after.png"), full_page=True)

    print("\nOffline-failure behaviour is covered separately (backend stop test)")
    real = [e for e in errs if "favicon" not in e.lower()]
    chk(not real, f"no console errors ({len(real)})")
    if real: print("   ", real[:2])
    b.close()

print("\n" + ("ALL PASS" if not FAIL else f"{len(FAIL)} FAILED"))
sys.exit(1 if FAIL else 0)
