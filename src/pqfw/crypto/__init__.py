"""Post-quantum cryptographic primitives.

PS requirement A6: NIST-standardized PQC for key exchange AND digital
signatures -- no classical public-key crypto anywhere in the trust chain.

  Key encapsulation : ML-KEM-768   (FIPS 203, NIST Level 3)
  Digital signature : ML-DSA-65    (FIPS 204, NIST Level 3)
  Content encryption: AES-256-GCM  (symmetric; quantum-safe at 256-bit)

Note on AES: Grover's algorithm gives at most a quadratic speedup, reducing
AES-256 to ~128-bit effective security, which remains infeasible. Symmetric
crypto does not need replacing -- only the public-key layer does, which is
exactly what ML-KEM and ML-DSA cover here.

All implementations are pure Python (kyber-py / dilithium-py). This is a
deliberate choice for air-gapped deployment: no native build toolchain, no
shared libraries, no platform-specific wheels. The interface below is
library-agnostic so liboqs can be substituted without touching callers.
"""
from .kem import KEM_ALG, kem_keygen, kem_encaps, kem_decaps
from .sig import SIG_ALG, sig_keygen, sign, verify
from .aead import aead_encrypt, aead_decrypt, random_key

__all__ = [
    "KEM_ALG", "kem_keygen", "kem_encaps", "kem_decaps",
    "SIG_ALG", "sig_keygen", "sign", "verify",
    "aead_encrypt", "aead_decrypt", "random_key",
]
