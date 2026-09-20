"""Environment-aware path resolution and cold-start seeding for PQ-FORENSIC.

Supports both local standalone execution and serverless environments (like Vercel)
where only /tmp is writable.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
IS_VERCEL = bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))


def _is_writable(p: Path) -> bool:
    try:
        p.mkdir(parents=True, exist_ok=True)
        test = p / ".test_write"
        test.write_text("ok")
        test.unlink()
        return True
    except (OSError, PermissionError):
        return False


# Determine base directories
if IS_VERCEL or not _is_writable(ROOT / "demo"):
    BASE_DIR = Path(tempfile.gettempdir()) / "pqfw_run"
    DEMO = BASE_DIR / "demo"
    DOCS_DIR = BASE_DIR / "docs"
else:
    BASE_DIR = ROOT
    DEMO = ROOT / "demo"
    DOCS_DIR = ROOT / "demo-docs"

HOME = DEMO / "pqfw-data"
WIZARD_HOME = DEMO / "wizard-data"

DEMO.mkdir(parents=True, exist_ok=True)
HOME.mkdir(parents=True, exist_ok=True)
WIZARD_HOME.mkdir(parents=True, exist_ok=True)

# Document paths
TENDER_DOC = ROOT / "demo-docs" / "tender-evaluation.pdf"
SAMPLE_DOC = ROOT / "spike" / "out" / "original.pdf"

if not TENDER_DOC.exists():
    TENDER_DOC = DOCS_DIR / "tender-evaluation.pdf"

if not SAMPLE_DOC.exists():
    SAMPLE_DOC = DOCS_DIR / "original.pdf"


def ensure_seeded() -> None:
    """Ensure sample documents and demo data exist on startup (especially for Vercel)."""
    global TENDER_DOC, SAMPLE_DOC
    
    # Fast path: copy pre-generated demo seed data (takes < 5ms)
    seed_dir = ROOT / "demo_seed"
    if seed_dir.exists():
        try:
            shutil.copytree(seed_dir, DEMO, dirs_exist_ok=True)
            if (seed_dir / "pqfw-data").exists():
                shutil.copytree(seed_dir / "pqfw-data", HOME, dirs_exist_ok=True)
            if (seed_dir / "wizard-data").exists():
                shutil.copytree(seed_dir / "wizard-data", WIZARD_HOME, dirs_exist_ok=True)
            return
        except Exception as e:
            print(f"Warning: fast demo_seed copy failed: {e}")

    # Fallback: ensure sample PDFs exist
    if not TENDER_DOC.exists():
        TENDER_DOC.parent.mkdir(parents=True, exist_ok=True)
        try:
            from spike.make_demo_doc import build as build_tender
            build_tender(str(TENDER_DOC))
        except Exception:
            pass

    if not SAMPLE_DOC.exists():
        SAMPLE_DOC.parent.mkdir(parents=True, exist_ok=True)
        try:
            from spike.make_testdoc import build as build_sample
            build_sample(str(SAMPLE_DOC))
        except Exception:
            pass

    # Ensure initial demo ledger and identities exist
    if not (HOME / "ledger.db").exists():
        try:
            from pqfw import pipeline
            from pqfw.identity import Keystore
            from pqfw.ledger.node import LedgerNode

            recipients = ["alice", "bob", "carol", "dave", "erin"]
            leaker = "carol"
            ks = Keystore(HOME / "keys")
            idents = [ks.create(u, overwrite=True) for u in recipients]
            led = LedgerNode(HOME / "ledger.db")

            doc_to_encrypt = TENDER_DOC if TENDER_DOC.exists() else SAMPLE_DOC
            if doc_to_encrypt.exists():
                bundle_path = DEMO / "tender-evaluation.pqfw"
                b = pipeline.encrypt(doc_to_encrypt, idents, bundle_path)

                for u in recipients:
                    out = DEMO / f"{u}-copy.pdf"
                    pipeline.decrypt(bundle_path, u, ks, led, out)

                if (DEMO / f"{leaker}-copy.pdf").exists():
                    shutil.copy(DEMO / f"{leaker}-copy.pdf", DEMO / "LEAKED-DOCUMENT.pdf")
            led.close()
        except Exception as e:
            print(f"Warning: automatic seeding failed: {e}")
