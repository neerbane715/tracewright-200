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
