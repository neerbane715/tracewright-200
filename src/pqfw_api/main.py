"""FastAPI layer.

STRICTLY a client of pqfw core. No business logic lives here -- every endpoint
is a thin wrapper over the same functions the CLI calls, so the CLI remains a
complete fallback if this process dies during a demo.

Binds to localhost only. Nothing in this service reaches the network.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from pqfw import pipeline
from pqfw.forensics.investigate import investigate
from pqfw.identity import Keystore
from pqfw.ledger.node import LedgerNode
from pqfw.ledger import gossip as gsp
from pqfw.watermark import engine, tardos

DEMO = Path(__file__).parent.parent.parent / "demo"
HOME = DEMO / "pqfw-data"

app = FastAPI(title="PQ-FORENSIC", version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["http://localhost:5173"],
    allow_methods=["*"], allow_headers=["*"])


def ks() -> Keystore:
    return Keystore(HOME / "keys")


def led() -> LedgerNode:
    return LedgerNode(HOME / "ledger.db")


# --------------------------------------------------------------- identities

@app.get("/api/identities")
def identities():
    k = ks()
    return [{"user_id": u, "fingerprint": k.public(u).fingerprint,
             "has_secret": k.has_secret(u)} for u in k.list_identities()]


class CreateIdentity(BaseModel):
    user_id: str


@app.post("/api/identities")
def create_identity(body: CreateIdentity):
    try:
        i = ks().create(body.user_id)
    except Exception as e:
        raise HTTPException(400, str(e))
    return {"user_id": i.user_id, "fingerprint": i.fingerprint}


# ------------------------------------------------------------------ encrypt

class EncryptBody(BaseModel):
    document: str
    recipients: list[str]


@app.post("/api/encrypt")
def api_encrypt(body: EncryptBody):
    doc = Path(body.document)
    if not doc.exists():
        raise HTTPException(404, f"document not found: {doc}")
    k = ks()
    try:
        idents = [k.public(u) for u in body.recipients]
    except Exception as e:
        raise HTTPException(400, str(e))

    out = DEMO / f"{doc.stem}.pqfw"
    b = pipeline.encrypt(doc, idents, out)
    return {"doc_id": b.doc_id, "bundle": str(out),
            "recipients": body.recipients,
            "capacity_bits": engine.capacity(str(doc)),
            "required_bits": tardos.required_length(len(idents), 3)}


# ------------------------------------------------------------------ decrypt

class DecryptBody(BaseModel):
    bundle: str
    identity: str


@app.post("/api/decrypt")
def api_decrypt(body: DecryptBody):
    out = DEMO / f"{body.identity}-copy.pdf"
    steps: list[str] = []
    try:
        r = pipeline.decrypt(Path(body.bundle), body.identity, ks(), led(),
                             out, progress=steps.append)
    except (pipeline.PipelineError, engine.CapacityError) as e:
        raise HTTPException(400, str(e))
    return {"output": str(out), "steps": steps,
            "session_id": r.record.session_id,
            "ledger_index": r.ledger_index,
            "bits": r.bits_embedded,
            "record": r.record.to_dict()}


# -------------------------------------------------------------- investigate

@app.post("/api/investigate")
async def api_investigate(file: UploadFile = File(...)):
    tmp = Path(tempfile.mkdtemp()) / (file.filename or "leaked.pdf")
    with tmp.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)
    try:
        return investigate(tmp, led()).to_dict()
    finally:
        try:
            tmp.unlink()
            tmp.parent.rmdir()
        except OSError:
            pass


# ------------------------------------------------------------------- ledger

@app.get("/api/ledger")
def api_ledger():
    L = led()
    sth = L.latest_sth()
    return {
        "size": L.size(),
        "root": L.root().hex(),
        "sth": {"tree_size": sth["tree_size"], "root": sth["root"].hex(),
                "signed_at": sth["signed_at"],
                "signature_bytes": len(sth["signature"]),
                "valid": L.verify_sth(sth)} if sth else None,
        "records": [
            {"index": i, "user_id": r.record.recipient_user_id,
             "fingerprint": r.record.recipient_fingerprint,
             "doc_id": r.record.doc_id, "session_id": r.record.session_id,
             "timestamp": r.record.timestamp, "n_bits": r.record.n_bits}
            for i, r in L.all_records()],
    }


@app.get("/api/ledger/verify")
def api_ledger_verify():
    tampered, idx, msg = led().detect_tamper()
    return {"tampered": tampered, "index": idx, "message": msg}


@app.get("/api/ledger/proof/{index}")
def api_proof(index: int):
    L = led()
    if index >= L.size():
        raise HTTPException(404, "no such record")
    p = L.prove_inclusion(index)
    return {"index": index, "tree_size": p["tree_size"],
            "root": p["root"].hex(),
            "path": [h.hex() for h in p["proof"]]}


@app.get("/api/ledger/sth")
def api_sth():
    """This node's signed tree head, for a peer to compare against."""
    try:
        return gsp.export_sth(led()).to_dict()
    except ValueError as e:
        raise HTTPException(409, str(e))


class GossipBody(BaseModel):
    peers: list[dict]


@app.post("/api/ledger/gossip")
def api_gossip(body: GossipBody):
    """Compare peer tree heads against ours; detects a split view."""
    try:
        peers = [gsp.STH.from_dict(p) for p in body.peers]
    except Exception as e:
        raise HTTPException(400, f"malformed peer STH: {e}")
    L = led()
    results = gsp.audit(L, peers)
    ok, msg = gsp.quorum_view(results)
    return {"ok": ok, "summary": msg,
            "results": [r.to_dict() for r in results]}


class TamperBody(BaseModel):
    index: int
    new_user_id: str = "dave"


@app.post("/api/ledger/tamper")
def api_tamper(body: TamperBody):
    """DEMO ONLY: act as a malicious administrator editing the database.

    This exists to prove the detection works. It writes directly to SQLite,
    bypassing every application-level control -- exactly what a privileged
    insider would do.
    """
    import json
    import sqlite3
    db = sqlite3.connect(str(HOME / "ledger.db"))
    row = db.execute("SELECT entry FROM leaves WHERE idx=?",
                     (body.index,)).fetchone()
    if not row:
        db.close()
        raise HTTPException(404, "no such record")
    e = json.loads(row[0])
    before = e["record"]["recipient_user_id"]
    e["record"]["recipient_user_id"] = body.new_user_id
    db.execute("UPDATE leaves SET entry=? WHERE idx=?",
               (json.dumps(e, sort_keys=True, separators=(",", ":")),
                body.index))
    db.commit()
    db.close()
    tampered, idx, msg = led().detect_tamper()
    return {"edited_index": body.index, "from": before, "to": body.new_user_id,
            "detected": tampered, "detected_at": idx, "message": msg}
