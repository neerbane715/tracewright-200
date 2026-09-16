"""Test suite mapped to the problem statement's requirement IDs.

Each test names the requirement it proves (see docs/REQUIREMENTS.md).
"""
from __future__ import annotations

import json
import sqlite3
import socket
from pathlib import Path

import numpy as np
import pytest

from pqfw import pipeline
from pqfw.crypto import (aead_decrypt, aead_encrypt, kem_decaps, kem_encaps,
                         kem_keygen, random_key, sig_keygen, sign, verify)
from pqfw.forensics.investigate import Outcome, investigate
from pqfw.identity import IdentityError, Keystore
from pqfw.ledger.merkle import (consistency_proof, hash_leaf, inclusion_proof,
                                root_from_leaves, verify_consistency,
                                verify_inclusion)
from pqfw.ledger.node import LedgerNode
from pqfw.records import DecryptionRecord, SignedRecord, sha256
from pqfw.watermark import engine, tardos

DOC = Path(__file__).parent.parent / "spike" / "out" / "original.pdf"


@pytest.fixture(scope="module")
def doc():
    if not DOC.exists():
        pytest.skip("run: python spike/make_testdoc.py spike/out/original.pdf")
    return DOC


@pytest.fixture
def env(tmp_path, doc):
    ks = Keystore(tmp_path / "keys")
    ids = [ks.create(u) for u in ("alice", "bob", "carol")]
    led = LedgerNode(tmp_path / "l.db")
    bundle = tmp_path / "b.pqfw"
    pipeline.encrypt(doc, ids, bundle)
    return {"ks": ks, "ids": ids, "led": led, "bundle": bundle,
            "tmp": tmp_path}


# ---------------------------------------------------------------- A6: PQC

def test_a6_uses_nist_pqc_algorithms():
    """A6: NIST-standardised PQC for key exchange AND signatures."""
    pk, sk = kem_keygen()
    assert len(pk) == 1184 and len(sk) == 2400        # FIPS 203 ML-KEM-768
    ss, ct = kem_encaps(pk)
    assert len(ct) == 1088 and kem_decaps(sk, ct) == ss

    vk, sgk = sig_keygen()
    assert len(vk) == 1952                            # FIPS 204 ML-DSA-65
    s = sign(sgk, b"m")
    assert len(s) == 3309 and verify(vk, b"m", s)
    assert not verify(vk, b"tampered", s)


def test_no_classical_public_key_crypto():
    """A6: no RSA/ECDSA/ECDH anywhere in the source tree."""
    src = Path(__file__).parent.parent / "src"
    # Match on CODE, not prose: docstrings legitimately mention the classical
    # algorithms being replaced.
    banned = ("import rsa", "ec.generate_private_key", "rsa.generate_private_key",
              "Ed25519PrivateKey", "X25519PrivateKey", "ECDSA(")
    for f in src.rglob("*.py"):
        code = "\n".join(
            ln for ln in f.read_text(encoding="utf-8").splitlines()
            if not ln.lstrip().startswith("#"))
        for b in banned:
            assert b not in code, f"{f} uses classical PK crypto: {b}"


# ------------------------------------------------------ A12/A13/A14: offline

def test_a12_a14_no_network_calls(env, monkeypatch, tmp_path):
    """A12/A13/A14: full pipeline runs with networking disabled."""
    def boom(*a, **k):
        raise AssertionError("network access attempted in air-gapped system")

    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)

    r = pipeline.decrypt(env["bundle"], "bob", env["ks"], env["led"],
                         tmp_path / "out.pdf")
    assert r.output_path.exists()
    v = investigate(r.output_path, env["led"])
    assert v.outcome is Outcome.IDENTIFIED


# --------------------------------------------------------------- Merkle/A7/A8

def test_a7_inclusion_proofs_exhaustive():
    for n in range(1, 33):
        leaves = [hash_leaf(bytes([i])) for i in range(n)]
        root = root_from_leaves(leaves)
        for i in range(n):
            assert verify_inclusion(leaves[i], i, n, inclusion_proof(leaves, i),
                                    root)


def test_a8_consistency_proofs_exhaustive():
    """A8: append-only property holds for every (m, n) pair."""
    for n in range(1, 33):
        leaves = [hash_leaf(bytes([i])) for i in range(n)]
        rn = root_from_leaves(leaves)
        for m in range(1, n + 1):
            rm = root_from_leaves(leaves[:m])
            assert verify_consistency(rm, m, rn, n, consistency_proof(leaves, m))


def test_a8_consistency_rejects_rewritten_history():
    """A8: an altered history has no valid consistency proof."""
    n = 16
    leaves = [hash_leaf(bytes([i])) for i in range(n)]
    rn = root_from_leaves(leaves)
    for m in range(1, n):
        evil = list(leaves)
        evil[m - 1] = hash_leaf(b"EVIL")
        proof = consistency_proof(leaves, m)
        assert not verify_consistency(root_from_leaves(evil[:m]), m, rn, n,
                                      proof)


def test_a8_admin_modification_detected(env, tmp_path):
    """A8: a privileged admin editing SQLite directly is caught and located."""
    for u in ("alice", "bob", "carol"):
        pipeline.decrypt(env["bundle"], u, env["ks"], env["led"],
                         tmp_path / f"{u}.pdf")
    env["led"].close()

    db = sqlite3.connect(str(tmp_path / "l.db"))
    e = json.loads(db.execute("SELECT entry FROM leaves WHERE idx=1").fetchone()[0])
    e["record"]["recipient_user_id"] = "someone_else"
    db.execute("UPDATE leaves SET entry=? WHERE idx=1",
               (json.dumps(e, sort_keys=True, separators=(",", ":")),))
    db.commit()
    db.close()

    tampered, idx, msg = LedgerNode(tmp_path / "l.db").detect_tamper()
    assert tampered and idx == 1


def test_a8_deletion_detected(env, tmp_path):
    """A8: deleting a record is detected."""
    for u in ("alice", "bob", "carol"):
        pipeline.decrypt(env["bundle"], u, env["ks"], env["led"],
                         tmp_path / f"{u}.pdf")
    env["led"].close()
    db = sqlite3.connect(str(tmp_path / "l.db"))
    db.execute("DELETE FROM leaves WHERE idx=2")
    db.commit()
    db.close()
    tampered, _, msg = LedgerNode(tmp_path / "l.db").detect_tamper()
    assert tampered


def test_a8_forged_record_rejected_at_append(tmp_path):
    """A8: the ledger refuses records whose signature does not verify."""
    led = LedgerNode(tmp_path / "l.db")
    vk, sk = sig_keygen()
    rec = DecryptionRecord(
        session_id="s", doc_id="d", doc_hash=sha256(b"d"),
        recipient_fingerprint="fp", recipient_user_id="mallory",
        watermark_commitment=sha256(b"c"), watermark_seed=b"x" * 32,
        n_bits=16, user_index=0, n_users=2)
    bad = SignedRecord(record=rec, signature=b"\x00" * 3309, sig_public=vk)
    with pytest.raises(ValueError):
        led.append(bad)


# ------------------------------------------------------------ A1/A2/A3: mark

def test_a3_watermark_is_visually_identical(env, tmp_path):
    """A3: marked pages render identically to the original."""
    import pymupdf
    r = pipeline.decrypt(env["bundle"], "alice", env["ks"], env["led"],
                         tmp_path / "a.pdf")
    p0 = pymupdf.open(DOC)[0]
    p1 = pymupdf.open(r.output_path)[0]

    # 1. No text added, removed or reflowed.
    w0, w1 = p0.get_text("words"), p1.get_text("words")
    assert len(w0) == len(w1)
    assert [w[4] for w in w0] == [w[4] for w in w1]

    # 2. No vertical displacement: every baseline unmoved. (A 3.2pt drift from
    #    a descender bug was caught by THIS check; a raw pixel-diff threshold
    #    did not flag it, because sub-pixel kerning already moves ~30% of
    #    pixels legitimately.)
    y0 = sorted({round(w[3], 2) for w in w0})
    y1 = sorted({round(w[3], 2) for w in w1})
    assert max(abs(a - b) for a, b in zip(y0, y1)) < 0.01

    # 3. Total ink conserved: nothing darker or lighter on the page.
    a = np.frombuffer(p0.get_pixmap(dpi=150).samples, np.uint8).astype(float)
    b = np.frombuffer(p1.get_pixmap(dpi=150).samples, np.uint8).astype(float)
    assert abs(a.mean() - b.mean()) < 0.05


def test_a2_same_recipient_two_sessions_differ(env, tmp_path):
    """A2: the mark is per-SESSION, not merely per-recipient."""
    r1 = pipeline.decrypt(env["bundle"], "bob", env["ks"], env["led"],
                          tmp_path / "b1.pdf")
    r2 = pipeline.decrypt(env["bundle"], "bob", env["ks"], env["led"],
                          tmp_path / "b2.pdf")
    assert r1.record.session_id != r2.record.session_id
    assert r1.record.watermark_seed != r2.record.watermark_seed
    assert r1.record.watermark_commitment != r2.record.watermark_commitment


def test_a2_recipients_get_distinct_marks(env, tmp_path):
    outs = {}
    for u in ("alice", "bob", "carol"):
        r = pipeline.decrypt(env["bundle"], u, env["ks"], env["led"],
                             tmp_path / f"{u}.pdf")
        outs[u] = engine.extract(str(r.output_path), r.record.n_bits)
    assert outs["alice"] != outs["bob"] != outs["carol"]


def test_capacity_error_on_short_document(tmp_path):
    """A document too short to carry a codeword is REFUSED, not half-marked."""
    import pymupdf
    d = pymupdf.open()
    d.new_page().insert_text((72, 72), "too short to fingerprint")
    short = tmp_path / "short.pdf"
    d.save(short)
    with pytest.raises(engine.CapacityError):
        engine.plan_for_session(str(short), b"s" * 32, 0, 100, 3)


# --------------------------------------------------------- A9/A10/A11: verdict

def test_b7_to_b10_full_attribution(env, tmp_path):
    """B7-B10: leaked copy -> extract -> ledger match -> verified verdict."""
    outs = {}
    for u in ("alice", "bob", "carol"):
        outs[u] = pipeline.decrypt(env["bundle"], u, env["ks"], env["led"],
                                   tmp_path / f"{u}.pdf")
    for u in ("alice", "bob", "carol"):
        v = investigate(outs[u].output_path, env["led"])
        assert v.outcome is Outcome.IDENTIFIED
        assert v.recipient_user_id == u
        assert v.cryptographically_verified, v.to_dict()


def test_unwatermarked_document_accuses_nobody(env, doc, tmp_path):
    """A false accusation is worse than no attribution."""
    pipeline.decrypt(env["bundle"], "bob", env["ks"], env["led"],
                     tmp_path / "b.pdf")
    v = investigate(doc, env["led"])
    assert v.outcome is Outcome.NO_WATERMARK
    assert v.recipient_user_id is None


def test_compromised_ledger_withholds_attribution(env, tmp_path):
    """Attribution must be refused when the evidence base is unreliable."""
    r = pipeline.decrypt(env["bundle"], "bob", env["ks"], env["led"],
                         tmp_path / "b.pdf")
    env["led"].close()
    db = sqlite3.connect(str(tmp_path / "l.db"))
    e = json.loads(db.execute("SELECT entry FROM leaves WHERE idx=0").fetchone()[0])
    e["record"]["recipient_user_id"] = "zeta"
    db.execute("UPDATE leaves SET entry=? WHERE idx=0",
               (json.dumps(e, sort_keys=True, separators=(",", ":")),))
    db.commit()
    db.close()
    v = investigate(r.output_path, LedgerNode(tmp_path / "l.db"))
    assert v.outcome is Outcome.LEDGER_COMPROMISED
    assert v.recipient_user_id is None


# ----------------------------------------------------------- access control

def test_unauthorised_recipient_refused(env, tmp_path):
    ks = env["ks"]
    ks.create("mallory")
    with pytest.raises(pipeline.PipelineError, match="not an authorised"):
        pipeline.decrypt(env["bundle"], "mallory", ks, env["led"],
                         tmp_path / "m.pdf")


def test_modified_bundle_rejected(env, tmp_path):
    b = json.loads(Path(env["bundle"]).read_text())
    import base64
    ct = bytearray(base64.b64decode(b["ciphertext"]))
    ct[100] ^= 0xFF
    b["ciphertext"] = base64.b64encode(bytes(ct)).decode()
    bad = tmp_path / "bad.pqfw"
    bad.write_text(json.dumps(b))
    with pytest.raises(Exception):
        pipeline.decrypt(bad, "bob", env["ks"], env["led"], tmp_path / "x.pdf")


def test_key_substitution_refused(tmp_path):
    """Importing a different key for a known user must fail loudly."""
    a, b = Keystore(tmp_path / "a"), Keystore(tmp_path / "b")
    a.create("victim")
    b.create("victim")
    exported = b.export_public("victim", tmp_path / "evil.json")
    with pytest.raises(IdentityError, match="fingerprint"):
        a.import_public(exported)


# ----------------------------------------------------------------- Tardos

def test_tardos_identifies_single_leaker():
    n, seed = 50, b"seed" * 8
    m = tardos.required_length(n, 3)
    biases, book = tardos.codebook(n, m, seed)
    for guilty in (0, 17, 49):
        acc, s, thr = tardos.accuse(list(book[guilty]), biases, book)
        assert acc == guilty and s[guilty] > thr


def test_tardos_no_accusation_on_random_document():
    n, seed = 50, b"seed" * 8
    m = tardos.required_length(n, 3)
    biases, book = tardos.codebook(n, m, seed)
    rng = np.random.default_rng(7)
    for _ in range(20):
        y = list(rng.integers(0, 2, m).astype(int))
        acc, _, _ = tardos.accuse(y, biases, book)
        assert acc is None


def test_tardos_collusion_names_a_real_colluder():
    """Under the marking assumption, the coalition tops the ranking."""
    n, seed = 60, b"c" * 32
    m = tardos.required_length(n, 3)
    biases, book = tardos.codebook(n, m, seed)
    rng = np.random.default_rng(3)
    for _ in range(15):
        col = sorted(rng.choice(n, 3, replace=False).tolist())
        y = [int(round(float(np.mean([book[c][j] for c in col]))))
             for j in range(m)]
        top = [i for i, _ in tardos.rank_suspects(y, biases, book, top=3)]
        assert set(top) & set(col), "no colluder in the top 3"


def test_erasures_do_not_create_false_evidence():
    """An all-erasure extraction must accuse nobody."""
    n, seed = 30, b"e" * 32
    m = tardos.required_length(n, 3)
    biases, book = tardos.codebook(n, m, seed)
    acc, s, _ = tardos.accuse([None] * m, biases, book)
    assert acc is None and float(np.max(np.abs(s))) == 0.0


# ---------------------------------------------------------------- A4/A5 bind

def test_a4_record_binds_who_what_which_when(env, tmp_path):
    """A4: the record ties identity, document, watermark and time together."""
    r = pipeline.decrypt(env["bundle"], "carol", env["ks"], env["led"],
                         tmp_path / "c.pdf")
    rec = r.record
    ident = env["ks"].public("carol")

    assert rec.recipient_fingerprint == ident.fingerprint     # WHO
    assert rec.doc_hash == sha256(DOC.read_bytes())           # WHAT
    assert len(rec.watermark_commitment) == 32                # WHICH
    assert rec.session_id and rec.timestamp.endswith("+00:00")  # WHEN

    # The commitment must actually commit: changing any bit of the codeword
    # must change it, or it binds nothing.
    from pqfw.watermark.engine import WatermarkPlan
    biases = tardos.generate_biases(rec.n_bits, rec.watermark_seed)
    cw = [int(b) for b in tardos.codeword(biases, rec.user_index,
                                          rec.watermark_seed)]
    good = WatermarkPlan(rec.watermark_seed, rec.n_bits, rec.user_index,
                         rec.n_users, cw)
    assert good.commitment == rec.watermark_commitment
    flipped = list(cw)
    flipped[0] ^= 1
    bad = WatermarkPlan(rec.watermark_seed, rec.n_bits, rec.user_index,
                        rec.n_users, flipped)
    assert bad.commitment != rec.watermark_commitment


def test_a5_recipient_key_signs_record(env, tmp_path):
    """A5: the signature verifies under the RECIPIENT's key and no other."""
    r = pipeline.decrypt(env["bundle"], "carol", env["ks"], env["led"],
                         tmp_path / "c.pdf")
    carol = env["ks"].public("carol")
    alice = env["ks"].public("alice")

    assert r.signed.sig_public == carol.sig_public
    assert verify(carol.sig_public, r.record.canonical_bytes(),
                  r.signed.signature)
    # not carol's key -> must not verify
    assert not verify(alice.sig_public, r.record.canonical_bytes(),
                      r.signed.signature)
    # altered record -> must not verify
    tampered = DecryptionRecord.from_dict(
        {**r.record.to_dict(), "recipient_user_id": "alice"})
    assert not verify(carol.sig_public, tampered.canonical_bytes(),
                      r.signed.signature)


# ------------------------------------------------- A8: multi-node gossip

def _mk_signed(i, who, sk, pk):
    rec = DecryptionRecord(
        session_id=f"s{i}", doc_id="d", doc_hash=sha256(b"d"),
        recipient_fingerprint=f"fp{i}", recipient_user_id=who,
        watermark_commitment=sha256(bytes([i])), watermark_seed=bytes([i]) * 32,
        n_bits=64, user_index=i, n_users=4)
    return SignedRecord(record=rec, signature=sign(sk, rec.canonical_bytes()),
                        sig_public=pk)


def _forked_pair(tmp_path, tail_x="carol", tail_y="dave", extra_x=0):
    """Build two nodes sharing a prefix then diverging -- a real split view.

    Both halves are internally perfect: every record hashes correctly and every
    tree head verifies. Only cross-node comparison can expose the fork.
    """
    import shutil
    pk, sk = sig_keygen()
    a = LedgerNode(tmp_path / "A.db", "node-A")
    for i in range(3):
        a.append(_mk_signed(i, f"user{i}", sk, pk))
    a.close()
    shutil.copy(tmp_path / "A.db", tmp_path / "F.db")
    x = LedgerNode(tmp_path / "A.db", "node-A")
    y = LedgerNode(tmp_path / "F.db", "node-A")
    x.append(_mk_signed(3, tail_x, sk, pk))
    for j in range(extra_x):
        x.append(_mk_signed(4 + j, f"extra{j}", sk, pk))
    y.append(_mk_signed(3, tail_y, sk, pk))
    return x, y


def test_a8_gossip_accepts_honest_peer_behind(tmp_path):
    """A peer that is simply lagging must verify by consistency proof."""
    import shutil
    from pqfw.ledger import gossip
    pk, sk = sig_keygen()
    a = LedgerNode(tmp_path / "A.db", "node-A")
    for i in range(4):
        a.append(_mk_signed(i, f"user{i}", sk, pk))
    a.close()
    shutil.copy(tmp_path / "A.db", tmp_path / "B.db")
    b = LedgerNode(tmp_path / "B.db", "node-B")
    a = LedgerNode(tmp_path / "A.db", "node-A")
    a.append(_mk_signed(4, "user4", sk, pk))

    r = gossip.compare(a, gossip.export_sth(b))
    assert r.agreement is gossip.Agreement.CONSISTENT
    assert r.proof_checked, "must be proven, not merely assumed"


def test_a8_gossip_detects_split_view_same_size(tmp_path):
    """Equivocation at equal tree size: same size, different roots."""
    from pqfw.ledger import gossip
    x, y = _forked_pair(tmp_path)

    # each branch passes its OWN integrity check -- that is the whole point
    assert not x.detect_tamper()[0]
    assert not y.detect_tamper()[0]
    assert x.size() == y.size() and x.root() != y.root()

    r = gossip.compare(x, gossip.export_sth(y))
    assert r.agreement is gossip.Agreement.SPLIT_VIEW


def test_a8_gossip_detects_fork_disguised_as_lag(tmp_path):
    """A fork at unequal sizes must not pass as an honest peer-behind."""
    from pqfw.ledger import gossip
    x, y = _forked_pair(tmp_path, extra_x=1)
    assert x.size() > y.size()          # looks like y is merely behind
    r = gossip.compare(x, gossip.export_sth(y))
    assert r.agreement is gossip.Agreement.SPLIT_VIEW
    assert r.proof_checked


def test_a8_gossip_rejects_forged_sth(tmp_path):
    from pqfw.ledger import gossip
    x, y = _forked_pair(tmp_path)
    s = gossip.export_sth(y)
    s.signature = b"\x00" * 3309
    assert gossip.compare(x, s).agreement is gossip.Agreement.FORGED_STH


def test_a8_gossip_pins_log_identity(tmp_path):
    """An STH from a different log is not evidence about this one."""
    from pqfw.ledger import gossip
    pk, sk = sig_keygen()
    x = LedgerNode(tmp_path / "X.db", "node-X")
    x.append(_mk_signed(0, "a", sk, pk))
    z = LedgerNode(tmp_path / "Z.db", "node-Z")
    z.append(_mk_signed(0, "z", sk, pk))
    r = gossip.compare(x, gossip.export_sth(z), expect_node_public=x.public_key)
    assert r.agreement is gossip.Agreement.UNRELATED


def test_a8_gossip_sth_survives_file_transfer(tmp_path):
    """STHs must move across an air gap as files, not just over a socket."""
    from pqfw.ledger import gossip
    x, y = _forked_pair(tmp_path)
    p = tmp_path / "peer-sth.json"
    gossip.export_sth(y, p)
    loaded = gossip.load_sth(p)
    assert loaded.verify_signature()
    assert gossip.compare(x, loaded).agreement is gossip.Agreement.SPLIT_VIEW


def test_a8_quorum_one_split_condemns(tmp_path):
    """Consistency is not a majority vote: one valid proof of equivocation wins."""
    from pqfw.ledger import gossip
    x, y = _forked_pair(tmp_path)
    honest = gossip.compare(x, gossip.export_sth(x))
    split = gossip.compare(x, gossip.export_sth(y))
    ok, msg = gossip.quorum_view([honest, honest, honest, split])
    assert not ok and "SPLIT VIEW" in msg


def test_a8_self_comparison_is_not_corroboration(tmp_path):
    """A node agreeing with itself must not be reported as peer agreement.

    A split-view attacker always agrees with itself; counting that as
    corroboration would give an auditor false confidence.
    """
    from pqfw.ledger import gossip
    pk, sk = sig_keygen()
    n = LedgerNode(tmp_path / "A.db", "node-A")
    n.append(_mk_signed(0, "a", sk, pk))

    r = gossip.compare(n, gossip.export_sth(n))
    assert r.agreement is gossip.Agreement.CONSISTENT
    assert "not independent" in r.detail

    ok, msg = gossip.quorum_view([r])
    assert ok and "cannot detect equivocation" in msg


# ------------------------------------------- red-team regressions (found by
#                                              redteam.py, not by unit tests)

def _make_doc(path, font, size, justify, pages):
    from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate
    txt = ("Operational readiness across the northern sector remains "
           "contingent on sustained logistical throughput and the timely "
           "rotation of forward units under the established directive. ")
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=50,
                            rightMargin=50, topMargin=60, bottomMargin=60)
    st = ParagraphStyle("b", parent=getSampleStyleSheet()["Normal"],
                        fontName=font, fontSize=size, leading=size * 1.45,
                        alignment=TA_JUSTIFY if justify else TA_LEFT)
    doc.build([Paragraph(txt * 3, st) for _ in range(pages * 5)])


@pytest.mark.parametrize("font,size,justify", [
    ("Courier", 10.0, True),          # monospace: gap std 2.1pt vs 0.77
    ("Times-Roman", 11.0, True),
    ("Helvetica", 10.5, False),       # left-aligned, no justification stretch
])
def test_redteam_line_grouping_stable_across_fonts(tmp_path, font, size, justify):
    """Line grouping must survive the embed rewrite.

    Grouping by PyMuPDF's (block, line) indices broke here: a Courier page
    reported 46 lines before marking and 34 after, so the decoder read bits at
    positions the encoder never wrote. Baseline grouping is stable.
    """
    import random
    import pymupdf
    from pqfw.watermark import spacing

    src = tmp_path / "src.pdf"
    _make_doc(src, font, size, justify, 8)
    out = tmp_path / "marked.pdf"

    random.seed(11)
    bits = [random.randint(0, 1) for _ in range(256)]
    spacing.embed(str(src), str(out), bits)

    before = len(spacing._lines_of(pymupdf.open(src)[0]))
    after = len(spacing._lines_of(pymupdf.open(out)[0]))
    assert before == after, f"grouping changed {before} -> {after}"

    got = [b for b in spacing.extract(str(out)) if b is not None]
    acc = sum(1 for a, b in zip(bits, got) if a == b) / max(len(got), 1)
    assert acc == 1.0, f"recovery {acc:.1%}"


def test_redteam_excerpt_still_attributable(env, tmp_path):
    """Leaking a few pages must not defeat attribution.

    Sequential extraction reads one bit stream in page order, so a missing page
    shifts every later bit. identify_robust realigns per page.
    """
    import pymupdf
    r = pipeline.decrypt(env["bundle"], "carol", env["ks"], env["led"],
                         tmp_path / "carol.pdf")
    d = pymupdf.open(r.output_path)
    nd = pymupdf.open()
    nd.insert_pdf(d, from_page=2, to_page=4)     # three pages only
    excerpt = tmp_path / "excerpt.pdf"
    nd.save(str(excerpt))
    d.close()
    nd.close()

    v = investigate(excerpt, env["led"])
    assert v.recipient_user_id == "carol", v.to_dict()


def test_redteam_reordered_pages_still_attributable(env, tmp_path):
    """Reversed page order must not defeat attribution."""
    import pymupdf
    r = pipeline.decrypt(env["bundle"], "alice", env["ks"], env["led"],
                         tmp_path / "alice.pdf")
    d = pymupdf.open(r.output_path)
    d.select(list(range(d.page_count))[::-1])
    shuffled = tmp_path / "shuffled.pdf"
    d.save(str(shuffled))
    d.close()

    v = investigate(shuffled, env["led"])
    assert v.recipient_user_id == "alice", v.to_dict()


def test_unmarked_document_is_not_reported_as_collusion(env, doc, tmp_path):
    """An unmarked file must report NO_WATERMARK, never COLLUSION.

    Found via the UI: a pristine, never-distributed PDF yielded 34 of 1534
    slots above the confidence floor purely from natural spacing variation.
    The verdict logic treated any non-zero count as "a watermark was
    recovered" and reported the expected signature of a COLLUSION -- a false
    and damaging claim about a document that had never been distributed.
    """
    pipeline.decrypt(env["bundle"], "alice", env["ks"], env["led"],
                     tmp_path / "a.pdf")
    v = investigate(doc, env["led"])
    assert v.outcome is Outcome.NO_WATERMARK, v.to_dict()
    assert v.recipient_user_id is None
    assert not any("COLLUSION" in n for n in v.notes), v.notes
