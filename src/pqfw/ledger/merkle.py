"""RFC 6962 Merkle tree -- append-only log with cryptographic proofs.

PS requirements A7/A8: an immutable, tamper-evident audit layer where no single
administrator can retroactively modify or delete records.

WHY THIS AND NOT A BLOCKCHAIN
-----------------------------
Blockchain solves Byzantine consensus among mutually distrusting parties with no
shared identity. Here every participant already holds a strong PQ identity and
the participant set is permissioned, so consensus is the wrong primitive. What
is actually required is APPEND-ONLY VERIFIABILITY: proof that the log has only
ever grown, never been rewritten. That is exactly what Certificate Transparency
provides, and it is what secures the public web PKI.

Two proofs carry the security property:

  inclusion proof   -- "record X is in the log at index i"        O(log n)
  consistency proof -- "log at size m is a PREFIX of log at n"    O(log n)

The consistency proof is the anti-administrator property. If an admin edits or
deletes any historical leaf, the recomputed root diverges and no valid
consistency proof exists between the old published root and the new tree. The
tampering is not merely detectable -- it is LOCATABLE (see node.detect_tamper).

Hashing follows RFC 6962 s2.1 exactly, including the domain-separation prefixes
that prevent second-preimage attacks:
    leaf node     : SHA-256(0x00 || entry)
    internal node : SHA-256(0x01 || left || right)
Without the distinct prefixes an attacker could present an internal node as a
leaf and forge inclusion proofs.
"""
from __future__ import annotations

import hashlib

LEAF_PREFIX = b"\x00"
NODE_PREFIX = b"\x01"


def hash_leaf(entry: bytes) -> bytes:
    return hashlib.sha256(LEAF_PREFIX + entry).digest()


def hash_children(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(NODE_PREFIX + left + right).digest()


def _split(n: int) -> int:
    """Largest power of two strictly less than n (RFC 6962 k)."""
    k = 1
    while k << 1 < n:
        k <<= 1
    return k


def root_from_leaves(leaves: list[bytes]) -> bytes:
    """Merkle Tree Hash (MTH) of a list of already-hashed leaves."""
    if not leaves:
        # RFC 6962: MTH({}) = SHA-256()
        return hashlib.sha256(b"").digest()
    if len(leaves) == 1:
        return leaves[0]
    k = _split(len(leaves))
    return hash_children(root_from_leaves(leaves[:k]),
                         root_from_leaves(leaves[k:]))


def inclusion_proof(leaves: list[bytes], index: int) -> list[bytes]:
    """Audit path proving leaves[index] is in the tree."""
    n = len(leaves)
    if not 0 <= index < n:
        raise IndexError(f"index {index} out of range for {n} leaves")
    if n == 1:
        return []
    k = _split(n)
    if index < k:
        return inclusion_proof(leaves[:k], index) + [root_from_leaves(leaves[k:])]
    return inclusion_proof(leaves[k:], index - k) + [root_from_leaves(leaves[:k])]


def verify_inclusion(leaf: bytes, index: int, tree_size: int,
                     proof: list[bytes], root: bytes) -> bool:
    """Recompute the root from a leaf + audit path. No tree access needed --
    this is what lets an offline investigator verify evidence independently."""
    if not 0 <= index < tree_size:
        return False
    node = leaf
    fn, sn = index, tree_size - 1
    for sibling in proof:
        if fn % 2 == 1 or fn == sn:
            node = hash_children(sibling, node)
            while fn % 2 == 0 and fn != 0:
                fn >>= 1
                sn >>= 1
        else:
            node = hash_children(node, sibling)
        fn >>= 1
        sn >>= 1
    return sn == 0 and node == root


def consistency_proof(leaves: list[bytes], m: int) -> list[bytes]:
    """Prove the tree of size m is a prefix of the current tree.

    This is the proof that no history was rewritten.
    """
    n = len(leaves)
    if not 0 < m <= n:
        raise ValueError(f"invalid consistency range m={m} n={n}")
    if m == n:
        return []
    return _consistency(leaves, m, True)


def _consistency(leaves: list[bytes], m: int, is_full: bool) -> list[bytes]:
    n = len(leaves)
    if m == n:
        return [] if is_full else [root_from_leaves(leaves)]
    k = _split(n)
    if m <= k:
        return _consistency(leaves[:k], m, is_full) + [root_from_leaves(leaves[k:])]
    return _consistency(leaves[k:], m - k, False) + [root_from_leaves(leaves[:k])]


def verify_consistency(old_root: bytes, old_size: int,
                       new_root: bytes, new_size: int,
                       proof: list[bytes]) -> bool:
    """Verify that the log grew from old_size to new_size append-only.

    A False here means history was altered -- the core tamper signal.

    Implements RFC 9162 s2.1.4.2 verbatim. (RFC 6962 defines only how to BUILD
    a consistency proof, not how to verify one; CT v2 added the explicit
    verification algorithm. Deriving it by inspection is error-prone -- this
    followed the published steps.)
    """
    if old_size > new_size or old_size == 0:
        return False
    if old_size == new_size:
        return not proof and old_root == new_root
    if not proof:
        return False

    path = list(proof)
    # step 2: if `first` is an exact power of 2, prepend first_hash
    if old_size & (old_size - 1) == 0:
        path.insert(0, old_root)

    fn, sn = old_size - 1, new_size - 1

    # step 4: right-shift while LSB(fn) is set
    while fn & 1:
        fn >>= 1
        sn >>= 1

    # step 5
    fr = sr = path[0]

    # step 6-8
    for c in path[1:]:
        if sn == 0:
            return False
        if (fn & 1) or fn == sn:
            fr = hash_children(c, fr)
            sr = hash_children(c, sr)
            while fn != 0 and not (fn & 1):
                fn >>= 1
                sn >>= 1
        else:
            sr = hash_children(sr, c)
        fn >>= 1
        sn >>= 1

    # step 9
    return fr == old_root and sr == new_root and sn == 0
