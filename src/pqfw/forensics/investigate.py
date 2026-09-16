"""Forensic investigation: leaked document -> verifiable attribution.

    B7  extract the watermark from the leaked copy
    B8  match it against the immutable ledger
    B9  verify the PQ signature and ledger evidence
    B10 produce a verifiable record identifying the recipient

The verdict deliberately distinguishes four outcomes. A forensic tool that only
ever says "it was X" is dangerous; "I cannot tell" must be a first-class answer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import numpy as np

from ..crypto import verify
from ..ledger.merkle import hash_leaf, verify_inclusion
from ..ledger.node import LedgerNode
from ..records import SignedRecord
from ..watermark import engine, tardos


class Outcome(str, Enum):
    IDENTIFIED = "IDENTIFIED"          # single recipient, verified evidence
    INCONCLUSIVE = "INCONCLUSIVE"      # mark found but no confident match
    NO_WATERMARK = "NO_WATERMARK"      # nothing recoverable
    LEDGER_COMPROMISED = "LEDGER_COMPROMISED"


@dataclass
class Verdict:
    outcome: Outcome
    recipient_user_id: str | None = None
    recipient_fingerprint: str | None = None
    session_id: str | None = None
    doc_id: str | None = None
    timestamp: str | None = None
    ledger_index: int | None = None

    score: float | None = None
    threshold: float | None = None
    margin: float | None = None
    bits_recovered: int = 0
    bits_expected: int = 0

    signature_valid: bool = False
    inclusion_valid: bool = False
    commitment_valid: bool = False
    ledger_intact: bool = False

    ranking: list[tuple[str, float]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def cryptographically_verified(self) -> bool:
        """All four independent checks must hold for the verdict to stand."""
        return (self.signature_valid and self.inclusion_valid
                and self.commitment_valid and self.ledger_intact)

    def to_dict(self) -> dict:
        return {
            "outcome": self.outcome.value,
            "recipient": {"user_id": self.recipient_user_id,
                          "fingerprint": self.recipient_fingerprint},
            "event": {"session_id": self.session_id, "doc_id": self.doc_id,
                      "timestamp": self.timestamp,
                      "ledger_index": self.ledger_index},
            "evidence": {
                "signature_valid": self.signature_valid,
                "inclusion_proof_valid": self.inclusion_valid,
                "watermark_commitment_valid": self.commitment_valid,
                "ledger_intact": self.ledger_intact,
                "cryptographically_verified": self.cryptographically_verified,
            },
            "detection": {
                "score": self.score, "threshold": self.threshold,
                "margin": self.margin,
                "bits_recovered": self.bits_recovered,
                "bits_expected": self.bits_expected,
            },
            "ranking": self.ranking,
            "notes": self.notes,
        }


# Below this separation the top suspect is not meaningfully ahead of the field.
# Phase-4 measurement: legitimate single-leaker margins were >1.5; colluded
# documents compressed the gap sharply, so a thin margin is reported as
# inconclusive with a ranking rather than as a confident accusation.
MARGIN_FLOOR = 0.8

# Minimum fraction of codeword positions that must carry signal before we call
# a document marked at all. Measured: a pristine, never-distributed PDF yields
# ~2% of slots above the confidence floor purely from natural spacing
# variation; a genuinely marked copy yields ~90-100%. 25% sits far from both,
# so the classification is not sensitive to where exactly it is set.
COVERAGE_FLOOR = 0.25


def investigate(leaked_pdf: str | Path, ledger: LedgerNode,
                doc_id: str | None = None) -> Verdict:
    """Attribute a leaked document (PS steps B7-B10)."""
    v = Verdict(outcome=Outcome.NO_WATERMARK)

    # --- B9 (first): is the ledger itself trustworthy?
    tampered, bad_idx, msg = ledger.detect_tamper()
    v.ledger_intact = not tampered
    if tampered:
        v.outcome = Outcome.LEDGER_COMPROMISED
        v.notes.append(f"ledger integrity check FAILED: {msg}")
        v.notes.append("attribution withheld: evidence base is unreliable")
        return v
    v.notes.append("ledger integrity verified")

    # --- B8: candidate records to test against
    candidates = [(i, r) for i, r in ledger.all_records()
                  if doc_id is None or r.record.doc_id == doc_id]
    if not candidates:
        v.notes.append("no decryption records in the ledger to match against")
        return v

    # Records from one distribution share a codebook seed only within a
    # session, so each record is tested independently and the strongest
    # verified match wins.
    best = None
    for idx, sr in candidates:
        rec = sr.record
        try:
            accused, scores_, thr, marg, ranking, recovered = engine.identify(
                str(leaked_pdf), rec.watermark_seed, rec.n_bits,
                max(rec.n_users, 2))
        except Exception as e:
            v.notes.append(f"record #{idx}: extraction failed ({type(e).__name__})")
            continue
        # Fast path failed to separate a suspect. The marks may still be
        # intact but misaligned -- an excerpt or a reordered copy shifts every
        # bit. Retry with per-page realignment before giving up. (Both cases
        # were found by the red-team harness, not by the unit tests.)
        if accused is None or marg < MARGIN_FLOOR:
            try:
                r2 = engine.identify_robust(
                    str(leaked_pdf), rec.watermark_seed, rec.n_bits,
                    max(rec.n_users, 2))
                if r2[0] is not None and r2[3] > marg:
                    accused, scores_, thr, marg, ranking, recovered = r2
                    v.notes.append(
                        "document was an excerpt or had reordered pages; "
                        "attribution used per-page realignment")
            except Exception as e:
                v.notes.append(
                    f"realignment pass failed ({type(e).__name__})")

        if recovered == 0:
            continue
        top_score = float(np.max(scores_))
        if best is None or top_score > best[0]:
            best = (top_score, idx, sr, accused, thr, marg, ranking, recovered)

    if best is None:
        v.notes.append(
            "no watermark could be recovered from this document. It may have "
            "been rasterised (screenshot/print), or produced by a client that "
            "bypassed watermarking -- itself evidence of tampering.")
        return v

    top_score, idx, sr, accused, thr, marg, ranking, recovered = best
    rec = sr.record
    v.score, v.threshold, v.margin = top_score, thr, marg
    v.bits_recovered, v.bits_expected = recovered, rec.n_bits
    v.ledger_index = idx
    v.doc_id = rec.doc_id

    # --- B9: verify the evidence chain
    v.signature_valid = verify(sr.sig_public, rec.canonical_bytes(),
                               sr.signature)
    proof = ledger.prove_inclusion(idx)
    v.inclusion_valid = verify_inclusion(
        hash_leaf(sr.leaf_bytes()), idx, proof["tree_size"],
        proof["proof"], proof["root"])

    # Re-derive the codeword from the record's own parameters and check it
    # against the ledger's commitment. This proves the mark we matched is the
    # same one the recipient signed for -- the link between document and record.
    biases = tardos.generate_biases(rec.n_bits, rec.watermark_seed)
    cw = tardos.codeword(biases, rec.user_index, rec.watermark_seed)
    plan = engine.WatermarkPlan(seed=rec.watermark_seed, n_bits=rec.n_bits,
                                user_index=rec.user_index, n_users=rec.n_users,
                                bits=[int(b) for b in cw])
    v.commitment_valid = (plan.commitment == rec.watermark_commitment)

    by_slot = {c[1].record.user_index: c[1].record.recipient_user_id
               for c in candidates}
    v.ranking = [(by_slot.get(i, f"slot{i}"), sc) for i, sc in ranking]

    # --- B10: produce the verdict
    #
    # Distinguish "no mark at all" from "a mark we cannot resolve". An
    # unmarked document still yields a handful of slots whose spacing happens
    # to clear the confidence floor -- measured at 34 of 1534 (2%) on a
    # pristine original. Treating that as a recovered watermark made the system
    # report a COLLUSION for a file that had never been distributed, which is a
    # false and damaging claim.
    coverage = recovered / rec.n_bits if rec.n_bits else 0.0
    if coverage < COVERAGE_FLOOR:
        v.outcome = Outcome.NO_WATERMARK
        v.notes.append(
            f"no watermark is present: only {recovered} of {rec.n_bits} "
            f"positions carried any signal ({coverage:.1%}), which is "
            f"consistent with ordinary variation in unmarked text rather than "
            f"an embedded mark.")
        v.notes.append(
            "this document was either never distributed through the system, "
            "or was rasterised (screenshot, print, photograph), which destroys "
            "the mark entirely.")
        return v

    if accused is None or marg < MARGIN_FLOOR:
        v.outcome = Outcome.INCONCLUSIVE
        v.notes.append(
            f"a watermark was recovered ({recovered}/{rec.n_bits} bits) but no "
            f"single recipient is separated from the field "
            f"(margin {marg:.2f} < {MARGIN_FLOOR}). This is the expected "
            f"signature of a COLLUSION: see the ranking for the likely "
            f"coalition.")
        return v

    v.outcome = Outcome.IDENTIFIED
    v.recipient_user_id = rec.recipient_user_id
    v.recipient_fingerprint = rec.recipient_fingerprint
    v.session_id = rec.session_id
    v.timestamp = rec.timestamp
    if not v.cryptographically_verified:
        v.notes.append(
            "WARNING: attribution matched but part of the evidence chain did "
            "not verify -- treat as unproven")
    return v

