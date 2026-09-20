"""Five-stage guided walkthrough over the real pipeline.

Packages encrypt -> decrypt/watermark -> ledger -> breach -> attribution into
a linear narrative for a demo video. Every value returned here comes from the
same pqfw.pipeline / ledger / forensics code the CLI uses -- nothing is
hardcoded or precomputed. The only thing this module adds is state to walk
through that story in order with three fixed recipients (alice, bob, carol)
instead of the free-form investigator console in App.jsx.

Runs in its own data directory (demo/wizard-data) so it never collides with
the main demo/pqfw-data ledger used by DEMO-SCRIPT.md.
"""
from __future__ import annotations

import random
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from pqfw import pipeline
from pqfw.forensics.investigate import investigate
from pqfw.identity import Keystore
from pqfw.ledger.merkle import hash_leaf
from pqfw.ledger.node import LedgerNode
from pqfw.watermark import engine, tardos

from .paths import ROOT, SAMPLE_DOC as DOC, WIZARD_HOME as HOME

RECIPIENTS = ["alice", "bob", "carol"]

router = APIRouter(prefix="/api/wizard", tags=["wizard"])

import gc

# Single-process demo state -- there is exactly one wizard run at a time.
_state: dict = {}
_led_node: LedgerNode | None = None


def _ks() -> Keystore:
    return Keystore(HOME / "keys")


def _led() -> LedgerNode:
    global _led_node
    if _led_node is None:
        _led_node = LedgerNode(HOME / "ledger.db")
    return _led_node


def _close_led() -> None:
    global _led_node
    if _led_node is not None:
        try:
            _led_node.close()
        except Exception:
            pass
        _led_node = None
    gc.collect()


def _handle_remove_readonly(func, path, exc_info):
    import os, stat
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


@router.post("/stage1")
def stage1():
    """Fresh real run: new identities, encrypt once for alice/bob/carol."""
    if not DOC.exists():
        raise HTTPException(
            500, f"missing sample document: {DOC} -- run "
            f"'python spike/make_testdoc.py {DOC}' first")

    _close_led()

    if HOME.exists():
        try:
            shutil.rmtree(HOME, onerror=_handle_remove_readonly)
        except Exception:
            _close_led()
            try:
                shutil.rmtree(HOME, onerror=_handle_remove_readonly)
            except Exception:
                # Windows SQLite lock fallback: remove individual items and truncate DB
                for item in list(HOME.iterdir()):
                    if item.name == "ledger.db":
                        try:
                            item.unlink()
                        except Exception:
                            try:
                                import sqlite3
                                conn = sqlite3.connect(str(item))
                                conn.executescript(
                                    "DELETE FROM leaves; DELETE FROM sth; DELETE FROM nodekey; VACUUM;"
                                )
                                conn.commit()
                                conn.close()
                            except Exception:
                                pass
                    elif item.is_dir():
                        shutil.rmtree(item, ignore_errors=True, onerror=_handle_remove_readonly)
                    else:
                        try:
                            item.unlink()
                        except Exception:
                            pass
    HOME.mkdir(parents=True, exist_ok=True)
    _state.clear()

    ks = _ks()
    idents = [ks.create(u, overwrite=True) for u in RECIPIENTS]

    bundle_path = HOME / "classified-report.pqfw"
    b = pipeline.encrypt(DOC, idents, bundle_path)

    size_bytes = DOC.stat().st_size
    _state["bundle_path"] = str(bundle_path)

    return {
        "file": DOC.name,
        "size": f"{size_bytes / (1024 * 1024):.2f} MB",
        "hash": "0x" + b.doc_hash.hex()[:8],
        "cipher": "AES-256-GCM + ML-KEM-768",
        "doc_id": b.doc_id,
        "capacity_bits": engine.capacity(str(DOC)),
        "required_bits": tardos.required_length(len(idents), 3),
    }


@router.get("/stage2")
def stage2():
    """Each recipient decrypts independently: watermark, sign, commit."""
    if "bundle_path" not in _state:
        raise HTTPException(409, "run stage1 first")
    ks, led = _ks(), _led()
    decrypted = []
    for u in RECIPIENTS:
        dest = HOME / f"{u}-copy.pdf"
        r = pipeline.decrypt(_state["bundle_path"], u, ks, led, dest)
        decrypted.append({
            "name": u.capitalize(),
            "watermark": f"W_{u}_{r.record.watermark_commitment.hex()[:6]}",
            "session": r.record.timestamp.replace("T", " ")[:19],
            "nonce": r.record.watermark_seed.hex()[:8],
            "path": str(dest),
            "ledger_index": r.ledger_index,
        })
    _state["decrypted"] = decrypted
    return {"recipients": [
        {k: v for k, v in d.items() if k not in ("path", "ledger_index")}
        for d in decrypted]}


@router.get("/stage3")
def stage3():
    """Render the ledger's last three entries as a chained block view."""
    if "decrypted" not in _state:
        raise HTTPException(409, "run stage2 first")
    led = _led()
    blocks = []
    prev = "0x0000"
    for d in _state["decrypted"]:
        sr = led.get(d["ledger_index"])
        block_hash = "0x" + hash_leaf(sr.leaf_bytes()).hex()[:8]
        block = {
            "num": 100 + d["ledger_index"],
            "watermark": d["watermark"],
            "signature": f"Sig_{d['name'].lower()}_{sr.signature.hex()[:8]}",
            "hash": block_hash,
            "prev": prev,
        }
        blocks.append(block)
        prev = block_hash
    _state["blocks"] = blocks
    return {"blocks": blocks}


@router.post("/stage4")
def stage4():
    """Simulate a leak: copy one recipient's real copy out and investigate it."""
    if "decrypted" not in _state or _led().size() == 0:
        raise HTTPException(409, "run stage2 first")
    leaker = random.choice(_state["decrypted"])
    leaked_path = HOME / "leaked.pdf"
    shutil.copy(leaker["path"], leaked_path)

    verdict = investigate(leaked_path, _led())
    _state["verdict"] = verdict
    _state["leaked_watermark"] = leaker["watermark"]

    breach_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    return {"leaked_watermark": leaker["watermark"], "breach_time": breach_time}


class Stage5Body(BaseModel):
    watermark: str


@router.post("/stage5")
def stage5(body: Stage5Body):
    """Verify the extracted mark against the real ledger and signatures."""
    if "verdict" not in _state:
        raise HTTPException(409, "run stage4 first")
    if body.watermark != _state["leaked_watermark"]:
        return {"found": False}

    v = _state["verdict"]
    if v.outcome != "IDENTIFIED":
        return {"found": False, "outcome": str(v.outcome), "notes": v.notes}

    block = next((b for b in _state.get("blocks", [])
                  if b["watermark"] == body.watermark), None)
    return {
        "found": True,
        "user": v.recipient_user_id.capitalize(),
        "block": block["num"] if block else None,
        "signature": block["signature"] if block else None,
        "hash": block["hash"] if block else None,
        "timestamp": (v.timestamp or "").replace("T", " ")[:19],
        "evidence": {
            "signature_valid": v.signature_valid,
            "inclusion_valid": v.inclusion_valid,
            "commitment_valid": v.commitment_valid,
            "ledger_intact": v.ledger_intact,
        },
        "detection": {
            "score": v.score, "threshold": v.threshold, "margin": v.margin,
            "bits_recovered": v.bits_recovered, "bits_expected": v.bits_expected,
        },
    }
