"""Endpoints the redesigned UI needs that the original API did not expose.

Three additions, each tied to a UX requirement that could not otherwise be met
honestly:

  B1  POST /api/attribute        real extraction from a supplied file
  B2  GET  /api/event/{index}    the full signed record for one decryption
  B3  POST /api/verify-signature verify a record+signature server-side

B1 exists because the previous wizard labelled a cached string "Extracted
watermark" without performing an extraction (it ran investigate() one stage
earlier and replayed the answer). The new Act 5 must do the real thing.

B2 and B3 exist so the technical-detail layer can show the *same* signature in
Act 2 that Act 5 later verifies, and so "verify it yourself" actually verifies
rather than decorating.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from pqfw.crypto import verify
from pqfw.forensics.investigate import investigate
from pqfw.ledger.merkle import hash_leaf, verify_inclusion
from pqfw.ledger.node import LedgerNode
from pqfw.records import DecryptionRecord, SignedRecord, b64d, b64e

router = APIRouter(prefix="/api", tags=["attribution"])

ROOT = Path(__file__).parent.parent.parent
DEMO = ROOT / "demo"
HOME = DEMO / "pqfw-data"


def _led() -> LedgerNode:
    return LedgerNode(HOME / "ledger.db")


def _safe(p: str | Path) -> Path:
    """Resolve a client path inside the project, never outside it."""
    cand = (DEMO / Path(p)).resolve() if not Path(p).is_absolute() else Path(p).resolve()
    if not cand.is_relative_to(ROOT.resolve()):
        raise HTTPException(400, "that file is outside the working directory")
    return cand


# --------------------------------------------------------------------- B1

@router.post("/attribute")
async def attribute(file: UploadFile = File(...)):
    """Extract a watermark from an uploaded file and attribute it.

    This is a genuine extraction: the bits are recovered from the file's own
    word-spacing geometry, scored against every codeword in the ledger, and the
    resulting record's signature and inclusion proof are verified. Nothing is
    cached or pre-computed.
    """
    suffix = Path(file.filename or "leaked.pdf").suffix or ".pdf"
    tmpdir = Path(tempfile.mkdtemp())
    tmp = tmpdir / f"subject{suffix}"
    with tmp.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)

    try:
        v = investigate(tmp, _led())
    except Exception as e:
        raise HTTPException(500, f"extraction failed: {type(e).__name__}")
    finally:
        try:
            tmp.unlink()
            tmpdir.rmdir()
        except OSError:
            pass

    out = v.to_dict()
    out["source_filename"] = file.filename

    # Attach the Merkle proof so the technical layer can show the real path
    # rather than asserting one exists.
    if v.ledger_index is not None:
        try:
            p = _led().prove_inclusion(v.ledger_index)
            out["inclusion_proof"] = {
                "index": p["index"], "tree_size": p["tree_size"],
                "root": p["root"].hex(),
                "path": [h.hex() for h in p["proof"]],
            }
        except Exception:
            out["inclusion_proof"] = None
    return out


class AttributePath(BaseModel):
    path: str


@router.post("/attribute-path")
def attribute_path(body: AttributePath):
    """Same as /attribute but for a file already on disk (the staged leak)."""
    target = _safe(body.path)
    if not target.exists():
        raise HTTPException(404, "that file is no longer present")
    try:
        v = investigate(target, _led())
    except Exception as e:
        raise HTTPException(500, f"extraction failed: {type(e).__name__}")

    out = v.to_dict()
    out["source_filename"] = target.name
    if v.ledger_index is not None:
        try:
            p = _led().prove_inclusion(v.ledger_index)
            out["inclusion_proof"] = {
                "index": p["index"], "tree_size": p["tree_size"],
                "root": p["root"].hex(),
                "path": [h.hex() for h in p["proof"]],
            }
        except Exception:
            out["inclusion_proof"] = None
    return out


# --------------------------------------------------------------------- B2

@router.get("/event/{index}")
def event(index: int):
    """The complete signed record for one decryption event.

    Returns the exact bytes that were signed, so the UI can show in Act 2 the
    same signature Act 5 later verifies -- and a viewer can check they match.
    """
    L = _led()
    if index < 0 or index >= L.size():
        raise HTTPException(404, "no such decryption event")
    sr = L.get(index)
    if sr is None:
        raise HTTPException(404, "no such decryption event")

    rec = sr.record
    proof = L.prove_inclusion(index)
    return {
        "index": index,
        "record": rec.to_dict(),
        "signed_bytes": rec.canonical_bytes().decode("utf-8"),
        "signature": b64e(sr.signature),
        "signature_hex": sr.signature.hex(),
        "signature_len": len(sr.signature),
        "sig_public": b64e(sr.sig_public),
        "sig_public_len": len(sr.sig_public),
        "algorithm": "ML-DSA-65",
        "leaf_hash": hash_leaf(sr.leaf_bytes()).hex(),
        "inclusion_proof": {
            "index": proof["index"], "tree_size": proof["tree_size"],
            "root": proof["root"].hex(),
            "path": [h.hex() for h in proof["proof"]],
        },
    }


# --------------------------------------------------------------------- B3

class VerifyBody(BaseModel):
    index: int


@router.post("/verify-signature")
def verify_signature(body: VerifyBody):
    """Re-verify one ledger entry from scratch, reporting each sub-check.

    Deliberately recomputes rather than reading a stored flag: the point of the
    'verify it yourself' action is that it performs the verification live.
    """
    L = _led()
    if body.index < 0 or body.index >= L.size():
        raise HTTPException(404, "no such decryption event")
    sr = L.get(body.index)
    if sr is None:
        raise HTTPException(404, "no such decryption event")

    signed = rec_bytes = sr.record.canonical_bytes()
    sig_ok = verify(sr.sig_public, signed, sr.signature)

    proof = L.prove_inclusion(body.index)
    incl_ok = verify_inclusion(
        hash_leaf(sr.leaf_bytes()), body.index, proof["tree_size"],
        proof["proof"], proof["root"])

    # Negative control: flipping one byte of the signed message must fail.
    mutated = bytearray(rec_bytes)
    mutated[len(mutated) // 2] ^= 0x01
    control_fails = not verify(sr.sig_public, bytes(mutated), sr.signature)

    tampered, bad_idx, msg = L.detect_tamper()

    return {
        "index": body.index,
        "checks": [
            {"id": "signature",
             "label": "Signature verifies under the recipient's public key",
             "passed": sig_ok,
             "detail": f"ML-DSA-65 · {len(sr.signature)} byte signature "
                       f"over {len(rec_bytes)} bytes of canonical record"},
            {"id": "inclusion",
             "label": "Record is provably in the ledger at this position",
             "passed": incl_ok,
             "detail": f"Merkle path of {len(proof['proof'])} hashes to root "
                       f"{proof['root'].hex()[:16]}…"},
            {"id": "control",
             "label": "A one-bit change to the record breaks the signature",
             "passed": control_fails,
             "detail": "negative control — proves the check is real"},
            {"id": "ledger",
             "label": "Ledger history has not been rewritten",
             "passed": not tampered,
             "detail": msg},
        ],
        "all_passed": sig_ok and incl_ok and control_fails and not tampered,
        "tamper_index": bad_idx,
    }
