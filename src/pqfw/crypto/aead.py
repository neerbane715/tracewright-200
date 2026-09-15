"""AES-256-GCM authenticated encryption.

Used for (a) the document body and (b) wrapping content keys under KEM shared
secrets. Authentication matters as much as confidentiality here: a modified
ciphertext or a wrong key must fail loudly, not decrypt to garbage.
"""
from __future__ import annotations

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_LEN = 32     # AES-256
NONCE_LEN = 12   # GCM standard


def random_key() -> bytes:
    return os.urandom(KEY_LEN)


def aead_encrypt(key: bytes, plaintext: bytes,
                 aad: bytes | None = None) -> tuple[bytes, bytes]:
    """Returns (ciphertext_with_tag, nonce)."""
    if len(key) != KEY_LEN:
        raise ValueError(f"key must be {KEY_LEN} bytes, got {len(key)}")
    nonce = os.urandom(NONCE_LEN)
    ct = AESGCM(key).encrypt(nonce, plaintext, aad)
    return ct, nonce


def aead_decrypt(key: bytes, ciphertext: bytes, nonce: bytes,
                 aad: bytes | None = None) -> bytes:
    """Raises cryptography.exceptions.InvalidTag if key/ciphertext/aad differ
    from what was encrypted. That failure IS the integrity check."""
    if len(key) != KEY_LEN:
        raise ValueError(f"key must be {KEY_LEN} bytes, got {len(key)}")
    return AESGCM(key).decrypt(nonce, ciphertext, aad)
