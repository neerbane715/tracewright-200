# Operator-Chosen Document and Leaker — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the demo operator upload the document to be distributed, and choose which of the five recipients leaked it, without the attribution path ever being told the answer.

**Architecture:** Additive API + UI work. A new `POST /api/documents` validates an uploaded PDF and reports its watermark capacity before anything is sealed; Act 1 gains a document picker; Act 4 becomes a chooser over recipients who actually decrypted, read from the ledger. `stage_leak` keeps returning no identity, enforced by a regression test. Nothing under `src/pqfw/` changes — the engine already exposes `capacity()` and `required_length()`.

**Tech Stack:** Python 3.11+, FastAPI, PyMuPDF, pytest + `fastapi.testclient.TestClient`, React 18 + TypeScript, Vite, Tailwind.

**Spec:** `docs/superpowers/specs/2026-09-22-upload-and-choose-leaker-design.md`

## Global Constraints

- **`stage_leak` must never return a recipient identity.** Its response is exactly `{filename, bytes, sha256, pages, title}`. No `user_id`, no `ledger_index`, no echo of `source`. This is the feature's central guarantee.
- **Act 5 must run real extraction.** It calls `/api/attribute-path` or `/api/attribute`; it never displays a value computed in an earlier act.
- **Required bits at n=5, c=3 is 1534.** Measured. `tardos.required_length(5, 3) == 1534`.
- **Uploaded files are stored under generated names** inside `DEMO / "uploads"`. The original filename is display-only and never used as a path component, so `_safe()`'s containment guarantee is preserved.
- **Upload size cap: 25 MB.**
- **Do not modify anything under `src/pqfw/`.** API and UI only.
- **The bundled sample must always remain selectable** in Act 1 — it is the recovery path when an upload is refused live.
- Run backend tests with `python -m pytest tests/ -q` from the repo root.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/pqfw_api/paths.py` | Add `UPLOADS` directory constant and create it at import |
| `src/pqfw_api/documents.py` | **New.** Upload validation, capacity reporting, document listing |
| `src/pqfw_api/main.py` | Mount the new router |
| `src/pqfw_api/attribute.py` | Widen `_safe()` to accept `UPLOADS` |
| `tests/test_documents.py` | **New.** Upload validation + capacity + non-disclosure tests |
| `ui/src/lib/api.ts` | Types for the new endpoints |
| `ui/src/lib/run.tsx` | Carry `documentPath` and `chosenLeaker` |
| `ui/src/acts/Act1Distribute.tsx` | Document picker + capacity panel |
| `ui/src/acts/Act4Leak.tsx` | Leaker chooser + Surprise me + download |
| `ui/src/acts/Act5Attribute.tsx` | Reveal-then-compare |
| `demo_reset.py` | Clarify `LEAKER` is the CLI ground truth only |
| `RUNNING.md` | Document the two new controls |

A new `documents.py` rather than growing `attribute.py`: that file is already 614 lines and covers attribution, comparison, tamper-restore and staging. Upload handling is a distinct responsibility with its own validation rules.

---

## Task 1: Uploads directory and path containment

**Files:**
- Modify: `src/pqfw_api/paths.py:38-44`
- Modify: `src/pqfw_api/attribute.py:46-51`
- Test: `tests/test_documents.py` (create)

**Interfaces:**
- Produces: `paths.UPLOADS: Path` — the directory uploaded PDFs live in, created at import time.
- Produces: `_safe()` accepts paths under `UPLOADS` in addition to `DEMO` and `ROOT`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_documents.py`:

```python
"""Upload path tests for the operator-chosen document feature.

See docs/superpowers/specs/2026-09-22-upload-and-choose-leaker-design.md
"""
from __future__ import annotations

from pathlib import Path

import pytest

from pqfw_api import paths


def test_uploads_dir_exists_and_is_inside_demo():
    assert paths.UPLOADS.exists()
    assert paths.UPLOADS.is_dir()
    assert paths.UPLOADS.resolve().is_relative_to(paths.DEMO.resolve())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_documents.py -q`
Expected: FAIL with `AttributeError: module 'pqfw_api.paths' has no attribute 'UPLOADS'`

- [ ] **Step 3: Add the constant**

In `src/pqfw_api/paths.py`, after the `WIZARD_HOME` line (currently line 39):

```python
HOME = DEMO / "pqfw-data"
WIZARD_HOME = DEMO / "wizard-data"
# Operator-uploaded documents. Stored under generated names so that a
# client-supplied filename never becomes a path component.
UPLOADS = DEMO / "uploads"

DEMO.mkdir(parents=True, exist_ok=True)
HOME.mkdir(parents=True, exist_ok=True)
WIZARD_HOME.mkdir(parents=True, exist_ok=True)
UPLOADS.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_documents.py -q`
Expected: PASS

- [ ] **Step 5: Widen `_safe()`**

In `src/pqfw_api/attribute.py`, replace lines 46-51:

```python
def _safe(p: str | Path) -> Path:
    """Resolve a client path inside the project, never outside it."""
    cand = (DEMO / Path(p)).resolve() if not Path(p).is_absolute() else Path(p).resolve()
    if not (cand.is_relative_to(DEMO.resolve())
            or cand.is_relative_to(ROOT.resolve())
            or cand.is_relative_to(UPLOADS.resolve())):
        raise HTTPException(400, "that file is outside the working directory")
    return cand
```

Update the import on line 39 of that file:

```python
from .paths import ROOT, DEMO, HOME, UPLOADS
```

(`UPLOADS` is already under `DEMO`, so this is belt-and-braces against a future
change that moves it. Keeping it explicit documents the intent.)

- [ ] **Step 6: Run the full suite to check nothing regressed**

Run: `python -m pytest tests/ -q`
Expected: all existing tests still pass, plus the new one.

- [ ] **Step 7: Commit**

```bash
git add src/pqfw_api/paths.py src/pqfw_api/attribute.py tests/test_documents.py
git commit -m "feat: add uploads directory with path containment"
```

---

## Task 2: Capacity reporting helper

**Files:**
- Create: `src/pqfw_api/documents.py`
- Test: `tests/test_documents.py`

**Interfaces:**
- Consumes: `paths.UPLOADS` from Task 1.
- Produces: `max_recipients(capacity_bits: int, n_colluders: int = 3, ceiling: int = 50) -> int` — the largest recipient count whose Tardos requirement fits in `capacity_bits`. Returns 0 when even 2 do not fit.
- Produces: `analyse(pdf_path: Path, n_recipients: int = 5) -> dict` — returns `{pages, capacity_bits, required_bits, sufficient, max_recipients}`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_documents.py`:

```python
from pqfw_api import documents
from pqfw.watermark import tardos


def test_max_recipients_matches_required_length_at_boundaries():
    # Exactly enough for 5 recipients -> 5 is allowed.
    need5 = tardos.required_length(5, 3)
    assert documents.max_recipients(need5) >= 5
    # One bit short of the 2-recipient requirement -> nobody fits.
    need2 = tardos.required_length(2, 3)
    assert documents.max_recipients(need2 - 1) == 0
    assert documents.max_recipients(need2) == 2


def test_max_recipients_is_monotonic():
    prev = 0
    for cap in (0, 500, 1369, 1534, 1917, 2300, 5000):
        cur = documents.max_recipients(cap)
        assert cur >= prev
        prev = cur
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_documents.py -q`
Expected: FAIL with `ImportError` / `ModuleNotFoundError: pqfw_api.documents`

- [ ] **Step 3: Create the module**

Create `src/pqfw_api/documents.py`:

```python
"""Operator-supplied documents: upload, validate, report watermark capacity.

Kept separate from attribute.py because upload handling has its own
validation rules and that module is already large.

The capacity check exists so a document that cannot carry a full codeword is
refused at the door, with the numbers stated, rather than failing with a
CapacityError midway through sealing. Refusing to mark a document the system
could not later defend is a feature; surfacing it as a mid-demo crash is not.
"""
from __future__ import annotations

from pathlib import Path

import pymupdf

from pqfw.watermark import engine, tardos

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_documents.py -q`
Expected: PASS

- [ ] **Step 5: Add an analyse test against real files**

Append to `tests/test_documents.py`:

```python
ROOT = Path(__file__).parent.parent
TENDER = ROOT / "demo-docs" / "tender-evaluation.pdf"


def test_analyse_accepts_the_bundled_document():
    if not TENDER.exists():
        pytest.skip("run: python spike/make_demo_doc.py demo-docs/tender-evaluation.pdf")
    r = documents.analyse(TENDER)
    assert r["sufficient"] is True
    assert r["capacity_bits"] >= r["required_bits"]
    assert r["required_bits"] == 1534      # n=5, c=3
    assert r["max_recipients"] >= 5


def test_analyse_refuses_a_thin_document(tmp_path):
    thin = tmp_path / "thin.pdf"
    d = pymupdf.open()
    page = d.new_page()
    page.insert_text((72, 72), "Hello world this is a short page")
    d.save(str(thin))
    d.close()

    r = documents.analyse(thin)
    assert r["sufficient"] is False
    assert r["capacity_bits"] < r["required_bits"]
    assert r["max_recipients"] == 0
```

Add `import pymupdf` to the test file's imports.

- [ ] **Step 6: Run and verify**

Run: `python -m pytest tests/test_documents.py -q`
Expected: PASS (4 tests, or 3 + 1 skip if the demo doc is not generated)

- [ ] **Step 7: Commit**

```bash
git add src/pqfw_api/documents.py tests/test_documents.py
git commit -m "feat: add watermark capacity analysis for uploaded documents"
```

---

## Task 3: The upload endpoint

**Files:**
- Modify: `src/pqfw_api/documents.py`
- Modify: `src/pqfw_api/main.py:34` (router includes)
- Test: `tests/test_documents.py`

**Interfaces:**
- Consumes: `analyse()` from Task 2.
- Produces: `POST /api/documents` (multipart, field name `file`) returning `{id, display_name, path, pages, capacity_bits, required_bits, sufficient, max_recipients}`. `path` is the value Act 1 passes to `/api/encrypt` as `document`.
- Produces: `GET /api/documents` returning a list of the same shape, bundled sample first.
- Produces: `router` — an `APIRouter` with prefix `/api`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_documents.py`:

```python
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from pqfw_api.main import app
    return TestClient(app)


def test_upload_rejects_non_pdf(client):
    r = client.post("/api/documents",
                    files={"file": ("notes.txt", b"just text", "text/plain")})
    assert r.status_code == 400
    assert "pdf" in r.json()["detail"].lower()


def test_upload_rejects_corrupt_pdf(client):
    # Correct magic bytes, garbage body.
    r = client.post("/api/documents",
                    files={"file": ("broken.pdf", b"%PDF-1.4\nnot really",
                                    "application/pdf")})
    assert r.status_code == 400


def test_upload_accepts_valid_pdf_and_reports_capacity(client):
    if not TENDER.exists():
        pytest.skip("demo document not generated")
    with TENDER.open("rb") as fh:
        r = client.post("/api/documents",
                        files={"file": ("my-report.pdf", fh, "application/pdf")})
    assert r.status_code == 200
    body = r.json()
    assert body["display_name"] == "my-report.pdf"
    assert body["sufficient"] is True
    assert body["required_bits"] == 1534
    assert body["max_recipients"] >= 5
    # The stored name must NOT be the client-supplied one.
    assert "my-report" not in body["path"]


def test_upload_refuses_thin_pdf_with_numbers(client, tmp_path):
    thin = tmp_path / "thin.pdf"
    d = pymupdf.open()
    d.new_page().insert_text((72, 72), "Short page with few words here")
    d.save(str(thin))
    d.close()
    with thin.open("rb") as fh:
        r = client.post("/api/documents",
                        files={"file": ("thin.pdf", fh, "application/pdf")})
    assert r.status_code == 200          # accepted for inspection...
    assert r.json()["sufficient"] is False   # ...but flagged unusable
```

Note the last test's intent: a thin PDF is *reported on*, not rejected with an
error. The UI needs the numbers in order to explain the refusal, and an HTTP
error would give it nothing to show.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_documents.py -q`
Expected: FAIL — 404 on `/api/documents` (route does not exist)

- [ ] **Step 3: Implement the endpoint**

Append to `src/pqfw_api/documents.py`:

```python
import shutil
import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile

from .paths import TENDER_DOC, UPLOADS

router = APIRouter(prefix="/api", tags=["documents"])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
PDF_MAGIC = b"%PDF"


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

    try:
        d = pymupdf.open(stored)
        needs_pass = d.needs_pass
        d.close()
    except Exception:
        stored.unlink(missing_ok=True)
        raise HTTPException(400, "that PDF could not be opened — it may be corrupt")

    if needs_pass:
        stored.unlink(missing_ok=True)
        raise HTTPException(
            400, "that PDF is password-protected; supply an unprotected copy")

    try:
        info = analyse(stored)
    except Exception:
        stored.unlink(missing_ok=True)
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
```

Add to the module's existing imports at the top: `import pymupdf` is already there.

- [ ] **Step 4: Mount the router**

In `src/pqfw_api/main.py`, alongside the existing includes (currently lines 33-34):

```python
from . import attribute, documents, wizard
...
app.include_router(wizard.router)
app.include_router(attribute.router)
app.include_router(documents.router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_documents.py -q`
Expected: PASS

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest tests/ -q`
Expected: no regressions.

- [ ] **Step 7: Commit**

```bash
git add src/pqfw_api/documents.py src/pqfw_api/main.py tests/test_documents.py
git commit -m "feat: add POST /api/documents upload with capacity pre-flight"
```

---

## Task 4: The non-disclosure regression test

**Files:**
- Test: `tests/test_documents.py`

**Interfaces:**
- Consumes: `POST /api/stage-leak` (already exists, `attribute.py`).

This task adds **no production code**. It pins the behaviour the rest of the
feature depends on, before Task 6 changes how `stage_leak` is called.

- [ ] **Step 1: Write the test**

Append to `tests/test_documents.py`:

```python
import json


def test_stage_leak_does_not_reveal_source(client):
    """The central guarantee: staging may KNOW the source, never TELL it.

    A previous build computed the verdict while staging and had the next
    screen replay it under the label "Extracted watermark". Since the operator
    now names the source explicitly, the only thing standing between that bug
    and its return is this assertion.
    """
    ledger = client.get("/api/ledger").json()
    if ledger["size"] == 0:
        pytest.skip("no decryptions in the ledger; run demo_reset.py")

    names = {r["user_id"] for r in ledger["records"]}
    assert names, "ledger has records but no user_ids"

    # Stage explicitly from one known recipient's copy.
    victim = sorted(names)[0]
    r = client.post("/api/stage-leak", json={"source": f"{victim}-copy.pdf"})
    assert r.status_code == 200

    blob = json.dumps(r.json()).lower()
    for n in names:
        assert n.lower() not in blob, (
            f"stage-leak response leaked recipient '{n}': {blob}")
    assert "ledger_index" not in r.json()
    assert "user_id" not in r.json()
```

- [ ] **Step 2: Run the test**

Run: `python -m pytest tests/test_documents.py::test_stage_leak_does_not_reveal_source -q`
Expected: PASS (the current implementation already satisfies it) — or SKIP if the ledger is empty.

If it SKIPs, seed first: `python demo_reset.py`, then re-run.

- [ ] **Step 3: Verify the test can actually fail**

Temporarily add `"user_id": "carol"` to the dict returned by `stage_leak` in
`src/pqfw_api/attribute.py`, re-run the test, and confirm it FAILS. Then revert
that edit. A regression test that cannot fail protects nothing.

- [ ] **Step 4: Confirm the revert**

Run: `git diff src/pqfw_api/attribute.py`
Expected: empty output.

- [ ] **Step 5: Commit**

```bash
git add tests/test_documents.py
git commit -m "test: pin stage-leak non-disclosure before wiring leaker choice"
```

---

## Task 5: Act 1 — document picker

**Files:**
- Modify: `ui/src/lib/api.ts`
- Modify: `ui/src/lib/run.tsx`
- Modify: `ui/src/acts/Act1Distribute.tsx:10` (remove `const DOC`)

**Interfaces:**
- Consumes: `GET /api/documents`, `POST /api/documents` from Task 3.
- Produces: `RunState.documentPath: string | null` — the path Act 1 sealed, so later acts can name the document.

- [ ] **Step 1: Add the types**

In `ui/src/lib/api.ts`, alongside the other interfaces:

```typescript
export interface DocumentInfo {
  id: string;
  display_name: string;
  path: string;
  bundled?: boolean;
  pages: number;
  capacity_bits: number;
  required_bits: number;
  sufficient: boolean;
  max_recipients: number;
}
```

Add an upload helper. `api.upload` already exists (`api.ts:120`) and posts a
single `file` field as multipart, but it cannot be referenced from inside the
`api` object literal that defines it. Declare the helper **after** that literal
closes:

```typescript
/** Upload a document for distribution. Separate from api.upload only because
 *  an object literal cannot reference itself during construction. */
export const uploadDocument = (file: File) =>
  api.upload<DocumentInfo>("/api/documents", file, 120_000);
```

Import it in Act 1 as `import { api, uploadDocument, type DocumentInfo } from "../lib/api";`
and call it as `uploadDocument(f)`, not `api.uploadDocument(f)`.

- [ ] **Step 2: Carry the choice in run state**

In `ui/src/lib/run.tsx`, extend the interface and provider:

```typescript
interface RunState {
  bundle: EncryptResult | null;
  setBundle: (b: EncryptResult | null) => void;
  documentPath: string | null;
  setDocumentPath: (p: string | null) => void;
  opened: OpenedCopy[];
  addOpened: (c: OpenedCopy) => void;
  leaked: OpenedCopy | null;
  setLeaked: (c: OpenedCopy | null) => void;
  chosenLeaker: string | null;
  setChosenLeaker: (u: string | null) => void;
  reset: () => void;
}
```

Add the two `useState` hooks, include both in the `useMemo` value and its
dependency array, and clear both in `reset()`.

- [ ] **Step 3: Replace the hardcoded document in Act 1**

Delete line 10 (`const DOC = "../demo-docs/tender-evaluation.pdf";`).

Add state and loading alongside the existing identity load:

```typescript
  const [docs, setDocs] = useState<DocumentInfo[] | null>(null);
  const [chosenDoc, setChosenDoc] = useState<DocumentInfo | null>(null);
  const [uploadErr, setUploadErr] = useState<unknown>(null);
  const [uploading, setUploading] = useState(false);
```

In `load()`, fetch documents alongside identities and default to the first:

```typescript
      const [d, ds] = await Promise.all([
        api.get<Identity[]>("/api/identities"),
        api.get<DocumentInfo[]>("/api/documents"),
      ]);
      setIds(d);
      setPicked(d.map((i) => i.user_id));
      setDocs(ds);
      setChosenDoc(ds[0] ?? null);
```

Add the upload handler:

```typescript
  const onUpload = async (f: File) => {
    setUploading(true);
    setUploadErr(null);
    try {
      const info = await uploadDocument(f);
      setDocs((prev) => (prev ? [info, ...prev] : [info]));
      setChosenDoc(info);
    } catch (e) {
      setUploadErr(e);
    } finally {
      setUploading(false);
    }
  };
```

Change `seal()` to use the chosen document and record it:

```typescript
  const seal = async () => {
    if (!chosenDoc) return;
    setBusy(true);
    setSealErr(null);
    try {
      const r = await api.post<EncryptResult>("/api/encrypt", {
        document: chosenDoc.path,
        recipients: picked,
      });
      setBundle(r);
      setDocumentPath(chosenDoc.path);
    } catch (e) {
      setSealErr(e);
    } finally {
      setBusy(false);
    }
  };
```

- [ ] **Step 4: Add the capacity panel and gate the Seal button**

Render above the recipients section:

```tsx
{chosenDoc && (
  <section className="rounded-[var(--card-radius)] border border-line bg-surface p-4">
    <div className="flex items-baseline justify-between gap-3">
      <span className="font-medium">{chosenDoc.display_name}</span>
      <span className="font-mono text-tiny text-ink-faint">
        {chosenDoc.pages} pages
      </span>
    </div>
    <p className="mt-2 text-tiny text-ink-dim">
      Carries <b>{chosenDoc.capacity_bits.toLocaleString()}</b> bits;{" "}
      <b>{chosenDoc.required_bits.toLocaleString()}</b> needed for{" "}
      {picked.length} recipients against 3 colluders.
    </p>
    {chosenDoc.sufficient ? (
      <p className="mt-1 text-tiny text-verified">
        Ready to seal — enough capacity for up to {chosenDoc.max_recipients}{" "}
        recipients.
      </p>
    ) : (
      <p className="mt-1 text-tiny text-[color:var(--danger,#b4242a)]">
        Too little body text to mark safely. The system refuses to issue a copy
        it could not later attribute. Choose the sample document instead.
      </p>
    )}
  </section>
)}
```

Disable Seal when the document is unusable — combine with the existing `enough` check:

```typescript
  const canSeal = !!chosenDoc && chosenDoc.sufficient && picked.length > 0;
```

Use `disabled={busy || !canSeal}` on the seal button.

- [ ] **Step 5: Build the UI to check it compiles**

Run: `cd ui && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 6: Verify by hand**

Start the backend (`python -m uvicorn pqfw_api.main:app --host 127.0.0.1 --port 8000`) and the UI (`cd ui && npm run dev`). On `/distribute`:
- the bundled document appears selected by default, with its capacity shown
- uploading `demo-docs/board-inquiry.pdf` adds it and selects it (2,300 bits)
- uploading a one-page PDF shows the refusal text and disables Seal

- [ ] **Step 7: Commit**

```bash
git add ui/src/lib/api.ts ui/src/lib/run.tsx ui/src/acts/Act1Distribute.tsx
git commit -m "feat: let the operator upload the document sealed in Act 1"
```

---

## Task 6: Act 4 — choosing the leaker

**Files:**
- Modify: `ui/src/acts/Act4Leak.tsx`

**Interfaces:**
- Consumes: `GET /api/ledger/chain` (exists, `attribute.py`), `POST /api/stage-leak` (exists), `RunState.setChosenLeaker` from Task 5.

- [ ] **Step 1: Load candidates from the ledger**

Candidates come from the ledger, not React state, so a direct navigation to
`/leak` still shows a correct list. Add:

```typescript
interface ChainRow { index: number; user_id: string; timestamp: string }

const [candidates, setCandidates] = useState<ChainRow[] | null>(null);
const [pick, setPick] = useState<string | null>(null);

const loadCandidates = async () => {
  try {
    const chain = await api.get<{ records: ChainRow[] }>("/api/ledger/chain");
    // One row per recipient — the most recent open wins.
    const latest = new Map<string, ChainRow>();
    for (const r of chain.records) latest.set(r.user_id, r);
    setCandidates([...latest.values()].sort((a, b) => a.index - b.index));
  } catch (e) {
    setErr(e);
  }
};

useEffect(() => { void loadCandidates(); }, []);
```

- [ ] **Step 2: Rewrite `stage()` to honour the choice**

```typescript
  const stage = async (who: string | null) => {
    setBusy(true);
    setErr(null);
    try {
      // null => let the server choose at random ("Surprise me").
      const source = who ? `${who}-copy.pdf` : undefined;
      const r = await api.post<Surfaced>("/api/stage-leak", { source });
      setItem(r);
      setChosenLeaker(who);   // remembered for Act 5's AFTER-the-fact comparison
      setLeaked(null);        // Act 5 must not inherit an answer from here
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  };
```

Pull `setChosenLeaker` from `useRun()`.

- [ ] **Step 3: Render the chooser**

```tsx
{!item && candidates && (
  <section className="rounded-[var(--card-radius)] border border-line bg-surface p-6">
    <h2 className="text-base font-medium">Whose copy surfaced?</h2>
    <p className="mt-1 text-tiny text-ink-dim">
      Only recipients who actually opened the document appear here — you cannot
      leak a copy that was never made.
    </p>
    <ul className="mt-4 space-y-1.5">
      {candidates.map((c) => (
        <li key={c.user_id}>
          <button
            type="button"
            onClick={() => setPick(c.user_id)}
            className={`flex w-full items-center gap-3 rounded-md border px-3 py-2 text-left
              ${pick === c.user_id ? "border-accent bg-accent/5" : "border-line"}`}
          >
            <span className="font-medium">{c.user_id}</span>
            <span className="ml-auto font-mono text-tiny text-ink-faint">
              ledger #{c.index}
            </span>
          </button>
        </li>
      ))}
    </ul>
    <div className="mt-5 flex flex-wrap gap-2">
      <button type="button" disabled={!pick || busy}
              onClick={() => void stage(pick)}
              className="rounded-md bg-accent px-4 py-2 text-white disabled:opacity-40">
        Stage the leak
      </button>
      <button type="button" disabled={busy}
              onClick={() => void stage(null)}
              className="rounded-md border border-line px-4 py-2">
        Surprise me
      </button>
    </div>
    <p className="mt-3 text-micro text-ink-faint">
      Either way, the next screen is not told. It extracts the mark from the
      file itself.
    </p>
  </section>
)}
```

Keep **Surprise me**: it is the stronger option when a judge suspects the demo
is rigged, because the operator genuinely does not know the answer.

- [ ] **Step 4: Offer the artefact for download**

In the block that renders once `item` exists, add:

```tsx
<a
  href={`/api/download?file=${encodeURIComponent(item.filename)}`}
  className="rounded-md border border-line px-3 py-1.5 text-tiny"
>
  Download this file
</a>
```

`GET /api/download` already accepts a `file` parameter and serves from `DEMO`
(`attribute.py`). A judge can drop this exact file into Act 5's upload control
and reach the verdict independently.

- [ ] **Step 5: Typecheck**

Run: `cd ui && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 6: Verify by hand**

On `/leak`: the list shows only recipients who opened the document; choosing
one and staging produces a file; **Surprise me** works without a selection.

- [ ] **Step 7: Commit**

```bash
git add ui/src/acts/Act4Leak.tsx
git commit -m "feat: let the operator choose whose copy surfaced in Act 4"
```

---

## Task 7: Act 5 — reveal, then compare

**Files:**
- Modify: `ui/src/acts/Act5Attribute.tsx`

**Interfaces:**
- Consumes: `RunState.chosenLeaker` from Task 5, verdict from `/api/attribute-path`.

- [ ] **Step 1: Read the choice without using it**

Pull `chosenLeaker` from `useRun()`. It must not participate in the attribution
request in any way — it is display-only, and only after the verdict renders.

- [ ] **Step 2: Render the comparison after the verdict**

Place this **below** the existing verdict block, so it renders second:

```tsx
{verdict && chosenLeaker && (
  <section className="rounded-[var(--card-radius)] border border-line bg-surface p-4">
    <h3 className="text-sm font-medium">Against the ground truth</h3>
    <dl className="mt-2 grid grid-cols-2 gap-2 text-tiny">
      <dt className="text-ink-faint">You staged</dt>
      <dd className="font-mono">{chosenLeaker}</dd>
      <dt className="text-ink-faint">The system found</dt>
      <dd className="font-mono">
        {verdict.recipient.user_id ?? "— no attribution —"}
      </dd>
    </dl>
    {verdict.recipient.user_id === chosenLeaker ? (
      <p className="mt-2 text-tiny text-verified">
        Match. The name was recovered from the file's own geometry — it was
        never sent to this screen.
      </p>
    ) : (
      <p className="mt-2 text-tiny text-ink-dim">
        These differ. With a margin near the floor the system reports what it
        can support rather than the answer you expected — see the ranking and
        notes above.
      </p>
    )}
  </section>
)}
```

The ordering carries the argument: the verdict first, the ground truth second.
Reversed, the verdict would look like a lookup.

A mismatch is shown honestly. Near `MARGIN_FLOOR` an `INCONCLUSIVE` outcome is
a legitimate result, and suppressing it would misrepresent the tool's own
confidence.

- [ ] **Step 3: Typecheck**

Run: `cd ui && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Verify by hand, end to end**

Upload `demo-docs/board-inquiry.pdf` in Act 1 → open as three recipients in
Act 2 → choose one in Act 4 → Act 5 names that person, and the comparison shows
a match.

Then repeat with **Surprise me** and confirm the comparison block is absent
(no choice was made).

- [ ] **Step 5: Commit**

```bash
git add ui/src/acts/Act5Attribute.tsx
git commit -m "feat: compare verdict against staged choice after revealing it"
```

---

## Task 8: End-to-end test and documentation

**Files:**
- Test: `tests/test_documents.py`
- Modify: `demo_reset.py:32`
- Modify: `RUNNING.md`

- [ ] **Step 1: Write the end-to-end test**

This is the test that proves the feature. Append to `tests/test_documents.py`:

```python
UPLOAD_DOC = ROOT / "demo-docs" / "board-inquiry.pdf"


@pytest.mark.slow
def test_chosen_leaker_is_correctly_attributed(tmp_path):
    """Choose each recipient in turn; attribution must name that person.

    Runs against the engine directly rather than the API so it does not
    depend on demo state. This is the feature's central claim: the operator's
    choice and the system's independent verdict agree, for every recipient,
    without the verdict path ever seeing the choice.
    """
    import shutil

    from pqfw import pipeline
    from pqfw.forensics.investigate import Outcome, investigate
    from pqfw.identity import Keystore
    from pqfw.ledger.node import LedgerNode

    if not UPLOAD_DOC.exists():
        pytest.skip("run: python spike/make_upload_doc.py demo-docs/board-inquiry.pdf")

    users = ["alice", "bob", "carol", "dave", "erin"]
    ks = Keystore(tmp_path / "keys")
    idents = [ks.create(u) for u in users]
    led = LedgerNode(tmp_path / "l.db")

    bundle = tmp_path / "b.pqfw"
    pipeline.encrypt(UPLOAD_DOC, idents, bundle)
    for u in users:
        pipeline.decrypt(bundle, u, ks, led, tmp_path / f"{u}.pdf")

    for chosen in users:
        surfaced = tmp_path / "surfaced.pdf"
        shutil.copy(tmp_path / f"{chosen}.pdf", surfaced)
        v = investigate(surfaced, led)
        assert v.outcome is Outcome.IDENTIFIED, f"{chosen}: {v.outcome} {v.notes}"
        assert v.recipient_user_id == chosen
        assert v.cryptographically_verified

    led.close()
```

Register the marker. `pyproject.toml` already has a `[tool.pytest.ini_options]`
section (line 34) containing only `testpaths`. Add a `markers` key to it —
do not create a second section:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["slow: end-to-end tests that seal and attribute real documents"]
```

- [ ] **Step 2: Run it**

Run: `python -m pytest tests/test_documents.py::test_chosen_leaker_is_correctly_attributed -q`
Expected: PASS. Takes several minutes — it performs five real decryptions and
twenty-five extraction attempts.

*This was verified before the plan was written: 5/5 correct, margins 2.36–2.45.*

- [ ] **Step 3: Correct the ground-truth claim in `demo_reset.py`**

The `LEAKER` constant is now the CLI's ground truth only — the UI chooses.
Change the line at `demo_reset.py:32`:

```python
RECIPIENTS = ["alice", "bob", "carol", "dave", "erin"]
# CLI ground truth only. The UI's Act 4 lets the operator choose the leaker
# (or randomise), so this fixes the answer for `pqfw investigate` against the
# seeded demo/ directory and nothing else.
LEAKER = "carol"
```

- [ ] **Step 4: Update `RUNNING.md`**

Under **The journey**, amend the Act 1 and Act 4 rows:

```markdown
| 1 · Seal | `/distribute` | Upload a document (or use the bundled one), then one encryption, one wrapped key per recipient |
| 4 · Breach | `/leak` | Choose whose copy surfaced — or let it pick at random |
```

Replace the **Ground truth** paragraph:

```markdown
**Ground truth:** In the UI, Act 4 lets you choose whose copy leaked from the
recipients who actually opened it, so you set the answer yourself. *Surprise
me* randomises instead, which is the better choice if someone suspects the
demo is rigged — nobody in the room knows the answer, including you. Act 5 is
never told either way; it extracts the mark from the file. For the CLI path,
`demo_reset.py` prints the ground truth, usually `carol`.

**Uploading your own document:** Act 1 accepts any PDF with a text layer. It
is measured on upload and refused if it cannot carry a full codeword — roughly
six pages of justified body text, or 1,534 bits for five recipients. A slide
deck or a scan will be refused, and the screen says why. `demo-docs/
board-inquiry.pdf` (`python spike/make_upload_doc.py`) is a second document
generated for exactly this purpose: 10 pages, 2,300 bits.
```

- [ ] **Step 5: Run the whole suite**

Run: `python -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add tests/test_documents.py pyproject.toml demo_reset.py RUNNING.md
git commit -m "test: prove each chosen leaker is independently attributed"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| §1 Upload with pre-flight capacity | 1, 2, 3, 5 |
| §2 Choosing the leaker | 6 |
| §3 Honesty guard (4 measures) | 4 (test), 6 (setLeaked null), 7 (ordering) |
| §4 Downloadable artefact | 6 step 4 |
| Scope: files changed | all tasks |
| Testing table | 2, 3, 4, 8 |

Every spec requirement maps to a task. The spec's `wizard.py` note is
explicitly out of scope and is not planned here.

**Placeholders:** none. Every code step contains the actual code.

**Type consistency:** `DocumentInfo` (Task 5) matches the response of
`POST /api/documents` (Task 3) field for field. `documentPath` and
`chosenLeaker` are defined in Task 5 and consumed in Tasks 6 and 7 under the
same names. `analyse()` returns exactly the five keys spread into the endpoint
response.

**Known deviation from the spec:** the spec's `max_recipients: 42` example
assumed the bundled document. Task 2's tests assert relationships
(`>= 5`, monotonic) rather than the literal 42, so they survive a change to
the demo PDF.
