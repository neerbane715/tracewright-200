"""Phase 0 spike: generate a realistic multi-page test document.

Dense, justified body text is the best case for spacing-based watermarking:
many words per line => many inter-word gaps => many carrier slots.
"""
import sys
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

BODY = (
    "The distribution of classified material across multiple authorised recipients "
    "creates an attribution problem that conventional access control cannot resolve. "
    "When a document is encrypted once and decrypted independently by each holder, "
    "the resulting plaintext is byte-identical for every party. Any subsequent "
    "disclosure therefore implicates the entire recipient set equally, and server "
    "side logging offers no remedy because a privileged operator may alter those "
    "records after the fact. A forensic marking scheme must instead bind each "
    "individual decryption event to the identity that performed it, embedding that "
    "binding in the document itself rather than in an external register that can be "
    "rewritten. The mark must be imperceptible to the reader, resistant to casual "
    "removal, and verifiable by an investigator holding only the leaked artefact. "
)

PARAS = 6      # paragraphs per page-ish
PAGES = 40


def build(path: str) -> None:
    doc = SimpleDocTemplate(
        path, pagesize=A4,
        leftMargin=56, rightMargin=56, topMargin=64, bottomMargin=64,
        title="Confidential Assessment", author="PQ-FORENSIC spike",
    )
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "body", parent=styles["Normal"],
        fontName="Helvetica", fontSize=10.5, leading=15.5,
        alignment=TA_JUSTIFY, spaceAfter=9,
    )
    head = ParagraphStyle(
        "head", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=13,
    )

    story = []
    for p in range(PAGES * PARAS):
        if p % PARAS == 0:
            story.append(Paragraph(f"Section {p // PARAS + 1}", head))
            story.append(Spacer(1, 4))
        # vary text slightly so lines are not identical across the doc
        story.append(Paragraph(BODY * 2, body))

    doc.build(story)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "spike/out/original.pdf"
    build(out)
    print(f"wrote {out}")
