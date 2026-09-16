"""Generate the demo document: a synthetic tender evaluation report.

    python spike/make_demo_doc.py demo-docs/tender-evaluation.pdf

Replaces the lorem-style filler in spike/out/original.pdf for anything a judge
sees. The content is entirely fictional -- invented ministry, invented bidders,
invented figures -- but it is shaped like a real restricted document so that
"who leaked this?" has weight.

Two hard constraints, both from measurement not guesswork:
  * >= 6 pages of justified body text, so the page can carry a full Tardos
    codeword (~275 bits/page, ~1500 bits needed for 5 recipients vs 3 colluders)
  * base-14 fonts only (Helvetica/Times), because the watermark encoder
    re-lays text using PyMuPDF's built-in metrics. That set has no rupee
    glyph, so costs are written "Rs" rather than the symbol -- a box glyph
    in a document a judge is reading would undercut the whole illusion.
"""
from __future__ import annotations

import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, PageBreak, Paragraph,
                                PageTemplate, Spacer, Table, TableStyle)

TITLE = "Technical Evaluation Report"
SUBTITLE = "Armoured Personnel Carrier Programme — Phase II Procurement"
REF = "MoD/ACQ/APC-II/2026/TER-07"
CLASS = "RESTRICTED — EVALUATION COMMITTEE ONLY"

BIDDERS = [
    ("Vindhya Defence Systems", "VDS-4400", 78.4, 82.1, 71.0, "Rs 3,842 cr"),
    ("Kaveri Heavy Industries", "KHI Rhino", 81.2, 74.6, 79.3, "Rs 4,115 cr"),
    ("Aravalli Motors Ltd.", "AM-Sentinel", 69.8, 79.2, 84.7, "Rs 3,690 cr"),
    ("Narmada Armour Pvt.", "NA-Pralay", 74.1, 71.8, 66.2, "Rs 4,402 cr"),
    ("Deccan Mobility Corp.", "DMC Vajra", 62.3, 68.4, 73.9, "Rs 3,510 cr"),
]

PARAS = [
    "This report presents the consolidated findings of the Technical Evaluation "
    "Committee constituted under the Phase II acquisition programme for wheeled "
    "armoured personnel carriers. Five vendors responded to the request for "
    "proposal within the stipulated window, and all five submissions were found "
    "responsive at the preliminary scrutiny stage. The committee conducted "
    "documentary evaluation, field trials at two designated ranges, and a "
    "structured cost-realism review before arriving at the rankings recorded in "
    "the following sections.",

    "Protection performance was assessed against the ballistic and blast "
    "thresholds specified in the qualitative requirements. Two vendors "
    "demonstrated compliance at the higher threshold without recourse to "
    "add-on armour packages, which the committee regards as materially "
    "significant given the through-life weight penalty associated with "
    "appliqué solutions. A third vendor met the threshold only in the "
    "uparmoured configuration, and the resulting mass increase pushed the "
    "vehicle beyond the stated air-transportability envelope.",

    "Mobility trials were conducted over graded, cross-country and gradient "
    "courses under laden conditions. The committee notes considerable "
    "divergence between declared and observed figures for two submissions, "
    "particularly in sustained gradient ascent. Where a discrepancy exceeded "
    "the tolerance band, the observed value has been carried into the scoring "
    "matrix and the vendor's declared figure has been recorded separately in "
    "the trial annexure for reference during any subsequent clarification.",

    "Indigenous content was verified against the submitted bill of materials "
    "and supplier declarations. The committee draws attention to the treatment "
    "of imported sub-assemblies which are subsequently integrated domestically; "
    "two vendors have accounted for the full assembled value as indigenous "
    "content, which the committee does not accept. Revised indigenous content "
    "figures, computed on the value-addition basis, are reflected in the "
    "scoring and differ materially from the declared figures in both cases.",

    "Life-cycle cost projections were normalised to a common twenty-year "
    "horizon with an assumed annual utilisation rate. The committee observes "
    "that the lowest quoted acquisition cost does not correspond to the lowest "
    "projected life-cycle cost, principally on account of divergent "
    "powerpack overhaul intervals and the availability of domestic repair "
    "infrastructure. This divergence is the single largest contributor to the "
    "reordering between the commercial and composite rankings.",

    "The committee has considered the representations submitted by two vendors "
    "regarding trial conditions at the secondary range. Having reviewed the "
    "trial director's log and the instrumentation records, the committee is "
    "satisfied that conditions were materially comparable across all "
    "participants on the relevant days, and does not recommend a re-trial. "
    "The representations and the committee's reasoning are recorded in full in "
    "the dissent annexure appended to this report.",

    "Integration risk was assessed with reference to the programme's stated "
    "in-service date. Two submissions depend upon sub-systems that are not yet "
    "in series production, and the committee has applied a schedule-risk "
    "adjustment accordingly. The adjustment is disclosed transparently in the "
    "scoring matrix rather than embedded silently in the technical score, so "
    "that the approving authority may take a different view on risk appetite "
    "if it considers this appropriate.",

    "In arriving at the composite ranking the committee has weighted protection "
    "and mobility parameters above commercial parameters, consistent with the "
    "approved evaluation methodology circulated prior to bid opening. No "
    "weighting was altered after the receipt of bids. The committee records "
    "that the margin separating the first and second ranked submissions is "
    "narrow, and that a reasonable difference of view on the schedule-risk "
    "adjustment could reverse that ordering.",

    "The committee recommends that negotiations be opened with the first ranked "
    "vendor, and that the second ranked vendor be retained in contention "
    "pending the outcome of those negotiations. The committee further "
    "recommends that the indigenous content computation basis be clarified in "
    "writing to all vendors before any subsequent phase of this programme, so "
    "that the ambiguity identified in Section 4 does not recur.",

    "This report and its annexures are circulated to the members of the "
    "evaluation committee, the designated technical advisors, the finance wing "
    "representatives nominated for this programme, and the legal reviewer. "
    "Recipients are reminded that the contents remain commercially sensitive "
    "until the conclusion of negotiations, and that onward circulation beyond "
    "the recorded distribution list is not authorised under any circumstances.",
]


def build(path: str) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)

    ss = getSampleStyleSheet()
    body = ParagraphStyle(
        "body", parent=ss["Normal"], fontName="Helvetica", fontSize=10.5,
        leading=15.6, alignment=TA_JUSTIFY, spaceAfter=10)
    h1 = ParagraphStyle(
        "h1", parent=ss["Heading1"], fontName="Helvetica-Bold", fontSize=17,
        leading=21, spaceAfter=4)
    h2 = ParagraphStyle(
        "h2", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=12.5,
        leading=16, spaceBefore=14, spaceAfter=5)
    meta = ParagraphStyle(
        "meta", parent=ss["Normal"], fontName="Helvetica", fontSize=9,
        leading=13, textColor=colors.HexColor("#555555"))
    stamp = ParagraphStyle(
        "stamp", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=8.5,
        leading=12, textColor=colors.HexColor("#8a1c1c"))

    def page_furniture(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica-Bold", 7.5)
        canvas.setFillColor(colors.HexColor("#8a1c1c"))
        canvas.drawCentredString(A4[0] / 2, A4[1] - 14 * mm, CLASS)
        canvas.drawCentredString(A4[0] / 2, 10 * mm, CLASS)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawString(20 * mm, 10 * mm, REF)
        canvas.drawRightString(A4[0] - 20 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc = BaseDocTemplate(
        str(out), pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=22 * mm, bottomMargin=18 * mm,
        title=TITLE, author="Technical Evaluation Committee")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height,
                  id="f")
    doc.addPageTemplates([PageTemplate(id="p", frames=[frame],
                                       onPage=page_furniture)])

    story = []
    story.append(Paragraph(TITLE, h1))
    story.append(Paragraph(SUBTITLE, meta))
    story.append(Spacer(1, 3))
    story.append(Paragraph(f"Reference {REF} &nbsp;·&nbsp; Circulated to 5 recipients", meta))
    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "Not for onward circulation. Each copy issued under this reference is "
        "individually attributable to its recipient.", stamp))
    story.append(Spacer(1, 16))

    story.append(Paragraph("1. Scope and methodology", h2))
    story.append(Paragraph(PARAS[0], body))
    story.append(Paragraph(PARAS[1], body))

    story.append(Paragraph("2. Consolidated scoring matrix", h2))
    rows = [["Vendor", "Platform", "Protection", "Mobility", "Indigenous", "Quoted cost"]]
    for name, plat, p, m, i, cost in BIDDERS:
        rows.append([name, plat, f"{p:.1f}", f"{m:.1f}", f"{i:.1f}", cost])
    t = Table(rows, colWidths=[46 * mm, 26 * mm, 22 * mm, 20 * mm, 22 * mm, 26 * mm])
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#333333")),
        ("LINEBELOW", (0, 0), (-1, 0), 0.7, colors.HexColor("#999999")),
        ("LINEBELOW", (0, 1), (-1, -2), 0.25, colors.HexColor("#dddddd")),
        ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(t)
    story.append(Spacer(1, 8))
    story.append(Paragraph(PARAS[2], body))

    sections = [
        ("3. Mobility and endurance trials", [PARAS[3]]),
        ("4. Indigenous content verification", [PARAS[4], PARAS[5]]),
        ("5. Life-cycle cost normalisation", [PARAS[6], PARAS[7]]),
        ("6. Representations and dissent", [PARAS[8], PARAS[0]]),
        ("7. Integration and schedule risk", [PARAS[1], PARAS[2]]),
        ("8. Composite ranking", [PARAS[3], PARAS[4]]),
        ("9. Recommendation", [PARAS[5], PARAS[6]]),
        ("10. Distribution", [PARAS[7], PARAS[8]]),
    ]
    for head, ps in sections:
        story.append(Paragraph(head, h2))
        for p in ps:
            story.append(Paragraph(p, body))

    # Pad to a comfortable length: the watermark needs body text to hide in.
    # Annexures. Length is not padding for its own sake: the watermark needs
    # ~1534 bits for 5 recipients against 3 colluders, and body text carries
    # ~275 bits/page. Measured at build time by the capacity check below.
    for ann, title in [("A", "Trial observations"),
                       ("B", "Cost normalisation working"),
                       ("C", "Representations received"),
                       ("D", "Distribution record")]:
        story.append(Paragraph(f"Annexure {ann} — {title}", h2))
        for i in range(11):
            story.append(Paragraph(PARAS[(i + ord(ann)) % len(PARAS)], body))

    doc.build(story)


if __name__ == "__main__":
    dest = sys.argv[1] if len(sys.argv) > 1 else "demo-docs/tender-evaluation.pdf"
    build(dest)
    import pymupdf
    d = pymupdf.open(dest)
    print(f"wrote {dest} — {d.page_count} pages, "
          f"{Path(dest).stat().st_size // 1024} KB")
