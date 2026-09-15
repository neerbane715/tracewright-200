# Implementation Plan — PQ-FORENSIC

**SIH PS 26237** — Cryptographic Attribution and Immutable Decryption Provenance
for Multi-Recipient Encrypted Document Distribution

> Companion to [`SIH26237-analysis.md`](./SIH26237-analysis.md). That document
> covers *why*. This one covers *what to build, in what order, and how to know
> it works*.

---

## 0. Decisions already locked

| Decision | Choice | Rationale |
|---|---|---|
| Core language | **Python 3.12** | Pure-Python PQC (`kyber-py`/`dilithium-py`), PyMuPDF for PDF geometry, numpy for correlation. No native toolchain required anywhere. |
| PQC KEM | **ML-KEM-768** (FIPS 203) via `kyber-py` | NIST Level 3. Pure-Python: no native build, trivially air-gapped. See PHASE0-RESULTS §4. |
| PQC signature | **ML-DSA-65** (FIPS 204) via `dilithium-py` | NIST Level 3. Matches KEM level. Interface kept library-agnostic so liboqs can swap in. |
| Ledger | **CT-style Merkle log** (RFC 6962/9162) | Append-only verifiability, not consensus. See analysis §"Build a hash-chained Merkle log". |
| Watermark primary | **Differential gap-pair spacing**, δ=0.35pt | ✅ Phase 0 measured: 100% recovery, 275 bits/page, survives all PDF-domain attacks. Absolute-width encoding was tested and REJECTED (justification noise σ=0.77pt swamps it). |
| Watermark secondary | **Zero-width / homoglyph** | High capacity, low robustness. Layered, not relied upon. |
| Fingerprint code | **Tardos** (binary, symmetric variant) | Collusion resistance. Length `Ω(c² log n)`. |
| Interface | **FastAPI + React SPA**, CLI underneath | CLI is the real product and the demo-day fallback. |
| Network | **Fully offline** | No cloud, no public chain, no external API. |

### Non-negotiable engineering rules

1. **The CLI must always work standalone.** The web layer is a client of the
   same core functions the CLI calls — never the other way around. If the SPA
   dies on demo day, the demo continues in a terminal.
2. **No component may import from the web layer.** Dependency arrow points one
   way: `web → core`. Enforced by structure, checked in review.
3. **Every crypto operation goes through `pqfw.crypto`.** No library calls
   scattered through the codebase.
4. **Determinism where possible.** Same inputs + same seed = same watermark.
   Makes testing sane.

---

## Phase 0 — Watermark robustness spike ⚠️ **DO THIS FIRST**

> ✅ **COMPLETE — 2026-09-16. Verdict: GO.** Full results in
> [`PHASE0-RESULTS.md`](./PHASE0-RESULTS.md). Key numbers: 275 bits/page,
> 100% recovery, 4/4 PDF-domain attacks survived, 0/3 rasterisation attacks
> survived (accepted scope limit).

### Objective
Determine empirically whether inter-word spacing modulation survives realistic
document handling, and measure achievable bit capacity per page.

### Why first
It is the only component whose feasibility is genuinely unknown. PQC, Merkle
logs, and FastAPI are all known-good. If spacing marks don't survive, we switch
carriers on day one having spent four hours — not day five having spent four days.

### Tasks
- [ ] Generate a realistic multi-page test PDF (dense justified text, ~40 pages)
- [ ] Implement minimal spacing encoder: shift inter-word gaps ±0.3pt to encode bits
- [ ] Implement minimal decoder: measure gaps, recover bits
- [ ] Run the attack gauntlet, measure bit-recovery rate for each:
  | # | Attack | Expected |
  |---|---|---|
  | 1 | Re-save in PyMuPDF | survive |
  | 2 | Re-save in LibreOffice / Acrobat | survive |
  | 3 | Copy-paste text to new doc | partial |
  | 4 | Print-to-PDF | degraded |
  | 5 | Screenshot @100% | likely fail |
  | 6 | Photo of screen | fail |
- [ ] Measure **bits per page** at acceptable error rate
- [ ] Compute required Tardos length for n=100, c=3 → derive minimum document length

### Expected output
A table of recovery rates, a bit-capacity number, and a **go / pivot decision**.

### Validation criteria
- ✅ **GO**: ≥90% bit recovery on attacks 1–3, ≥20 bits/page
- ⚠️ **PARTIAL**: survives 1–2 only → proceed, narrow the robustness claim
- ❌ **PIVOT**: fails attack 1 → switch to homoglyph primary, rescope same day

### Risks
- PDF text extraction may not give reliable gap measurements on all fonts →
  constrain demo docs to a known font set, state it as a limitation.

---

## Phase 1 — Project foundation

### Objective
Repo structure, dependencies, and the interfaces that let 5 people work in parallel.

### Tasks
- [ ] `git init`, `.gitignore`, `pyproject.toml`
- [ ] Package skeleton under `src/pqfw/`
- [ ] Install + smoke-test `kyber-py` + `dilithium-py` (ML-KEM-768 / ML-DSA-65) — ✅ already verified in Phase 0
- [ ] **Lock the record schema** (`docs/SCHEMA.md`) — the JSON structure every
      track depends on
- [ ] **Lock the CLI surface** — command names and arguments, even if unimplemented
- [ ] `pytest` configured, CI-less local test runner

### Dependencies
Phase 0 decision (determines which watermark module gets built).

### Expected output
`pytest` runs green on an empty suite; `pqfw --help` prints the full command list.

### Validation criteria
All five developers can `pip install -e .` and import the package.

### ⚠️ Critical
Schema and CLI signatures must be frozen **before** Phase 2 starts. Changing
them on day 4 is the classic integration disaster.

---

## Phase 2 — PQC crypto layer

### Objective
All post-quantum operations behind one clean module.

### Tasks
- [ ] `pqfw/crypto/kem.py` — ML-KEM-768 encapsulate/decapsulate
- [ ] `pqfw/crypto/sig.py` — ML-DSA-65 keygen/sign/verify
- [ ] `pqfw/crypto/aead.py` — AES-256-GCM content encryption
- [ ] `pqfw/identity.py` — offline identity: keypair generation, local keystore,
      self-signed identity certs (no CA infrastructure — air-gapped)
- [ ] Hybrid envelope: one content key, encapsulated once per recipient
- [ ] Unit tests incl. known-answer tests and tamper-detection tests

### Dependencies
Phase 1.

### Expected output
```
encrypt(doc, [alice_pub, bob_pub]) → bundle
decrypt(bundle, alice_priv)        → plaintext
sign(record, alice_priv)           → signature
verify(record, sig, alice_pub)     → bool
```

### Validation criteria
- Round-trip works for 3+ recipients
- Wrong key fails to decrypt
- Modified ciphertext fails GCM auth
- Modified record fails signature verification

### Risks
🟢 **Resolved in Phase 0.** `liboqs-python` ships no native library and this
environment lacks cmake/MSVC to build it. Using pure-Python `kyber-py` /
`dilithium-py` instead — verified correct against FIPS sizes and fast enough
(100-recipient encapsulation in 0.37s). Keep the module interface
library-agnostic so liboqs can be substituted if asked about production.

---

## Phase 3 — Merkle ledger

### Objective
Append-only, tamper-evident log with cryptographic proofs.

### Tasks
- [ ] `pqfw/ledger/merkle.py` — RFC 6962 tree: leaf/node hashing, root computation
- [ ] Inclusion proof generation + verification
- [ ] Consistency proof generation + verification (**the anti-admin property**)
- [ ] Signed Tree Head (STH), signed with node's ML-DSA key
- [ ] `pqfw/ledger/node.py` — persistent storage (SQLite), append, query
- [ ] Multi-node gossip: STH exchange over local socket, split-view detection
- [ ] **Tamper detection**: recompute tree from stored leaves, compare to STH

### Dependencies
Phase 2 (needs ML-DSA for STH signing).

### Expected output
```
append(record)              → (index, inclusion_proof)
verify_inclusion(...)       → bool
verify_consistency(old,new) → bool
detect_tamper()             → (bool, index_of_first_bad_leaf)
```

### Validation criteria
- Append 1000 records, verify every inclusion proof
- Consistency proof holds across all incremental versions
- **Directly edit a row in SQLite → `detect_tamper()` locates it**
- Two nodes with divergent histories → gossip flags the split view

### Risks
RFC 6962 hashing details are easy to get subtly wrong → test against the RFC's
published test vectors.

---

## Phase 4 — Watermark engine

### Objective
Embed and extract per-recipient forensic marks.

### Tasks
- [ ] `pqfw/watermark/tardos.py` — Tardos code generation + accusation scoring
- [ ] `pqfw/watermark/spacing.py` — embed/extract via `TJ` kerning (per Phase 0)
- [ ] `pqfw/watermark/homoglyph.py` — secondary layer
- [ ] `pqfw/watermark/extract.py` — correlation scoring against candidate codewords
- [ ] Capacity estimator: given a PDF, report max embeddable bits
- [ ] Robustness test harness (automates the Phase 0 gauntlet as regression tests)

### Dependencies
Phase 0 (carrier decision), Phase 1.

### Expected output
```
embed(pdf, codeword)        → watermarked_pdf  (visually identical)
extract(pdf)                → recovered_bits
accuse(bits, all_codewords) → (suspect_id, confidence_score)
```

### Validation criteria
- Visual diff: watermarked vs original shows no perceptible difference
- Extraction recovers ≥90% of bits on unmodified output
- Two different recipients produce different, correctly-attributed marks
- **Collusion test**: average two copies → accusation still names ≥1 real colluder

### Risks
- 🟠 Capacity may be lower than Tardos needs → mitigate by using long demo docs
  and stating the n/c bound honestly
- Extraction false-positive rate must be measured, not assumed

---

## Phase 5 — Pipeline integration (CLI end-to-end)

### Objective
**The complete flow working in a terminal. No UI yet.** This is the moment the
project becomes real.

### Tasks
- [ ] `pqfw encrypt <doc> --recipients a,b,c` → distributable bundle
- [ ] `pqfw decrypt <bundle> --identity a` → performs, in order:
      1. ML-KEM decapsulate → content key
      2. AES-GCM decrypt → plaintext PDF
      3. Generate session-unique Tardos codeword
      4. Embed watermark
      5. Build decryption record
      6. Sign record with recipient's ML-DSA key
      7. Commit to ledger, obtain inclusion proof
      8. Write watermarked PDF + receipt
- [ ] `pqfw investigate <leaked.pdf>` → extract → match → verify → verdict
- [ ] `pqfw ledger verify` / `pqfw ledger tamper-check`
- [ ] Rich terminal output (tables, colors) — this doubles as the fallback demo

### Dependencies
Phases 2, 3, 4. **This is the integration point — schedule it early, not late.**

### Expected output
Full round trip: encrypt → decrypt (×3 recipients) → leak one → identify correctly.

### Validation criteria
- Correct recipient identified from a leaked copy
- Verdict includes: recipient ID, timestamp, signature verification, inclusion proof
- Tampering with the ledger causes verification to fail loudly

---

## Phase 6 — Web layer (FastAPI + React)

### Objective
Visual interface for the demo. **Strictly a client of Phase 5's core.**

### Tasks

**Backend** (`src/pqfw_api/`)
- [ ] FastAPI app wrapping core functions — no business logic here
- [ ] `POST /api/encrypt`, `POST /api/decrypt`, `POST /api/investigate`
- [ ] `GET /api/ledger`, `GET /api/ledger/verify`, `POST /api/ledger/tamper`
- [ ] Server-Sent Events for live pipeline step updates

**Frontend** (`web/`)
- [ ] Vite + React + Tailwind
- [ ] **Sender view** — upload doc, pick recipients, encrypt
- [ ] **Recipient view** — decrypt, watch the 8 pipeline steps animate live
- [ ] **Investigator view** — drop leaked PDF → verdict card with proof chain
- [ ] **Ledger view** — live Merkle tree visualization
- [ ] **Tamper panel** — button that corrupts a record, then shows detection

### Dependencies
Phase 5 complete and stable.

### Validation criteria
- Every UI action maps to a CLI command that works independently
- Killing the frontend does not affect core functionality

### ⚠️ Risk
This phase has the highest scope-creep risk. **Timebox it.** A working ugly UI
beats a half-finished pretty one. If behind schedule, cut views in this order:
Ledger viz → Sender → Recipient → keep Investigator + Tamper (the money shots).

---

## Phase 7 — Testing

### Objective
Prove correctness and know exactly where the boundaries are.

### Test matrix

**Normal cases**
- Single recipient, 3 recipients, 100 recipients
- Small doc (2pp), large doc (100pp)

**Edge cases**
- Document too short to carry the codeword → must fail *gracefully with a clear message*
- Recipient not in the authorized set
- Duplicate decryption by same recipient (new session, new mark)
- Empty / image-only PDF (no extractable text)

**Adversarial**
- Modified ciphertext, forged signature, replayed record
- Direct ledger row edit; ledger row deletion; reordered rows
- Watermark stripped entirely → system reports "no valid mark; tampered client"
- 2-way and 3-way collusion (averaging attack)

**Failure modes**
- Corrupt bundle, missing key, disk full, malformed PDF

### Metrics to report in the demo
| Metric | Target |
|---|---|
| Bit recovery rate (clean) | ≥95% |
| Attribution accuracy | 100% on clean, measured under attack |
| False accusation rate | 0 observed (state sample size) |
| Encrypt time (10MB, 100 recipients) | < 5s |
| Decrypt + watermark + sign + commit | < 3s |
| Investigation (extract + match) | < 5s |
| Ledger tamper detection | < 1s |

---

## Phase 8 — Demo hardening

### Objective
The demo works even when things break.

### Tasks
- [ ] Pre-seed ledger with ~50 realistic records (makes the log look lived-in)
- [ ] Prepare 5 named demo identities with generated keys
- [ ] Pre-generate the leaked document used in the demo
- [ ] `demo_reset.py` — return to clean state in one command
- [ ] Record a screen-capture backup of the full flow
- [ ] Rehearse the CLI-only fallback path end to end
- [ ] Print a one-page metrics sheet for judges

### Demo-day failure plan
| Failure | Fallback |
|---|---|
| Frontend won't build | CLI demo with Rich output — rehearsed |
| Backend crashes | CLI demo |
| Watermark extraction fails live | Use pre-generated leaked doc with known-good mark |
| Machine dies | Screen recording + slides |
| Judge supplies own PDF | Run it — but warn: short docs can't carry full codeword |

---

## Build order summary

```
Phase 0  SPIKE ──────── gates everything
   │
Phase 1  Foundation ─── freezes schema + CLI
   │
   ├─── Phase 2  Crypto      ─┐
   ├─── Phase 3  Ledger      ─┤ parallel
   └─── Phase 4  Watermark   ─┘
              │
Phase 5  CLI integration ── project becomes real
              │
Phase 6  Web layer
              │
Phase 7  Testing
              │
Phase 8  Demo hardening
```

## Team assignment

| Dev | Track | Phases |
|---|---|---|
| 1 | Crypto + identity | 2 |
| 2 | Watermark embed + Tardos | 0, 4 |
| 3 | Watermark extract + robustness | 0, 4, 7 |
| 4 | Merkle ledger + gossip | 3 |
| 5 | Integration, API, UI, demo | 1, 5, 6, 8 |

Devs 2 and 3 pair during Phase 0, then split embed/extract.
Dev 5 owns the schema freeze in Phase 1 — everyone else depends on it.

---

## Definition of done

- [ ] Encrypt once → distribute to N recipients
- [ ] Each decryption produces a visually identical, forensically unique copy
- [ ] Each decryption is ML-DSA-signed by the recipient
- [ ] Each record is committed to the Merkle ledger with an inclusion proof
- [ ] A leaked copy is traced to the correct recipient
- [ ] The verdict carries a verifiable signature + inclusion proof
- [ ] Admin tampering with the ledger is detected and located
- [ ] Everything runs with networking disabled
