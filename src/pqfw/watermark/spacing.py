"""Differential inter-word spacing watermark.

PS requirements A1/A3: an invisible forensic mark, visually identical across
recipients but forensically distinct.

VALIDATED IN PHASE 0 -- see docs/PHASE0-RESULTS.md.
  capacity      275 bits/page (justified 10.5pt body text)
  recovery      100% clean, 0 false positives over 26,400 slots
  survives      re-save, incremental save, optimise, recompress  (4/4)
  destroyed by  rasterisation, plain-text extraction             (0/3, scoped out)

WHY DIFFERENTIAL, NOT ABSOLUTE
------------------------------
Measured natural inter-word gaps in justified text: mean 4.159pt, std 0.774pt.
Encoding a bit in an ABSOLUTE gap width at a perceptually safe depth (~0.3pt)
is unrecoverable -- justification noise is 2.6x the signal. This was measured,
not assumed, and it killed the original design.

Instead each bit uses a PAIR of adjacent gaps on the same line:
    bit 1 -> g1 += d, g2 -= d        bit 0 -> g1 -= d, g2 += d
    decode: bit = sign(g1 - g2)
Justification stretch is common-mode across a line and cancels in the
difference. Because +d and -d sum to zero the line width is preserved exactly,
so nothing reflows and the page is visually identical. Measured separation:
0.704pt on marked slots vs ~0.000pt on unmarked ones.
"""

from __future__ import annotations
from collections import defaultdict
import pymupdf

# Modulation depth in points. 0.35pt at 10.5pt type is ~3% of a space width:
# below the perceptual threshold, above the measurement noise floor after the
# differential cancels common-mode justification stretch.
DELTA = 0.35
MIN_WORDS_PER_LINE = 5      # need >=4 gaps to host 2 bits with margin
# Baseline quantisation for line grouping. Must be smaller than the tightest
# realistic line spacing (~10pt at 9pt type) and larger than intra-line bbox
# jitter (~0.5pt). 3pt sits comfortably between.
LINE_TOL = 3.0
FONT = "helv"               # base-14; matches reportlab Helvetica


def _lines_of(page) -> list[list[tuple]]:
    """Group a page's words into lines by BASELINE, left-to-right.

    Grouping by PyMuPDF's (block, line) indices looks natural but is wrong here:
    those indices are assigned by the text extractor, and rewriting a page can
    change how it groups the same words. Measured on a Courier document, one
    page reported 46 lines before marking and 34 after -- identical words,
    different grouping -- so the decoder read bits at positions the encoder
    never wrote, and attribution failed.

    The baseline y-coordinate is a geometric property of the page, not an
    artefact of extraction, so it survives the rewrite. Words are bucketed to a
    tolerance because glyphs on one line differ slightly in reported bbox.
    """
    words = page.get_text("words")
    if not words:
        return []

    buckets: dict[int, list] = defaultdict(list)
    for w in words:
        # quantise the bbox bottom; LINE_TOL is well below any line spacing
        buckets[round(w[3] / LINE_TOL)].append(w)

    out = []
    for key in sorted(buckets):                 # top-to-bottom
        ws = sorted(buckets[key], key=lambda w: w[0])   # left-to-right
        if len(ws) >= MIN_WORDS_PER_LINE:
            out.append(ws)
    return out


def capacity(doc: pymupdf.Document) -> int:
    """Bits this document can carry."""
    total = 0
    for page in doc:
        for ws in _lines_of(page):
            total += (len(ws) - 1) // 2   # one bit per gap-pair
    return total


def embed(in_path: str, out_path: str, bits: list[int]) -> int:
    """Embed bits. Returns how many were actually written."""
    doc = pymupdf.open(in_path)
    written = 0
    bit_iter = iter(bits)

    for page in doc:
        lines = _lines_of(page)
        if not lines:
            continue

        # Collect per-line rewrite instructions first.
        jobs = []
        for ws in lines:
            gaps = [ws[i + 1][0] - ws[i][2] for i in range(len(ws) - 1)]
            deltas = [0.0] * len(gaps)
            used = False
            exhausted = False
            for p in range(len(gaps) // 2):
                try:
                    bit = next(bit_iter)
                except StopIteration:
                    exhausted = True
                    break
                g1, g2 = 2 * p, 2 * p + 1
                d = DELTA if bit else -DELTA
                deltas[g1] += d
                deltas[g2] -= d
                used = True
                written += 1
            if used:
                jobs.append((ws, gaps, deltas))
            if exhausted:
                break

        if not jobs:
            continue

        # Redact original text, then re-lay it out at modulated positions.
        tw = pymupdf.TextWriter(page.rect)
        size = None
        for ws, gaps, deltas in jobs:
            # infer font size from the line's height
            y_base = max(w[3] for w in ws)
            if size is None:
                size = round(ws[0][3] - ws[0][1], 1)
            x = ws[0][0]
            fs = _fontsize_for(page, ws)
            base = _baseline(y_base, fs)
            tw.append((x, base), ws[0][4],
                      fontsize=fs, font=_FONT_CACHE)
            for i in range(1, len(ws)):
                x = x + _wordwidth(ws[i - 1][4], fs) + gaps[i - 1] + deltas[i - 1]
                tw.append((x, base), ws[i][4],
                          fontsize=fs, font=_FONT_CACHE)
            # erase the original line
            r = pymupdf.Rect(min(w[0] for w in ws) - 1, min(w[1] for w in ws) - 0.5,
                             max(w[2] for w in ws) + 40, max(w[3] for w in ws) + 0.5)
            page.add_redact_annot(r)
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE)
        tw.write_text(page)

    doc.save(out_path, garbage=3, deflate=True)
    doc.close()
    return written


_FONT_CACHE = pymupdf.Font(FONT)


def _wordwidth(text: str, fs: float) -> float:
    return _FONT_CACHE.text_length(text, fontsize=fs)


def _baseline(bbox_bottom: float, fs: float) -> float:
    """Convert a word's bounding-box bottom to its typographic baseline.

    get_text("words") reports the glyph bbox, whose bottom sits DESCENDER below
    the baseline. TextWriter.append() positions by baseline. Ignoring the
    difference shifts every rewritten line downward -- measured at 3.2pt, which
    is plainly visible and would break the "visually identical" requirement.
    """
    return bbox_bottom + _FONT_CACHE.descender * fs


def _fontsize_for(page, ws) -> float:
    """Recover font size from measured word width vs nominal glyph width."""
    w = ws[0]
    nominal = _FONT_CACHE.text_length(w[4], fontsize=100.0)
    if nominal <= 0:
        return 10.5
    return round((w[2] - w[0]) / nominal * 100.0, 2)


# A carried bit produces |g1-g2| ~= 2*DELTA. An unmarked slot in justified text
# produces ~0. Half of 2*DELTA separates the two populations with wide margin.
CONFIDENCE_FLOOR = DELTA


def extract(path: str, nbits: int | None = None,
            with_confidence: bool = False):
    """Recover bits from gap-pair differences.

    Slots whose |difference| falls below CONFIDENCE_FLOOR carry no watermark
    (unmarked text, or a region destroyed by an attack). They are reported as
    erasures (None) rather than guessed, so the accusation stage can weight
    them correctly instead of being poisoned by coin-flips.
    """
    doc = pymupdf.open(path)
    bits: list[int | None] = []
    confs: list[float] = []
    for page in doc:
        for ws in _lines_of(page):  # noqa: B007 - see extract_per_page
            gaps = [ws[i + 1][0] - ws[i][2] for i in range(len(ws) - 1)]
            for p in range(len(gaps) // 2):
                if nbits is not None and len(bits) >= nbits:
                    doc.close()
                    return (bits, confs) if with_confidence else bits
                diff = gaps[2 * p] - gaps[2 * p + 1]
                if abs(diff) < CONFIDENCE_FLOOR:
                    bits.append(None)
                else:
                    bits.append(1 if diff > 0 else 0)
                confs.append(abs(diff))
    doc.close()
    return (bits, confs) if with_confidence else bits


def extract_per_page(path: str) -> list[list[int | None]]:
    """Extract bits page by page, keeping each page's slots separate.

    `extract()` reads the whole document as one bit stream in page order. That
    is correct only when the investigator holds the complete, unmodified file.
    Real leaks are often excerpts or reordered copies, and a missing or moved
    page shifts every subsequent bit, destroying alignment.

    Measured on the red-team harness: leaking one page, or reversing page
    order, defeated attribution entirely even though the marks were intact.

    Returning per-page slot lists lets the caller realign (see
    engine.identify_robust), because each page's bits still sit at a fixed
    offset within the original codeword -- the offset is simply unknown.
    """
    doc = pymupdf.open(path)
    pages: list[list[int | None]] = []
    try:
        for page in doc:
            slots: list[int | None] = []
            for ws in _lines_of(page):
                gaps = [ws[i + 1][0] - ws[i][2] for i in range(len(ws) - 1)]
                for p in range(len(gaps) // 2):
                    diff = gaps[2 * p] - gaps[2 * p + 1]
                    slots.append(None if abs(diff) < CONFIDENCE_FLOOR
                                 else (1 if diff > 0 else 0))
            pages.append(slots)
    finally:
        doc.close()
    return pages
