"""Watermark engine: ties Tardos codewords to the PDF carrier.

This is the layer the pipeline calls. It owns the decisions that must be
consistent between embedding and extraction, above all the derivation of a
session-specific codeword (PS requirement A2).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np
import pymupdf

from . import spacing, tardos


class CapacityError(Exception):
    """Raised when a document cannot carry a usable mark.

    Failing loudly here is deliberate. Silently embedding a truncated codeword
    would produce a document that looks protected but cannot support a
    defensible accusation -- the worst possible outcome for a forensic tool.
    """


@dataclass
class WatermarkPlan:
    """Everything needed to embed, and to reproduce the mark at verification."""
    seed: bytes
    n_bits: int
    user_index: int
    n_users: int
    bits: list[int]

    @property
    def commitment(self) -> bytes:
        """Hash committed to the ledger instead of the raw codeword.

        Publishing raw codewords would let any recipient read another's mark
        out of the ledger and forge it into a document. The commitment lets an
        investigator confirm a match without the ledger ever exposing the code.
        """
        packed = bytes(self.bits)
        return hashlib.sha256(packed + self.seed).digest()


def capacity(pdf_path: str) -> int:
    doc = pymupdf.open(pdf_path)
    try:
        return spacing.capacity(doc)
    finally:
        doc.close()


def plan_for_session(pdf_path: str, session_seed: bytes, user_index: int,
                     n_users: int, n_colluders: int = 3) -> WatermarkPlan:
    """Derive this session's codeword and check the document can carry it.

    The seed is per-session, so the same recipient decrypting twice gets two
    different marks -- satisfying "specific to each recipient AND decryption
    session" rather than only per-recipient.
    """
    need = tardos.required_length(n_users, n_colluders)
    have = capacity(pdf_path)
    if have < need:
        raise CapacityError(
            f"document carries {have} bits but {need} are required for "
            f"{n_users} recipients against {n_colluders} colluders "
            f"(Tardos length ~ c^2*ln(n/eps)). "
            f"Use a longer document (~{need // 275 + 1} pages of body text) "
            f"or lower the collusion target."
        )
    biases = tardos.generate_biases(need, session_seed)
    cw = tardos.codeword(biases, user_index, session_seed)
    return WatermarkPlan(seed=session_seed, n_bits=need, user_index=user_index,
                         n_users=n_users, bits=[int(b) for b in cw])


def embed(pdf_in: str, pdf_out: str, plan: WatermarkPlan) -> int:
    """Embed the plan's codeword. Returns bits actually written."""
    written = spacing.embed(pdf_in, pdf_out, plan.bits)
    if written < plan.n_bits:
        raise CapacityError(
            f"embedded only {written}/{plan.n_bits} bits -- document capacity "
            f"was mis-estimated; refusing to emit a partially marked copy"
        )
    return written


def extract(pdf_path: str, n_bits: int | None = None) -> list[int | None]:
    """Extract raw bits (None = erasure) from a suspect document."""
    return spacing.extract(pdf_path, n_bits)


def identify(pdf_path: str, seed: bytes, n_bits: int, n_users: int,
             eps1: float = 1e-3):
    """Full attribution: extract -> score -> rank.

    Returns (accused_index, scores, threshold, margin, ranking, n_recovered).
    """
    raw = extract(pdf_path, n_bits)
    bits = raw[:n_bits]
    biases, book = tardos.codebook(n_users, n_bits, seed)
    accused, s, thr = tardos.accuse(bits, biases, book, eps1)
    return (accused, s, thr, tardos.margin(s),
            tardos.rank_suspects(bits, biases, book),
            sum(1 for b in bits if b is not None))


def identify_robust(pdf_path: str, seed: bytes, n_bits: int, n_users: int,
                    eps1: float = 1e-3):
    """Attribution that survives excerpts and reordered pages.

    `identify()` reads the document as one bit stream in page order, so it only
    works on a complete, unmodified file. A leaker who shares three pages, or
    whose PDF viewer reordered them, defeats it -- the marks are intact but
    every bit lands at the wrong codeword index.

    This variant extracts each page separately and realigns it. Each page's
    slots occupy a contiguous run of the codeword; the run's starting offset is
    unknown, so we try every plausible offset and keep the best-scoring one.
    Pages are then merged into one sparse bit vector for the normal Tardos
    accusation, with unmatched positions left as erasures.

    Cost is O(pages x offsets) correlations, which is milliseconds at demo
    scale. It is not free, so `identify()` remains the fast path for intact
    documents.
    """
    from . import spacing

    pages = spacing.extract_per_page(pdf_path)
    if not pages:
        return (None, np.zeros(n_users), 0.0, 0.0, [], 0)

    biases, book = tardos.codebook(n_users, n_bits, seed)
    merged: list[int | None] = [None] * n_bits

    for slots in pages:
        if not any(b is not None for b in slots):
            continue
        best_off, best_hits = None, -1
        # A page's run starts at a multiple of the smallest page capacity in
        # practice, but we do not know the original pagination, so scan every
        # offset that could host this many slots.
        for off in range(0, max(1, n_bits - len(slots) + 1)):
            hits = 0
            for j, b in enumerate(slots):
                if b is None:
                    continue
                idx = off + j
                if idx >= n_bits:
                    break
                # correlate against the whole codebook, not one user: the page
                # belongs to SOME recipient and we are only fixing alignment
                if any(book[u][idx] == b for u in range(n_users)):
                    hits += 1
            if hits > best_hits:
                best_hits, best_off = hits, off
        if best_off is None:
            continue
        for j, b in enumerate(slots):
            if b is None:
                continue
            idx = best_off + j
            if idx < n_bits and merged[idx] is None:
                merged[idx] = b

    accused, s, thr = tardos.accuse(merged, biases, book, eps1)
    return (accused, s, thr, tardos.margin(s),
            tardos.rank_suspects(merged, biases, book),
            sum(1 for b in merged if b is not None))
