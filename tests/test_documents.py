"""Upload path tests for the operator-chosen document feature.

See docs/superpowers/specs/2026-09-22-upload-and-choose-leaker-design.md
"""
from __future__ import annotations

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
