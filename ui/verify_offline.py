"""Prove the running app needs no internet.

Source inspection is not enough -- it cannot catch a runtime fetch. This blocks
every request that is not to our own localhost servers, at the browser level,
then drives the whole journey. Any external request is recorded and fails the
run.
"""
import sys, pathlib
from playwright.sync_api import sync_playwright
if sys.platform == "win32":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass

OUT = pathlib.Path("spike/out"); OUT.mkdir(parents=True, exist_ok=True)
FAIL, BLOCKED = [], []
def chk(ok, what, extra=""):
    print(("  [PASS] " if ok else "  [FAIL] ") + what + (f"  {extra}" if extra else ""))
    if not ok: FAIL.append(what)

LOCAL = ("127.0.0.1", "localhost")

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1340, "height": 950}, color_scheme="dark")

    def route(r):
        url = r.request.url
        if url.startswith("data:") or url.startswith("blob:"):
            r.continue_(); return
        if any(h in url for h in LOCAL):
            r.continue_(); return
        BLOCKED.append(url)          # anything else would need the internet
        r.abort()

    pg.route("**/*", route)
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))

    print("\nDriving the full journey with all external requests blocked")
    pg.goto("http://127.0.0.1:5174/", wait_until="networkidle")
    chk(pg.locator("text=Tracewright").count() > 0, "Act 0 renders")

    # Fonts must come from our own origin, not a CDN.
    fonts = pg.evaluate("Array.from(document.fonts).map(f=>f.family)")
    chk(any("Inter" in f for f in fonts), "Inter loaded from local assets",
        str(sorted(set(fonts))[:4]))

    pg.goto("http://127.0.0.1:5174/distribute", wait_until="networkidle")
    pg.wait_for_selector("button[aria-pressed]", timeout=20000)
    if pg.locator("button:has-text('Encrypt for')").count():
        pg.click("button:has-text('Encrypt for')")
        pg.wait_for_selector("text=Sealed for", timeout=90000)
    chk(True, "Act 1 encrypts offline")

    pg.goto("http://127.0.0.1:5174/open", wait_until="networkidle")
    pg.wait_for_selector("button[aria-pressed]", timeout=20000)
    pg.click("button[aria-pressed]:has-text('Carol')")
    pg.wait_for_selector("text=bits embedded", timeout=120000)
    chk(True, "Act 2 decrypts and watermarks offline")

    pg.goto("http://127.0.0.1:5174/ledger", wait_until="networkidle")
    pg.wait_for_selector("text=Ledger intact", timeout=60000)
    chk(True, "Act 3 verifies the ledger offline")

    pg.goto("http://127.0.0.1:5174/leak", wait_until="networkidle")
    pg.click("text=Recover the leaked file")
    pg.wait_for_selector("text=Artefact recovered", timeout=90000)
    chk(True, "Act 4 recovers the artefact offline")

    pg.click("text=Investigate this file")
    pg.wait_for_selector("text=chain of evidence", timeout=240000)
    body = pg.inner_text("body")
    chk("IDENTIFIED" in body, "Act 5 attributes offline")
    pg.screenshot(path=str(OUT / "tw-offline.png"), full_page=True)

    chk(not errs, f"no page errors ({len(errs)})")
    b.close()

external = [u for u in BLOCKED if not u.startswith(("data:", "blob:"))]
chk(not external, f"no external request attempted ({len(external)})",
    str(external[:3]))

print("\n" + ("OFFLINE VERIFIED" if not FAIL else f"{len(FAIL)} FAILED"))
sys.exit(1 if FAIL else 0)
