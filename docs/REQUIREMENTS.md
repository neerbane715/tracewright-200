# Requirement Traceability — SIH PS 26237

Every requirement extracted verbatim from the problem statement, mapped to the
component that satisfies it and the test that proves it. **Nothing here may be
silently dropped.** If a requirement cannot be met, it is marked ❌ with the
reason stated openly rather than quietly reinterpreted.

Status: ⬜ not started · 🔨 in progress · ✅ done + tested

---

## A. Key Requirements (explicit list in the PS)

| # | Requirement (verbatim) | Component | Test | Status |
|---|---|---|---|---|
| A1 | Generate a unique, invisible forensic watermark at the moment of decryption | `watermark/`, invoked inside `pipeline.decrypt` | `test_decrypt_embeds_watermark` | ⬜ |
| A2 | Make the watermark specific to each recipient and decryption session | Tardos codeword ⊕ session nonce | `test_two_sessions_differ` | ⬜ |
| A3 | Ensure every decrypted copy is visually identical while remaining forensically distinct | δ=0.35pt, line width preserved (Σδ=0) | `test_visually_identical` (raster diff) | ⬜ |
| A4 | Cryptographically bind each decryption event to the recipient's identity | Record includes recipient pubkey hash + doc hash + wm hash | `test_record_binding` | ⬜ |
| A5 | Use the recipient's own private key to generate a digital signature for the decryption record | `crypto/sig.py`, recipient's ML-DSA secret key | `test_signed_by_recipient` | ⬜ |
| A6 | Use NIST-standardized PQC algorithms instead of classical, for **Key Exchange and Digital Signatures** | ML-KEM-768 (FIPS 203) + ML-DSA-65 (FIPS 204) | `test_no_classical_pk_crypto` | ⬜ |
| A7 | Implement the immutable audit layer using blockchain or DLT | CT-style Merkle log, multi-node | `test_append_only` | ⬜ |
| A8 | Ensure no single administrator or compromised account can retroactively modify or delete audit records | Consistency proofs + multi-node gossip + signed STH | `test_tamper_detected`, `test_split_view_detected` | ⬜ |
| A9 | Extract the forensic watermark from a leaked document | `watermark/extract.py` | `test_extract_from_leak` | ⬜ |
| A10 | Look up the extracted watermark against the immutable ledger | `forensics/investigate.py` | `test_ledger_lookup` | ⬜ |
| A11 | Return a cryptographically verifiable record identifying the recipient | Verdict = record + sig + inclusion proof + STH | `test_verdict_verifiable` | ⬜ |
| A12 | Support complete operation within an offline and air-gapped environment | No network imports; offline check test | `test_no_network_calls` | ⬜ |
| A13 | Have no dependency on external cloud KMS services | Local file keystore only | `test_no_network_calls` | ⬜ |
| A14 | Have no dependency on public blockchain networks | Local Merkle log only | `test_no_network_calls` | ⬜ |

## B. End-to-End Workflow (the 10 numbered steps in the PS)

| # | Step | Implemented by | Status |
|---|---|---|---|
| B1 | Sender encrypts the document and distributes it to authorized recipients | `pqfw encrypt` | ⬜ |
| B2 | An authorized recipient decrypts using their credentials | `pqfw decrypt` | ⬜ |
| B3 | System generates a unique invisible forensic watermark tied to the session | `pipeline.decrypt` step 3 | ⬜ |
| B4 | Recipient signs the decryption record using their PQ private signing key | `pipeline.decrypt` step 6 | ⬜ |
| B5 | Signed record committed to offline tamper-evident ledger | `pipeline.decrypt` step 7 | ⬜ |
| B6 | Recipient receives a visually identical but uniquely fingerprinted document | `pipeline.decrypt` output | ⬜ |
| B7 | If leaked, watermark is extracted from the leaked copy | `pqfw investigate` | ⬜ |
| B8 | Extracted watermark matched against the immutable ledger | `forensics.match` | ⬜ |
| B9 | Associated PQ signature and ledger evidence cryptographically verified | `forensics.verify` | ⬜ |
| B10 | System produces a verifiable record identifying recipient + decryption event | Verdict object | ⬜ |

## C. Deployment Constraint

> "All cryptographic operations, identity management, watermark generation,
> ledger operations, and forensic verification must function without external
> cloud services, cloud KMS infrastructure, or public blockchain networks."

| Area | Satisfied by | Status |
|---|---|---|
| Cryptographic operations | pure-Python ML-KEM/ML-DSA + AES-GCM, no HSM | ⬜ |
| Identity management | local keystore, self-signed PQ identity certs | ⬜ |
| Watermark generation | local PDF processing | ⬜ |
| Ledger operations | local SQLite + Merkle tree, LAN gossip only | ⬜ |
| Forensic verification | fully local | ⬜ |

**Enforcement:** `test_no_network_calls` monkeypatches `socket.socket` to raise,
then runs the full pipeline. Any outbound connection fails the suite.

---

## D. Known scope limits (stated, not hidden)

| Limit | Reason | Where disclosed |
|---|---|---|
| Rasterised leaks (screenshot / print / photo) not attributable | Mark lives in PDF text-layer geometry; rasterisation destroys it | PHASE0-RESULTS §3, demo script |
| Client-side watermarking is patchable by a determined recipient | Inherent to "watermark at moment of decryption" as specified; needs hardware attestation | analysis §1, demo script |
| Short documents cannot carry a full collusion-resistant codeword | Tardos length Ω(c² log n) vs 275 bits/page | capacity check raises a clear error |

**On the third limit:** absence of a valid mark is itself evidence. If a leaked
copy carries no recoverable watermark but the ledger shows who held decryption
capability, the suspect set is still the ledger's recipient list — and a missing
mark proves client tampering.
