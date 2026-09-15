"""Phase 0 spike: attack gauntlet.

Measures watermark survival under realistic document handling. The result of
this script determines whether spacing modulation can be the primary carrier.
"""
from __future__ import annotations
import os, random, subprocess, sys, shutil
import numpy as np
import pymupdf

sys.path.insert(0, os.path.dirname(__file__))
import wm_spacing as W

OUT = os.path.join(os.path.dirname(__file__), "out")
ORIG = os.path.join(OUT, "original.pdf")
WM = os.path.join(OUT, "wm.pdf")
NBITS = 512
SEED = 42


def truth() -> list[int]:
    random.seed(SEED)
    return [random.randint(0, 1) for _ in range(NBITS)]


def score(path: str, expect: list[int]) -> tuple[float, int, int]:
    """Return (accuracy over recovered bits, n_recovered, n_expected)."""
    try:
        rec = W.extract(path)
    except Exception as e:
        return (0.0, 0, len(expect))
    got = [b for b in rec if b is not None]
    if not got:
        return (0.0, 0, len(expect))
    n = min(len(got), len(expect))
    ok = sum(1 for a, b in zip(expect[:n], got[:n]) if a == b)
    return (ok / n, len(got), len(expect))


# ---------------- attacks ----------------

def atk_resave_pymupdf(src: str, dst: str) -> bool:
    d = pymupdf.open(src); d.save(dst, garbage=4, deflate=True); d.close()
    return True


def atk_resave_incremental(src: str, dst: str) -> bool:
    shutil.copy(src, dst)
    d = pymupdf.open(dst)
    d.set_metadata({"producer": "resaver"})
    d.saveIncr(); d.close()
    return True


def atk_linearize(src: str, dst: str) -> bool:
    """PyMuPDF >=1.26 removed linearisation; emulate an optimiser pass instead
    by fully rewriting every object (garbage=4 + clean + ascii-safe streams)."""
    d = pymupdf.open(src)
    d.save(dst, garbage=4, clean=True, deflate=True, deflate_images=True,
           deflate_fonts=True)
    d.close()
    return True


def atk_recompress(src: str, dst: str) -> bool:
    """Strip object streams / recompress - simulates a PDF optimiser."""
    d = pymupdf.open(src); d.save(dst, garbage=4, deflate=True,
                                  clean=True, pretty=False); d.close()
    return True


def atk_copy_paste(src: str, dst: str) -> bool:
    """Extract plain text and re-render. Destroys all geometry."""
    d = pymupdf.open(src)
    text = "\n".join(p.get_text() for p in d)
    d.close()
    nd = pymupdf.open()
    pg = nd.new_page()
    pg.insert_textbox(pymupdf.Rect(50, 50, 545, 790), text[:3000], fontsize=10)
    nd.save(dst); nd.close()
    return True


def atk_print_to_pdf(src: str, dst: str) -> bool:
    """Rasterise at print DPI then wrap back into a PDF (no text layer)."""
    d = pymupdf.open(src)
    nd = pymupdf.open()
    for i in range(min(3, d.page_count)):
        pix = d[i].get_pixmap(dpi=150)
        pg = nd.new_page(width=pix.width * 0.75, height=pix.height * 0.75)
        pg.insert_image(pg.rect, pixmap=pix)
    nd.save(dst); d.close(); nd.close()
    return True


def atk_screenshot(src: str, dst: str) -> bool:
    """Rasterise at screen DPI - the classic leak vector."""
    d = pymupdf.open(src)
    nd = pymupdf.open()
    pix = d[0].get_pixmap(dpi=96)
    pg = nd.new_page(width=pix.width * 0.75, height=pix.height * 0.75)
    pg.insert_image(pg.rect, pixmap=pix)
    nd.save(dst); d.close(); nd.close()
    return True


ATTACKS = [
    ("1. re-save (PyMuPDF)",        atk_resave_pymupdf),
    ("2. incremental save",         atk_resave_incremental),
    ("3. linearise (web optimise)", atk_linearize),
    ("4. recompress / clean",       atk_recompress),
    ("5. copy-paste text",          atk_copy_paste),
    ("6. print-to-PDF (raster)",    atk_print_to_pdf),
    ("7. screenshot (96dpi)",       atk_screenshot),
]


def main() -> None:
    if not os.path.exists(ORIG):
        sys.exit("run make_testdoc.py first")

    expect = truth()
    n = W.embed(ORIG, WM, expect)
    print(f"embedded {n} bits into {ORIG}\n")

    base_acc, base_rec, _ = score(WM, expect)
    print(f"{'attack':<30} {'bits found':>11} {'accuracy':>10}   verdict")
    print("-" * 70)
    print(f"{'0. no attack (baseline)':<30} {base_rec:>11} {base_acc*100:>9.1f}%   "
          f"{'PASS' if base_acc >= 0.9 else 'FAIL'}")

    results = []
    for name, fn in ATTACKS:
        dst = os.path.join(OUT, f"atk_{name.split('.')[0]}.pdf")
        err = None
        try:
            fn(WM, dst)
            acc, rec, exp = score(dst, expect)
        except Exception as e:
            # An attack that cannot run is NOT a defeated watermark. Surface it
            # as ERROR so a harness bug can never be misread as a result.
            acc, rec, err = 0.0, 0, f"{type(e).__name__}: {e}"
        if err:
            verdict = "ERROR"
        elif acc >= 0.9 and rec >= NBITS * 0.5:
            verdict = "PASS"
        elif acc >= 0.7 and rec > 0:
            verdict = "PARTIAL"
        else:
            verdict = "FAIL"
        results.append((name, rec, acc, verdict))
        if err:
            print(f"{name:<30} {'-':>11} {'-':>10}   ERROR  {err[:40]}")
            continue
        print(f"{name:<30} {rec:>11} {acc*100:>9.1f}%   {verdict}")

    print("-" * 70)
    passed = sum(1 for _, _, _, v in results if v == "PASS")
    print(f"\n{passed}/{len(results)} attacks survived at >=90% accuracy")


if __name__ == "__main__":
    main()
