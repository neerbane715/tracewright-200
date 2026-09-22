"""Operator-supplied documents: upload, validate, report watermark capacity.

Kept separate from attribute.py because upload handling has its own
validation rules and that module is already large.

The capacity check exists so a document that cannot carry a full codeword is
refused at the door, with the numbers stated, rather than failing with a
CapacityError midway through sealing. Refusing to mark a document the system
could not later defend is a feature; surfacing it as a mid-demo crash is not.
"""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pymupdf
from fastapi import APIRouter, File, HTTPException, UploadFile

from pqfw.watermark import engine, tardos

from .paths import TENDER_DOC, UPLOADS

# Above this, a demo is not the right tool anyway, and the search below stays
# cheap. Requirements grow as ln(n), so this ceiling is generous.
RECIPIENT_CEILING = 50


def max_recipients(capacity_bits: int, n_colluders: int = 3,
                   ceiling: int = RECIPIENT_CEILING) -> int:
    """Largest recipient count whose codeword fits in `capacity_bits`.

    Returns 0 when even two recipients do not fit. Because
    required_length grows as ln(n), capacity is almost entirely fixed cost:
    a document clearing the bar for 5 usually clears it for many more, which
    is worth showing rather than reporting a bare pass/fail.
    """
    best = 0
    for n in range(2, ceiling + 1):
        if tardos.required_length(n, n_colluders) <= capacity_bits:
            best = n
        else:
            break
    return best


def analyse(pdf_path: Path, n_recipients: int = 5,
            n_colluders: int = 3) -> dict:
    """Measure what mark this PDF can carry. Reads the file; changes nothing."""
    doc = pymupdf.open(pdf_path)
    try:
        pages = doc.page_count
    finally:
        doc.close()

    cap = engine.capacity(str(pdf_path))
    need = tardos.required_length(n_recipients, n_colluders)
    return {
        "pages": pages,
        "capacity_bits": cap,
        "required_bits": need,
        "sufficient": cap >= need,
        "max_recipients": max_recipients(cap, n_colluders),
    }


router = APIRouter(prefix="/api", tags=["documents"])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
PDF_MAGIC = b"%PDF"


def _safe_unlink(path: Path) -> None:
    """Best-effort cleanup of a rejected upload.

    On Windows, a file PyMuPDF just failed to fully open can briefly remain
    memory-mapped by the OS even after close()/GC, which turns an immediate
    unlink into a transient PermissionError. A short retry clears it without
    risking the request on a cleanup detail; a failure here must never mask
    the HTTPException the caller is about to raise.
    """
    import time
    for attempt in range(5):
        try:
            path.unlink(missing_ok=True)
            return
        except PermissionError:
            if attempt == 4:
                return
            time.sleep(0.05)


@router.post("/documents")
async def upload_document(file: UploadFile = File(...)):
    """Accept an operator-supplied PDF and report what mark it can carry.

    A document too thin to carry a codeword is NOT an error: it is accepted,
    measured, and returned with sufficient=false so the UI can explain the
    refusal with the actual numbers. An error status would leave the UI
    nothing to say.
    """
    raw = await file.read()

    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            400, f"that file is {len(raw) // (1024 * 1024)} MB; the limit is "
                 f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
    if not raw.startswith(PDF_MAGIC):
        raise HTTPException(400, "that file is not a PDF")

    doc_id = uuid.uuid4().hex
    stored = UPLOADS / f"{doc_id}.pdf"
    stored.write_bytes(raw)

    d = None
    try:
        d = pymupdf.open(stored)
        needs_pass = d.needs_pass
    except Exception:
        if d is not None:
            d.close()
        _safe_unlink(stored)
        raise HTTPException(400, "that PDF could not be opened — it may be corrupt")
    else:
        d.close()

    if needs_pass:
        _safe_unlink(stored)
        raise HTTPException(
            400, "that PDF is password-protected; supply an unprotected copy")

    try:
        info = analyse(stored)
    except Exception:
        _safe_unlink(stored)
        raise HTTPException(400, "that PDF could not be analysed")

    return {
        "id": doc_id,
        "display_name": file.filename or "document.pdf",
        # Relative to DEMO, which is what /api/encrypt resolves against.
        "path": f"uploads/{doc_id}.pdf",
        **info,
    }


@router.get("/documents")
def list_documents():
    """Documents available to seal: the bundled sample first, then uploads."""
    out = []
    if TENDER_DOC.exists():
        try:
            out.append({
                "id": "bundled",
                "display_name": TENDER_DOC.name,
                "path": str(TENDER_DOC),
                "bundled": True,
                **analyse(TENDER_DOC),
            })
        except Exception:
            pass

    for p in sorted(UPLOADS.glob("*.pdf"),
                    key=lambda q: q.stat().st_mtime, reverse=True):
        try:
            out.append({
                "id": p.stem,
                "display_name": p.name,
                "path": f"uploads/{p.name}",
                "bundled": False,
                **analyse(p),
            })
        except Exception:
            continue
    return out
