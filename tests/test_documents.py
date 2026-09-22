"""Upload path tests for the operator-chosen document feature.

See docs/superpowers/specs/2026-09-22-upload-and-choose-leaker-design.md
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import pymupdf

from pqfw_api.paths import UPLOADS, DEMO
from pqfw_api import documents
from pqfw.watermark import tardos


def test_uploads_dir_exists_and_is_inside_demo():
    assert UPLOADS.exists()
    assert UPLOADS.is_dir()
    assert UPLOADS.resolve().is_relative_to(DEMO.resolve())


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


def test_uploaded_display_name_survives_into_listing(client):
    """The operator's filename must persist past the initial response.

    GET /api/documents used to fall back to the stored uuid filename because
    nothing persisted the original name, so a reload made every upload
    indistinguishable. The sidecar JSON fixes that.
    """
    if not TENDER.exists():
        pytest.skip("demo document not generated")
    with TENDER.open("rb") as fh:
        r = client.post("/api/documents",
                        files={"file": ("quarterly-report.pdf", fh,
                                        "application/pdf")})
    assert r.status_code == 200
    doc_id = r.json()["id"]

    listing = client.get("/api/documents").json()
    match = next((d for d in listing if d["id"] == doc_id), None)
    assert match is not None, "uploaded document missing from listing"
    assert match["display_name"] == "quarterly-report.pdf"
    # The security property must still hold: display_name never leaks into path.
    assert "quarterly-report" not in match["path"]


def test_malformed_sidecar_falls_back_without_dropping_the_document(client):
    """A sidecar whose top-level JSON isn't an object must not vanish the
    upload from the listing.

    json.loads() happily parses `[1,2,3]`, `"foo"`, `42`, and `null` as
    valid JSON -- calling .get("display_name") on any of those raises
    AttributeError, not the (OSError, ValueError) that a naive fallback
    might only guard against. If that AttributeError escapes, it propagates
    to list_documents()'s outer `except Exception: continue`, and the whole
    document silently disappears from the picker instead of just showing an
    ugly name. This is the assertion that would have caught that.
    """
    if not TENDER.exists():
        pytest.skip("demo document not generated")
    with TENDER.open("rb") as fh:
        r = client.post("/api/documents",
                        files={"file": ("will-be-tampered.pdf", fh,
                                        "application/pdf")})
    assert r.status_code == 200
    doc_id = r.json()["id"]

    # Simulate tampering / a partial write: valid JSON, wrong top-level shape.
    sidecar = UPLOADS / f"{doc_id}.json"
    sidecar.write_text("[1, 2, 3]")

    listing = client.get("/api/documents").json()
    match = next((d for d in listing if d["id"] == doc_id), None)
    assert match is not None, "malformed sidecar must not drop the document"
    assert match["display_name"] == f"{doc_id}.pdf"


def test_uploads_listing_is_capped(client):
    """GET /api/documents caps the uploads shown, newest first, without
    deleting anything from disk."""
    if not TENDER.exists():
        pytest.skip("demo document not generated")

    n_to_create = documents.UPLOAD_LISTING_CAP + 3
    for _ in range(n_to_create):
        with TENDER.open("rb") as fh:
            r = client.post("/api/documents",
                            files={"file": ("cap-test.pdf", fh,
                                            "application/pdf")})
            assert r.status_code == 200

    on_disk = list(UPLOADS.glob("*.pdf"))
    assert len(on_disk) >= n_to_create, "uploads must not be deleted from disk"

    listing = client.get("/api/documents").json()
    uploaded = [d for d in listing if not d.get("bundled")]
    assert len(uploaded) == documents.UPLOAD_LISTING_CAP


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


UPLOAD_DOC = ROOT / "demo-docs" / "board-inquiry.pdf"


@pytest.fixture(scope="module")
def upload_doc():
    """Ensure demo-docs/board-inquiry.pdf exists, generating it if not.

    That file is gitignored (only tender-evaluation.pdf is allow-listed in
    .gitignore), so on a fresh clone or CI runner it is simply absent. The
    test this feeds is the spec's designated end-to-end proof and must
    actually run rather than silently skip, so build the document instead of
    skipping when it is missing.
    """
    if not UPLOAD_DOC.exists():
        import spike.make_upload_doc as make_upload_doc
        make_upload_doc.build(str(UPLOAD_DOC))
    assert UPLOAD_DOC.exists()
    return UPLOAD_DOC


@pytest.mark.slow
def test_chosen_leaker_is_correctly_attributed(tmp_path, upload_doc):
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


def test_upload_recreates_missing_uploads_dir(client):
    """A wiped uploads/ directory must not turn the next upload into a 500.

    demo_reset.py's cleanup rmtree's all of demo/, including demo/uploads/,
    and (before this fix) nothing recreated it until the process restarted.
    UPLOADS is only created once, at module import, so any later removal was
    permanent for the life of the process -- and POST /api/documents raised
    an uncaught FileNotFoundError writing into a directory that no longer
    existed. The endpoint must now recreate its own directory on demand.

    The backup lives under DEMO (a sibling of UPLOADS) rather than under
    pytest's tmp_path: tmp_path is created on the system temp drive, which on
    Windows CI/dev boxes is routinely a different drive letter than the repo,
    and Path.rename() cannot cross drives.
    """
    if not TENDER.exists():
        pytest.skip("demo document not generated")

    moved_aside = DEMO / "uploads-backup-for-test"
    try:
        assert UPLOADS.exists()
        UPLOADS.rename(moved_aside)
        assert not UPLOADS.exists()

        with TENDER.open("rb") as fh:
            r = client.post("/api/documents",
                            files={"file": ("resurrected.pdf", fh,
                                            "application/pdf")})
        assert r.status_code == 200, r.text
        assert UPLOADS.exists()
    finally:
        # Restore original state: fold back anything the test's own upload
        # left behind, then remove the directory this test created so the
        # next test sees the pre-existing uploads/ contents again.
        if moved_aside.exists():
            if UPLOADS.exists():
                for item in UPLOADS.iterdir():
                    item.rename(moved_aside / item.name)
                UPLOADS.rmdir()
            moved_aside.rename(UPLOADS)


def test_uploads_directory_stays_bounded_after_repeated_uploads(client):
    """Repeated uploads must not let uploads/ grow without bound on disk.

    UPLOAD_LISTING_CAP only ever capped what GET /api/documents *shows*;
    nothing pruned the files themselves, so the directory grew forever (the
    working tree had accumulated dozens of stale PDFs before this fix, since
    demo_reset.py wiping the whole demo/ tree was the only thing that ever
    cleared it). Uploading past the retention cap must prune the oldest
    files -- and their sidecars -- down to the cap, not just hide them from
    the listing.
    """
    if not TENDER.exists():
        pytest.skip("demo document not generated")

    n_to_create = documents.UPLOAD_RETENTION_CAP + 5
    for _ in range(n_to_create):
        with TENDER.open("rb") as fh:
            r = client.post("/api/documents",
                            files={"file": ("bound-test.pdf", fh,
                                            "application/pdf")})
            assert r.status_code == 200

    on_disk_pdfs = list(UPLOADS.glob("*.pdf"))
    on_disk_json = list(UPLOADS.glob("*.json"))
    assert len(on_disk_pdfs) <= documents.UPLOAD_RETENTION_CAP
    # No orphaned sidecars left behind by the prune.
    pdf_stems = {p.stem for p in on_disk_pdfs}
    assert all(j.stem in pdf_stems for j in on_disk_json)
