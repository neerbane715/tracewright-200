"""Frozen data contracts.

Every track (crypto, ledger, watermark, forensics) depends on these shapes.
Changing them mid-project breaks all parallel work, so they are defined once,
here, and treated as immutable.

CANONICAL SERIALISATION
-----------------------
Signatures are computed over bytes, so two parties must produce byte-identical
encodings of the same record. We use JSON with sorted keys, no whitespace, and
UTF-8 -- deterministic and human-inspectable during a demo. Binary fields are
base64. `canonical_bytes()` is the ONLY thing that may be signed or hashed.
"""
from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


def b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def b64d(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))


def utc_now() -> str:
    """RFC3339 UTC. Air-gapped machines may have skewed clocks; the ledger's
    append order is authoritative for sequencing, this is human context only."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def sha256(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


# --------------------------------------------------------------------------
# Identity
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class PublicIdentity:
    """A recipient's public identity. Distributed to senders out-of-band.

    No CA, no cloud KMS -- air-gapped deployment means identities are exchanged
    physically and pinned by fingerprint (PS requirement A13).
    """
    user_id: str
    kem_public: bytes      # ML-KEM-768 encapsulation key
    sig_public: bytes      # ML-DSA-65 verification key

    @property
    def fingerprint(self) -> str:
        """Stable short id used in ledger records and UI."""
        return hashlib.sha256(
            self.kem_public + self.sig_public
        ).hexdigest()[:16]

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "kem_public": b64e(self.kem_public),
            "sig_public": b64e(self.sig_public),
            "fingerprint": self.fingerprint,
        }

    @staticmethod
    def from_dict(d: dict) -> "PublicIdentity":
        return PublicIdentity(
            user_id=d["user_id"],
            kem_public=b64d(d["kem_public"]),
            sig_public=b64d(d["sig_public"]),
        )


# --------------------------------------------------------------------------
# Encrypted bundle
# --------------------------------------------------------------------------

@dataclass
class RecipientSlot:
    """One recipient's wrapped copy of the content key."""
    fingerprint: str
    user_id: str
    kem_ciphertext: bytes   # ML-KEM encapsulation
    wrapped_key: bytes      # content key, AES-GCM-wrapped under KEM shared secret
    wrap_nonce: bytes

    def to_dict(self) -> dict:
        return {
            "fingerprint": self.fingerprint,
            "user_id": self.user_id,
            "kem_ciphertext": b64e(self.kem_ciphertext),
            "wrapped_key": b64e(self.wrapped_key),
            "wrap_nonce": b64e(self.wrap_nonce),
        }

    @staticmethod
    def from_dict(d: dict) -> "RecipientSlot":
        return RecipientSlot(
            fingerprint=d["fingerprint"], user_id=d["user_id"],
            kem_ciphertext=b64d(d["kem_ciphertext"]),
            wrapped_key=b64d(d["wrapped_key"]),
            wrap_nonce=b64d(d["wrap_nonce"]),
        )


@dataclass
class Bundle:
    """Broadcast-encrypt container: encrypted once, decryptable independently.

    This is the "encrypt once, distribute to many" model from the PS. The
    document is encrypted a single time under a random content key; that key is
    then encapsulated separately for each recipient via ML-KEM.
    """
    doc_id: str
    doc_name: str
    doc_hash: bytes            # SHA-256 of ORIGINAL plaintext
    ciphertext: bytes          # AES-256-GCM
    nonce: bytes
    slots: list[RecipientSlot]
    created_at: str = field(default_factory=utc_now)
    version: int = 1

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "doc_id": self.doc_id,
            "doc_name": self.doc_name,
            "doc_hash": b64e(self.doc_hash),
            "ciphertext": b64e(self.ciphertext),
            "nonce": b64e(self.nonce),
            "created_at": self.created_at,
            "slots": [s.to_dict() for s in self.slots],
        }

    @staticmethod
    def from_dict(d: dict) -> "Bundle":
        return Bundle(
            doc_id=d["doc_id"], doc_name=d["doc_name"],
            doc_hash=b64d(d["doc_hash"]), ciphertext=b64d(d["ciphertext"]),
            nonce=b64d(d["nonce"]),
            slots=[RecipientSlot.from_dict(s) for s in d["slots"]],
            created_at=d["created_at"], version=d.get("version", 1),
        )


# --------------------------------------------------------------------------
# Decryption record -- the core evidentiary object
# --------------------------------------------------------------------------

@dataclass
class DecryptionRecord:
    """What gets signed by the recipient and committed to the ledger.

    Binds together (PS requirement A4):
      - WHO      : recipient fingerprint + user_id
      - WHAT     : doc_id + hash of the original document
      - WHICH    : watermark codeword hash + session id
      - WHEN     : timestamp
    so that a leaked copy's extracted watermark maps to exactly one record, and
    that record is signed by a key only the recipient holds.

    `watermark_commitment` is a hash, not the codeword itself: publishing raw
    codewords in the ledger would let a recipient look up and forge another's
    mark. The investigator re-derives the codeword from the seed at verification
    time and checks it against this commitment.
    """
    session_id: str
    doc_id: str
    doc_hash: bytes
    recipient_fingerprint: str
    recipient_user_id: str
    watermark_commitment: bytes   # SHA-256(codeword_bits || session_id)
    watermark_seed: bytes         # seed the codeword was derived from
    n_bits: int
    user_index: int               # slot position; needed to re-derive the codeword
    n_users: int                  # codebook size at embed time
    timestamp: str = field(default_factory=utc_now)
    version: int = 1

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "session_id": self.session_id,
            "doc_id": self.doc_id,
            "doc_hash": b64e(self.doc_hash),
            "recipient_fingerprint": self.recipient_fingerprint,
            "recipient_user_id": self.recipient_user_id,
            "watermark_commitment": b64e(self.watermark_commitment),
            "watermark_seed": b64e(self.watermark_seed),
            "n_bits": self.n_bits,
            "user_index": self.user_index,
            "n_users": self.n_users,
            "timestamp": self.timestamp,
        }

    @staticmethod
    def from_dict(d: dict) -> "DecryptionRecord":
        return DecryptionRecord(
            session_id=d["session_id"], doc_id=d["doc_id"],
            doc_hash=b64d(d["doc_hash"]),
            recipient_fingerprint=d["recipient_fingerprint"],
            recipient_user_id=d["recipient_user_id"],
            watermark_commitment=b64d(d["watermark_commitment"]),
            watermark_seed=b64d(d["watermark_seed"]),
            n_bits=d["n_bits"], user_index=d["user_index"],
            n_users=d["n_users"], timestamp=d["timestamp"],
            version=d.get("version", 1),
        )

    def canonical_bytes(self) -> bytes:
        """The exact bytes that are signed. Never sign anything else."""
        return _canonical(self.to_dict())


@dataclass
class SignedRecord:
    """A DecryptionRecord plus the recipient's ML-DSA signature over it.

    This is the ledger leaf. Non-repudiation rests on the signature: only the
    holder of the recipient's ML-DSA secret key could have produced it.
    """
    record: DecryptionRecord
    signature: bytes
    sig_public: bytes      # included so the leaf is self-verifying

    def to_dict(self) -> dict:
        return {
            "record": self.record.to_dict(),
            "signature": b64e(self.signature),
            "sig_public": b64e(self.sig_public),
        }

    @staticmethod
    def from_dict(d: dict) -> "SignedRecord":
        return SignedRecord(
            record=DecryptionRecord.from_dict(d["record"]),
            signature=b64d(d["signature"]),
            sig_public=b64d(d["sig_public"]),
        )

    def leaf_bytes(self) -> bytes:
        """Canonical encoding hashed into the Merkle tree."""
        return _canonical(self.to_dict())
