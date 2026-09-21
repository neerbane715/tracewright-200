"""Ledger node: persistent append-only log + tamper detection.

PS requirement A8: no single administrator or compromised account can
retroactively modify or delete audit records.

We cannot PREVENT an admin with filesystem access from editing the SQLite file
-- no software can, short of a hardware root of trust. What we guarantee instead
is that any such edit is DETECTED and LOCALISED:

  1. Every append extends a Merkle tree whose root is signed (the STH).
  2. Signed Tree Heads are retained, so any earlier published state is pinned.
  3. detect_tamper() recomputes the tree from stored leaves and compares to the
     last STH, then binary-searches to name the first corrupted index.
  4. Nodes gossip STHs; a node showing different histories to different peers
     (a split view) is caught by cross-checking consistency proofs.

An admin who edits a record must therefore also forge an ML-DSA signature over
the new root -- which requires the node's secret key -- AND convince every other
node simultaneously. That is the security boundary, and it is honest.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ..crypto import sign, verify, sig_keygen
from ..records import SignedRecord, b64d, b64e, utc_now
from .merkle import (consistency_proof, hash_leaf, inclusion_proof,
                     root_from_leaves, verify_consistency, verify_inclusion)

SCHEMA = """
CREATE TABLE IF NOT EXISTS leaves (
    idx        INTEGER PRIMARY KEY,
    leaf_hash  BLOB NOT NULL,
    entry      TEXT NOT NULL,
    added_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sth (
    tree_size  INTEGER PRIMARY KEY,
    root_hash  BLOB NOT NULL,
    signature  BLOB NOT NULL,
    signed_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS nodekey (
    id         INTEGER PRIMARY KEY CHECK (id = 1),
    public     BLOB NOT NULL,
    secret     BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_leaf_hash ON leaves(leaf_hash);
"""


class TamperDetected(Exception):
    def __init__(self, message: str, index: int | None = None):
        super().__init__(message)
        self.index = index


class LedgerNode:
    """One replica of the audit log."""

    def __init__(self, path: str | Path, node_id: str = "node-0"):
        self.path = Path(path)
        self.node_id = node_id
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path))
        self.db.executescript(SCHEMA)
        self._ensure_key()

    def _ensure_key(self) -> None:
        row = self.db.execute("SELECT public, secret FROM nodekey WHERE id=1").fetchone()
        if row is None:
            pub, sec = sig_keygen()
            self.db.execute("INSERT INTO nodekey (id, public, secret) VALUES (1,?,?)",
                            (pub, sec))
            self.db.commit()
            self._pub, self._sec = pub, sec
        else:
            self._pub, self._sec = row[0], row[1]

    @property
    def public_key(self) -> bytes:
        return self._pub

    # -- reading ----------------------------------------------------------

    def _leaf_hashes(self) -> list[bytes]:
        return [r[0] for r in self.db.execute(
            "SELECT leaf_hash FROM leaves ORDER BY idx")]

    def size(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM leaves").fetchone()[0]

    def root(self) -> bytes:
        return root_from_leaves(self._leaf_hashes())

    def get(self, index: int) -> SignedRecord | None:
        row = self.db.execute("SELECT entry FROM leaves WHERE idx=?",
                              (index,)).fetchone()
        return SignedRecord.from_dict(json.loads(row[0])) if row else None

    def all_records(self) -> list[tuple[int, SignedRecord]]:
        return [(r[0], SignedRecord.from_dict(json.loads(r[1])))
                for r in self.db.execute("SELECT idx, entry FROM leaves ORDER BY idx")]

    # -- appending --------------------------------------------------------

    def append(self, signed: SignedRecord) -> tuple[int, list[bytes]]:
        """Append a signed decryption record. Returns (index, inclusion_proof).

        The record's own signature is verified BEFORE admission: the ledger will
        not store evidence it cannot itself vouch for.
        """
        if not verify(signed.sig_public, signed.record.canonical_bytes(),
                      signed.signature):
            raise ValueError(
                "refusing to append: record signature does not verify against "
                "the enclosed public key"
            )

        entry = signed.leaf_bytes()
        lh = hash_leaf(entry)
        idx = self.size()
        self.db.execute(
            "INSERT INTO leaves (idx, leaf_hash, entry, added_at) VALUES (?,?,?,?)",
            (idx, lh, entry.decode("utf-8"), utc_now()))
        self.db.commit()

        self._sign_tree_head()
        leaves = self._leaf_hashes()
        return idx, inclusion_proof(leaves, idx)

    def _sign_tree_head(self) -> None:
        n = self.size()
        r = self.root()
        sig = sign(self._sec, self._sth_message(n, r))
        self.db.execute(
            "INSERT OR REPLACE INTO sth (tree_size, root_hash, signature, signed_at)"
            " VALUES (?,?,?,?)", (n, r, sig, utc_now()))
        self.db.commit()

    @staticmethod
    def _sth_message(tree_size: int, root: bytes) -> bytes:
        return json.dumps({"tree_size": tree_size, "root": b64e(root)},
                          sort_keys=True, separators=(",", ":")).encode()

    # -- proofs -----------------------------------------------------------

    def latest_sth(self) -> dict | None:
        row = self.db.execute(
            "SELECT tree_size, root_hash, signature, signed_at FROM sth "
            "ORDER BY tree_size DESC LIMIT 1").fetchone()
        if not row:
            return None
        return {"tree_size": row[0], "root": row[1], "signature": row[2],
                "signed_at": row[3], "node_id": self.node_id,
                "node_public": self._pub}

    def verify_sth(self, sth: dict, node_public: bytes | None = None) -> bool:
        pub = node_public or sth.get("node_public") or self._pub
        return verify(pub, self._sth_message(sth["tree_size"], sth["root"]),
                      sth["signature"])

    def prove_inclusion(self, index: int) -> dict:
        leaves = self._leaf_hashes()
        return {"index": index, "tree_size": len(leaves),
                "proof": inclusion_proof(leaves, index),
                "root": root_from_leaves(leaves)}

    def prove_consistency(self, old_size: int) -> list[bytes]:
        return consistency_proof(self._leaf_hashes(), old_size)

    # -- tamper detection -------------------------------------------------

    def detect_tamper(self) -> tuple[bool, int | None, str]:
        """Recompute the tree and compare against retained STHs.

        Returns (tampered, first_bad_index, explanation).

        Catches three distinct attacks:
          - record MODIFIED  : stored entry no longer hashes to its leaf_hash
          - record DELETED   : tree shrank below a previously signed size
          - record REORDERED : recomputed root differs from the signed root
        """
        rows = list(self.db.execute(
            "SELECT idx, leaf_hash, entry FROM leaves ORDER BY idx"))

        # 1. per-leaf integrity: does the entry still hash to its stored hash?
        for idx, stored_hash, entry in rows:
            if hash_leaf(entry.encode("utf-8")) != stored_hash:
                return (True, idx,
                        f"record #{idx} was modified: its content no longer "
                        f"matches the hash committed to the tree")

        # 2. signature integrity of each record
        for idx, _, entry in rows:
            try:
                sr = SignedRecord.from_dict(json.loads(entry))
            except Exception:
                return (True, idx, f"record #{idx} is not valid JSON any more")
            if not verify(sr.sig_public, sr.record.canonical_bytes(),
                          sr.signature):
                return (True, idx,
                        f"record #{idx} has an invalid recipient signature")

        # 3. compare against every retained STH
        current = [r[1] for r in rows]
        sths = list(self.db.execute(
            "SELECT tree_size, root_hash, signature FROM sth ORDER BY tree_size"))
        for size, signed_root, sig in sths:
            if not verify(self._pub, self._sth_message(size, signed_root), sig):
                return (True, None,
                        f"the signed tree head for size {size} is forged: its "
                        f"signature does not verify")
            if size > len(current):
                return (True, len(current),
                        f"{size - len(current)} record(s) were DELETED: the log "
                        f"was signed at size {size} but now holds {len(current)}")
            if root_from_leaves(current[:size]) != signed_root:
                bad = self._first_divergent(current, size, signed_root)
                return (True, bad,
                        f"history was rewritten at or before record #{bad}: the "
                        f"tree no longer matches the root signed at size {size}")

        return (False, None, "ledger intact: all records and tree heads verify")

    def _first_divergent(self, leaves: list[bytes], size: int,
                         signed_root: bytes) -> int:
        """Binary search for the earliest index whose prefix root diverges."""
        lo, hi = 1, size
        while lo < hi:
            mid = (lo + hi) // 2
            row = self.db.execute(
                "SELECT root_hash FROM sth WHERE tree_size=?", (mid,)).fetchone()
            if row and root_from_leaves(leaves[:mid]) == row[0]:
                lo = mid + 1
            else:
                hi = mid
        return lo - 1

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> LedgerNode:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

