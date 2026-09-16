"""Full end-to-end verification, per the redesign brief's section 8.

Broader than the per-act suites: two recipients twice, byte-diff evidence,
cross-act consistency of the SAME signature, tamper in both directions, the
attribution loop closed for both recipients, negative and edge cases, and an
offline check.

This is a verification run. A failure is reported, not worked around.
"""
from __future__ import annotations

import hashlib
import io
import json
import pathlib
import sys
import urllib.error
import urllib.request

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

API = "http://127.0.0.1:8000"
UI = "http://127.0.0.1:5174"
ROOT = pathlib.Path(__file__).parent.parent
DEMO = ROOT / "demo"
OUT = ROOT / "spike" / "out"
OUT.mkdir(parents=True, exist_ok=True)

RESULTS: list[tuple[bool, str, str]] = []


def chk(ok: bool, what: str, extra: str = "") -> bool:
    RESULTS.append((bool(ok), what, extra))
    print(("  [PASS] " if ok else "  [FAIL] ") + what + (f"  {extra}" if extra else ""))
    return bool(ok)


def head(t: str) -> None:
    print(f"\n\033[1m{t}\033[0m" if sys.stdout.isatty() else f"\n{t}")


def post(path: str, body: dict, timeout: int = 240) -> dict:
    req = urllib.request.Request(
        API + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def get(path: str, timeout: int = 60) -> dict:
    return json.loads(urllib.request.urlopen(API + path, timeout=timeout).read())


def upload(path: str, file: pathlib.Path, timeout: int = 240) -> dict:
    boundary = "----tw" + hashlib.md5(file.name.encode()).hexdigest()[:12]
    body = io.BytesIO()
    body.write(f"--{boundary}\r\n".encode())
    body.write(
        f'Content-Disposition: form-data; name="file"; filename="{file.name}"\r\n'
        f"Content-Type: application/pdf\r\n\r\n".encode())
    body.write(file.read_bytes())
    body.write(f"\r\n--{boundary}--\r\n".encode())
    req = urllib.request.Request(
        API + path, data=body.getvalue(),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def main() -> int:
    # ---------------------------------------------------------------- 1
    head("1 · Two recipients, full happy path, run twice")

    bundles = get("/api/bundles")
    if not bundles:
        print("  no bundle on disk — run demo_reset.py first")
        return 1
    bundle = bundles[0]["name"]

    runs: list[dict[str, dict]] = []
    for pass_no in (1, 2):
        this: dict[str, dict] = {}
        for who in ("alice", "erin"):
            r = post("/api/decrypt", {"bundle": bundle, "identity": who})
            this[who] = r
        runs.append(this)
        chk(all(v["bits"] > 0 for v in this.values()),
            f"pass {pass_no}: both recipients decrypted",
            f"{this['alice']['bits']} bits each")

    # Session uniqueness across passes -- same person, different mark.
    chk(runs[0]["alice"]["session_id"] != runs[1]["alice"]["session_id"],
        "same recipient opening twice gets a different session")
    chk(runs[0]["alice"]["record"]["watermark_commitment"]
        != runs[1]["alice"]["record"]["watermark_commitment"],
        "…and a different watermark commitment")

    # ---------------------------------------------------------------- 2
    head("2 · Forensically distinct, visually identical")

    cmp_ = post("/api/compare",
                {"a": "alice-copy.pdf", "b": "erin-copy.pdf"})
    chk(not cmp_["byte_identical"], "the two files are not byte-identical",
        f"{cmp_['differing_byte_positions']:,} positions differ")
    chk(cmp_["same_words"], "every word is identical",
        f"{cmp_['word_count']} words")
    chk(cmp_["max_baseline_shift_pt"] == 0,
        "no line moved", f"{cmp_['max_baseline_shift_pt']} pt")
    chk((cmp_["ink_delta"] or 1) < 1e-3, "ink on the page is conserved",
        f"{cmp_['ink_delta']:.2e}")

    # Independent check: the difference must be in the text-positioning
    # operators, not incidental file noise.
    import pymupdf
    a_words = pymupdf.open(DEMO / "alice-copy.pdf")[0].get_text("words")
    e_words = pymupdf.open(DEMO / "erin-copy.pdf")[0].get_text("words")
    gaps_a = [a_words[i + 1][0] - a_words[i][2] for i in range(len(a_words) - 1)]
    gaps_e = [e_words[i + 1][0] - e_words[i][2] for i in range(len(e_words) - 1)]
    differing_gaps = sum(1 for x, y in zip(gaps_a, gaps_e) if abs(x - y) > 0.01)
    chk(differing_gaps > 0,
        "the difference lies in inter-word spacing, as claimed",
        f"{differing_gaps} of {len(gaps_a)} gaps differ")

    # ---------------------------------------------------------------- 3
    head("3 · Attribution loop closed for BOTH recipients")

    got: dict[str, dict] = {}
    for who in ("alice", "erin"):
        v = post("/api/attribute-path", {"path": f"{who}-copy.pdf"})
        got[who] = v
        chk(v["outcome"] == "IDENTIFIED" and v["recipient"]["user_id"] == who,
            f"{who}'s copy names {who}",
            f"margin {v['detection']['margin']:.2f}, "
            f"{v['detection']['bits_recovered']}/{v['detection']['bits_expected']} bits")
        chk(v["evidence"]["cryptographically_verified"],
            f"…with all four evidence checks passing")

    chk(got["alice"]["recipient"]["user_id"] != got["erin"]["recipient"]["user_id"],
        "the two answers are distinct (not a constant)")
    chk(got["alice"]["event"]["ledger_index"] != got["erin"]["event"]["ledger_index"],
        "…and point at different ledger records")

    # ---------------------------------------------------------------- 4
    head("4 · Cross-act consistency: the SAME signature")

    idx = got["alice"]["event"]["ledger_index"]
    ev = get(f"/api/event/{idx}")
    chk(ev["record"]["recipient_user_id"] == "alice",
        "Act 2's record and Act 5's verdict refer to the same event")
    chk(ev["record"]["session_id"] == got["alice"]["event"]["session_id"],
        "session id matches across both layers")
    chk(ev["inclusion_proof"]["root"] == got["alice"]["inclusion_proof"]["root"],
        "ledger root matches across both layers")

    ver = post("/api/verify-signature", {"index": idx})
    chk(ver["all_passed"], "that signature verifies live, re-checked now")
    control = next(c for c in ver["checks"] if c["id"] == "control")
    chk(control["passed"],
        "negative control holds: a one-bit change breaks the signature")

    # ---------------------------------------------------------------- 5
    head("5 · Ledger integrity, both directions")

    chk(not get("/api/ledger/verify")["tampered"], "clean ledger verifies")

    t = post("/api/ledger/tamper", {"index": 1, "new_user_id": "someone_else"})
    chk(t["detected"], "tampering is detected")
    chk(t["detected_at"] == t["edited_index"],
        "…and the reported record matches the one edited",
        f"#{t['detected_at']}")
    chk("no longer matches the hash" in t["message"],
        "…with an accurate reason, not a generic message")

    v_t = post("/api/attribute-path", {"path": "alice-copy.pdf"})
    chk(v_t["outcome"] == "LEDGER_COMPROMISED"
        and v_t["recipient"]["user_id"] is None,
        "attribution is withheld while the ledger is unreliable")

    r = post("/api/ledger/restore", {})
    chk(r["restored"], "the ledger can be repaired for a continued demo")
    chk(not get("/api/ledger/verify")["tampered"], "…and verifies again")

    # ---------------------------------------------------------------- 6
    head("6 · Negative and edge cases")

    v = upload("/api/attribute", ROOT / "demo-docs" / "tender-evaluation.pdf")
    chk(v["outcome"] == "NO_WATERMARK" and v["recipient"]["user_id"] is None,
        "an undistributed original names nobody", v["outcome"])
    chk(not any("COLLUSION" in n for n in v["notes"]),
        "…and is not misreported as collusion")

    # Robustness to the stated bar: re-saving must NOT break attribution;
    # rasterising is documented as destroying the mark.
    resaved = OUT / "resaved.pdf"
    d = pymupdf.open(DEMO / "alice-copy.pdf")
    d.save(resaved, garbage=4, deflate=True, clean=True)
    d.close()
    v = upload("/api/attribute", resaved)
    chk(v["recipient"]["user_id"] == "alice",
        "survives a full re-save/optimise, as documented")

    rast = OUT / "rasterised.pdf"
    d = pymupdf.open(DEMO / "alice-copy.pdf")
    nd = pymupdf.open()
    for i in range(min(3, d.page_count)):
        pix = d[i].get_pixmap(dpi=120)
        pg = nd.new_page(width=pix.width * 0.75, height=pix.height * 0.75)
        pg.insert_image(pg.rect, pixmap=pix)
    nd.save(rast)
    d.close()
    nd.close()
    v = upload("/api/attribute", rast)
    chk(v["recipient"]["user_id"] is None,
        "a rasterised copy names nobody rather than guessing wrong",
        v["outcome"])

    # A judge's arbitrary PDF -- built here so it is genuinely not ours.
    foreign = OUT / "foreign.pdf"
    fd = pymupdf.open()
    p = fd.new_page()
    p.insert_text((72, 100), "An unrelated document from somewhere else.",
                  fontsize=12)
    fd.save(foreign)
    fd.close()
    v = upload("/api/attribute", foreign)
    chk(v["recipient"]["user_id"] is None,
        "an unrelated PDF names nobody", v["outcome"])

    try:
        post("/api/attribute-path", {"path": "does-not-exist.pdf"})
        chk(False, "a missing file is refused cleanly")
    except urllib.error.HTTPError as e:
        detail = json.loads(e.read()).get("detail", "")
        chk(e.code == 404, "a missing file is refused cleanly", f"HTTP {e.code}")
        chk("\\" not in detail and "/" not in detail.replace("no longer", ""),
            "…without leaking a filesystem path", repr(detail))

    # ---------------------------------------------------------------- 7
    head("7 · Offline operation")

    src = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
    chk("googleapis" not in src and "cdn." not in src,
        "the page loads no font or script from a CDN")

    remote = []
    for f in (ROOT / "ui" / "src").rglob("*"):
        if f.is_file() and f.suffix in (".ts", ".tsx", ".css", ".html"):
            txt = f.read_text(encoding="utf-8")
            for token in ("https://fonts.", "cdn.jsdelivr", "unpkg.com",
                          "cdnjs.cloudflare"):
                if token in txt:
                    remote.append(f"{f.name}:{token}")
    chk(not remote, "no remote asset referenced anywhere in the UI source",
        str(remote))

    return 0


if __name__ == "__main__":
    rc = main()
    bad = [r for r in RESULTS if not r[0]]
    print("\n" + "=" * 64)
    if bad:
        print(f"{len(bad)} of {len(RESULTS)} checks FAILED")
        for _, w, x in bad:
            print(f"   - {w}  {x}")
        sys.exit(1)
    print(f"all {len(RESULTS)} checks passed")
    sys.exit(rc)
