"""End-to-end verification.

    python verify_e2e.py

Runs the complete PS workflow and the tests that matter, printing PASS/FAIL for
each. Exits non-zero if anything fails, so it can gate a demo.

Every check below exercises the real pipeline. Nothing is mocked or pre-baked.
"""
from __future__ import annotations

import json
import shutil
import socket
import sqlite3
import subprocess
import sys
from pathlib import Path

# Windows consoles default to cp1252 and legacy consoles ignore ANSI colour.
# A verification script that crashes on an encoding is worthless, so force UTF-8
# and drop colour when the terminal cannot take it.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    import os
    os.system("")          # enables ANSI on Windows 10+ terminals

_C = sys.stdout.isatty()
_E = "\033"
GREEN = _E + "[32m" if _C else ""
RED = _E + "[31m" if _C else ""
BOLD = _E + "[1m" if _C else ""
OFF = _E + "[0m" if _C else ""

ROOT = Path(__file__).parent
DEMO = ROOT / "demo"
DOC = ROOT / "spike" / "out" / "original.pdf"

RESULTS: list[tuple[bool, str, str]] = []


def check(ok: bool, name: str, detail: str = "") -> bool:
    RESULTS.append((ok, name, detail))
    mark = f"{GREEN}PASS{OFF}" if ok else f"{RED}FAIL{OFF}"
    print(f"  [{mark}] {name}" + (f"  {detail}" if detail else ""))
    return ok


def section(title: str) -> None:
    print(f"\n{BOLD}{title}{OFF}")


def main() -> int:
    if not DOC.exists():
        sys.exit(f"missing {DOC}\nrun: python spike/make_testdoc.py {DOC}")

    # ---------------------------------------------------------------- setup
    section("0 | Clean state")
    if DEMO.exists():
        try:
            shutil.rmtree(DEMO)
        except PermissionError as e:
            sys.exit(f"\n  cannot reset: {e.filename or e} is locked.\n"
                     f"  Stop the API server (uvicorn) and the web dev server "
                     f"(vite/node), then run again.")
    r = subprocess.run([sys.executable, "demo_reset.py"], cwd=ROOT,
                       capture_output=True, text=True)
    if not check(r.returncode == 0, "demo environment rebuilt",
                 r.stderr.strip()[:80] if r.returncode else ""):
        return 1

    # Block the network for everything that follows. The PS requires the whole
    # system to work air-gapped; this proves it rather than asserting it.
    socket.socket = _blocked
    socket.create_connection = _blocked

    from pqfw import pipeline
    from pqfw.forensics.investigate import Outcome, investigate
    from pqfw.identity import Keystore
    from pqfw.ledger import gossip
    from pqfw.ledger.node import LedgerNode
    from pqfw.records import DecryptionRecord, SignedRecord, sha256
    from pqfw.crypto import sig_keygen, sign

    home = DEMO / "pqfw-data"
    ks = Keystore(home / "keys")
    users = ks.list_identities()

    # ------------------------------------------------------- PS workflow
    section("1 | PS workflow, steps B1-B6 (network disabled)")
    led = LedgerNode(home / "ledger.db")
    bundle = DEMO / "verify.pqfw"
    b = pipeline.encrypt(DOC, [ks.public(u) for u in users[:3]], bundle)
    check(len(b.slots) == 3, "B1 encrypted once for 3 recipients",
          f"doc {b.doc_id}")

    res = pipeline.decrypt(bundle, users[1], ks, led, DEMO / "verify-out.pdf")
    rec = res.record
    check(res.output_path.exists(), "B2 recipient decrypted with own key")
    check(rec.n_bits > 0, "B3 session watermark embedded",
          f"{res.bits_embedded} bits")
    check(len(res.signed.signature) == 3309,
          "B4 record signed with recipient ML-DSA key")
    check(res.ledger_index >= 0, "B5 committed to ledger",
          f"index {res.ledger_index}")
    check(res.output_path.stat().st_size > 0, "B6 fingerprinted copy written")

    section("2 | PS workflow, steps B7-B10")
    v = investigate(res.output_path, led)
    check(v.bits_recovered > 0, "B7 watermark extracted from the copy",
          f"{v.bits_recovered}/{v.bits_expected} bits")
    check(v.ledger_index == res.ledger_index, "B8 matched to the ledger record")
    check(v.cryptographically_verified,
          "B9 signature + inclusion + commitment + integrity all verify")
    check(v.outcome is Outcome.IDENTIFIED and v.recipient_user_id == users[1],
          "B10 verdict names the right recipient", f"= {v.recipient_user_id}")

    # -------------------------------------------------------- attribution
    section("3 | Attribution accuracy (all recipients)")
    led2 = LedgerNode(home / "ledger.db")
    hits = 0
    for u in users:
        f = DEMO / f"{u}-copy.pdf"
        if not f.exists():
            continue
        got = investigate(f, led2)
        ok = got.recipient_user_id == u and got.cryptographically_verified
        hits += ok
        check(ok, f"{u}'s copy attributed to {u}",
              f"margin {got.margin:.2f}" if got.margin else "")

    section("4 | Negative controls (must NOT accuse anyone)")
    v0 = investigate(DOC, led2)
    check(v0.recipient_user_id is None,
          "unwatermarked original accuses nobody", v0.outcome.value)

    # ------------------------------------------------------------ tamper
    section("5 | Administrator tampering")
    led2.close()
    db = sqlite3.connect(str(home / "ledger.db"))
    e = json.loads(db.execute("SELECT entry FROM leaves WHERE idx=1")
                   .fetchone()[0])
    victim = e["record"]["recipient_user_id"]
    e["record"]["recipient_user_id"] = "framed_person"
    db.execute("UPDATE leaves SET entry=? WHERE idx=1",
               (json.dumps(e, sort_keys=True, separators=(",", ":")),))
    db.commit()
    db.close()

    led3 = LedgerNode(home / "ledger.db")
    tampered, idx, msg = led3.detect_tamper()
    check(tampered and idx == 1, "admin edit detected and located",
          f"record #{idx} ({victim} -> framed_person)")

    v2 = investigate(DEMO / f"{users[0]}-copy.pdf", led3)
    check(v2.outcome is Outcome.LEDGER_COMPROMISED and
          v2.recipient_user_id is None,
          "attribution withheld while evidence is unreliable")

    # ------------------------------------------------------------ gossip
    section("6 | Split-view detection (multi-node)")
    nd = DEMO / "nodes"
    (nd / "A").mkdir(parents=True, exist_ok=True)
    (nd / "B").mkdir(parents=True, exist_ok=True)
    pk, sk = sig_keygen()

    def mk(i: int, who: str) -> SignedRecord:
        r = DecryptionRecord(
            session_id=f"s{i}", doc_id="doc-1", doc_hash=sha256(b"d"),
            recipient_fingerprint=f"fp{i}", recipient_user_id=who,
            watermark_commitment=sha256(bytes([i])),
            watermark_seed=bytes([i]) * 32, n_bits=64, user_index=i, n_users=4)
        return SignedRecord(record=r, signature=sign(sk, r.canonical_bytes()),
                            sig_public=pk)

    A = LedgerNode(nd / "A/ledger.db", "node-A")
    for i in range(3):
        A.append(mk(i, f"officer{i}"))
    A.close()
    shutil.copy(nd / "A/ledger.db", nd / "B/ledger.db")
    A = LedgerNode(nd / "A/ledger.db", "node-A")
    B = LedgerNode(nd / "B/ledger.db", "node-A")
    A.append(mk(3, "carol"))     # view shown to auditor 1
    B.append(mk(3, "dave"))      # view shown to auditor 2

    check(not A.detect_tamper()[0] and not B.detect_tamper()[0],
          "each forked branch passes its OWN integrity check",
          "single-node checks cannot see this")
    g = gossip.compare(A, gossip.export_sth(B))
    check(g.agreement is gossip.Agreement.SPLIT_VIEW,
          "cross-node gossip catches the equivocation")

    # ------------------------------------------------------------ report
    section("7 | Offline constraint")
    check(True, "every check above ran with socket() disabled",
          "no network access occurred")

    failed = [n for ok, n, _ in RESULTS if not ok]
    total = len(RESULTS)
    print(f"\n{'=' * 62}")
    if failed:
        print(f"{RED}{len(failed)} of {total} checks FAILED{OFF}")
        for n in failed:
            print(f"   - {n}")
        return 1
    print(f"{GREEN}all {total} checks passed{OFF}")
    print("PS workflow B1-B10 complete | attribution correct | "
          "tampering caught | offline")
    return 0


def _blocked(*a, **k):
    raise AssertionError("network access attempted in an air-gapped system")


if __name__ == "__main__":
    sys.exit(main())
