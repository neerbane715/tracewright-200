"""Rebuild a clean demo environment in one command.

    python demo_reset.py

Creates identities, encrypts the demo document, performs decryptions so the
ledger looks lived-in, and leaves one 'leaked' copy ready for investigation.
Everything it produces is real output from the real pipeline -- no mocks, no
pre-baked results.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from pqfw import pipeline
from pqfw.identity import Keystore
from pqfw.ledger.node import LedgerNode

ROOT = Path(__file__).parent
DEMO = ROOT / "demo"
# The realistic demo document. spike/out/original.pdf is lorem-style filler
# kept for robustness testing -- anything a judge sees should be the tender
# evaluation report, or the story and the artefact do not match.
DOC = ROOT / "demo-docs" / "tender-evaluation.pdf"
FALLBACK_DOC = ROOT / "spike" / "out" / "original.pdf"

RECIPIENTS = ["alice", "bob", "carol", "dave", "erin"]
LEAKER = "carol"


def main() -> None:
    doc = DOC
    if not doc.exists():
        doc = FALLBACK_DOC
        if not doc.exists():
            sys.exit("missing the demo document — run:\n"
                     "  python spike/make_demo_doc.py demo-docs/tender-evaluation.pdf")
        print(f"note: {DOC.name} not found, falling back to {doc.name}")

    if DEMO.exists():
        try:
            shutil.rmtree(DEMO)
        except PermissionError as e:
            # Windows holds a lock on an open SQLite file. If the API server is
            # running, the old ledger survives and the "reset" silently does
            # nothing -- which during a demo means a stale, possibly tampered
            # ledger. Fail loudly instead.
            sys.exit(
                f"cannot remove {DEMO}: {e.filename or e} is locked.\n"
                f"Stop the API server (uvicorn) and run this again.")
    DEMO.mkdir(parents=True)
    home = DEMO / "pqfw-data"

    print("creating post-quantum identities...")
    ks = Keystore(home / "keys")
    idents = [ks.create(u) for u in RECIPIENTS]
    for i in idents:
        print(f"  {i.user_id:6} {i.fingerprint}")

    led = LedgerNode(home / "ledger.db")

    print("\nencrypting document for all recipients...")
    bundle = DEMO / "tender-evaluation.pqfw"
    b = pipeline.encrypt(doc, idents, bundle)
    print(f"  doc id {b.doc_id}, {len(b.slots)} recipient slots")

    print("\nperforming decryptions...")
    for u in RECIPIENTS:
        out = DEMO / f"{u}-copy.pdf"
        r = pipeline.decrypt(bundle, u, ks, led, out)
        flag = "   <-- this one will be 'leaked'" if u == LEAKER else ""
        print(f"  {u:6} -> ledger #{r.ledger_index}, "
              f"{r.bits_embedded} bits{flag}")

    shutil.copy(DEMO / f"{LEAKER}-copy.pdf", DEMO / "LEAKED-DOCUMENT.pdf")

    print(f"\nledger: {led.size()} records, root {led.root().hex()[:32]}...")
    print(f"""
ready. from the {DEMO.name}/ directory:

  python -m pqfw.cli ledger list
  python -m pqfw.cli investigate LEAKED-DOCUMENT.pdf
  python -m pqfw.cli ledger verify

ground truth: the leaked copy belongs to '{LEAKER}'.
""")


if __name__ == "__main__":
    main()
