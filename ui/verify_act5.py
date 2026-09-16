"""Act 5: the verdict must be FOUND, not remembered.

The decisive test: attribute two different recipients' copies and confirm the
answers are correct AND different. A cached or hardcoded result cannot pass it.
"""
import sys, pathlib, json, urllib.request
from playwright.sync_api import sync_playwright
OUT = pathlib.Path("spike/out"); OUT.mkdir(parents=True, exist_ok=True)
FAIL = []
def chk(ok, what, extra=""):
    print(("  [PASS] " if ok else "  [FAIL] ") + what + (f"  {extra}" if extra else ""))
    if not ok: FAIL.append(what)

def post(path, body, timeout=200):
    req = urllib.request.Request("http://127.0.0.1:8000" + path,
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())

print("\nAPI: attribution is distinct per recipient")
results = {}
for who in ("alice", "erin"):
    d = post("/api/attribute-path", {"path": f"{who}-copy.pdf"})
    results[who] = d
    ok = d["outcome"] == "IDENTIFIED" and d["recipient"]["user_id"] == who
    chk(ok, f"{who}'s copy attributes to {who}",
        f"got {d['recipient']['user_id']} margin {d['detection']['margin']:.2f}")
chk(results["alice"]["recipient"]["user_id"] != results["erin"]["recipient"]["user_id"],
    "the two answers differ (not a cached constant)")
chk(all(r["evidence"]["cryptographically_verified"] for r in results.values()),
    "all four evidence checks passed for both")

print("\nAPI: negative control")
d = post("/api/attribute-path", {"path": "../demo-docs/tender-evaluation.pdf"})
chk(d["outcome"] == "NO_WATERMARK" and d["recipient"]["user_id"] is None,
    "undistributed original names nobody", d["outcome"])

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1340, "height": 950}, color_scheme="dark")
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)

    print("\nAct 4 -> Act 5 handoff")
    pg.goto("http://127.0.0.1:5174/leak", wait_until="networkidle")
    pg.click("text=Recover the leaked file")
    pg.wait_for_selector("text=Artefact recovered", timeout=60000)
    pg.click("text=Investigate this file")
    # Wait for the panel rather than checking instantly -- React has not
    # rendered at the moment the click returns.
    try:
        pg.wait_for_selector("text=Examining the document", timeout=15000)
        shown = pg.locator("text=Reading the document's word spacing").count() > 0
    except Exception:
        shown = False
    chk(shown, "shows what it is doing during the wait")
    pg.screenshot(path=str(OUT / "tw-act5-working.png"))

    pg.wait_for_selector("text=chain of evidence", timeout=200000)
    pg.wait_for_timeout(900)
    body = pg.inner_text("body")
    chk("IDENTIFIED" in body, "verdict reached")
    chk("How clear-cut was it" in body, "ranking shown")
    chk("all four checks passed" in body, "four-check chain verified")
    chk("bits" in body and "ledger record" in body, "detection stats shown")
    pg.screenshot(path=str(OUT / "tw-act5-verdict.png"), full_page=True)

    print("\nJudge uploads their own file")
    pg.set_input_files("input[type=file]", "demo-docs/tender-evaluation.pdf")
    pg.wait_for_selector("text=No mark in this document", timeout=200000)
    pg.wait_for_timeout(500)
    body = pg.inner_text("body")
    chk("names nobody rather than guessing" in body,
        "negative result explained, not shown as an error")
    chk("NO WATERMARK" in body, "outcome labelled honestly")
    pg.screenshot(path=str(OUT / "tw-act5-nomark.png"), full_page=True)

    real = [e for e in errs if "favicon" not in e.lower()]
    chk(not real, f"no console errors ({len(real)})")
    if real: print("   ", real[:2])
    b.close()

print("\n" + ("ALL PASS" if not FAIL else f"{len(FAIL)} FAILED"))
sys.exit(1 if FAIL else 0)
