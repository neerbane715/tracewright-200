"""Drive Act 2 end-to-end: two recipients, real decrypt, real comparison."""
import sys, pathlib
from playwright.sync_api import sync_playwright
OUT = pathlib.Path("spike/out"); OUT.mkdir(parents=True, exist_ok=True)
FAIL = []
def chk(ok, what, extra=""):
    print(("  [PASS] " if ok else "  [FAIL] ") + what + (f"  {extra}" if extra else ""))
    if not ok: FAIL.append(what)

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1340, "height": 950}, color_scheme="dark")
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)

    # seal first so a bundle exists
    pg.goto("http://127.0.0.1:5174/distribute", wait_until="networkidle")
    pg.wait_for_selector("button[aria-pressed]", timeout=15000)
    if pg.locator("button:has-text('Encrypt for')").count():
        pg.click("button:has-text('Encrypt for')")
        pg.wait_for_selector("text=Sealed for", timeout=60000)

    print("\nAct 2 — open as two recipients")
    pg.goto("http://127.0.0.1:5174/open", wait_until="networkidle")
    pg.wait_for_selector("button[aria-pressed]", timeout=15000)

    pg.click("button[aria-pressed]:has-text('Alice')")
    pg.wait_for_selector("text=bits embedded", timeout=90000)
    chk(True, "alice opened — pipeline completed")
    steps = pg.locator("ol li").count()
    chk(steps >= 6, f"pipeline steps shown ({steps})")
    chk(pg.locator("text=ML-DSA-65 private key").count() > 0, "signing step visible")
    pg.screenshot(path=str(OUT / "tw-act2-one.png"), full_page=True)

    pg.click("button[aria-pressed]:has-text('Bob')")
    pg.wait_for_selector("text=Identical to read", timeout=90000)
    pg.wait_for_selector("text=byte positions differ", timeout=60000)
    pg.wait_for_timeout(1200)
    chk(True, "bob opened — comparison panel appeared")

    body = pg.inner_text("body")
    chk("byte positions differ" in body, "byte-distinctness measured")
    chk("words, identical in both" in body, "word equality measured")
    chk("pt maximum shift" in body, "baseline shift measured")
    imgs = pg.locator("figure img").count()
    chk(imgs == 2, f"both copies rendered ({imgs} images)")
    broken = pg.eval_on_selector_all(
        "figure img", "els=>els.filter(e=>!e.complete||e.naturalWidth===0).length")
    chk(broken == 0, "page images actually loaded")
    pg.screenshot(path=str(OUT / "tw-act2-proof.png"), full_page=True)

    print("\nTechnical depth")
    pg.click("text=Technical detail"); pg.wait_for_timeout(900)
    body = pg.inner_text("body")
    chk("signature" in body.lower() and "3309" in body, "real signature length shown")
    chk("the exact bytes that were signed" in body, "signed bytes available")
    pg.screenshot(path=str(OUT / "tw-act2-deep.png"), full_page=True)

    real = [e for e in errs if "favicon" not in e.lower()]
    chk(not real, f"no console errors ({len(real)})")
    if real: print("   ", real[:2])
    b.close()

print("\n" + ("ALL PASS" if not FAIL else f"{len(FAIL)} FAILED"))
sys.exit(1 if FAIL else 0)
