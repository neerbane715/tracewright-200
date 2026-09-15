"""Red-team harness: try to break attribution.

    python redteam.py

Written to FAIL, not to pass. Everything here is a document or an attack the
system was not tuned against:

  - fonts and layouts other than the one demo document
  - documents a leaker would realistically produce
  - deliberate attempts to strip, forge or confuse the watermark

An honest result is more useful than a green screen. Attacks that succeed are
reported as EXPECTED where they match a documented limitation, and as
**UNEXPECTED** where they do not -- the second kind is what needs fixing.

Hand this to someone who did not write the system and let them add cases.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pymupdf
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

ROOT = Path(__file__).parent
WORK = ROOT / "redteam-out"

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

RESULTS: list[tuple[str, str, str]] = []


def report(name: str, verdict: str, note: str = "") -> None:
    RESULTS.append((name, verdict, note))
    print(f"  [{verdict:10}] {name}" + (f"  {note}" if note else ""))


TEXT = (
    "Operational readiness across the northern sector remains contingent on "
    "sustained logistical throughput and the timely rotation of forward units. "
    "Assessments compiled during the preceding quarter indicate that resupply "
    "intervals have lengthened materially, and that contingency stocks held at "
    "regional depots would not sustain current posture beyond a limited window. "
    "Commanders are directed to review local holdings and report shortfalls "
    "through the established channel without delay. "
)


def make_doc(path: Path, font: str, size: float, justify: bool,
             pages: int, page_size, leading: float) -> None:
    """Build a document deliberately unlike the one the system was tuned on."""
    doc = SimpleDocTemplate(str(path), pagesize=page_size,
                            leftMargin=50, rightMargin=50,
                            topMargin=60, bottomMargin=60)
    st = ParagraphStyle(
        "b", parent=getSampleStyleSheet()["Normal"],
        fontName=font, fontSize=size, leading=leading,
        alignment=TA_JUSTIFY if justify else TA_LEFT, spaceAfter=8)
    story = []
    for _ in range(pages * 5):
        story.append(Paragraph(TEXT * 2, st))
        story.append(Spacer(1, 3))
    doc.build(story)


def main() -> int:
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)

    from pqfw import pipeline
    from pqfw.forensics.investigate import Outcome, investigate
    from pqfw.identity import Keystore
    from pqfw.ledger.node import LedgerNode
    from pqfw.watermark import engine

    ks = Keystore(WORK / "keys")
    users = ["nadia", "omar", "priya", "quentin"]
    idents = [ks.create(u) for u in users]
    led = LedgerNode(WORK / "ledger.db")

    # ------------------------------------------------ unfamiliar documents
    print("\n\033[1m1 | Documents the system was never tuned on\033[0m")

    variants = [
        ("times 11pt justified A4",  "Times-Roman", 11.0, True,  14, A4,     16.0),
        ("courier 10pt justified",   "Courier",     10.0, True,  14, A4,     14.5),
        ("helvetica LEFT-ALIGNED",   "Helvetica",   10.5, False, 14, A4,     15.0),
        ("times 9pt dense LETTER",   "Times-Roman",  9.0, True,  16, LETTER, 12.0),
        ("helvetica 14pt sparse",    "Helvetica",   14.0, True,  20, A4,     20.0),
    ]

    for label, font, size, just, pages, ps, lead in variants:
        src = WORK / f"doc-{label.split()[0]}-{int(size)}-{just}.pdf"
        make_doc(src, font, size, just, pages, ps, lead)
        try:
            cap = engine.capacity(str(src))
        except Exception as e:
            report(label, "ERROR", f"capacity failed: {type(e).__name__}")
            continue

        bundle = src.with_suffix(".pqfw")
        pipeline.encrypt(src, idents, bundle)
        try:
            r = pipeline.decrypt(bundle, "omar", ks, led,
                                 WORK / f"{src.stem}-omar.pdf")
        except engine.CapacityError:
            report(label, "REFUSED",
                   f"capacity {cap} bits too low -- refused, not half-marked")
            continue
        except Exception as e:
            report(label, "ERROR", f"{type(e).__name__}: {e}")
            continue

        v = investigate(r.output_path, led)
        if v.recipient_user_id == "omar" and v.cryptographically_verified:
            report(label, "ATTRIBUTED",
                   f"cap {cap}, {v.bits_recovered}/{v.bits_expected} bits, "
                   f"margin {v.margin:.2f}")
        else:
            report(label, "**MISSED**",
                   f"got {v.outcome.value} / {v.recipient_user_id}")

    # ------------------------------------------------------- real attacks
    print("\n\033[1m2 | Attacks a leaker would actually try\033[0m")

    src = WORK / "target.pdf"
    make_doc(src, "Helvetica", 10.5, True, 16, A4, 15.0)
    bundle = WORK / "target.pqfw"
    pipeline.encrypt(src, idents, bundle)
    victim = pipeline.decrypt(bundle, "priya", ks, led, WORK / "priya.pdf")
    marked = victim.output_path

    def probe(label: str, path: Path, expect_fail: bool = False) -> None:
        try:
            v = investigate(path, led)
        except Exception as e:
            report(label, "ERROR", f"{type(e).__name__}: {e}")
            return
        hit = (v.recipient_user_id == "priya" and v.cryptographically_verified)
        if hit:
            report(label, "ATTRIBUTED",
                   f"{v.bits_recovered}/{v.bits_expected} bits, "
                   f"margin {v.margin:.2f}")
        elif expect_fail:
            report(label, "EXPECTED", f"{v.outcome.value} -- documented limit")
        else:
            report(label, "**MISSED**",
                   f"{v.outcome.value} / {v.recipient_user_id}")

    # a. strip metadata and re-save
    p = WORK / "atk-stripped.pdf"
    d = pymupdf.open(marked)
    d.set_metadata({})
    d.save(p, garbage=4, clean=True, deflate=True)
    d.close()
    probe("strip metadata + full rewrite", p)

    # b. delete half the pages -- a leaker sharing an excerpt
    p = WORK / "atk-excerpt.pdf"
    d = pymupdf.open(marked)
    d.delete_pages(range(d.page_count // 2, d.page_count))
    d.save(p)
    d.close()
    probe("leak only the first half", p)

    # c. a single page
    p = WORK / "atk-onepage.pdf"
    d = pymupdf.open(marked)
    nd = pymupdf.open()
    nd.insert_pdf(d, from_page=3, to_page=3)
    nd.save(p)
    d.close()
    nd.close()
    probe("leak one page only", p)

    # d. reorder pages
    p = WORK / "atk-shuffled.pdf"
    d = pymupdf.open(marked)
    order = list(range(d.page_count))[::-1]
    d.select(order)
    d.save(p)
    d.close()
    probe("reverse page order", p)

    # e. add an annotation / highlight, as a reader would
    p = WORK / "atk-annotated.pdf"
    d = pymupdf.open(marked)
    pg = d[0]
    words = pg.get_text("words")[:8]
    for w in words:
        pg.add_highlight_annot(pymupdf.Rect(w[:4]))
    d.save(p)
    d.close()
    probe("highlighted by a reader", p)

    # f. rotate pages
    p = WORK / "atk-rotated.pdf"
    d = pymupdf.open(marked)
    for pg in d:
        pg.set_rotation(90)
    d.save(p)
    d.close()
    probe("rotate every page 90 degrees", p)

    # g. rasterise -- the documented limit
    p = WORK / "atk-raster.pdf"
    d = pymupdf.open(marked)
    nd = pymupdf.open()
    for i in range(min(4, d.page_count)):
        pix = d[i].get_pixmap(dpi=120)
        np_ = nd.new_page(width=pix.width * 0.75, height=pix.height * 0.75)
        np_.insert_image(np_.rect, pixmap=pix)
    nd.save(p)
    d.close()
    nd.close()
    probe("rasterise (screenshot equivalent)", p, expect_fail=True)

    # h. frame someone: take an innocent party's copy and relabel the ledger?
    #    The ledger refuses unsigned edits, so instead try the document side:
    #    feed a DIFFERENT recipient's copy and see who is named.
    other = pipeline.decrypt(bundle, "nadia", ks, led, WORK / "nadia.pdf")
    v = investigate(other.output_path, led)
    if v.recipient_user_id == "nadia":
        report("nadia's copy names nadia (not priya)", "ATTRIBUTED",
               f"margin {v.margin:.2f}")
    else:
        report("nadia's copy names nadia", "**MISSED**",
               f"named {v.recipient_user_id}")

    # i. the original, never decrypted by anyone
    v = investigate(src, led)
    if v.recipient_user_id is None:
        report("pristine original accuses nobody", "CORRECT", v.outcome.value)
    else:
        report("pristine original accuses nobody", "**FALSE ACCUSATION**",
               f"named {v.recipient_user_id}")

    # j. a completely unrelated document
    unrelated = WORK / "unrelated.pdf"
    make_doc(unrelated, "Times-Roman", 12.0, True, 6, A4, 16.0)
    v = investigate(unrelated, led)
    if v.recipient_user_id is None:
        report("unrelated document accuses nobody", "CORRECT", v.outcome.value)
    else:
        report("unrelated document accuses nobody", "**FALSE ACCUSATION**",
               f"named {v.recipient_user_id}")

    # ---------------------------------------------------------- collusion
    print("\n\033[1m3 | Collusion\033[0m")
    a = pymupdf.open(WORK / "priya.pdf")
    b = pymupdf.open(WORK / "nadia.pdf")
    out = pymupdf.open()
    for i in range(a.page_count):
        out.insert_pdf(a if i % 2 == 0 else b, from_page=i, to_page=i)
    cp = WORK / "atk-collusion.pdf"
    out.save(cp)
    out.close()
    v = investigate(cp, led)
    named = v.recipient_user_id
    if named in ("priya", "nadia"):
        report("2-way collusion names a real colluder", "ATTRIBUTED",
               f"named {named}, margin {v.margin:.2f}")
    elif named is None:
        report("2-way collusion", "INCONCLUSIVE",
               "no single suspect separated -- ranking shown to investigator")
    else:
        report("2-way collusion", "**FALSE ACCUSATION**", f"named {named}")

    # ------------------------------------------------------------- report
    print("\n" + "=" * 66)
    missed = [r for r in RESULTS if "**" in r[1]]
    expected = [r for r in RESULTS if r[1] == "EXPECTED"]
    print(f"{len(RESULTS)} probes · {len(missed)} unexpected failures · "
          f"{len(expected)} documented limits confirmed")
    if missed:
        print("\nNEEDS ATTENTION:")
        for n, v, note in missed:
            print(f"   {v}  {n}  ({note})")
        return 1
    print("\nNo unexpected failures. Documented limits behaved as documented.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
