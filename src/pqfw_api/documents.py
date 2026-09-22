"""Operator-supplied documents: upload, validate, report watermark capacity.

Kept separate from attribute.py because upload handling has its own
validation rules and that module is already large.

The capacity check exists so a document that cannot carry a full codeword is
refused at the door, with the numbers stated, rather than failing with a
CapacityError midway through sealing. Refusing to mark a document the system
could not later defend is a feature; surfacing it as a mid-demo crash is not.
"""
from __future__ import annotations

import json
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
# How many uploads (beyond the always-present bundled sample) the listing
# shows, newest first. A listing cap only -- nothing is deleted from disk.
UPLOAD_LISTING_CAP = 8

# How many uploaded PDFs are retained on disk after a successful upload.
# Unlike UPLOAD_LISTING_CAP this one does delete: without it uploads/
# accumulates forever, since demo_reset.py wiping the whole demo/ tree was
# previously the only thing pruning this directory.
UPLOAD_RETENTION_CAP = 20


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


def _prune_uploads(keep: int = UPLOAD_RETENTION_CAP) -> None:
    """Keep only the newest `keep` uploaded PDFs (plus their sidecars).

    Best-effort and silent: a prune failure (locked file, race with another
    request, permissions) must never fail the upload that triggered it. Also
    removes orphaned sidecars -- a .json whose .pdf is already gone -- so
    those do not accumulate either.
    """
    try:
        pdfs = sorted(UPLOADS.glob("*.pdf"),
                      key=lambda q: q.stat().st_mtime, reverse=True)
        for stale in pdfs[keep:]:
            stale.unlink(missing_ok=True)
            stale.with_suffix(".json").unlink(missing_ok=True)

        # Orphaned sidecars: a .json left behind by a .pdf that is gone
        # (pruned above, or removed by some other path entirely).
        kept_stems = {p.stem for p in pdfs[:keep]}
        for sc in UPLOADS.glob("*.json"):
            if sc.stem not in kept_stems and not sc.with_suffix(".pdf").exists():
                sc.unlink(missing_ok=True)
    except Exception:
        pass


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
    # Self-healing: UPLOADS is created at module import, but a demo reset (or
    # anything else that wipes DEMO/uploads mid-process) removes it for the
    # life of this process since nothing re-creates it afterward. Guard right
    # before the write so the endpoint works regardless of who wiped what.
    stored.parent.mkdir(parents=True, exist_ok=True)
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

    display_name = file.filename or "document.pdf"

    # Sidecar is display-only: never let it influence any path. All paths
    # are derived from doc_id alone, both here and in list_documents().
    sidecar = UPLOADS / f"{doc_id}.json"
    try:
        sidecar.write_text(json.dumps({"display_name": display_name}))
    except OSError:
        pass  # Best-effort; the listing falls back to the stored filename.

    _prune_uploads()

    return {
        "id": doc_id,
        "display_name": display_name,
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

    uploads = sorted(UPLOADS.glob("*.pdf"),
                     key=lambda q: q.stat().st_mtime, reverse=True)
    for p in uploads[:UPLOAD_LISTING_CAP]:
        try:
            out.append({
                "id": p.stem,
                "display_name": _display_name_for(p),
                "path": f"uploads/{p.name}",
                "bundled": False,
                **analyse(p),
            })
        except Exception:
            continue
    return out


def _display_name_for(pdf_path: Path) -> str:
    """The operator-supplied filename for an uploaded PDF, if recorded.

    Read from the sidecar JSON written at upload time. The sidecar's
    contents are display-only -- this never feeds into any path -- and a
    missing or corrupt sidecar (older upload, partial write, or a top-level
    JSON value that isn't an object -- e.g. tampering or a partial write
    that produced valid JSON of the wrong shape) falls back to the stored
    filename (the uuid) rather than breaking, or silently dropping, the
    listing.
    """
    fallback = pdf_path.name
    sidecar = pdf_path.with_suffix(".json")
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback
    if not isinstance(data, dict):
        return fallback
    name = data.get("display_name")
    return name if isinstance(name, str) and name.strip() else fallback
