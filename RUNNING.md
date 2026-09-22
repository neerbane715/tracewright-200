# Running Tracewright end to end

Everything below was run from a cold start on Windows and works. Timings are
real, not estimates.

---

## Quick start

Three commands, three terminals. Takes about a minute.

```bash
# terminal 1 — rebuild the demo data (≈5 s)
python demo_reset.py

# terminal 2 — the backend
python -m uvicorn pqfw_api.main:app --host 127.0.0.1 --port 8000

# terminal 3 — the UI
cd ui && npm run dev
```

Then open **http://127.0.0.1:5174** and click *Start the walkthrough*.

> Run `demo_reset.py` **before** starting the servers. It deletes and rebuilds
> the ledger, and Windows will not let it delete a file a running server has
> open. It fails loudly if that happens, but it is easier to just go in order.

---

## First time on a new machine

```bash
pip install -r requirements.txt     # third-party libraries
pip install -e .                    # puts the local pqfw package on the path

python spike/make_demo_doc.py demo-docs/tender-evaluation.pdf

cd ui && npm install && cd ..
```

Then follow the quick start.

**Both pip lines are needed.** The first installs the libraries; the second
registers `pqfw` and `pqfw_api` from `src/` so `import pqfw` and
`python -m pqfw.cli` work. Installing only the requirements leaves you with
`ModuleNotFoundError: No module named 'pqfw'`.

The demo document is generated rather than committed, so a fresh clone needs
that middle line once.

Requirements: **Python 3.11+**, **Node 18+**. Nothing needs a C compiler — the
post-quantum cryptography is pure Python, deliberately, so this installs on a
machine with no build toolchain.

For the browser verification suites only:

```bash
python -m playwright install chromium
```

### Installing without internet

`requirements.txt` pins nothing exotic and every package ships a wheel. On a
machine with connectivity:

```bash
pip download -r requirements.txt -d wheels/
```

Copy `wheels/` across, then on the air-gapped machine:

```bash
pip install --no-index --find-links wheels/ -r requirements.txt
pip install -e .
```

`npm` is only needed to build the UI; the CLI has no JavaScript dependency at
all.

---

## What each part is

| Port | What | Needed for the demo? |
|---|---|---|
| 8000 | FastAPI backend — all cryptography happens here | **yes** |
| 5174 | `ui/` — the Tracewright journey (Acts 0–5) | yes, for the visual demo |
| 5173 | `web/` — the older console | no, legacy |

The backend is the only thing that does real work. Both UIs are clients of it,
and so is the CLI.

---

## The journey

Six screens, in order. The whole thing takes about four minutes to click
through.

| Act | Route | What happens |
|---|---|---|
| 0 · Brief | `/` | The problem, before any cryptography |
| 1 · Seal | `/distribute` | Upload a document (or use the bundled one), then one encryption, one wrapped key per recipient |
| 2 · Open | `/open` | A recipient decrypts; the mark is made and signed |
| 3 · Record | `/ledger` | The chain, and the tamper demonstration |
| 4 · Breach | `/leak` | Choose whose copy surfaced — or let it pick at random |
| 5 · Verdict | `/attribute` | Real extraction → who leaked it |

**Ground truth:** In the UI, Act 4 lets you choose whose copy leaked from the
recipients who actually opened it, so you set the answer yourself. *Surprise
me* randomises instead, which is the better choice if someone suspects the
demo is rigged — nobody in the room knows the answer, including you. Act 5 is
never told either way; it extracts the mark from the file. For the CLI path,
`demo_reset.py` prints the ground truth, usually `carol`.

**Uploading your own document:** Act 1 accepts any PDF with a text layer. It
is measured on upload and refused if it cannot carry a full codeword — roughly
six pages of justified body text, or 1,534 bits for five recipients. A slide
deck or a scan will be refused, and the screen says why. `demo-docs/
board-inquiry.pdf` (`python spike/make_upload_doc.py`) is a second document
generated for exactly this purpose: 10 pages, 2,300 bits.

**Technical detail** (top right) reveals algorithm names, byte lengths, real
signatures and the raw API responses on every screen. It persists across acts,
and turning it off never hides anything the plain layer was saying.

### Two moments worth pausing on

**Act 2, after opening as a second recipient.** Two copies render side by side
with four measurements taken from the real files — ~28,000 byte positions
differ, 398 words identical, 0.0 pt baseline shift. That is the product's
central claim, proven rather than asserted.

**Act 3, the tamper button.** It edits the database directly, bypassing the
application. The screen then names the exact record and the exact reason. Use
*Rebuild a clean ledger* afterwards, or Act 5 will correctly refuse to attribute
anything.

---

## The CLI — the real fallback

Every capability exists here too, with no ports and nothing to crash. Practise
this path; it is what rescues a demo.

```bash
cd demo

python -m pqfw.cli ledger list
python -m pqfw.cli investigate LEAKED-DOCUMENT.pdf   # → IDENTIFIED · carol
python -m pqfw.cli ledger verify
```

Full round trip from scratch:

```bash
python -m pqfw.cli id create frank
python -m pqfw.cli encrypt ../demo-docs/tender-evaluation.pdf -r alice,bob,frank -o r.pqfw
python -m pqfw.cli decrypt r.pqfw -i frank -o frank.pdf
python -m pqfw.cli investigate frank.pdf
```

---

## Checking it works

| Command | Covers | Time |
|---|---|---|
| `python -m pytest tests/ -q` | 55 backend tests | ~48 s + several min for the `slow` e2e test |
| `python -m pytest tests/ -q -m "not slow"` | same, skipping the slow e2e attribution test | ~48 s |
| `python ui/verify_full.py` | 36 integration checks | ~4 min |
| `python ui/verify_offline.py` | air-gap proof, 9 checks | ~3 min |
| `python ui/verify_ui.py` | Acts 0–1 in a browser | ~30 s |
| `python ui/verify_act2.py` … `act5.py` | one act each | 1–4 min |

The browser suites need Chromium downloaded once (playwright itself comes from
`requirements.txt`):

```bash
python -m playwright install chromium
```

`verify_offline.py` is the one to run before claiming the air-gap requirement:
it blocks every non-localhost request at the browser level and drives all six
acts. Source inspection alone cannot catch a runtime fetch.

---

## When something goes wrong

**Port 8000 already in use.** A previous backend is still running:

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

**`demo_reset.py` says the ledger is locked.** A server has the file open. Stop
everything and retry:

```powershell
Get-Process python,node -ErrorAction SilentlyContinue | Stop-Process -Force
```

`pkill` does not exist in PowerShell — use the above.

**The UI says "The engine isn't running."** That is the correct message: the
backend is down. Start it and press *Try again*. The UI deliberately
distinguishes a missing server from a broken product.

**Everything returns LEDGER_COMPROMISED.** The tamper demo was left on. Either
press *Rebuild a clean ledger* in Act 3, or stop the servers and re-run
`demo_reset.py`.

**A judge's own PDF says NO_WATERMARK.** That is correct — their file was never
distributed through the system. The screen explains why. It is a feature worth
pointing at, not a failure.

**`ModuleNotFoundError: No module named 'pqfw'`.** The requirements installed
but the project itself did not. Run `pip install -e .` from the repository
root.

**`ModuleNotFoundError` for something else** (fastapi, pymupdf, reportlab…).
Run `pip install -r requirements.txt`. If it names `reportlab`, that is only
needed to regenerate the demo document; if it names `playwright`, only the
browser test suites use it.

---

## Before a demo

1. Stop every stray process (see above)
2. `python demo_reset.py` — note the ground-truth name it prints
3. Start the backend, then the UI
4. Click through all six acts once yourself
5. Leave Act 3's ledger **intact** — do not leave it tampered
6. Have a terminal open in `demo/` with the CLI ready

The last one matters. If the UI fails on stage, `python -m pqfw.cli investigate
LEAKED-DOCUMENT.pdf` still names the leaker with the full evidence chain, and
nobody in the room needs to know anything went wrong.
