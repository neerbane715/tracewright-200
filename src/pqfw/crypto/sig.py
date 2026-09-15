"""ML-DSA-65 digital signatures (FIPS 204).

Replaces classical ECDSA/RSA signatures. Used by the RECIPIENT to sign their own
decryption record (PS requirement A5), which is what makes the event
non-repudiable and binds it to their identity.
"""
from __future__ import annotations

from dilithium_py.ml_dsa import ML_DSA_65

SIG_ALG = "ML-DSA-65"
SIG_PUBLIC_LEN = 1952
SIG_SECRET_LEN = 4032
SIG_LEN = 3309


def sig_keygen() -> tuple[bytes, bytes]:
    """Return (public_key, secret_key)."""
    pk, sk = ML_DSA_65.keygen()
    return bytes(pk), bytes(sk)


def sign(secret_key: bytes, message: bytes) -> bytes:
    """Sign a message with the recipient's ML-DSA secret key."""
    if len(secret_key) != SIG_SECRET_LEN:
        raise ValueError(
            f"{SIG_ALG} secret key must be {SIG_SECRET_LEN} bytes, "
            f"got {len(secret_key)}"
        )
    return bytes(ML_DSA_65.sign(secret_key, message))


def verify(public_key: bytes, message: bytes, signature: bytes) -> bool:
    """Verify. Returns False on any malformed input rather than raising, so
    callers can treat verification uniformly as a boolean decision."""
    if len(public_key) != SIG_PUBLIC_LEN or len(signature) != SIG_LEN:
        return False
    try:
        return bool(ML_DSA_65.verify(public_key, message, signature))
    except Exception:
        return False
