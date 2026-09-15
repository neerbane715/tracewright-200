# Phase 0 — Spike Results

**Date:** 2026-09-16 · **Status:** ✅ **GO** (with one carrier-scope correction)

Reproduce: `python spike/make_testdoc.py spike/out/original.pdf && python spike/gauntlet.py`

---

## Headline

| Question | Answer |
|---|---|
| Does spacing watermarking work? | **Yes** — 100% bit recovery, clean |
| Capacity | **275 bits/page** (justified 10.5pt Helvetica) |
| Survives PDF-domain handling? | **Yes** — 4/4 attacks at 100% |
| Survives text-layer destruction? | **No** — 0/3, by design |
| PQC available? | **Yes**, pure-Python (see PQC section) |

---

## 1. The finding that changed the design

Initial plan assumed encoding a bit in an **absolute** gap width (±0.3pt).
Measurement killed that immediately:

```
natural inter-word gap: mean 4.159pt, std 0.774pt, range 2.92-5.44
```

Justification noise (σ=0.77) is **2.6× larger** than the intended signal
(0.3pt). Absolute encoding is unrecoverable in justified text.

**Correction — differential encoding.** Each bit uses a *pair* of adjacent gaps
on the same line:

```
bit 1 -> g1 += δ, g2 -= δ
bit 0 -> g1 -= δ, g2 += δ      δ = 0.35pt
decode: bit = sign(g1 - g2)
```

Why it works:
- Justification stretch is **common-mode** across a line and cancels in the difference
- `+δ` and `−δ` sum to zero, so **line width is preserved exactly** — no reflow
- Measured separation: **|g1−g2| = 0.704pt** on marked slots vs ~0.000pt unmarked

This is the core technical insight of the spike. It should be in the pitch.

## 2. Erasure-aware extraction

Naive extraction scored only 77.5%, because it guessed a bit at every slot —
including the 25,888 unmarked ones. Reading sign() of noise is a coin flip.

Fix: slots with `|g1−g2| < 0.35pt` are reported as **erasures (`None`)**, not
guesses.

| | value |
|---|---|
| Slots scanned | 26,400 |
| Marked slots detected | **512 / 512** |
| False positives | **0** |
| Bit accuracy on detected slots | **100.00%** |

Erasures matter downstream: the Tardos accusation stage must weight an erased
slot as "no evidence" rather than 50/50 noise, or a damaged document produces
false accusations.

## 3. Attack gauntlet

```
attack                          bits found   accuracy   verdict
0. no attack (baseline)                512     100.0%   PASS
1. re-save (PyMuPDF)                   512     100.0%   PASS
2. incremental save                    512     100.0%   PASS
3. linearise / optimise                512     100.0%   PASS
4. recompress + clean                  512     100.0%   PASS
5. copy-paste text                       0       0.0%   FAIL
6. print-to-PDF (raster)                 0       0.0%   FAIL
7. screenshot (96dpi)                    0       0.0%   FAIL
```

**The boundary is principled, not flaky:** the mark lives in the PDF text
layer's geometry. Anything preserving that layer preserves the mark perfectly.
Anything destroying it (rasterisation, plain-text extraction) destroys the mark
totally. There is no fragile middle band — a good property, because behaviour is
predictable and explainable to judges.

> ⚠️ Harness bug caught during the run: an attack that *threw an exception* was
> being scored 0.0% and reported as FAIL, making linearisation look like a
> defeated watermark. It was actually `PyMuPDF >=1.26 removed linearisation`.
> The gauntlet now reports `ERROR` separately from `FAIL`. **A broken test must
> never be able to masquerade as a result.**

## 4. PQC stack — plan correction

`liboqs-python` installs but ships **no native library**, and this machine has
no cmake/ninja/MSVC to build it:

```
RuntimeError: No oqs shared libraries found
```

**Switched to pure-Python implementations**, verified against FIPS sizes:

| | `kyber-py` ML-KEM-768 | `dilithium-py` ML-DSA-65 |
|---|---|---|
| Correctness | ✅ encaps/decaps agree | ✅ sign/verify, tamper rejected |
| Sizes | ek 1184, ct 1088, ss 32 | pk 1952, sig 3309 |
| Spec match | FIPS 203 ✅ | FIPS 204 ✅ |

Performance (this laptop):

| op | time |
|---|---|
| ML-KEM keygen / encaps / decaps | 2.8 / 3.7 / 5.0 ms |
| ML-DSA sign / verify | 38.2 / 9.7 ms |
| **100-recipient encapsulation** | **0.37 s** |

Well inside plan targets. **This is a net positive for the project:** no native
build step, no DLL, trivially air-gapped, runs anywhere Python runs. Keep the
crypto module's interface library-agnostic so liboqs can be swapped in later if
a judge asks about production hardening.

---

## Decisions locked by this spike

1. **Differential gap-pair encoding**, δ=0.35pt — not absolute width
2. **Erasure-aware extraction** with a 0.35pt confidence floor
3. **Spacing = primary carrier**, scoped to digital PDF redistribution
4. **`kyber-py` + `dilithium-py`**, behind a swappable interface
5. **Claim scope:** digital forwarding of the PDF. Rasterised leaks
   (screenshot/print/photo) are explicitly out of scope — state this, do not
   let a judge discover it

## Consequences for the plan

- Phase 4 builds the differential encoder, not the absolute one
- Tardos stage must consume **erasures**, not just bits
- Phase 2 targets pure-Python PQC; drop the liboqs build task
- Demo documents must be text-layer PDFs, and **long** — at 275 bits/page a
  40-page doc carries ~11,000 bits, ample for Tardos at n=100, c=3
- A second carrier (homoglyph) adds capacity but not rasterisation robustness;
  it remains optional, not a fix for the FAIL rows
