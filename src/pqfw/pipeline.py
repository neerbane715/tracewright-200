"""End-to-end pipeline implementing the PS workflow.

    B1  sender encrypts and distributes                 -> encrypt()
    B2  recipient decrypts with their credentials       -> decrypt()
    B3  unique invisible watermark tied to the session  -> decrypt() step 3
    B4  recipient signs the record with their PQ key    -> decrypt() step 6
    B5  signed record committed to the ledger           -> decrypt() step 7
    B6  recipient receives the fingerprinted document   -> decrypt() output

No network calls anywhere in this module (PS A12/A14).
"""
from __future__ import annotations

import json
import os
import secrets
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from .crypto import (aead_decrypt, aead_encrypt, kem_decaps, kem_encaps,
                     random_key, sign)
from .identity import Keystore
from .ledger.node import LedgerNode
from .records import (Bundle, DecryptionRecord, PublicIdentity, RecipientSlot,
                      SignedRecord, sha256)
from .watermark import engine


class PipelineError(Exception):
    pass


# --------------------------------------------------------------------------
# B1 -- sender side
# --------------------------------------------------------------------------

def encrypt(doc_path: str | Path, recipients: list[PublicIdentity],
            out_path: str | Path, doc_id: str | None = None) -> Bundle:
    """Encrypt once, wrap the content key for each recipient (broadcast-encrypt).

    The document body is encrypted a SINGLE time under a random content key;
    that key is then encapsulated per-recipient with ML-KEM. This is what makes
    every recipient's plaintext byte-identical -- and is precisely why the
    attribution problem exists and the watermark is necessary.
    """
    if not recipients:
        raise PipelineError("at least one recipient is required")

    doc_path = Path(doc_path)
    plaintext = doc_path.read_bytes()
    content_key = random_key()
    ciphertext, nonce = aead_encrypt(content_key, plaintext)

    slots = []
    for r in recipients:
        shared, kem_ct = kem_encaps(r.kem_public)
        wrapped, wnonce = aead_encrypt(shared, content_key,
                                       aad=r.fingerprint.encode())
        slots.append(RecipientSlot(
            fingerprint=r.fingerprint, user_id=r.user_id,
            kem_ciphertext=kem_ct, wrapped_key=wrapped, wrap_nonce=wnonce))

    bundle = Bundle(
        doc_id=doc_id or uuid.uuid4().hex[:12],
        doc_name=doc_path.name,
        doc_hash=sha256(plaintext),
        ciphertext=ciphertext, nonce=nonce, slots=slots)

    Path(out_path).write_text(json.dumps(bundle.to_dict(), indent=1))
    return bundle


# --------------------------------------------------------------------------
# B2-B6 -- recipient side
# --------------------------------------------------------------------------

@dataclass
class DecryptionResult:
    output_path: Path
    record: DecryptionRecord
    signed: SignedRecord
    ledger_index: int
    inclusion_proof: list[bytes]
    bits_embedded: int
    steps: list[str]


def decrypt(bundle_path: str | Path, user_id: str, keystore: Keystore,
            ledger: LedgerNode, out_path: str | Path,
            n_colluders: int = 3,
            progress=None) -> DecryptionResult:
    """The full decrypt-watermark-sign-commit sequence.

    Ordering is security-relevant and deliberate:
      the watermark is embedded BEFORE the record is signed, and the record is
      signed BEFORE it reaches the ledger. So the signature covers the exact
      mark that was embedded, and the ledger never holds an unsigned claim.
    """
    steps: list[str] = []

    def emit(msg: str) -> None:
        steps.append(msg)
        if progress:
            progress(msg)

    bundle = Bundle.from_dict(json.loads(Path(bundle_path).read_text()))

    # --- step 1: locate this recipient's slot
    ident = keystore.public(user_id)
    slot = next((s for s in bundle.slots if s.fingerprint == ident.fingerprint),
                None)
    if slot is None:
        raise PipelineError(
            f"'{user_id}' is not an authorised recipient of this bundle "
            f"(fingerprint {ident.fingerprint} not among "
            f"{len(bundle.slots)} slots)")
    if not keystore.has_secret(user_id):
        raise PipelineError(
            f"no secret key for '{user_id}' on this machine -- decryption "
            f"must run as the recipient")
    kem_sec, sig_sec = keystore.secrets(user_id)
    emit(f"authorised recipient: {user_id} ({ident.fingerprint})")

    # --- step 2: ML-KEM decapsulate, then AES-GCM decrypt
    shared = kem_decaps(kem_sec, slot.kem_ciphertext)
    try:
        content_key = aead_decrypt(shared, slot.wrapped_key, slot.wrap_nonce,
                                   aad=ident.fingerprint.encode())
    except Exception as e:
        raise PipelineError(
            "failed to unwrap the content key -- wrong key, or the bundle was "
            f"modified in transit ({type(e).__name__})") from e
    plaintext = aead_decrypt(content_key, bundle.ciphertext, bundle.nonce)
    emit("ML-KEM-768 decapsulation + AES-256-GCM decryption complete")

    if sha256(plaintext) != bundle.doc_hash:
        raise PipelineError("decrypted content does not match the bundle hash")

    # --- step 3: derive a session-unique watermark (PS B3)
    session_id = uuid.uuid4().hex
    session_seed = secrets.token_bytes(32)
    tmp = Path(tempfile.mkdtemp()) / "plain.pdf"
    tmp.write_bytes(plaintext)

    user_index = next(i for i, s in enumerate(bundle.slots)
                      if s.fingerprint == ident.fingerprint)
    plan = engine.plan_for_session(str(tmp), session_seed, user_index,
                                   len(bundle.slots), n_colluders)
    emit(f"derived session watermark: {plan.n_bits} bits, "
         f"session {session_id[:12]}")

    # --- step 4: embed (PS B3/B6)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    written = engine.embed(str(tmp), str(out_path), plan)
    emit(f"embedded {written} bits -- document is visually identical")
    try:
        tmp.unlink()
        tmp.parent.rmdir()
    except OSError:
        pass

    # --- step 5: build the decryption record (PS A4)
    record = DecryptionRecord(
        session_id=session_id, doc_id=bundle.doc_id, doc_hash=bundle.doc_hash,
        recipient_fingerprint=ident.fingerprint, recipient_user_id=user_id,
        watermark_commitment=plan.commitment, watermark_seed=session_seed,
        n_bits=plan.n_bits)

    # --- step 6: the RECIPIENT signs it with their own ML-DSA key (PS B4/A5)
    signature = sign(sig_sec, record.canonical_bytes())
    signed = SignedRecord(record=record, signature=signature,
                          sig_public=ident.sig_public)
    emit("record signed with recipient's ML-DSA-65 private key")

    # --- step 7: commit to the tamper-evident ledger (PS B5)
    index, proof = ledger.append(signed)
    emit(f"committed to ledger at index {index} "
         f"(tree size {ledger.size()}, root {ledger.root().hex()[:16]}...)")

    return DecryptionResult(
        output_path=out_path, record=record, signed=signed,
        ledger_index=index, inclusion_proof=proof, bits_embedded=written,
        steps=steps)
