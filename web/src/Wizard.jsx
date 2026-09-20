import { useEffect, useState } from "react";

const api = {
  async get(p) {
    const r = await fetch(p);
    if (!r.ok) {
      let msg = r.statusText;
      try { const j = await r.json(); msg = j.detail || msg; } catch (_) {}
      throw new Error(msg);
    }
    return r.json();
  },
  async post(p, b) {
    const r = await fetch(p, {
      method: "POST",
      headers: b ? { "Content-Type": "application/json" } : undefined,
      body: b ? JSON.stringify(b) : undefined,
    });
    if (!r.ok) {
      let msg = r.statusText;
      try { const j = await r.json(); msg = j.detail || msg; } catch (_) {}
      throw new Error(msg);
    }
    return r.json();
  },
};

const STAGES = ["Encrypt", "Decrypt & Watermark", "Ledger", "Breach", "Attribution"];

// One entry per stage: how to fetch it, given data already collected.
const LOADERS = [
  () => api.post("/api/wizard/stage1"),
  () => api.get("/api/wizard/stage2"),
  () => api.get("/api/wizard/stage3"),
  () => api.post("/api/wizard/stage4"),
  (all) => api.post("/api/wizard/stage5", { watermark: all[3].leaked_watermark }),
];

export default function Wizard() {
  const [stage, setStage] = useState(0);
  const [furthest, setFurthest] = useState(-1);
  const [stageData, setStageData] = useState({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const loadStage = async (n, all) => {
    setBusy(true); setErr(null);
    try {
      const result = await LOADERS[n](all);
      setStageData((d) => ({ ...d, [n]: result }));
      setFurthest((f) => Math.max(f, n));
      return result;
    } catch (e) {
      setErr(e.message);
      throw e;
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (stageData[stage] === undefined && !busy) {
      loadStage(stage, stageData).catch(() => {});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stage]);

  const nextStage = () => setStage((s) => Math.min(s + 1, STAGES.length - 1));
  const prevStage = () => setStage((s) => Math.max(s - 1, 0));
  const jumpTo = (n) => { if (n <= furthest + 1) { setErr(null); setStage(n); } };

  const startOver = () => {
    setStage(0); setFurthest(-1); setStageData({}); setErr(null);
  };

  const d = stageData[stage];

  return (
    <>
      <h1>Forensic watermark system</h1>
      <p className="sub">
        A guided run over the real pipeline: one document, encrypted once and
        decrypted independently by three recipients, each producing a
        cryptographically unique, invisible watermark tied to their own
        post-quantum identity. No canned data -- every value below comes from
        a live ML-KEM/ML-DSA run.
      </p>

      <Dots stage={stage} furthest={furthest} onJump={jumpTo} />

      {err && <p className="err" style={{ marginTop: 16 }}>{err}</p>}
      {busy && !d && <p className="dim" style={{ marginTop: 16 }}>Working&hellip;</p>}

      <div style={{ marginTop: 20 }}>
        {d && stage === 0 && <StageEncrypt d={d} busy={busy} onNext={nextStage} />}
        {d && stage === 1 && <StageWatermark d={d} busy={busy} onBack={prevStage} onNext={nextStage} />}
        {d && stage === 2 && <StageLedger d={d} busy={busy} onBack={prevStage} onNext={nextStage} />}
        {d && stage === 3 && <StageBreach d={d} busy={busy} onBack={prevStage} onNext={nextStage} />}
        {d && stage === 4 && <StageAttribution d={d} onBack={prevStage} onRestart={startOver} />}
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ */

function Dots({ stage, furthest, onJump }) {
  return (
    <div className="wiz-dots">
      {STAGES.map((label, i) => {
        const state = i < stage ? "done" : i === stage ? "active" : "pending";
        return (
          <div className="wiz-dot-wrap" key={i}>
            <button
              className="wiz-dot" data-state={state}
              disabled={i > furthest + 1}
              onClick={() => onJump(i)}
              title={label}
            >
              {state === "done" ? "✓" : i + 1}
            </button>
            <span className="wiz-dot-label">{label}</span>
            {i < STAGES.length - 1 && <div className="wiz-dot-line" data-done={i < stage} />}
          </div>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ */

function StageEncrypt({ d, busy, onNext }) {
  return (
    <div className="panel">
      <header>Stage 1 &middot; Sender encrypts once</header>
      <div className="body">
        <p className="note" style={{ marginTop: 0 }}>
          The document is encrypted a single time under a random content key.
          That key is then sealed separately per recipient with ML-KEM-768.
        </p>
        <div className="facts wiz-grid4">
          <div><span>File</span><b>{d.file}</b></div>
          <div><span>Size</span><b>{d.size}</b></div>
          <div><span>Hash</span><b className="mono">{d.hash}</b></div>
          <div><span>Cipher</span><b>{d.cipher}</b></div>
        </div>
        <div className="facts wiz-grid4" style={{ marginTop: 4 }}>
          <div><span>Doc id</span><b className="mono">{d.doc_id}</b></div>
          <div><span>Watermark capacity</span><b>{d.capacity_bits.toLocaleString()} bits</b></div>
          <div><span>Required (3 recipients)</span><b>{d.required_bits.toLocaleString()} bits</b></div>
        </div>
        <div className="row" style={{ marginTop: 18 }}>
          <button className="act" onClick={onNext} disabled={busy}>
            Proceed to decryption &rarr;
          </button>
        </div>
      </div>
    </div>
  );
}

function StageWatermark({ d, busy, onBack, onNext }) {
  return (
    <div className="panel">
      <header>Stage 2 &middot; Each recipient decrypts and is watermarked</header>
      <div className="body">
        <p className="note" style={{ marginTop: 0 }}>
          Alice, Bob and Carol each decrypt independently. Decryption embeds a
          session-unique invisible watermark, then the recipient signs a
          record of it with their own ML-DSA-65 private key.
        </p>
        <div className="wiz-recipients">
          {d.recipients.map((r) => (
            <div className="wiz-recipient" key={r.name}>
              <div className="wiz-recipient-name">{r.name}</div>
              <div className="wiz-recipient-wm mono">{r.watermark}</div>
              <div className="wiz-recipient-meta"><span>session</span><b className="mono">{r.session}</b></div>
              <div className="wiz-recipient-meta"><span>nonce</span><b className="mono">{r.nonce}</b></div>
            </div>
          ))}
        </div>
        <div className="row" style={{ marginTop: 18 }}>
          <button className="act ghost" onClick={onBack}>&larr; Back</button>
          <button className="act" onClick={onNext} disabled={busy}>
            Sign with private keys &rarr;
          </button>
        </div>
      </div>
    </div>
  );
}

function StageLedger({ d, busy, onBack, onNext }) {
  return (
    <div className="panel">
      <header>Stage 3 &middot; Signed records committed to the ledger</header>
      <div className="body">
        <p className="note" style={{ marginTop: 0 }}>
          Every signed decryption record is appended to a tamper-evident
          Merkle ledger. Each block's hash depends on the one before it, so
          rewriting history breaks the chain.
        </p>
        <div className="wiz-blocks">
          {d.blocks.map((b) => (
            <div className="wiz-block" key={b.num}>
              <div className="wiz-block-num">Block #{b.num}</div>
              <div className="wiz-block-row"><span>watermark</span><b className="mono">{b.watermark}</b></div>
              <div className="wiz-block-row"><span>signature</span><b className="mono">{b.signature}</b></div>
              <div className="wiz-block-row"><span>hash</span><b className="mono">{b.hash}</b></div>
              {b.prev !== "0x0000" && (
                <div className="wiz-block-row"><span>prev</span><b className="mono dim">{b.prev}</b></div>
              )}
            </div>
          ))}
        </div>
        <div className="row" style={{ marginTop: 18 }}>
          <button className="act ghost" onClick={onBack}>&larr; Back</button>
          <button className="act" onClick={onNext} disabled={busy}>
            Simulate breach &rarr;
          </button>
        </div>
      </div>
    </div>
  );
}

function StageBreach({ d, busy, onBack, onNext }) {
  return (
    <div className="panel">
      <header>Stage 4 &middot; Breach detected</header>
      <div className="body">
        <div className="wiz-breach-banner">&#9888; Document leaked to competitor</div>
        <p className="note">
          <code className="mono">leaked.pdf</code> found in an attacker's inbox &mdash; breach detected {d.breach_time} UTC.
        </p>
        <div className="wiz-data-card wiz-data-card-breach">
          <span>Extracted watermark</span>
          <b className="mono">{d.leaked_watermark}</b>
        </div>
        <div className="row" style={{ marginTop: 18 }}>
          <button className="act ghost" onClick={onBack}>&larr; Back</button>
          <button className="act" onClick={onNext} disabled={busy}>
            Verify attribution &rarr;
          </button>
        </div>
      </div>
    </div>
  );
}

function StageAttribution({ d, onBack, onRestart }) {
  if (!d.found) {
    return (
      <div className="panel">
        <header>Stage 5 &middot; Attribution result</header>
        <div className="body">
          <p className="note" style={{ marginTop: 0 }}>
            No verified match ({d.outcome || "not found"}). The system refuses
            to name anyone rather than guess.
          </p>
          <div className="row" style={{ marginTop: 18 }}>
            <button className="act ghost" onClick={onBack}>&larr; Back</button>
            <button className="act" onClick={onRestart}>Start over</button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="panel">
      <header>Stage 5 &middot; Attribution result</header>
      <div className="body">
        <div className="wiz-success">
          <div className="wiz-success-tag">&#10003; ATTRIBUTION VERIFIED</div>
          <div className="wiz-success-sub">Recipient: {d.user} | Block #{d.block}</div>
        </div>

        <div className="facts wiz-grid4" style={{ marginTop: 18 }}>
          <div><span>Signature</span><b className="mono">{d.signature}</b></div>
          <div><span>Block hash</span><b className="mono">{d.hash}</b></div>
          <div><span>Timestamp</span><b className="mono">{d.timestamp}</b></div>
          <div><span>Bits recovered</span><b className="mono">{d.detection?.bits_recovered}/{d.detection?.bits_expected}</b></div>
        </div>

        <div className="wiz-checks">
          <div className="wiz-check" data-ok={d.evidence?.signature_valid}>
            &#10003; Signature cryptographically verified (ML-DSA private key)
          </div>
          <div className="wiz-check" data-ok={d.evidence?.ledger_intact}>
            &#10003; Ledger chain intact (tamper-proof)
          </div>
        </div>

        <div className="row" style={{ marginTop: 18 }}>
          <button className="act ghost" onClick={onBack}>&larr; Back</button>
          <button className="act" onClick={onRestart}>Start over</button>
        </div>
      </div>
    </div>
  );
}
