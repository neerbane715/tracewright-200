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

from .paths import ROOT, DEMO, HOME

# Original rows saved before a demo tamper, so the presenter can undo it.
# Keyed by ledger index; holds the exact JSON that was there before.
_TAMPER_BACKUP: dict[int, str] = {}


def _led() -> LedgerNode:
    return LedgerNode(HOME / "ledger.db")


def _safe(p: str | Path) -> Path:
    """Resolve a client path inside the project, never outside it."""
    cand = (DEMO / Path(p)).resolve() if not Path(p).is_absolute() else Path(p).resolve()
    if not (cand.is_relative_to(DEMO.resolve()) or cand.is_relative_to(ROOT.resolve())):
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


# --------------------------------------------------------------------- B4

@router.get("/page-image")
def page_image(path: str, page: int = 0, dpi: int = 110):
    """Render one page of a decrypted copy so the UI can show it.

    Act 2 has to *show* that two copies look identical rather than assert it.
    Rendering server-side keeps the claim honest: the image a viewer compares
    is produced from the actual file on disk.
    """
    import io as _io

    import pymupdf
    from fastapi.responses import Response

    target = _safe(path)
    if not target.exists():
        raise HTTPException(404, "that copy is no longer present")
    try:
        doc = pymupdf.open(target)
        if page < 0 or page >= doc.page_count:
            raise HTTPException(400, "no such page")
        pix = doc[page].get_pixmap(dpi=max(40, min(dpi, 200)))
        buf = _io.BytesIO(pix.tobytes("png"))
        doc.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"could not render that page: {type(e).__name__}")
    return Response(buf.getvalue(), media_type="image/png",
                    headers={"Cache-Control": "no-store"})


class CompareBody(BaseModel):
    a: str
    b: str
    page: int = 0


@router.post("/compare")
def compare(body: CompareBody):
    """Prove two copies are visually identical but forensically distinct.

    Every number here is measured from the two files, not asserted:
      * byte equality and SHA-256 of each
      * how many byte positions differ
      * whether the rendered pixels differ, and by how much
      * whether the text and every baseline are unchanged

    The last one matters most: identical words at identical baselines with a
    different byte stream is exactly the claim the product makes.
    """
    import hashlib

    import numpy as np
    import pymupdf

    pa, pb = _safe(body.a), _safe(body.b)
    for p in (pa, pb):
        if not p.exists():
            raise HTTPException(404, "one of those copies is no longer present")

    A, B = pa.read_bytes(), pb.read_bytes()
    n = min(len(A), len(B))
    differing = sum(1 for i in range(n) if A[i] != B[i]) + abs(len(A) - len(B))

    da, db = pymupdf.open(pa), pymupdf.open(pb)
    page = max(0, min(body.page, min(da.page_count, db.page_count) - 1))

    wa = da[page].get_text("words")
    wb = db[page].get_text("words")
    same_text = [w[4] for w in wa] == [w[4] for w in wb]

    ya = sorted({round(w[3], 2) for w in wa})
    yb = sorted({round(w[3], 2) for w in wb})
    baseline_shift = (max((abs(x - y) for x, y in zip(ya, yb)), default=0.0)
                      if len(ya) == len(yb) else None)

    xa = da[page].get_pixmap(dpi=100)
    xb = db[page].get_pixmap(dpi=100)
    M = np.frombuffer(xa.samples, np.uint8).astype(int)
    N = np.frombuffer(xb.samples, np.uint8).astype(int)
    same_shape = M.shape == N.shape
    pixel_diff = float(np.abs(M - N).mean()) if same_shape else None
    ink_delta = float(abs(M.mean() - N.mean())) if same_shape else None

    da.close()
    db.close()

    return {
        "a": {"name": pa.name, "bytes": len(A),
              "sha256": hashlib.sha256(A).hexdigest()},
        "b": {"name": pb.name, "bytes": len(B),
              "sha256": hashlib.sha256(B).hexdigest()},
        "byte_identical": A == B,
        "differing_byte_positions": differing,
        "same_words": same_text,
        "word_count": len(wa),
        "max_baseline_shift_pt": baseline_shift,
        "pixel_mean_abs_diff": pixel_diff,
        "ink_delta": ink_delta,
        "page": page,
    }


# --------------------------------------------------------------------- B5

@router.get("/ledger/chain")
def ledger_chain():
    """The ledger as a verifiable chain, with per-record integrity.

    /api/ledger returns a flat list. Act 3 draws the linkage, so it needs each
    record's own leaf hash and whether that leaf still matches its stored
    content -- which is what makes tampering *locatable* rather than merely
    detectable.
    """
    L = _led()
    tampered, bad_idx, msg = L.detect_tamper()
    sth = L.latest_sth()

    rows = []
    for idx, sr in L.all_records():
        rec = sr.record
        leaf = hash_leaf(sr.leaf_bytes()).hex()
        # A record is intact when its stored bytes still hash to the leaf that
        # was committed, AND its own signature still verifies.
        sig_ok = verify(sr.sig_public, rec.canonical_bytes(), sr.signature)
        rows.append({
            "index": idx,
            "user_id": rec.recipient_user_id,
            "fingerprint": rec.recipient_fingerprint,
            "doc_id": rec.doc_id,
            "session_id": rec.session_id,
            "timestamp": rec.timestamp,
            "n_bits": rec.n_bits,
            "leaf_hash": leaf,
            "signature_valid": sig_ok,
            "signature_len": len(sr.signature),
            "broken": (bad_idx is not None and idx == bad_idx) or not sig_ok,
        })

    return {
        "size": L.size(),
        "root": L.root().hex(),
        "sth": {
            "tree_size": sth["tree_size"],
            "root": sth["root"].hex(),
            "signed_at": sth["signed_at"],
            "signature_bytes": len(sth["signature"]),
            "valid": L.verify_sth(sth),
            "algorithm": "ML-DSA-65",
        } if sth else None,
        "integrity": {
            "intact": not tampered,
            "first_broken_index": bad_idx,
            "message": msg,
        },
        "records": rows,
    }


@router.post("/ledger/restore")
def ledger_restore():
    """Undo the demo tamper by restoring the damaged record from its backup.

    The obvious implementation -- shell out to demo_reset.py -- cannot work:
    this server holds an open SQLite handle, so Windows refuses to delete the
    file and the restore fails every time. Instead the tamper endpoint keeps
    the original row, and this puts it back through the same connection.

    Only possible because tampering here is a demo affordance. A real
    deployment has no such button; that is the whole point of the ledger.
    """
    import sqlite3

    if not _TAMPER_BACKUP:
        tampered, _, msg = _led().detect_tamper()
        if tampered:
            raise HTTPException(
                409, "this ledger was altered outside the demo and cannot be "
                     "repaired from here")
        return {"restored": True, "message": msg}

    db = sqlite3.connect(str(HOME / "ledger.db"))
    try:
        for idx, entry in _TAMPER_BACKUP.items():
            db.execute("UPDATE leaves SET entry=? WHERE idx=?", (entry, idx))
        db.commit()
    finally:
        db.close()
    _TAMPER_BACKUP.clear()

    tampered, _, msg = _led().detect_tamper()
    return {"restored": not tampered, "message": msg}


# --------------------------------------------------------------------- B6

class StageLeakBody(BaseModel):
    source: str | None = None


@router.post("/stage-leak")
def stage_leak(body: StageLeakBody):
    """Stage a leaked artefact WITHOUT working out who leaked it.

    Deliberately ignorant. The previous wizard ran the real investigation at
    this point, cached the answer, and had the next screen replay it while
    labelling it "Extracted watermark". Act 5 must do the extraction, so this
    endpoint refuses to look.

    Returns only what a person who *found* the file would know: a filename, a
    size, a hash, and how many pages it has.
    """
    import hashlib
    import random

    import pymupdf

    if body.source:
        src = _safe(body.source)
    else:
        # Pick one recipient's copy at random. Which one is not recorded
        # anywhere in this response -- the demo operator does not know either.
        copies = sorted(DEMO.glob("*-copy.pdf"))
        if not copies:
            raise HTTPException(
                409, "no opened copies exist yet — open the document as a "
                     "recipient first")
        src = random.choice(copies)

    if not src.exists():
        raise HTTPException(404, "that file is no longer present")

    leaked = DEMO / "surfaced-document.pdf"
    shutil.copy(src, leaked)

    raw = leaked.read_bytes()
    try:
        doc = pymupdf.open(leaked)
        pages = doc.page_count
        title = doc.metadata.get("title") or ""
        doc.close()
    except Exception:
        pages, title = 0, ""

    return {
        "path": leaked.name,
        "filename": leaked.name,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "pages": pages,
        "title": title,
        # Explicitly not included: who this came from. Act 5 has to find out.
    }


@router.get("/bundles")
def bundles():
    """Distributable bundles currently on disk, newest first.

    Acts must not hardcode a filename. demo_reset.py produces
    classified-report.pqfw while Act 1 produces one named after whichever
    document was sealed, so a hardcoded name breaks whenever someone lands on
    Act 2 without walking through Act 1 first.
    """
    found = sorted(DEMO.glob("*.pqfw"), key=lambda p: p.stat().st_mtime,
                   reverse=True)
    return [{"name": p.name, "bytes": p.stat().st_size} for p in found]
