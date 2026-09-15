"""ML-KEM-768 key encapsulation (FIPS 203).

Replaces classical ECDH/RSA key exchange. Used to wrap the per-document content
key once per recipient, giving the broadcast-encrypt / individually-decrypt
model the PS describes.
"""
from __future__ import annotations

from kyber_py.ml_kem import ML_KEM_768

KEM_ALG = "ML-KEM-768"
KEM_PUBLIC_LEN = 1184
KEM_SECRET_LEN = 2400
KEM_CIPHERTEXT_LEN = 1088
SHARED_SECRET_LEN = 32


def kem_keygen() -> tuple[bytes, bytes]:
    """Return (public_key, secret_key)."""
    ek, dk = ML_KEM_768.keygen()
    return bytes(ek), bytes(dk)


def kem_encaps(public_key: bytes) -> tuple[bytes, bytes]:
    """Encapsulate to a recipient. Returns (shared_secret, ciphertext)."""
    if len(public_key) != KEM_PUBLIC_LEN:
        raise ValueError(
            f"{KEM_ALG} public key must be {KEM_PUBLIC_LEN} bytes, "
            f"got {len(public_key)}"
        )
    ss, ct = ML_KEM_768.encaps(public_key)
    return bytes(ss), bytes(ct)


def kem_decaps(secret_key: bytes, ciphertext: bytes) -> bytes:
    """Recover the shared secret. Returns 32 bytes.

    ML-KEM is IND-CCA2 secure with implicit rejection: a malformed ciphertext
    yields a pseudorandom secret rather than an error. The AES-GCM unwrap that
    follows is what actually detects the failure, via its auth tag.
    """
    if len(ciphertext) != KEM_CIPHERTEXT_LEN:
        raise ValueError(
            f"{KEM_ALG} ciphertext must be {KEM_CIPHERTEXT_LEN} bytes, "
            f"got {len(ciphertext)}"
        )
    return bytes(ML_KEM_768.decaps(secret_key, ciphertext))
