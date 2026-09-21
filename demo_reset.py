"""Rebuild a clean demo environment in one command.

    python demo_reset.py

Creates identities, encrypts the demo document, performs decryptions so the
ledger looks lived-in, and leaves one 'leaked' copy ready for investigation.
Everything it produces is real output from the real pipeline -- no mocks, no
pre-baked results.
"""
from __future__ import annotations

import gc
import os
import shutil
import sqlite3
import sys
from pathlib import Path

from pqfw import pipeline
from pqfw.identity import Keystore
from pqfw.ledger.node import LedgerNode

ROOT = Path(__file__).resolve().parent
DEMO = ROOT / "demo"
# The realistic demo document. spike/out/original.pdf is lorem-style filler
# kept for robustness testing -- anything a judge sees should be the tender
# evaluation report, or the story and the artefact do not match.
DOC = ROOT / "demo-docs" / "tender-evaluation.pdf"
FALLBACK_DOC = ROOT / "spike" / "out" / "original.pdf"

RECIPIENTS = ["alice", "bob", "carol", "dave", "erin"]
LEAKER = "carol"


def _clean_demo_dir(demo_dir: Path) -> None:
    """Safely wipe demo_dir even if Windows holds locks on SQLite files."""
    if not demo_dir.exists():
        return

    gc.collect()
    try:
        shutil.rmtree(demo_dir)
        return
    except (PermissionError, OSError):
        pass

    # Windows lock fallback: delete what can be deleted, and truncate SQLite DB if locked.
    for item in list(demo_dir.rglob("*")):
        if item.is_file():
            try:
                item.unlink()
            except (PermissionError, OSError):
                if item.name == "ledger.db":
                    try:
                        conn = sqlite3.connect(str(item))
                        conn.executescript(
                            "DELETE FROM leaves; DELETE FROM sth; DELETE FROM nodekey; VACUUM;"
                        )
                        conn.commit()
                        conn.close()
                    except Exception:
                        pass

    for root_dir, dirs, _ in os.walk(str(demo_dir), topdown=False):
        for d in dirs:
            try:
                os.rmdir(os.path.join(root_dir, d))
            except (PermissionError, OSError):
                pass


def run_reset() -> dict:
    """Execute demo reset programmatically and return status information."""
    doc = DOC
    if not doc.exists():
        doc = FALLBACK_DOC
        if not doc.exists():
            raise FileNotFoundError(
                "missing demo document -- run 'python spike/make_demo_doc.py demo-docs/tender-evaluation.pdf'"
            )

    _clean_demo_dir(DEMO)
    DEMO.mkdir(parents=True, exist_ok=True)
    home = DEMO / "pqfw-data"
    home.mkdir(parents=True, exist_ok=True)
    (home / "keys").mkdir(parents=True, exist_ok=True)

    ks = Keystore(home / "keys")
    idents = [ks.create(u, overwrite=True) for u in RECIPIENTS]

    led = LedgerNode(home / "ledger.db")
    bundle = DEMO / "tender-evaluation.pqfw"
    b = pipeline.encrypt(doc, idents, bundle)

    decryptions = []
    for u in RECIPIENTS:
        out = DEMO / f"{u}-copy.pdf"
        r = pipeline.decrypt(bundle, u, ks, led, out)
        decryptions.append({
            "user": u,
            "ledger_index": r.ledger_index,
            "bits": r.bits_embedded,
            "leaker": (u == LEAKER),
        })

    shutil.copy(DEMO / f"{LEAKER}-copy.pdf", DEMO / "LEAKED-DOCUMENT.pdf")

    size = led.size()
    root_hex = led.root().hex()
    tampered, bad_idx, msg = led.detect_tamper()
    led.close()

    # Sync to demo_seed if available
    seed = ROOT / "demo_seed"
    if seed.exists():
        try:
            shutil.copytree(DEMO, seed, dirs_exist_ok=True)
        except Exception:
            pass

    return {
        "doc_id": b.doc_id,
        "size": size,
        "root": root_hex,
        "tampered": tampered,
        "message": msg,
        "leaker": LEAKER,
        "decryptions": decryptions,
    }


def main() -> None:
    doc = DOC
    if not doc.exists():
        doc = FALLBACK_DOC
        if not doc.exists():
            sys.exit("missing the demo document — run:\n"
                     "  python spike/make_demo_doc.py demo-docs/tender-evaluation.pdf")
        print(f"note: {DOC.name} not found, falling back to {doc.name}")

    print("rebuilding demo environment...")
    res = run_reset()

    print("creating post-quantum identities...")
    home = DEMO / "pqfw-data"
    ks = Keystore(home / "keys")
    for u in RECIPIENTS:
        print(f"  {u:6} {ks.public(u).fingerprint}")

    print(f"\nencrypting document for all recipients...")
    print(f"  doc id {res['doc_id']}, {len(RECIPIENTS)} recipient slots")

    print("\nperforming decryptions...")
    for d in res["decryptions"]:
        flag = "   <-- this one will be 'leaked'" if d["leaker"] else ""
        print(f"  {d['user']:6} -> ledger #{d['ledger_index']}, "
              f"{d['bits']} bits{flag}")

    print(f"\nledger: {res['size']} records, root {res['root'][:32]}... ({res['message']})")
    print(f"""
ready. from the {DEMO.name}/ directory:

  python -m pqfw.cli ledger list
  python -m pqfw.cli investigate LEAKED-DOCUMENT.pdf
  python -m pqfw.cli ledger verify

ground truth: the leaked copy belongs to '{res['leaker']}'.
""")


if __name__ == "__main__":
    main()
