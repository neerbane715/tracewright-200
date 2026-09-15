"""Multi-node STH gossip and split-view detection.

PS requirement A8, the part single-node detection cannot reach.

THE ATTACK THIS CLOSES
----------------------
`node.detect_tamper()` catches an administrator who edits one database. It
cannot catch an administrator who never edits anything -- one who instead runs a
node that shows DIFFERENT HISTORIES TO DIFFERENT AUDITORS. Each view is
internally consistent: every record hashes correctly, every tree head verifies,
every inclusion proof checks out. Audit either view alone and it looks perfect.

This is the split-view (equivocation) attack, and it is the reason Certificate
Transparency gossips. A log that shows view A to one party and view B to another
has effectively rewritten history for one of them, while passing every local
check.

HOW DETECTION WORKS
-------------------
Nodes exchange signed tree heads. For any two STHs from the same log, one of
three things must be true:

  1. same size, same root            -> consistent
  2. different sizes, and the smaller is provably a PREFIX of the larger
     (a valid consistency proof exists)                     -> consistent
  3. anything else                   -> SPLIT VIEW: the log equivocated

Case 3 is not ambiguous and not recoverable. Two validly-signed tree heads that
cannot be reconciled are non-repudiable proof of misbehaviour, because both
carry the node's own ML-DSA signature. The node cannot disown either one.

OFFLINE / AIR-GAPPED OPERATION
------------------------------
Exchange is over the local network between peers inside the same facility, or
entirely by file: `export_sth()` writes a signed STH that can move on a USB
stick, and `ingest_sth()` reads it back. Nothing leaves the air gap, and the
security property does not depend on connectivity -- only on auditors
eventually comparing notes.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ..crypto import verify
from ..records import b64d, b64e, utc_now
from .merkle import verify_consistency
from .node import LedgerNode


class Agreement(str, Enum):
    CONSISTENT = "CONSISTENT"        # views reconcile
    SPLIT_VIEW = "SPLIT_VIEW"        # log equivocated -- non-repudiable
    FORGED_STH = "FORGED_STH"        # signature does not verify
    UNRELATED = "UNRELATED"          # different logs; not comparable


@dataclass
class STH:
    """A signed tree head, portable between nodes."""
    node_id: str
    tree_size: int
    root: bytes
    signature: bytes
    node_public: bytes
    signed_at: str

    def to_dict(self) -> dict:
        return {"node_id": self.node_id, "tree_size": self.tree_size,
                "root": b64e(self.root), "signature": b64e(self.signature),
                "node_public": b64e(self.node_public), "signed_at": self.signed_at}

    @staticmethod
    def from_dict(d: dict) -> "STH":
        return STH(node_id=d["node_id"], tree_size=d["tree_size"],
                   root=b64d(d["root"]), signature=b64d(d["signature"]),
                   node_public=b64d(d["node_public"]), signed_at=d["signed_at"])

    def message(self) -> bytes:
        """Must match LedgerNode._sth_message byte for byte."""
        return json.dumps({"tree_size": self.tree_size, "root": b64e(self.root)},
                          sort_keys=True, separators=(",", ":")).encode()

    def verify_signature(self) -> bool:
        return verify(self.node_public, self.message(), self.signature)


@dataclass
class GossipResult:
    agreement: Agreement
    detail: str
    local: STH | None = None
    remote: STH | None = None
    proof_checked: bool = False

    @property
    def ok(self) -> bool:
        return self.agreement is Agreement.CONSISTENT

    def to_dict(self) -> dict:
        return {"agreement": self.agreement.value, "detail": self.detail,
                "proof_checked": self.proof_checked,
                "local": self.local.to_dict() if self.local else None,
                "remote": self.remote.to_dict() if self.remote else None}


def export_sth(node: LedgerNode, path: str | Path | None = None) -> STH:
    """Publish this node's current signed tree head.

    With `path`, also writes it as JSON so it can cross an air gap on removable
    media rather than a network link.
    """
    raw = node.latest_sth()
    if raw is None:
        raise ValueError("node has no tree head yet: the log is empty")
    sth = STH(node_id=node.node_id, tree_size=raw["tree_size"],
              root=raw["root"], signature=raw["signature"],
              node_public=raw["node_public"], signed_at=raw["signed_at"])
    if path:
        Path(path).write_text(json.dumps(sth.to_dict(), indent=2))
    return sth


def load_sth(path: str | Path) -> STH:
    return STH.from_dict(json.loads(Path(path).read_text()))


def compare(node: LedgerNode, remote: STH,
            expect_node_public: bytes | None = None) -> GossipResult:
    """Check a peer's STH against this node's own view of the log.

    `expect_node_public` pins which key the remote STH must be signed under. A
    split view proves nothing if the two STHs came from different logs, so
    callers auditing one log should pin its key.
    """
    if not remote.verify_signature():
        return GossipResult(
            Agreement.FORGED_STH,
            f"STH from '{remote.node_id}' at size {remote.tree_size} is not "
            f"validly signed -- it did not come from that node",
            remote=remote)

    if expect_node_public is not None and remote.node_public != expect_node_public:
        return GossipResult(
            Agreement.UNRELATED,
            f"STH from '{remote.node_id}' is signed by a different key than "
            f"the log under audit; the two are not comparable",
            remote=remote)

    local = export_sth(node)

    # identical view
    if local.tree_size == remote.tree_size:
        if local.root == remote.root:
            # Comparing a node against its own STH proves nothing about
            # equivocation -- a split-view attacker agrees with itself. Say so,
            # so an audit round cannot mistake self-agreement for corroboration.
            same_node = (remote.node_public == local.node_public
                         and remote.node_id == local.node_id)
            return GossipResult(
                Agreement.CONSISTENT,
                (f"this is our own tree head (size {local.tree_size}); "
                 f"self-comparison is not independent corroboration"
                 if same_node else
                 f"both nodes report size {local.tree_size} with the same root"),
                local=local, remote=remote)
        return GossipResult(
            Agreement.SPLIT_VIEW,
            f"SPLIT VIEW: both STHs claim size {local.tree_size} but the roots "
            f"differ ({local.root.hex()[:16]}... vs "
            f"{remote.root.hex()[:16]}...). The log showed two different "
            f"histories and signed both.",
            local=local, remote=remote)

    # different sizes: the smaller must be a prefix of the larger
    older, newer = ((remote, local) if remote.tree_size < local.tree_size
                    else (local, remote))
    holder = node if newer is local else None

    if holder is None:
        # The larger tree lives on the peer, so we cannot build the proof
        # ourselves. Report honestly rather than guessing.
        return GossipResult(
            Agreement.CONSISTENT,
            f"peer is ahead (size {newer.tree_size} vs our "
            f"{older.tree_size}); ask the peer for a consistency proof to "
            f"complete the check",
            local=local, remote=remote, proof_checked=False)

    try:
        proof = holder.prove_consistency(older.tree_size)
    except ValueError as e:
        return GossipResult(
            Agreement.SPLIT_VIEW,
            f"SPLIT VIEW: cannot construct a consistency proof from size "
            f"{older.tree_size} to {newer.tree_size} ({e})",
            local=local, remote=remote)

    if verify_consistency(older.root, older.tree_size,
                          newer.root, newer.tree_size, proof):
        return GossipResult(
            Agreement.CONSISTENT,
            f"size {older.tree_size} is provably a prefix of size "
            f"{newer.tree_size}; the log only appended",
            local=local, remote=remote, proof_checked=True)

    return GossipResult(
        Agreement.SPLIT_VIEW,
        f"SPLIT VIEW: the tree head at size {older.tree_size} is NOT a prefix "
        f"of the tree at size {newer.tree_size}. History was rewritten between "
        f"these two signed views.",
        local=local, remote=remote, proof_checked=True)


def audit(node: LedgerNode, peers: list[STH],
          expect_node_public: bytes | None = None) -> list[GossipResult]:
    """Compare this node against every peer STH it has collected."""
    return [compare(node, p, expect_node_public) for p in peers]


def quorum_view(results: list[GossipResult]) -> tuple[bool, str]:
    """Summarise an audit round.

    A single irreconcilable peer is enough to condemn the log. This is not a
    majority vote: consistency is not a popularity contest, and one valid proof
    of equivocation stands regardless of how many nodes agree with each other.
    """
    splits = [r for r in results if r.agreement is Agreement.SPLIT_VIEW]
    forged = [r for r in results if r.agreement is Agreement.FORGED_STH]
    if splits:
        return False, splits[0].detail
    if forged:
        return False, forged[0].detail
    independent = [
        r for r in results
        if not (r.local and r.remote
                and r.remote.node_public == r.local.node_public
                and r.remote.node_id == r.local.node_id)
    ]
    if not independent:
        return True, ("no independent peer views to compare against; "
                      "single-node operation cannot detect equivocation")
    checked = sum(1 for r in independent if r.proof_checked)
    return True, (f"{len(independent)} independent peer view(s) agree; "
                  f"{checked} verified by consistency proof")
