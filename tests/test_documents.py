"""Upload path tests for the operator-chosen document feature.

See docs/superpowers/specs/2026-09-22-upload-and-choose-leaker-design.md
"""
from __future__ import annotations

from pathlib import Path

import pytest

from pqfw_api.paths import UPLOADS, DEMO


def test_uploads_dir_exists_and_is_inside_demo():
    assert UPLOADS.exists()
    assert UPLOADS.is_dir()
    assert UPLOADS.resolve().is_relative_to(DEMO.resolve())
