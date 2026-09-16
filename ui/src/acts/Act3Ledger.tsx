import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { HUES } from "../acts";
import { CryptoValue } from "../components/Crypto";
import { ApiTrace, Deep, Plain } from "../components/Layers";
import { ErrorPanel, Spinner } from "../components/States";

/** Act 3 — the ledger, and why an administrator cannot rewrite it.
 *
 * Two jobs. First, show the records as a *chain* so the linkage is visible —
 * a flat table is indistinguishable from a database viewer. Second, make the
 * tamper-evidence demonstrable: break a record on purpose and show precisely
 * which one broke and why, never a generic "tampered" banner.
 */

interface ChainRecord {
  index: number;
  user_id: string;
  fingerprint: string;
  doc_id: string;
  session_id: string;
  timestamp: string;
  n_bits: number;
  leaf_hash: string;
  signature_valid: boolean;
  signature_len: number;
  broken: boolean;
}

interface Chain {
  size: number;
  root: string;
  sth: {
    tree_size: number;
    root: string;
    signed_at: string;
    signature_bytes: number;
    valid: boolean;
    algorithm: string;
  } | null;
  integrity: {
    intact: boolean;
    first_broken_index: number | null;
    message: string;
  };
  records: ChainRecord[];
}

interface TamperResult {
  edited_index: number;
  from: string;
  to: string;
  detected: boolean;
  detected_at: number | null;
  message: string;
}

export default function Act3Ledger() {
  const nav = useNavigate();
  const [chain, setChain] = useState<Chain | null>(null);
  const [rev, setRev] = useState(0);
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState<null | "tamper" | "restore" | "verify">(null);
  const [tamper, setTamper] = useState<TamperResult | null>(null);
  const [actionErr, setActionErr] = useState<unknown>(null);

  const load = useCallback(async () => {
    setErr(null);
    try {
      setChain(await api.get<Chain>("/api/ledger/chain"));
      setRev((v) => v + 1);
    } catch (e) {
      setErr(e);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const recipients = [...new Set(chain?.records.map((r) => r.user_id) ?? [])];
  const hueOf = (u: string) =>
    HUES[Math.max(0, recipients.indexOf(u)) % HUES.length]!;

  const doTamper = async () => {
    if (!chain || chain.records.length === 0) return;
    // Target a record in the middle of the chain -- breaking the last one
    // would be less convincing, because everything after it is unaffected.
    const target =
      chain.records[Math.floor(chain.records.length / 2)]?.index ?? 0;
    setBusy("tamper");
    setActionErr(null);
    try {
      const r = await api.post<TamperResult>("/api/ledger/tamper", {
        index: target,
        new_user_id: "someone_else",
      });
      setTamper(r);
      await load();
    } catch (e) {
      setActionErr(e);
    } finally {
      setBusy(null);
    }
  };

  const doRestore = async () => {
    setBusy("restore");
    setActionErr(null);
    try {
      await api.post("/api/ledger/restore", undefined, 180_000);
      setTamper(null);
      await load();
    } catch (e) {
      setActionErr(e);
    } finally {
      setBusy(null);
    }
  };

  const doVerify = async () => {
    setBusy("verify");
    setActionErr(null);
    try {
      await load();
    } finally {
      setBusy(null);
    }
  };

  const intact = chain?.integrity.intact ?? true;

  return (
    <div className="space-y-8">
      <header>
        <p className="font-mono text-tiny text-ink-faint">Act 3</p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">
          The record nobody can quietly change
        </h1>
        <Plain>
          Every opening becomes a link in a chain. Each link carries a hash of
          its own contents, and the end of the chain is signed. Change anything
          earlier and the chain stops matching its own signature — including for
          an administrator with full access to the database.
        </Plain>
      </header>

      {err !== null && (
        <ErrorPanel error={err} onRetry={load} context="loading the ledger" />
      )}
      {!chain && err === null && <Spinner label="Reading the ledger…" />}

      {chain && (
        <>
          <IntegrityBanner
            intact={intact}
            message={chain.integrity.message}
            brokenIndex={chain.integrity.first_broken_index}
            tamper={tamper}
          />

          {actionErr !== null && (
            <ErrorPanel error={actionErr} context="acting on the ledger" />
          )}

          <section className="flex flex-wrap gap-2.5">
            <button
              onClick={doVerify}
              disabled={busy !== null}
              className="rounded-md border border-[var(--btn-ghost-border)] px-3.5 py-2 text-sm transition-colors duration-fast hover:border-ink-faint disabled:opacity-45"
            >
              {busy === "verify" ? "Checking…" : "Check integrity"}
            </button>
            {intact ? (
              <button
                onClick={doTamper}
                disabled={busy !== null}
                className="rounded-md border border-broken/50 bg-broken/10 px-3.5 py-2 text-sm text-broken transition-colors duration-fast hover:bg-broken/20 disabled:opacity-45"
              >
                {busy === "tamper"
                  ? "Editing the database…"
                  : "Tamper with a record (as an administrator)"}
              </button>
            ) : (
              <button
                onClick={doRestore}
                disabled={busy !== null}
                className="rounded-md border border-[var(--btn-ghost-border)] px-3.5 py-2 text-sm transition-colors duration-fast hover:border-ink-faint disabled:opacity-45"
              >
                {busy === "restore" ? "Rebuilding…" : "Rebuild a clean ledger"}
              </button>
            )}
          </section>

          <SignedHead sth={chain.sth} intact={intact} />

          <section>
            <h2 className="text-base font-medium">
              The chain{" "}
              <span className="ml-1 font-normal text-ink-faint">
                {chain.size} records
              </span>
            </h2>
            <p className="mt-1 max-w-prose text-sm text-ink-dim">
              Newest last. Each record's hash feeds the one above it, all the
              way to the signed head.
            </p>
            <ChainView records={chain.records} hueOf={hueOf} ledgerRev={rev} />
          </section>

          <Deep title="What makes this tamper-evident">
            <p className="text-sm text-ink-dim">
              The records form a Merkle tree (RFC 6962 — the same construction
              that secures the web's certificate system). Each record is hashed;
              pairs of hashes are hashed together; the single hash at the top is
              signed with ML-DSA-65. Editing one record changes its hash, which
              changes its parent, and so on to the root — so the stored tree no
              longer matches the signature.
            </p>
            <p className="text-sm text-ink-dim">
              To hide an edit an administrator would need the node's signing key
              to forge a new head, <em>and</em> the recipient's key to re-sign
              the altered record. Those are different keys, held by different
              parties.
            </p>
            <ApiTrace method="GET" path="/api/ledger/chain" response={chain} />
          </Deep>

          <div className="border-t border-line pt-6">
            <button
              onClick={() => nav("/leak")}
              className="rounded-md bg-[var(--btn-primary-bg)] px-4 py-2.5 text-base font-medium text-[var(--btn-primary-ink)] transition-colors duration-fast hover:bg-[var(--btn-primary-bg-hover)]"
            >
              Next — the document surfaces
            </button>
          </div>
        </>
      )}
    </div>
  );
}

/* ------------------------------------------------------------- banner */

function IntegrityBanner({
  intact,
  message,
  brokenIndex,
  tamper,
}: {
  intact: boolean;
  message: string;
  brokenIndex: number | null;
  tamper: TamperResult | null;
}) {
  if (intact) {
    return (
      <section className="rounded-[var(--card-radius)] border border-verified/40 bg-verified/5 p-4">
        <div className="flex items-center gap-2.5">
          <span className="grid h-5 w-5 place-items-center rounded-full bg-verified/20 text-tiny font-bold text-verified" aria-hidden>
            ✓
          </span>
          <h2 className="text-base font-medium text-verified">Ledger intact</h2>
        </div>
        <p className="mt-1.5 max-w-prose text-sm text-ink-dim">
          Every record still hashes to the value committed to the tree, every
          recipient's signature still verifies, and the signed head matches.
        </p>
      </section>
    );
  }

  return (
    <section className="rounded-[var(--card-radius)] border border-broken/50 bg-broken/5 p-4">
      <div className="flex items-center gap-2.5">
        <span className="grid h-5 w-5 place-items-center rounded-full bg-broken/20 text-tiny font-bold text-broken" aria-hidden>
          ✕
        </span>
        <h2 className="text-base font-medium text-broken">Tampering detected</h2>
      </div>

      {tamper && (
        <p className="mt-2 max-w-prose text-sm text-ink-dim">
          An administrator edited the database directly, changing record{" "}
          <strong className="font-medium text-ink">#{tamper.edited_index}</strong>{" "}
          from <strong className="font-medium text-ink">{tamper.from}</strong> to{" "}
          <strong className="font-medium text-ink">{tamper.to}</strong> — bypassing
          the application entirely, exactly as a privileged insider would.
        </p>
      )}

      <div className="mt-3 rounded-md border border-broken/30 bg-ground p-3">
        <div className="text-micro text-ink-faint">what the ledger reports</div>
        <p className="mt-1 text-sm text-broken">{message}</p>
      </div>

      <p className="mt-3 max-w-prose text-sm text-ink-dim">
        The system did not merely notice that <em>something</em> is wrong — it
        named the record
        {brokenIndex !== null && (
          <>
            {" "}
            (<strong className="font-medium text-ink">#{brokenIndex}</strong>)
          </>
        )}{" "}
        and the reason. Attribution is withheld while the evidence base is
        unreliable, which you will see in Act 5.
      </p>
    </section>
  );
}

/* --------------------------------------------------------------- head */

function SignedHead({
  sth,
  intact,
}: {
  sth: Chain["sth"];
  intact: boolean;
}) {
  if (!sth) return null;
  return (
    <section className="rounded-[var(--card-radius)] border border-line bg-surface p-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <h2 className="text-base font-medium">Signed head of the chain</h2>
        <span
          className={`rounded-full px-2 py-0.5 font-mono text-micro ${
            sth.valid && intact
              ? "bg-verified/15 text-verified"
              : "bg-broken/15 text-broken"
          }`}
        >
          {sth.valid && intact ? "signature valid" : "no longer matches"}
        </span>
      </div>
      <p className="mt-1.5 max-w-prose text-sm text-ink-dim">
        One hash summarising all {sth.tree_size} records, signed so it cannot be
        replaced without the node's private key.
      </p>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <CryptoValue
          label="root hash"
          value={sth.root}
          head={20}
          note={`covers ${sth.tree_size} records`}
          tone={sth.valid && intact ? "verified" : "broken"}
        />
        <div>
          <div className="text-micro text-ink-faint">signature</div>
          <div className="mt-1 font-mono text-tiny">
            {sth.algorithm} · {sth.signature_bytes.toLocaleString()} bytes
          </div>
        </div>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------- chain */

function ChainView({
  records,
  hueOf,
  ledgerRev,
}: {
  records: ChainRecord[];
  hueOf: (u: string) => string;
  ledgerRev: number;
}) {
  const [open, setOpen] = useState<number | null>(null);
  const shown = records.slice(-12);

  return (
    <div className="mt-4">
      {records.length > shown.length && (
        <p className="mb-2 font-mono text-micro text-ink-faint">
          showing the most recent {shown.length} of {records.length}
        </p>
      )}
      <ol className="space-y-0">
        {shown.map((r, i) => {
          const isOpen = open === r.index;
          return (
            <li key={r.index} className="relative">
              {i < shown.length - 1 && (
                <span
                  className={`absolute left-[15px] top-[38px] h-[calc(100%-30px)] w-px ${
                    r.broken ? "bg-broken/50" : "bg-line"
                  }`}
                  aria-hidden
                />
              )}
              <button
                onClick={() => setOpen(isOpen ? null : r.index)}
                aria-expanded={isOpen}
                className={`flex w-full items-start gap-3 rounded-md px-1 py-2 text-left transition-colors duration-fast hover:bg-raised/60 ${
                  r.broken ? "bg-broken/5" : ""
                }`}
              >
                <span
                  className={`relative z-10 mt-0.5 grid h-[31px] w-[31px] shrink-0 place-items-center rounded-full border font-mono text-[11px] ${
                    r.broken
                      ? "border-broken bg-broken/15 text-broken"
                      : "border-line bg-surface text-ink-dim"
                  }`}
                >
                  {r.broken ? "✕" : r.index}
                </span>

                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-baseline gap-x-2">
                    <span
                      className="h-2 w-2 shrink-0 translate-y-[3px] rounded-full"
                      style={{ background: hueOf(r.user_id) }}
                      aria-hidden
                    />
                    <span className="text-sm font-medium capitalize">
                      {r.user_id}
                    </span>
                    <span className="font-mono text-micro text-ink-faint">
                      {r.leaf_hash.slice(0, 12)}…
                    </span>
                    <span className="ml-auto font-mono text-micro text-ink-faint">
                      {r.timestamp.replace("T", " ").slice(0, 19)}
                    </span>
                  </span>
                  {r.broken && (
                    <span className="mt-0.5 block text-micro text-broken">
                      this record no longer matches the hash committed to the
                      tree
                    </span>
                  )}
                </span>
              </button>

              {isOpen && (
                <div className="mb-2 ml-[43px] rounded-md border border-line bg-raised/50 p-3">
                  <div className="grid gap-3 sm:grid-cols-2">
                    <CryptoValue
                      label="leaf hash"
                      value={r.leaf_hash}
                      head={16}
                      tone={r.broken ? "broken" : "default"}
                    />
                    <CryptoValue
                      label="recipient fingerprint"
                      value={r.fingerprint}
                      head={16}
                    />
                    <CryptoValue
                      label="session"
                      value={r.session_id}
                      head={16}
                    />
                    <div>
                      <div className="text-micro text-ink-faint">
                        recipient's signature
                      </div>
                      <div
                        className={`mt-1 font-mono text-tiny ${
                          r.signature_valid ? "text-verified" : "text-broken"
                        }`}
                      >
                        {r.signature_valid ? "verifies" : "does not verify"} ·{" "}
                        {r.signature_len.toLocaleString()} bytes
                      </div>
                    </div>
                  </div>
                  <VerifyNow index={r.index} ledgerRev={ledgerRev} />
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

/* --------------------------------------------------------- verify now */

interface VerifyCheck {
  id: string;
  label: string;
  passed: boolean;
  detail: string;
}

function VerifyNow({ index, ledgerRev }: { index: number; ledgerRev: number }) {
  const [res, setRes] = useState<{ checks: VerifyCheck[]; all_passed: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);

  // A verification is a snapshot of one moment. If the ledger changes (the
  // tamper button), the old result is stale -- keeping it on screen would have
  // it claiming "history has not been rewritten" next to a broken chain.
  useEffect(() => {
    setRes(null);
    setErr(null);
  }, [ledgerRev]);

  const run = async () => {
    setBusy(true);
    setErr(null);
    try {
      setRes(
        await api.post<{ checks: VerifyCheck[]; all_passed: boolean }>(
          "/api/verify-signature",
          { index },
        ),
      );
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-3 border-t border-line-soft pt-3">
      {!res && (
        <button
          onClick={run}
          disabled={busy}
          className="rounded-md border border-[var(--btn-ghost-border)] px-3 py-1.5 text-tiny transition-colors duration-fast hover:border-ink-faint disabled:opacity-45"
        >
          {busy ? "Verifying…" : "Verify this record now"}
        </button>
      )}
      {err !== null && <ErrorPanel error={err} onRetry={run} />}
      {res && (
        <div className="space-y-1.5">
          {res.checks.map((c) => (
            <div key={c.id} className="flex items-start gap-2">
              <span
                className={`mt-0.5 grid h-3.5 w-3.5 shrink-0 place-items-center rounded-full text-[9px] font-bold ${
                  c.passed
                    ? "bg-verified/15 text-verified"
                    : "bg-broken/15 text-broken"
                }`}
                aria-hidden
              >
                {c.passed ? "✓" : "✕"}
              </span>
              <div className="min-w-0">
                <div className={`text-tiny ${c.passed ? "" : "text-broken"}`}>
                  {c.label}
                </div>
                <div className="font-mono text-[10.5px] text-ink-faint">
                  {c.detail}
                </div>
              </div>
            </div>
          ))}
          <p className="pt-1 text-micro text-ink-faint">
            Checked just now, against the live ledger — not a stored result.
          </p>
        </div>
      )}
    </div>
  );
}
