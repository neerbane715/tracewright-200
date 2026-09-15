# Demo Script — PQ-FORENSIC

**Target: 7 minutes.** Every number below is real output from the real pipeline.

---

## Before you start

```bash
pkill -f uvicorn                 # the ledger DB must not be locked
python demo_reset.py             # rebuilds identities, bundle, 5 decryptions
python -m uvicorn pqfw_api.main:app --host 127.0.0.1 --port 8000   # terminal 1
cd web && npm run dev                                              # terminal 2
```

Open `http://127.0.0.1:5173`. **Disconnect the network now** — and say so out loud.
The whole system runs air-gapped; pulling the cable is the most convincing proof.

Ground truth: the leaked file belongs to **carol**. Do not reveal this until step 4.

---

## 1 · The problem (45 s) — no screen

> "A classified report goes to five officers. It's encrypted once; each decrypts
> with their own key. Every copy is byte-for-byte identical. One copy appears on
> a messaging app. Who leaked it?
>
> Access logs don't answer it — an administrator can edit those. A watermark
> that's the same for everyone doesn't answer it either. Five equally plausible
> suspects, no evidence."

## 2 · Distribute (45 s) — **Distribute** tab

Encrypt for all five. Point at the capacity line:

> "26,400 bits of hiding capacity; we need 1,534 for five recipients against
> three colluders. That number comes from Tardos's bound, c²·ln(n/ε). If the
> document were too short, the system refuses to mark it rather than issue a
> copy it can't defend."

## 3 · Decrypt (75 s) — **Receive** tab, decrypt as carol

Read the seven steps as they appear:

> "ML-KEM-768 unwraps the key. Then — and this is the point — decryption is not
> passive. It embeds a mark unique to *this session*, carol signs a record with
> her own ML-DSA private key, and that signed record goes into the ledger
> *before* she gets the file.
>
> She cannot later deny it: only her private key could have produced that
> signature."

Open carol's PDF beside the original. Scroll both.

> "Visually identical. The mark is in the spacing between words, shifted by
> about a third of a point, and the shifts cancel so line width is unchanged.
> Nothing reflows. You cannot see it, and neither can she."

## 4 · The leak (90 s) — **Investigate** tab

Upload `LEAKED-DOCUMENT.pdf`.

> "**carol.** Recovered 1,418 of 1,534 bits, score 951 against a threshold of
> 155 — separation of 2.47 sigma."

Then point at the four seals — **this is the core claim**:

> "Four independent checks. She signed it. The record is provably in the ledger.
> The mark in this file matches the mark she signed for. And the ledger's history
> hasn't been rewritten. All four must hold. This isn't a log entry someone typed
> — it's a cryptographic proof."

## 5 · The administrator attack (90 s) — **Ledger** tab

> "Now the hard question. What if the administrator is the problem?"

Click **Tamper as administrator**. Explain it writes straight to SQLite, bypassing
the whole application — exactly what a privileged insider does.

Click **Check integrity** → tamper detected, located at record #1.

Go back to **Investigate**, upload the same file again:

> "All four seals red. The system refuses to name anyone.
>
> That refusal is the feature. A forensic tool that still produces a confident
> answer from corrupted evidence is worse than useless — it convicts people on
> bad data. We'd rather say *I cannot tell you, and here's exactly why*."

Reset (`demo_reset.py`) if you want a clean state for questions.

## 6 · Close (45 s)

> "Post-quantum throughout — ML-KEM-768 and ML-DSA-65, the NIST standards
> finalised in 2024. No cloud KMS, no public blockchain, no network at all —
> the cable's been out since we started."

---

## Numbers to have ready

| | |
|---|---|
| Watermark capacity | 275 bits/page |
| Bit recovery, clean | 100% (512/512, 0 false positives in 26,400 slots) |
| Attribution, 5 recipients | 5/5 correct |
| False accusations | 0 in 200 random-document trials |
| Survives | re-save, incremental save, optimise, recompress (4/4) |
| Destroyed by | screenshot, print, copy-paste (3/3 — stated limit) |
| ML-KEM encaps, 100 recipients | 0.37 s |
| ML-DSA sign / verify | 38 ms / 10 ms |
| Tamper detection | < 1 s, locates exact record |
| Tests | 23 passing |

## Questions you will be asked

**"What stops a recipient patching the watermark out of your client?"**
> Nothing in software — that's inherent to watermarking at decryption time, and
> it's true of Netflix too. We defend against the opportunistic leaker, which is
> most real leaks. Against a reverse engineer you need hardware attestation; we
> designed the interface for it. But note: if a leaked copy has *no* valid mark,
> that absence is itself evidence, because the ledger records who held decryption
> capability.

**"Why not a real blockchain?"**
> Blockchain solves Byzantine consensus among strangers. Our participants already
> have strong PQ identities and the set is permissioned, so consensus is the
> wrong primitive. We need append-only verifiability — which is Certificate
> Transparency, RFC 6962/9162. That's what secures the web PKI. Less machinery,
> stronger fit.

**"Two recipients compare copies — then what?"**
> Show the ranking. We ran it: alice and bob interleaved their copies, and the
> system named alice, a real colluder. Tardos guarantees catching at least one
> coalition member, not all of them. Be precise: page-interleaving is not a
> bit-level averaging attack, and at c=3 with n=100 the margin narrows — the
> ranking carries more signal than the threshold. We report both.

**"Does the signature prove *she* decrypted it, or that her key did?"**
> Her key. Signatures prove key possession, not human intent. Non-repudiation is
> a legal-procedural construct resting on key-custody obligations, not a
> mathematical one. Anyone who tells you otherwise is overselling.

**"What if the document is a scan or an image?"**
> Out of scope, and we'd tell you before you found out. The mark lives in the
> text layer's geometry. No text layer, no mark. Pixel-domain marking would cover
> it and is the obvious next step.

---

## If something breaks

| Failure | Do this |
|---|---|
| Frontend won't load | Run the CLI demo — same capabilities, rehearse it |
| API crashes | CLI: `python -m pqfw.cli investigate demo/LEAKED-DOCUMENT.pdf` |
| Ledger stuck tampered | `pkill -f uvicorn && python demo_reset.py` |
| Reset says "locked" | The API server is still running; stop it first |
| Machine dies | Screenshots in `spike/out/`, metrics table above |

**The CLI is the real product.** Practise the terminal path until it's as
comfortable as the UI — then nothing on stage can actually stop you.
