"""Generate a SECOND demo document, for exercising the upload path.

    python spike/make_upload_doc.py demo-docs/board-inquiry.pdf

Why a second document exists
----------------------------
demo-docs/tender-evaluation.pdf is what the system ships and seals by default.
To demonstrate that the operator can supply their OWN document, the thing they
upload must be visibly a different document -- different title, different
subject, different page count -- or a viewer cannot tell whether the upload did
anything at all.

So this is a court-of-inquiry report rather than a tender evaluation. Same
constraints, deliberately different content.

The same two hard constraints apply, both from measurement:

  * >= 6 pages of justified body text. The mark needs ~1534 bits for five
    recipients against three colluders, and justified body text carries
    ~275 bits/page. The build prints the measured capacity so a shortfall is
    caught at generation time rather than during a demo.

  * base-14 fonts only (Helvetica/Times). The watermark encoder re-lays text
    using PyMuPDF's built-in metrics, so a font outside that set will not
    round-trip. That set has no rupee glyph, hence "Rs" spelled out.

Capacity comes only from lines of >= 5 words (see watermark/spacing.py:
MIN_WORDS_PER_LINE). Headings, table rows and short lines contribute nothing,
which is why this document is mostly flowing prose.
"""
from __future__ import annotations

import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, Paragraph,
                                PageTemplate, Spacer, Table, TableStyle)

TITLE = "Court of Inquiry — Findings and Recommendations"
SUBTITLE = "Loss of Communications Relay Station at Forward Post 114"
REF = "HQ/COI/FP-114/2026/FIN-03"
CLASS = "RESTRICTED — INQUIRY MEMBERS ONLY"

# Fictional throughout: invented post, invented units, invented timeline.
TIMELINE = [
    ("0412", "Relay station reports intermittent carrier loss on primary link"),
    ("0430", "Duty signaller logs fault, initiates standby changeover"),
    ("0447", "Standby link fails to establish; fault escalated to post commander"),
    ("0502", "Post commander orders runner despatch to secondary node"),
    ("0631", "Runner reports secondary node unmanned, generator shut down"),
    ("0708", "Communications restored via alternate formation net"),
]

PARAS = [
    "This court of inquiry was convened to establish the circumstances in which "
    "communications from the relay station at Forward Post 114 were lost for a "
    "period of approximately two hours and fifty-six minutes, to determine "
    "whether the loss was attributable to equipment failure, procedural lapse "
    "or a combination of the two, and to recommend such remedial measures as "
    "the court considers necessary. The court took evidence from eleven "
    "witnesses and examined the maintenance record of the installation in full.",

    "The court finds that the primary link failure originated in a degraded "
    "feeder connection at the antenna base, and that the degradation was "
    "progressive rather than sudden. Maintenance logs record three earlier "
    "instances of intermittent carrier loss within the preceding six weeks. On "
    "each occasion the fault was cleared by reseating the connector and the "
    "installation was returned to service without the underlying cause being "
    "investigated or the incident being escalated to the formation signals "
    "officer as standing instructions require.",

    "On the question of the standby link, the court finds that the changeover "
    "did not establish because the standby equipment had been powered down at "
    "the secondary node some days earlier and had not been restored. The court "
    "heard conflicting evidence as to who authorised the shutdown and on what "
    "date. In the absence of a written authorisation or a corresponding entry "
    "in the node occurrence book, the court is unable to attribute the decision "
    "to any individual and records that failure of documentation as a finding "
    "in its own right.",

    "The court has considered whether the duty signaller acted correctly upon "
    "detecting the fault. The court is satisfied that the initial response was "
    "in accordance with the fault drill, that escalation occurred within the "
    "period prescribed, and that no criticism attaches to the individual "
    "concerned. The court observes that the drill itself assumes an operative "
    "standby path, and that the drill offers no guidance where that assumption "
    "does not hold, which the court regards as a material deficiency.",

    "Evidence was taken regarding the generator at the secondary node. The "
    "court finds that fuel stocks were adequate, that the machine was "
    "serviceable, and that it had been shut down deliberately rather than "
    "having failed. The court notes that no alarm was raised by this shutdown "
    "because the monitoring circuit at that node reports only to a panel within "
    "the node itself, which is unmanned outside working hours, and that this "
    "arrangement defeats the purpose of the monitoring circuit entirely.",

    "The court examined the decision to despatch a runner rather than to "
    "attempt restoration by other means. Having regard to the terrain, the "
    "hour, and the communications state then obtaining, the court considers "
    "the decision sound and consistent with the post commander's obligations. "
    "The court notes that the runner reached the secondary node in a time "
    "materially longer than the planning figure held at the post, and "
    "recommends that the planning figure be revised on the basis of the "
    "measured transit rather than the estimate presently recorded.",

    "On the wider question of maintenance culture at the installation, the "
    "court is troubled by the pattern disclosed in the logs. A recurring fault "
    "cleared three times without investigation, a standby path powered down "
    "without record, and a monitoring circuit reporting to an unmanned panel "
    "are not independent lapses. They share a common character, which is the "
    "treatment of a restored service as a closed incident, and the court "
    "considers that character to be the principal finding of this inquiry.",

    "The court has reviewed the representations submitted by the formation "
    "signals officer regarding the adequacy of the manpower establishment at "
    "the secondary node. Having examined the establishment table against the "
    "tasks assigned, the court accepts that the node is manned below the level "
    "the task properly requires, and that this materially contributed to the "
    "circumstances examined. The court's recommendations at Section 8 address "
    "this point directly and are not contingent upon the other findings.",

    "The court recommends that the feeder installation at the relay station be "
    "replaced in its entirety rather than repaired, that the monitoring circuit "
    "at the secondary node be re-terminated to a continuously manned panel, and "
    "that the fault drill be amended to cover the case in which no standby path "
    "is available. The court further recommends that recurring faults cleared "
    "by field expedient be subject to mandatory escalation after the second "
    "occurrence within any rolling ninety-day period.",

    "This report and its annexures are circulated to the members of the court, "
    "the convening authority, the formation signals officer, and the legal "
    "member nominated for this inquiry. Recipients are reminded that the "
    "contents remain restricted until the convening authority has recorded its "
    "decision, and that onward circulation beyond the recorded distribution "
    "list is not authorised under any circumstances whatever.",
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
        title=TITLE, author="Court of Inquiry")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height,
                  id="f")
    doc.addPageTemplates([PageTemplate(id="p", frames=[frame],
                                       onPage=page_furniture)])

    story = []
    story.append(Paragraph(TITLE, h1))
    story.append(Paragraph(SUBTITLE, meta))
    story.append(Spacer(1, 3))
    story.append(Paragraph(
        f"Reference {REF} &nbsp;·&nbsp; Circulated to 5 recipients", meta))
    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "Not for onward circulation. Each copy issued under this reference is "
        "individually attributable to its recipient.", stamp))
    story.append(Spacer(1, 16))

    story.append(Paragraph("1. Convening and terms of reference", h2))
    story.append(Paragraph(PARAS[0], body))
    story.append(Paragraph(PARAS[1], body))

    story.append(Paragraph("2. Sequence of events", h2))
    rows = [["Time", "Event"]] + [[t, e] for t, e in TIMELINE]
    t = Table(rows, colWidths=[22 * mm, 140 * mm])
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#333333")),
        ("LINEBELOW", (0, 0), (-1, 0), 0.7, colors.HexColor("#999999")),
        ("LINEBELOW", (0, 1), (-1, -2), 0.25, colors.HexColor("#dddddd")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(t)
    story.append(Spacer(1, 8))
    story.append(Paragraph(PARAS[2], body))

    sections = [
        ("3. Primary link failure", [PARAS[3]]),
        ("4. Standby path and documentation", [PARAS[4], PARAS[5]]),
        ("5. Conduct of the duty signaller", [PARAS[6], PARAS[7]]),
        ("6. Generator and monitoring circuit", [PARAS[8], PARAS[0]]),
        ("7. Maintenance culture", [PARAS[1], PARAS[2]]),
        ("8. Manpower establishment", [PARAS[3], PARAS[4]]),
        ("9. Recommendations", [PARAS[5], PARAS[6]]),
        ("10. Distribution", [PARAS[7], PARAS[8]]),
    ]
    for head, ps in sections:
        story.append(Paragraph(head, h2))
        for p in ps:
            story.append(Paragraph(p, body))

    # Annexures. Length is not padding for its own sake: the mark needs ~1534
    # bits for five recipients against three colluders, and justified body text
    # carries ~275 bits/page. The capacity print below is the check that this
    # document actually clears that bar.
    for ann, title in [("A", "Witness schedule"),
                       ("B", "Maintenance log extracts"),
                       ("C", "Representations received"),
                       ("D", "Distribution record")]:
        story.append(Paragraph(f"Annexure {ann} — {title}", h2))
        for i in range(11):
            story.append(Paragraph(PARAS[(i + ord(ann)) % len(PARAS)], body))

    doc.build(story)


if __name__ == "__main__":
    dest = sys.argv[1] if len(sys.argv) > 1 else "demo-docs/board-inquiry.pdf"
    build(dest)

    import pymupdf

    from pqfw.watermark import engine, tardos

    d = pymupdf.open(dest)
    pages = d.page_count
    d.close()

    cap = engine.capacity(dest)
    need = tardos.required_length(5, 3)
    print(f"wrote {dest} — {pages} pages, "
          f"{Path(dest).stat().st_size // 1024} KB")
    print(f"capacity {cap} bits; {need} required for 5 recipients vs 3 colluders")
    if cap < need:
        raise SystemExit(
            f"ERROR: {cap} bits is below the {need} required. Add body text.")
    print("OK — this document can carry a full codeword.")
