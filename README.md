# PQ-FORENSIC

Post-quantum cryptographic attribution and immutable decryption provenance for
multi-recipient encrypted document distribution.

**SIH PS 26237.** A document is encrypted once and decrypted independently by
many recipients. Every plaintext is byte-identical, so a leak implicates
everyone equally. This system makes each decrypted copy forensically unique,
binds the decryption to the recipient's post-quantum identity, and records it in
a ledger that a privileged administrator cannot quietly rewrite.

Runs entirely offline. No cloud KMS, no public blockchain, no network.

---

## What it does

```
sender                recipient                      investigator
------                ---------                      ------------
encrypt once     ->   ML-KEM decapsulate
for N people          AES-GCM decrypt
                      embed session watermark   ->    extract watermark
                      sign record (ML-DSA)            match against ledger
                      commit to Merkle ledger         verify signature
                      receive marked copy             verify inclusion proof
                                                      -> named recipient
```

## Quick start

```bash
pip install -e ".[api,dev]"
python spike/make_testdoc.py spike/out/original.pdf   # sample 96-page document
python demo_reset.py                                  # identities + 5 decryptions

python -m pqfw.cli ledger list
python -m pqfw.cli investigate demo/LEAKED-DOCUMENT.pdf
python -m pqfw.cli ledger verify
```

Web console (optional — the CLI is the full product):

```bash
python -m uvicorn pqfw_api.main:app --host 127.0.0.1 --port 8000
cd web && npm install && npm run dev      # http://127.0.0.1:5173
```

## How it works

**Post-quantum crypto.** ML-KEM-768 (FIPS 203) wraps the content key once per
recipient; ML-DSA-65 (FIPS 204) signs each decryption record. Pure Python, so
there is no native toolchain to install on an air-gapped machine.

**The watermark** modulates inter-word spacing *differentially*: each bit shifts
one gap `+0.35pt` and the next `−0.35pt`. Justification stretch is common-mode
across a line and cancels in the difference, and since the shifts sum to zero,
line width is unchanged and nothing reflows. Absolute-width encoding was tried
first and measured as unrecoverable — natural gap variance (σ=0.77pt) is 2.6×
any perceptually safe signal.

**Collusion resistance** uses Tardos fingerprinting codes, sized by the
`c²·ln(n/ε)` bound. Documents too short to carry a full codeword are refused
rather than half-marked.

**Split-view detection.** Nodes exchange signed tree heads, over the LAN or on a
USB stick. Two STHs from one log must either match or be reconcilable by a
consistency proof; anything else is non-repudiable proof the log equivocated,
since both carry the node's own ML-DSA signature.

**The ledger** is a Certificate-Transparency-style append-only Merkle log
(RFC 6962, verification per RFC 9162). Not a blockchain: consensus among
strangers is the wrong primitive when every participant already holds a strong
PQ identity. What is needed is append-only verifiability, and inclusion plus
consistency proofs provide exactly that.

## Measured results

| | |
|---|---|
| Watermark capacity | 275 bits/page |
| Bit recovery, clean | 100% (0 false positives in 26,400 slots) |
| Attribution, 5 recipients | 5/5 correct |
| False accusations | 0 in 200 random-document trials |
| Survives | re-save, incremental save, optimise, recompress |
| Destroyed by | screenshot, print-to-PDF, copy-paste |
| ML-KEM encapsulation, 100 recipients | 0.37 s |
| ML-DSA sign / verify | 38 ms / 10 ms |
| Tests | 33 passing |

## Limits, stated plainly

- **Rasterised leaks are not attributable.** The mark lives in the PDF text
  layer's geometry. A screenshot or photograph destroys it completely. Covering
  that needs pixel-domain marking.
- **A determined recipient can patch the client.** Watermarking happens on the
  recipient's machine, as the problem statement requires, so the marking code
  runs where the adversary has control. Real defence needs hardware attestation.
  Note though that a leaked copy with *no* valid mark is itself evidence: the
  ledger still records who held decryption capability.
- **Signatures prove key possession, not human intent.** Non-repudiation here is
  a legal-procedural property resting on key-custody obligations, not a
  mathematical one.
- **Gossip requires at least two honest nodes.** Split-view detection compares
  tree heads across nodes; a single node cannot detect its own equivocation, and
  the system says so rather than reporting false confidence.

## Layout

```
src/pqfw/
  crypto/        ML-KEM, ML-DSA, AES-GCM behind one swappable interface
  watermark/     differential spacing carrier + Tardos codes
  ledger/        RFC 6962 Merkle tree + tamper detection
  forensics/     leak -> verdict
  records.py     frozen schema; canonical bytes for signing
  pipeline.py    the PS workflow, end to end
  cli.py
src/pqfw_api/    FastAPI wrapper (thin client of the above)
web/             React investigator console
docs/            analysis, plan, requirements traceability, demo script
spike/           Phase 0 validation code (kept: it documents the measurements)
```

## Documentation

- **[How it works](docs/how-it-works.html)** — visual walkthrough for newcomers; open in a browser
- [Analysis](docs/SIH26237-analysis.md) — problem, risks, approach comparison
- [Implementation plan](docs/IMPLEMENTATION-PLAN.md) — phases, team split
- [Phase 0 results](docs/PHASE0-RESULTS.md) — the measurements that set the design
- [Requirements](docs/REQUIREMENTS.md) — every PS requirement → test
- [Demo script](docs/DEMO-SCRIPT.md) — 7-minute walkthrough + judge questions
