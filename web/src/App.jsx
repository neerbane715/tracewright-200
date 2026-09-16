import { useEffect, useState } from "react";
import Wizard from "./Wizard.jsx";

const api = {
  async get(p) { const r = await fetch(p); if (!r.ok) throw new Error((await r.json()).detail); return r.json(); },
  async post(p, b) {
    const r = await fetch(p, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) });
    if (!r.ok) throw new Error((await r.json()).detail); return r.json();
  },
  async upload(p, file) {
    const fd = new FormData(); fd.append("file", file);
    const r = await fetch(p, { method: "POST", body: fd });
    if (!r.ok) throw new Error((await r.json()).detail); return r.json();
  },
};

const VIEWS = [
  ["wizard", "Wizard"],
  ["distribute", "Distribute"],
  ["receive", "Receive"],
  ["investigate", "Investigate"],
  ["ledger", "Ledger"],
];

export default function App() {
  const [view, setView] = useState("wizard");
  const [ledger, setLedger] = useState(null);
  const refresh = () => api.get("/api/ledger").then(setLedger).catch(() => {});
  useEffect(() => { refresh(); }, []);

  return (
    <div className="app">
      <aside className="rail">
        <div className="brand">
          <b>PQ-FORENSIC</b>
          <span>ML-KEM-768 · ML-DSA-65</span>
        </div>
        <nav>
          {VIEWS.map(([k, label]) => (
            <button key={k} aria-current={view === k} onClick={() => setView(k)}>{label}</button>
          ))}
        </nav>
        <div className="foot">
          <div className="air">● air-gapped</div>
          <div>ledger {ledger ? `${ledger.size} records` : "—"}</div>
        </div>
      </aside>
      <main>
        {view === "wizard" && <Wizard />}
        {view === "distribute" && <Distribute onDone={refresh} />}
        {view === "receive" && <Receive onDone={refresh} />}
        {view === "investigate" && <Investigate />}
        {view === "ledger" && <Ledger data={ledger} refresh={refresh} />}
      </main>
    </div>
  );
}

/* ------------------------------------------------------------------ */

function Distribute({ onDone }) {
  const [ids, setIds] = useState([]);
  const [picked, setPicked] = useState([]);
  const [res, setRes] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => { api.get("/api/identities").then(d => { setIds(d); setPicked(d.map(i => i.user_id)); }); }, []);

  const run = async () => {
    setErr(null);
    try {
      setRes(await api.post("/api/encrypt", { document: "../spike/out/original.pdf", recipients: picked }));
      onDone();
    } catch (e) { setErr(e.message); }
  };

  return (
    <>
      <h1>Distribute a document</h1>
      <p className="sub">
        The file is encrypted once under a single content key. That key is then sealed
        separately for each recipient with ML-KEM. Every recipient decrypts to byte-identical
        plaintext — which is exactly why attribution needs a watermark.
      </p>

      <div className="panel" style={{ marginBottom: 16 }}>
        <header>Recipients</header>
        <div className="body">
          <table>
            <tbody>
              {ids.map(i => (
                <tr key={i.user_id}>
                  <td style={{ width: 34 }}>
                    <input type="checkbox" checked={picked.includes(i.user_id)}
                      onChange={e => setPicked(p => e.target.checked ? [...p, i.user_id] : p.filter(x => x !== i.user_id))} />
                  </td>
                  <td>{i.user_id}</td>
                  <td className="mono dim">{i.fingerprint}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="row">
        <button className="act" onClick={run} disabled={!picked.length}>Encrypt for {picked.length} recipients</button>
      </div>
      {err && <p className="err">{err}</p>}

      {res && (
        <div className="panel" style={{ marginTop: 16 }}>
          <header>Bundle created</header>
          <div className="body facts">
            <div><span>document id</span><b>{res.doc_id}</b></div>
            <div><span>recipient slots</span><b>{res.recipients.length}</b></div>
            <div><span>watermark capacity</span><b>{res.capacity_bits.toLocaleString()} bits</b></div>
            <div><span>required for 3 colluders</span><b>{res.required_bits.toLocaleString()} bits</b></div>
          </div>
        </div>
      )}
    </>
  );
}

/* ------------------------------------------------------------------ */

function Receive({ onDone }) {
  const [ids, setIds] = useState([]);
  const [who, setWho] = useState("");
  const [res, setRes] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.get("/api/identities").then(d => { setIds(d); setWho(d[0]?.user_id ?? ""); }); }, []);

  const run = async () => {
    setBusy(true); setErr(null); setRes(null);
    try {
      setRes(await api.post("/api/decrypt", { bundle: "classified-report.pqfw", identity: who }));
      onDone();
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };

  return (
    <>
      <h1>Receive and decrypt</h1>
      <p className="sub">
        Decryption is not a passive read. It marks the copy, signs a record with the
        recipient's own private key, and commits that record to the ledger before the
        file is written.
      </p>

      <div className="row" style={{ marginBottom: 18 }}>
        <select value={who} onChange={e => setWho(e.target.value)}>
          {ids.map(i => <option key={i.user_id} value={i.user_id}>{i.user_id}</option>)}
        </select>
        <button className="act" onClick={run} disabled={busy || !who}>
          {busy ? "Working…" : "Decrypt as " + who}
        </button>
      </div>
      {err && <p className="err">{err}</p>}

      {res && (
        <div className="stack">
          <div className="panel">
            <header>What happened</header>
            <div className="body">
              <ol className="steps">{res.steps.map((s, i) => <li key={i} className="done">{s}</li>)}</ol>
            </div>
          </div>
          <div className="panel">
            <header>Your copy</header>
            <div className="body facts">
              <div><span>file</span><b>{res.output.split(/[\\/]/).pop()}</b></div>
              <div><span>session</span><b>{res.session_id.slice(0, 16)}…</b></div>
              <div><span>watermark</span><b>{res.bits} bits, invisible</b></div>
              <div><span>ledger index</span><b>#{res.ledger_index}</b></div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

/* ------------------------------------------------------------------ */

const CHECKS = [
  ["signature_valid", "Recipient signed this decryption with their ML-DSA key"],
  ["inclusion_proof_valid", "Record is provably in the ledger"],
  ["watermark_commitment_valid", "Mark in the file matches the mark they signed for"],
  ["ledger_intact", "Ledger history has not been rewritten"],
];

function Investigate() {
  const [v, setV] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState(null);

  const onFile = async e => {
    const f = e.target.files?.[0]; if (!f) return;
    setName(f.name); setBusy(true); setErr(null); setV(null);
    try { setV(await api.upload("/api/investigate", f)); }
    catch (x) { setErr(x.message); } finally { setBusy(false); }
  };

  return (
    <>
      <h1>Investigate a leak</h1>
      <p className="sub">
        Upload a document that escaped. The watermark is recovered from the file itself,
        matched against the ledger, and the resulting record is verified end to end.
      </p>

      <div className="row" style={{ marginBottom: 20 }}>
        <label className="drop">
          <input type="file" accept="application/pdf" onChange={onFile} />
          <span>{name ?? "Choose a leaked PDF"}</span>
        </label>
        {busy && <span className="dim">Extracting…</span>}
      </div>
      {err && <p className="err">{err}</p>}

      {v && (
        <>
          <div className="verdict" data-o={v.outcome}>
            <div className="tag">{v.outcome.replace(/_/g, " ")}</div>
            <div className="who">{v.recipient.user_id ?? "No recipient named"}</div>
            {v.recipient.fingerprint && <div className="mono dim">{v.recipient.fingerprint}</div>}
            {v.outcome === "IDENTIFIED" && (
              <div className="facts">
                <div><span>decrypted at</span><b>{v.event.timestamp?.replace("T", " ").slice(0, 19)}</b></div>
                <div><span>session</span><b>{v.event.session_id?.slice(0, 16)}…</b></div>
                <div><span>ledger record</span><b>#{v.event.ledger_index}</b></div>
                <div><span>bits recovered</span><b>{v.detection.bits_recovered} / {v.detection.bits_expected}</b></div>
                <div><span>score vs threshold</span><b>{Math.round(v.detection.score)} / {Math.round(v.detection.threshold)}</b></div>
                <div><span>separation</span><b>{v.detection.margin?.toFixed(2)}σ</b></div>
              </div>
            )}
          </div>

          <div className="seal">
            {CHECKS.map(([k, label]) => (
              <div className="chk" key={k} data-ok={v.evidence[k]}>
                <div className="name">{label}</div>
                <div className="state"><i className="dot" />{v.evidence[k] ? "verified" : "failed"}</div>
              </div>
            ))}
          </div>

          {v.ranking?.length > 1 && v.outcome === "INCONCLUSIVE" && (
            <div className="panel" style={{ marginTop: 16 }}>
              <header>Ranked suspects — a flat spread here is the signature of collusion</header>
              <div className="body">
                <table>
                  <tbody>{v.ranking.map(([u, s], i) => (
                    <tr key={i}><td style={{ width: 30 }} className="dim">{i + 1}</td><td>{u}</td>
                      <td className="mono">{Math.round(s)}</td></tr>))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {v.notes.map((n, i) => <p className="note" key={i}>{n}</p>)}
        </>
      )}
    </>
  );
}

/* ------------------------------------------------------------------ */

function Ledger({ data, refresh }) {
  const [status, setStatus] = useState(null);
  const [tampered, setTampered] = useState(null);

  const verify = async () => setStatus(await api.get("/api/ledger/verify"));
  const tamper = async () => {
    const r = await api.post("/api/ledger/tamper", { index: 1, new_user_id: "erin" });
    setTampered(r); setStatus({ tampered: r.detected, index: r.detected_at, message: r.message });
    refresh();
  };

  if (!data) return <p className="dim">Loading…</p>;

  return (
    <>
      <h1>Audit ledger</h1>
      <p className="sub">
        Every decryption, in order, each one signed by the recipient who performed it.
        The tree head below is signed too, so rewriting any earlier record breaks the chain.
      </p>

      <div className="grid2" style={{ marginBottom: 16 }}>
        <div className="panel">
          <header>Signed tree head</header>
          <div className="body">
            <div className="facts" style={{ marginTop: 0 }}>
              <div><span>records</span><b>{data.size}</b></div>
              <div><span>signature</span><b>{data.sth?.signature_bytes} bytes</b></div>
            </div>
            <div style={{ marginTop: 13 }}>
              <span className="dim" style={{ fontSize: 11.5 }}>root hash</span>
              <div className="hash">{data.root}</div>
            </div>
          </div>
        </div>
        <div className="panel">
          <header>Integrity</header>
          <div className="body">
            <div className="row">
              <button className="act ghost" onClick={verify}>Check integrity</button>
              <button className="act danger" onClick={tamper}>Tamper as administrator</button>
            </div>
            {tampered && (
              <p className="note">
                Edited record #{tampered.edited_index} directly in the database:
                recipient changed from <b>{tampered.from}</b> to <b>{tampered.to}</b>,
                bypassing the application entirely.
              </p>
            )}
            {status && (
              <p className="note" style={{ color: status.tampered ? "var(--bad)" : "var(--ok)" }}>
                {status.message}
              </p>
            )}
          </div>
        </div>
      </div>

      <div className="panel">
        <header>Decryption records</header>
        <table>
          <thead><tr><th style={{ width: 44 }}>#</th><th>Recipient</th><th>Fingerprint</th><th>Session</th><th>When</th></tr></thead>
          <tbody>
            {data.records.map(r => (
              <tr key={r.index}>
                <td className="dim mono">{r.index}</td>
                <td>{r.user_id}</td>
                <td className="mono dim">{r.fingerprint}</td>
                <td className="mono dim">{r.session_id.slice(0, 12)}</td>
                <td className="dim">{r.timestamp.replace("T", " ").slice(0, 19)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
