"""Act 4: the leak is staged WITHOUT computing who did it.

The central assertion: nothing on this screen, and nothing in its API
response, names the recipient. That was the original wizard's failure -- it
investigated here and replayed the answer later while calling it extraction.
"""
import sys, pathlib, json, urllib.request
from playwright.sync_api import sync_playwright
OUT = pathlib.Path("spike/out"); OUT.mkdir(parents=True, exist_ok=True)
FAIL = []
def chk(ok, what, extra=""):
    print(("  [PASS] " if ok else "  [FAIL] ") + what + (f"  {extra}" if extra else ""))
    if not ok: FAIL.append(what)

NAMES = ("alice", "bob", "carol", "dave", "erin")

print("\nAPI: staging must not reveal the source")
req = urllib.request.Request("http://127.0.0.1:8000/api/stage-leak",
                             data=json.dumps({}).encode(),
                             headers={"Content-Type": "application/json"})
body = json.loads(urllib.request.urlopen(req, timeout=30).read())
chk(not any(k in body for k in ("user_id", "recipient", "source", "outcome")),
    "response has no recipient field", str(list(body.keys())))
blob = json.dumps(body).lower()
chk(not any(n in blob for n in NAMES),
    "response text does not name any recipient")

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1340, "height": 900}, color_scheme="dark")
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)

    # make sure copies exist
    pg.goto("http://127.0.0.1:5174/open", wait_until="networkidle")
    pg.wait_for_selector("button[aria-pressed]", timeout=15000)
    for who in ("Alice", "Carol"):
        pg.click(f"button[aria-pressed]:has-text('{who}')")
        pg.wait_for_selector("text=bits embedded", timeout=90000)
        pg.wait_for_timeout(300)

    print("\nAct 4 — before recovery")
    pg.goto("http://127.0.0.1:5174/leak", wait_until="networkidle")
    chk("document surfaces" in pg.inner_text("h1"), "leak framed as a scenario")
    chk(pg.locator("svg[role=img]").count() >= 1, "scene diagram present")
    chk(pg.locator("input[type=file]").count() == 0,
        "no bare file picker as the entry point")
    pg.screenshot(path=str(OUT / "tw-act4-before.png"), full_page=True)

    print("\nAct 4 — after recovery")
    pg.click("text=Recover the leaked file")
    pg.wait_for_selector("text=Artefact recovered", timeout=60000)
    pg.wait_for_timeout(900)
    txt = pg.inner_text("body").lower()
    chk("sha-256" in txt, "hash recorded")
    chk("bytes" in txt and "pages" in txt, "size and page count shown")
    imgs = pg.locator("img").count()
    chk(imgs >= 1, "recovered document rendered")
    broken = pg.eval_on_selector_all(
        "img", "els=>els.filter(e=>!e.complete||e.naturalWidth===0).length")
    chk(broken == 0, "preview image actually loaded")

    # THE assertion
    named = [n for n in NAMES if n in txt]
    chk(not named, "screen does not name any recipient", str(named))
    pg.screenshot(path=str(OUT / "tw-act4-after.png"), full_page=True)

    chk(pg.locator("text=Investigate this file").count() > 0,
        "hands off to Act 5")

    real = [e for e in errs if "favicon" not in e.lower()]
    chk(not real, f"no console errors ({len(real)})")
    if real: print("   ", real[:2])
    b.close()

print("\n" + ("ALL PASS" if not FAIL else f"{len(FAIL)} FAILED"))
sys.exit(1 if FAIL else 0)
