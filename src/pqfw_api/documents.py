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
