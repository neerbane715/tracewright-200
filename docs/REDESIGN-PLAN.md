# Product Redesign Plan

**Scope:** product name, frontend rebuild, end-to-end UX. The Python crypto core
is not rearchitected. Backend touched only where the current API blocks a
required UX step — every such change is listed and justified below.

---

## 1 · Audit findings

Read before designing: `src/pqfw/` (crypto, watermark, ledger, forensics,
pipeline), `src/pqfw_api/main.py`, `src/pqfw_api/wizard.py`, `web/src/`.

### What is real

Verified by running it, not by reading it:

| Claim | Status | Evidence |
|---|---|---|
| ML-KEM-768 key encapsulation | **real** | `kyber_py.ml_kem`, pure Python, FIPS 203 sizes (ek 1184 / ct 1088) |
| ML-DSA-65 signatures | **real** | `dilithium_py.ml_dsa`, FIPS 204, sig 3309 B |
| Watermark embed + extract | **real** | differential inter-word spacing, ±0.35pt, `watermark/spacing.py` |
| Merkle ledger + proofs | **real** | RFC 6962 build, RFC 9162 verification, `ledger/merkle.py` |
| Tamper detection | **real** | writes directly to SQLite, then recomputes tree |
| Forensic attribution | **real** | 1534/1534 bits recovered *from the file*, margin 2.46, names `carol` |

Measured just now on the live pipeline:

```
investigate(demo/LEAKED-DOCUMENT.pdf)
  -> IDENTIFIED · carol · 9.5 s
     bits recovered from the file: 1534 / 1534
     score 1022 vs threshold 162, margin 2.46
     ranking: carol 1022 · erin 15 · bob 14
     signature ✓  inclusion ✓  commitment ✓  ledger ✓
```

**The watermark mechanism, stated precisely** (the UI must depict this and
nothing more): each bit is carried by a *pair* of adjacent word gaps on one
line — one widened by 0.35pt, the next narrowed by the same amount. The two
nudges sum to zero, so line width is unchanged and nothing reflows. Decoding
reads `sign(gap1 − gap2)`. It is **not** metadata, **not** font substitution,
**not** invisible characters. Capacity ≈ 275 bits/page.

### What is NOT real — must be fixed before it ships

**Finding 1 — the wizard's Act 5 does not extract anything.**

`wizard.py` runs the genuine `investigate()` in **stage4**, caches the verdict,
and `stage5` is a *string comparison* against that cached value:

```python
# wizard.py:168
if body.watermark != _state["leaked_watermark"]:
    return {"found": False}
```

And the frontend hands stage5 the value stage4 just gave it:

```js
// Wizard.jsx:28
(all) => api.post("/api/wizard/stage5", { watermark: all[3].leaked_watermark })
```

The screen labels this **"Extracted watermark"**. Nothing was extracted at that
step. This is exactly the class of claim the brief forbids. The real extraction
*is* available and *does* work — it is simply invoked one stage too early and
then replayed from memory.

**Fix:** Act 5 calls a real extraction endpoint against the uploaded/selected
leaked file. Stage4 becomes *"a file surfaced"* and must not pre-compute the
answer. Confirmed feasible: the real call returns a correct, fully-verified
attribution in 9.5 s.

**Finding 2 — `W_alice_3f9c21` is a display string, not the watermark.**

`wizard.py:106` builds `f"W_{u}_{...commitment.hex()[:6]}"`. The real artifact
is a 1534-bit Tardos codeword plus a 32-byte commitment hash. The label is fine
as a *human handle* but must be presented as one, with the real commitment
available underneath — not captioned as though it were the mark itself.

**Finding 3 — `Sig_alice_a1b2c3d4` likewise.** The real signature is 3309 bytes.
Show `ML-DSA-65 · 3309 B · a1b2c3d4…` with the full value on demand.

**Finding 4 — block numbers are cosmetic.** `100 + ledger_index` is invented for
looks. Real ledger indices are 0-based. Show the real index.

**Finding 5a — connection failures are indistinguishable from product failure.**

Observed live (user screenshot): the wizard renders a bare red
**"Failed to fetch"** under the stage rail when the API is unreachable.
Reproduced by stopping uvicorn — the proxy returns 500 and the UI shows that
string with no explanation, no retry, and no indication that a *server* is
missing rather than the product being broken. The frontend fires stage1 on
mount with `.catch(() => {})` (`Wizard.jsx:55`), so a race at startup silently
produces a dead screen.

For a live jury demo this is the worst possible failure mode: it looks like the
product does not work. **Fix:** distinguish transport failure from application
error, state plainly that the backend is not reachable, offer retry, and
auto-retry briefly on mount so a startup race self-heals.

**Finding 5b — leaked local paths reach the user.** `wizard.py:70` raises
`f"could not clear {HOME}"`, surfacing `D:\Code\SIH26237\demo\wizard-data`. Root
cause is a Windows file lock when the server holds the SQLite handle. Fix both:
handle the lock properly, and never put a filesystem path in a user-facing
string.

### Data the backend already produces and the UI throws away

All of this is free — it is returned today and discarded:

- `ranking` — every recipient's score. **The single most persuasive artifact in
  the product**: `carol 1022 · erin 15 · bob 14` shows attribution is not a
  coin-flip. Currently unused.
- `score` / `threshold` / `margin` — how far past the accusation bar.
- `bits_recovered / bits_expected` — 1534/1534 proves recovery quality.
- `notes` — plain-language explanation of *why* a verdict came out that way.
- Merkle `proof` path — `/api/ledger/proof/{index}` exists and is never called.
- `capacity_bits` / `required_bits` — the Tardos sizing argument.
- Per-record inclusion proofs, STH signature bytes, gossip/split-view results.

### Recipients

`alice / bob / carol / dave / erin` with pre-provisioned ML-KEM + ML-DSA
keypairs in a local keystore (`demo/pqfw-data/keys/`). Keys are **real**, created
by `Keystore.create()`. Key provisioning is legitimately out of scope for the
demo, but the identities should be presented as cryptographic identities
(fingerprint = SHA-256 over both public keys, truncated to 16 hex) rather than
as names in a table.

### Air-gap violation in the current build

`web/index.html` loads IBM Plex from `fonts.googleapis.com`. On an air-gapped
machine this fails and the UI falls back to system fonts. The problem statement
makes offline operation a hard requirement, so **fonts must be vendored**.

### Existing endpoints

`/api/identities` · `/api/encrypt` · `/api/decrypt` · `/api/investigate` ·
`/api/ledger` · `/api/ledger/verify` · `/api/ledger/proof/{index}` ·
`/api/ledger/sth` · `/api/ledger/gossip` · `/api/ledger/tamper` ·
`/api/wizard/stage1‑5`

---

## 2 · The name

Requirements: evoke attribution-by-invisible-mark-at-decryption, not "we use
PQC"; no `Secure-`/`-Shield`/`-Guard`; no algorithm names in the brand; works
spoken in a jury pitch; no prevention metaphors (this attributes, it does not
block).

| Name | Rationale |
|---|---|
| **Tracewright** | A *wright* makes things; this one manufactures traceability at the moment of decryption. Not a blocker — a maker of provenance. Unusual, ownable, easy to say. |
| **Silt** | Sediment settles invisibly into a document as it passes through a hand, and later reveals where it has been. Short, memorable, zero security-vendor baggage. |
| **Attest** | Plain English for "bear witness." Each decryption attests to itself with the recipient's own key. Very clear; slightly generic. |
| **Provenire** | Latin root of *provenance* — "to come forth." Scholarly, evokes chain of custody. Risks sounding like a wine startup. |
| **Inkwell** | Where invisible ink comes from; the mark is drawn per reader. Warm and non-technical, but leans decorative. |

### Recommended: **Tracewright**

> **Tracewright** — *Every copy remembers who opened it.*

The tagline states the mechanism (per-decryption marking), the consequence
(memory / evidence), and implies non-repudiation, in seven words with no jargon.
It works as a spoken opener: *"We built Tracewright. When a document leaks,
Tracewright tells you which recipient's copy it was — and proves it."*

Implemented as one config constant:

```ts
// web/src/brand.ts
export const PRODUCT_NAME = "Tracewright";
export const PRODUCT_TAGLINE = "Every copy remembers who opened it.";
export const PRODUCT_SUBTITLE = "ML-KEM-768 · ML-DSA-65 · air-gapped";
```

Used in: browser tab title, wordmark, Act 0, exported verdict report, footer.
**No Python module, folder, or service rename** — `pqfw` stays as the internal
identity. The name is a brand concern, not a codebase-identity concern.

---

## 3 · Information architecture

Six routes, one continuous journey, persistent progress rail across all.

| Route | Act | Purpose |
|---|---|---|
| `/` | 0 · Brief | The scenario in plain words. Technical-depth toggle. |
| `/distribute` | 1 · Seal | Document → one encryption → N sealed keys |
| `/open` | 2 · Open | Play a recipient; watch provenance being created |
| `/ledger` | 3 · Record | Chain view; tamper and watch it break |
| `/leak` | 4 · Breach | A file surfaces. Context, not a file picker. |
| `/attribute` | 5 · Verdict | Real extraction → ledger → chain of evidence |

**Technical-depth toggle** — a lens, never a gate. Persisted to `localStorage`,
respected on every Act. Off: plain-language only. On: algorithm names, byte
lengths, real hex values, the actual request/response for that action, and a
"verify this yourself" action where one exists.

**Recipient colour identity** — each recipient gets one hue, used everywhere
they appear (sealed key in Act 1, their card in Act 2, their ledger block in
Act 3, their bar in the Act 5 ranking). A viewer tracks "carol" visually across
the whole story. Chosen for ≥3:1 contrast on both themes and distinguishable
under the common colour-vision deficiencies.

---

## 4 · Design direction

**Instrument, not dashboard.** The reference point is lab equipment and evidence
handling, not SaaS. Dense where data matters, quiet everywhere else.

- **Type** — Inter (UI) + JetBrains Mono (all cryptographic material).
  **Vendored locally**, not CDN. Mono is load-bearing: hashes must be
  comparable character by character.
- **Colour** — near-black ground `#0B0E14`; one accent (`#3B82F6`) for the
  active path; semantic green/amber/red reserved *exclusively* for verification
  outcomes, never decoration. Per-recipient hues are a separate scale.
- **Cryptographic material pattern** — used everywhere, no exceptions:
  `label · truncated-hash · [copy] · [expand]`. Never a bare hex dump.
- **Motion** — only to show state changing (a key sealing, a hash breaking). No
  decorative entrances.
- **States** — every async action has explicit loading / empty / error /
  success. Act 5's extraction takes **9.5 s**; that needs a real progress
  treatment showing *what is happening*, not a spinner.

---

## 5 · Backend changes

Minimal, and only where the current API blocks a required UX step.

| # | Change | Why it is required |
|---|---|---|
| B1 | `POST /api/attribute` — real extraction against an uploaded or named file, returning `ranking`, `score`, `threshold`, `margin`, `bits_*`, `notes`, all four evidence flags, and the Merkle proof | Act 5 must perform a genuine extraction. Today `wizard/stage5` replays a cached answer. **This is the single most important change in the plan.** |
| B2 | `GET /api/event/{index}` — the full signed record for one decryption: canonical bytes, signature, public key, inclusion proof | Act 2's technical layer must show the real signature, and Act 5 must confirm *the same* signature. Cross-Act consistency is unverifiable without it. |
| B3 | `POST /api/verify-signature` — verify a supplied record+signature+key, server-side, returning the boolean and what was checked | "Verify it yourself" must actually verify. Otherwise the depth layer is decoration. |
| B4 | SSE or staged progress on decrypt | Act 2 shows six pipeline steps; today they arrive as one array after the fact. Needed to show provenance being created rather than reported. |
| B5 | Fix `wizard.py` path leakage + lock handling | Finding 5b. User-facing strings must never contain filesystem paths. |
| B7 | Frontend: typed transport-vs-application error handling, retry, startup grace | Finding 5a. A missing backend must never read as a broken product during a jury demo. |
| B6 | Vendor fonts; drop the Google Fonts link | Finding: air-gap violation. Hard requirement. |

Everything else the new UI needs already exists. `wizard.py` is superseded by
B1/B2 and will be retired rather than extended — keeping it would leave a
second, misleading code path in the repo.

---

## 6 · Stack

**React 18 + TypeScript + Vite + Tailwind + React Router.** Justification:
Vite and React are already in the repo and working; TypeScript because the
backend returns richly-shaped verdict objects and silent field drift is exactly
how a UI ends up lying about crypto; Tailwind for a consistent spacing/type
scale without a component library's weight. **No component library** — the
component count here is small and bespoke; shadcn/ui would add a dependency
surface for four or five widgets.

Everything bundled. No runtime CDN. Verified offline before sign-off.

---

## 7 · Build order

Each Act ships working end-to-end against the live backend before the next
begins. No "build all UI, wire data later."

1. **Foundations** — brand constants, vendored fonts, design tokens, depth
   toggle, crypto-material component, API client with typed responses
2. **B1 + B2 + B3** — the endpoints Acts 2 and 5 depend on, with tests
3. **Act 0** — Brief
4. **Act 1** — Seal *(verify against real `/api/encrypt`)*
5. **Act 2** — Open *(real decrypt, real signature shown)*
6. **Act 3** — Record *(real ledger, real tamper, real failure explanation)*
7. **Act 4** — Breach
8. **Act 5** — Verdict *(real extraction — the critical one)*
9. **Retire** `wizard.py` and the old `App.jsx`
10. **Full test pass** per §8 of the brief

---

## 8 · Test plan

Reported honestly, including anything that cannot be proven.

- Two recipients, full happy path, **twice**
- Byte-diff the two decrypted files: confirm distinct, confirm the difference
  sits in the text-positioning operators, confirm identical rendering
- Ledger: clean append passes; tamper fails; **the UI's stated reason matches
  what actually broke** (which record, which hash)
- Attribution closed for real, both recipients, distinct correct answers
- Negative: untouched original → *no watermark*, not a false match
- Robustness tested to the **measured** bar, not an assumed one: survives
  re-save / optimise / recompress / excerpt / reorder; destroyed by
  rasterisation. Rasterised input must report failure, never a wrong name.
- Cross-Act consistency: the signature shown in Act 2 is byte-identical to the
  one Act 5 verifies
- Offline: full journey with the network disabled

---

## Decisions taken (answers received)

| Question | Decision |
|---|---|
| Product name | **Tracewright** as placeholder; swappable via one constant. Final name deferred. |
| Demo document | Synthetic 10-page tender evaluation report. Built, capacity-verified (1917 bits vs 1534 needed). |
| Judge uploads own file in Act 5 | **Yes.** Needs an explicit, well-designed `NO_WATERMARK` state so a correct negative does not read as a failure. |
| Known limits in Act 0 | **Present, not shouted.** Findable link, not a banner. |
| Audience | **Both** presenter-led and self-guided. Build for unattended exploration that a presenter can also narrate. |
| Scoring rubric | None published. Optimise for: a technical judge can verify every claim end to end. |
| `wizard.py` | Retire on this branch. Teammate coordinated; `main` untouched. |

## Open question for the team

**Is "Tracewright" the name?** Everything else here I can decide on engineering
grounds; the name is a judgement call that should be yours. It is a one-line
change if you prefer `Silt`, `Attest`, or something of your own — which is
exactly why it is implemented as a constant.
