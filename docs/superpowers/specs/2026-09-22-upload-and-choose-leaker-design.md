# Design — Operator-chosen document and leaker

**Date:** 2026-09-22
**Status:** approved, ready for implementation planning

---

## Purpose

Today a viewer cannot change what the demo operates on. Act 1 seals a hardcoded
path (`ui/src/acts/Act1Distribute.tsx:10`), and Act 4 stages a leak by picking a
copy at random. Everything inside that frame is real — recipients, marks,
signatures, verdicts are all computed — but the frame itself is fixed, and a
sceptical judge has no way to test it with their own material.

This change adds exactly two degrees of freedom:

1. **Which document** is distributed — uploaded by the operator.
2. **Whose copy surfaced** — chosen by the operator from the people who opened it.

## The property this must not break

Act 5's verdict must remain a genuine extraction from the artefact's own
geometry, never a replay of a value computed earlier.

This is not a hypothetical concern. `src/pqfw_api/attribute.py` records that a
previous build ran the real investigation while staging the leak, cached the
verdict, and had the next screen replay it under the label "Extracted
watermark". `stage_leak` is deliberately ignorant as a direct consequence.

That ignorance cannot survive this change: the operator now names the source.
So the guarantee moves rather than disappearing:

> **`stage_leak` may receive a source. It must never return an identity.**

Enforced by a test, not by convention.

The operator chooses the ground truth; the system independently rediscovers it.
A viewer should experience those as two separate events, in that order.

---

## Section 1 — Document upload with pre-flight capacity check

### The constraint

A watermark needs `required_length(n, c) = ceil(20 · c² · ln(n/ε))` bits. At
c=3, ε=1e-3 that is **1,534 bits for 5 recipients**. Capacity comes only from
justified body text — `(words_per_line − 1) // 2` bits per line, lines under 5
words contributing nothing.

Measured on real files:

| Document | Capacity | Verdict at n=5 |
|---|---|---|
| `demo-docs/tender-evaluation.pdf` (7 pp) | 1,917 bits | sufficient |
| One page of sparse text | 3 bits | refused |

Slide decks, scanned pages, title-heavy reports and short memos will be
refused. That refusal is correct behaviour — the system declines to mark a
document it could not later defend — but arriving mid-narrative it reads as a
crash.

Note that the requirement grows as `ln(n)`: 1,369 bits for 2 recipients, 1,534
for 5, 1,658 for 10. Capacity is almost entirely fixed cost, so a document that
clears the bar for 5 people clears it for far more. A 1,917-bit document
supports 42. This is worth surfacing — it reframes the check from a limit into
a headroom statement.

### Endpoint

`POST /api/documents` (multipart)

Validation, in order, each with a distinct message:

1. Magic bytes are `%PDF`
2. `pymupdf.open()` succeeds — rejects corrupt files
3. `doc.needs_pass` is false — rejects password-protected files
4. Size ≤ 25 MB
5. Store as `demo/uploads/<uuid4>.pdf`; the original filename is retained for
   display only and never used as a path component

Step 5 is what preserves the existing security invariant: every path the rest
of the system handles still resolves inside the demo directory, so `_safe()`
and `_resolve()` continue to hold without modification.

Response:

```json
{
  "id": "a3f2c1d4…",
  "display_name": "my-report.pdf",
  "pages": 7,
  "capacity_bits": 1917,
  "required_bits": 1534,
  "sufficient": true,
  "max_recipients": 42
}
```

`max_recipients` inverts `required_length` by search over n ∈ [2, 50], returning
the largest n whose requirement fits. Returns 0 when even 2 recipients do not
fit.

`GET /api/documents` lists what is available — uploads plus the bundled sample —
so Act 1 can offer both.

### UI

Act 1 replaces `const DOC` with a picker: upload control, plus the bundled
sample as a permanently available fallback. On selection it shows the capacity
verdict — "1,917 bits available, 1,534 needed for 5 recipients" — and on a
short document disables Seal with the reason and a one-click switch to the
sample.

The bundled sample must always remain selectable. It is the recovery path when
an uploaded file is refused during a live demo.

---

## Section 2 — Choosing the leaker

Act 4 becomes a chooser rather than a randomiser.

Candidates are read from the **ledger**, via the existing `/api/ledger/chain`,
not from React state. Someone who navigates directly to Act 4 must still see a
correct list, and the ledger is the only authority on who actually decrypted.
This also makes the constraint self-enforcing: you can only leak a copy that
exists, because the list is built from copies that exist.

Each row shows recipient, open time, and ledger index.

**Surprise me** is retained alongside explicit choice. It is the stronger
option when a judge suspects the demo is rigged — the operator genuinely does
not know the answer, and the response body does not carry it.

`stage_leak` already accepts an optional `source`; Act 4 now passes it
deliberately. The response shape is unchanged.

---

## Section 3 — The honesty guard

Four measures, together:

1. `stage_leak` returns `{filename, bytes, sha256, pages, title}`. No
   `user_id`, no `ledger_index`, no `source`. Unchanged from today.
2. Act 4 continues to call `setLeaked(null)` so Act 5 inherits nothing through
   `run.tsx`.
3. Act 5 continues to attribute via `/api/attribute-path`, running real
   extraction.
4. **New test** `test_stage_leak_does_not_reveal_source`: for every recipient
   in the ledger, assert their user_id appears nowhere in the serialized
   `stage_leak` response. This is what stops the old bug silently returning.

### Reveal ordering in Act 5

Act 5 shows its verdict **first**. Only after the verdict renders does the UI
reveal the operator's pick for comparison.

This ordering is the point. Showing the pick first would make the verdict look
like a lookup; showing it second makes a match a confirmation.

A mismatch is displayed honestly rather than suppressed. With a margin near
`MARGIN_FLOOR` an `INCONCLUSIVE` outcome is a legitimate result, and a forensic
tool that hid it would be misrepresenting its own confidence. The comparison
panel states the verdict, the pick, and whether they agree.

---

## Section 4 — The artefact

Staging copies the chosen recipient's real watermarked PDF to
`surfaced-document.pdf` — the same bytes that recipient received, not a
regeneration — and Act 4 offers it for download.

A judge can take that file, drop it into Act 5's existing upload control
(`/api/attribute`, already implemented), and reach the same verdict
independently of the staged path. This costs almost nothing to add and is the
most direct answer to "how do I know the screen isn't lying".

---

## Scope

### Files changed

| File | Change |
|---|---|
| `src/pqfw_api/attribute.py` | `POST /api/documents`, `GET /api/documents`, `max_recipients` helper |
| `src/pqfw_api/paths.py` | `UPLOADS` directory; add to `_safe()` allowed roots |
| `ui/src/acts/Act1Distribute.tsx` | Document picker + capacity panel; remove `const DOC` |
| `ui/src/acts/Act4Leak.tsx` | Leaker chooser, *Surprise me*, download link |
| `ui/src/acts/Act5Attribute.tsx` | Reveal-then-compare ordering |
| `ui/src/lib/run.tsx` | Carry `documentId` and `chosenLeaker` |
| `ui/src/lib/api.ts` | Types for the new endpoints |
| `tests/test_pqfw.py` | Capacity refusal, upload validation, stage-leak non-disclosure |
| `demo_reset.py` | Comment on `LEAKER`: CLI ground truth only; UI chooses |
| `RUNNING.md` | Document upload + leaker choice; correct the ground-truth claim |

### Explicitly not changed

Nothing under `src/pqfw/`. The crypto core, ledger, watermark engine and
`investigate()` already support everything here — `capacity()` and
`required_length()` are public and were verified to work on arbitrary PDFs.
This is API and UI work.

### Related, handled separately

`src/pqfw_api/wizard.py` is the superseded design: module-level `_state`,
a cached verdict in `stage4`, and a `stage5` that compares a client-submitted
string against that cache. It serves the legacy `web/` console, already marked
"no, legacy" in RUNNING.md. Leaving it in place means the repository holds two
contradictory answers to how attribution works. Recommend deletion in its own
commit — out of scope here, but it should not be forgotten.

---

## Testing

| Test | Proves |
|---|---|
| `test_upload_rejects_non_pdf` | Magic-byte check fires |
| `test_upload_rejects_encrypted_pdf` | `needs_pass` check fires |
| `test_capacity_check_refuses_thin_document` | A 3-bit PDF is refused with capacity stated |
| `test_capacity_check_accepts_demo_document` | 1,917 ≥ 1,534, `sufficient` true |
| `test_max_recipients_inversion` | Matches `required_length` at boundaries |
| `test_stage_leak_does_not_reveal_source` | **No recipient name in the response** |
| `test_chosen_leaker_is_correctly_attributed` | Choose each of 5 in turn; `investigate()` names that person |
| `test_uploaded_document_full_round_trip` | Upload → seal → open → stage → attribute |

The seventh is the one that proves the feature end to end: the operator's choice
and the system's independent verdict agree, for every recipient, without the
verdict path ever seeing the choice.

---

## Risks

| Risk | Handling |
|---|---|
| Judge uploads an unmarkable PDF mid-demo | Pre-flight check refuses at the door, states why, offers the sample |
| Upload path weakens `_safe()` | Files stored under generated names inside the demo dir; invariant preserved |
| Chosen leaker leaks into Act 5 | Response shape unchanged + regression test |
| Chosen leaker never opened the document | List built from ledger records, so the case cannot arise |
| Attribution disagrees with the pick | Shown honestly; `INCONCLUSIVE` near the margin floor is a real outcome |
| Large upload exhausts memory on Render | 25 MB cap, streamed to disk |
