import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type EncryptResult, type Identity } from "../lib/api";
import { useRun } from "../lib/run";
import { HUES } from "../acts";
import { IdentityCard, CryptoValue } from "../components/Crypto";
import { ApiTrace, Deep, Plain } from "../components/Layers";
import { ErrorPanel, Spinner } from "../components/States";

const DOC = "../demo-docs/tender-evaluation.pdf";

/** Act 1 — one encryption, many sealed keys.
 *
 * The diagram here carries the argument: because the document is encrypted
 * exactly once, every recipient's plaintext is identical, so marking before
 * distribution cannot distinguish them. Decryption is the only fork in the
 * road, which is why the mark has to be made there.
 */
export default function Act1Distribute() {
  const nav = useNavigate();
  const { bundle, setBundle } = useRun();

  const [ids, setIds] = useState<Identity[] | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [loadErr, setLoadErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [sealErr, setSealErr] = useState<unknown>(null);

  const load = async () => {
    setLoadErr(null);
    try {
      const d = await api.get<Identity[]>("/api/identities");
      setIds(d);
      setPicked(d.map((i) => i.user_id));
    } catch (e) {
      setLoadErr(e);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const seal = async () => {
    setBusy(true);
    setSealErr(null);
    try {
      const r = await api.post<EncryptResult>("/api/encrypt", {
        document: DOC,
        recipients: picked,
      });
      setBundle(r);
    } catch (e) {
      setSealErr(e);
    } finally {
      setBusy(false);
    }
  };

  const enough = bundle ? bundle.capacity_bits >= bundle.required_bits : true;

  return (
    <div className="space-y-8">
      <header>
        <p className="font-mono text-tiny text-ink-faint">Act 1</p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">
          Encrypt once, seal for each reader
        </h1>
        <Plain>
          The document is encrypted a single time. The key that opens it is then
          wrapped separately for every recipient, so each can unwrap it with
          their own private key — and nobody else's.
        </Plain>
      </header>

      {loadErr !== null && (
        <ErrorPanel
          error={loadErr}
          onRetry={load}
          context="loading the recipient list"
        />
      )}

      {!ids && !loadErr && <Spinner label="Loading recipients…" />}

      {ids && (
        <>
          <section>
            <h2 className="text-base font-medium">
              Recipients{" "}
              <span className="ml-1 font-normal text-ink-faint">
                {picked.length} of {ids.length} selected
              </span>
            </h2>
            <p className="mt-1 max-w-prose text-sm text-ink-dim">
              Each is a real cryptographic identity — an ML-KEM keypair for
              receiving, an ML-DSA keypair for signing. The fingerprint is a
              hash over both public keys.
            </p>
            <div className="mt-4 grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
              {ids.map((id, i) => (
                <IdentityCard
                  key={id.user_id}
                  userId={id.user_id}
                  fingerprint={id.fingerprint}
                  hue={HUES[i % HUES.length]!}
                  selected={picked.includes(id.user_id)}
                  disabled={!!bundle}
                  onToggle={
                    bundle
                      ? undefined
                      : () =>
                          setPicked((p) =>
                            p.includes(id.user_id)
                              ? p.filter((u) => u !== id.user_id)
                              : [...p, id.user_id],
                          )
                  }
                />
              ))}
            </div>
          </section>

          <SealDiagram recipients={picked} sealed={!!bundle} />

          {sealErr !== null && (
            <ErrorPanel
              error={sealErr}
              onRetry={seal}
              context="encrypting the document"
            />
          )}

          {!bundle ? (
            <div className="flex flex-wrap items-center gap-4">
              <button
                onClick={seal}
                disabled={busy || picked.length === 0}
                className="rounded-md bg-[var(--btn-primary-bg)] px-4 py-2.5 text-base font-medium text-[var(--btn-primary-ink)] transition-colors duration-fast hover:bg-[var(--btn-primary-bg-hover)] disabled:opacity-45"
              >
                {busy
                  ? "Encrypting…"
                  : `Encrypt for ${picked.length} recipient${picked.length === 1 ? "" : "s"}`}
              </button>
              {picked.length === 0 && (
                <span className="text-sm text-ink-faint">
                  Select at least one recipient.
                </span>
              )}
            </div>
          ) : (
            <section className="rounded-[var(--card-radius)] border border-verified/40 bg-verified/5 p-4">
              <div className="flex items-center gap-2">
                <span className="grid h-4 w-4 place-items-center rounded-full bg-verified/20 text-[10px] font-bold text-verified" aria-hidden>
                  ✓
                </span>
                <h2 className="text-base font-medium text-verified">
                  Sealed for {bundle.recipients.length} recipients
                </h2>
              </div>
              <Plain>
                One ciphertext now exists, with {bundle.recipients.length}{" "}
                separately-wrapped copies of its key. Every recipient will
                decrypt to exactly the same bytes — which is precisely why the
                mark has to be added when they open it.
              </Plain>

              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                <CryptoValue label="document id" value={bundle.doc_id} head={14} />
                <div>
                  <div className="text-micro text-ink-faint">
                    watermark capacity
                  </div>
                  <div className="mt-1 font-mono text-tiny">
                    <span className={enough ? "text-verified" : "text-broken"}>
                      {bundle.capacity_bits.toLocaleString()} bits available
                    </span>
                    <span className="text-ink-faint">
                      {" "}· {bundle.required_bits.toLocaleString()} required
                    </span>
                  </div>
                </div>
              </div>

              <Deep title="Why those two numbers">
                <p className="text-sm text-ink-dim">
                  The mark must survive recipients comparing copies to find and
                  strip it. A Tardos fingerprinting code resists that, but its
                  length grows as c²·ln(n/ε) — {bundle.required_bits} bits for{" "}
                  {bundle.recipients.length} recipients against 3 colluders.
                  Body text carries roughly 275 bits per page. A document too
                  short to hold a full codeword is refused rather than
                  half-marked.
                </p>
                <ApiTrace method="POST" path="/api/encrypt" response={bundle} />
              </Deep>

              <button
                onClick={() => nav("/open")}
                className="mt-5 rounded-md bg-[var(--btn-primary-bg)] px-4 py-2.5 text-base font-medium text-[var(--btn-primary-ink)] transition-colors duration-fast hover:bg-[var(--btn-primary-bg-hover)]"
              >
                Next — open it as a recipient
              </button>
            </section>
          )}
        </>
      )}
    </div>
  );
}

/* ------------------------------------------------------------- diagram */

function SealDiagram({
  recipients,
  sealed,
}: {
  recipients: string[];
  sealed: boolean;
}) {
  const n = Math.max(recipients.length, 1);
  const H = Math.max(180, 30 + n * 38);
  const midY = H / 2;

  return (
    <figure className="m-0">
      <svg
        viewBox={`0 0 700 ${H}`}
        role="img"
        aria-label="The document is encrypted once; the content key is wrapped separately for each recipient."
        className="w-full rounded-[var(--card-radius)] border border-line bg-surface"
      >
        <defs>
          <marker id="s-ar" viewBox="0 0 10 10" refX="9" refY="5"
                  markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill="currentColor" />
          </marker>
        </defs>

        <rect x="18" y={midY - 26} width="120" height="52" rx="7"
              fill="none" stroke="currentColor" strokeWidth="1.3" opacity=".85" />
        <text x="78" y={midY - 4} textAnchor="middle" fontSize="12"
              fill="currentColor" fontWeight="600">document</text>
        <text x="78" y={midY + 13} textAnchor="middle" fontSize="10"
              fill="currentColor" opacity=".55">encrypted once</text>

        <line x1="138" y1={midY} x2="196" y2={midY} stroke="currentColor"
              strokeWidth="1.3" markerEnd="url(#s-ar)" opacity=".7" />

        <rect x="200" y={midY - 24} width="112" height="48" rx="7"
              fill="none" stroke={sealed ? "var(--verified)" : "currentColor"}
              strokeWidth="1.3" opacity={sealed ? 1 : 0.6} />
        <text x="256" y={midY - 4} textAnchor="middle" fontSize="11.5"
              fill={sealed ? "var(--verified)" : "currentColor"}>content key</text>
        <text x="256" y={midY + 12} textAnchor="middle" fontSize="9.5"
              fill="currentColor" opacity=".55">AES-256</text>

        {recipients.map((r, i) => {
          const y = 22 + i * 38;
          const hue = HUES[i % HUES.length]!;
          return (
            <g key={r}>
              <path
                d={`M312,${midY} C 360,${midY} 370,${y + 14} 418,${y + 14}`}
                fill="none" stroke={hue} strokeWidth="1.3"
                opacity={sealed ? 0.9 : 0.45}
                markerEnd="url(#s-ar)"
              />
              <rect x="424" y={y} width="176" height="28" rx="6"
                    fill="none" stroke={hue} strokeWidth="1.2"
                    opacity={sealed ? 0.9 : 0.5} />
              <text x="436" y={y + 18} fontSize="11" fill={hue}>
                {r}
              </text>
              <text x="592" y={y + 18} textAnchor="end" fontSize="9.5"
                    fill="currentColor" opacity=".5"
                    fontFamily="JetBrains Mono, monospace">
                ML-KEM
              </text>
            </g>
          );
        })}

        <text x="512" y={H - 6} textAnchor="middle" fontSize="10"
              fill="currentColor" opacity=".55">
          {sealed
            ? "one ciphertext · one wrapped key each"
            : "the key will be wrapped once per recipient"}
        </text>
      </svg>
      <figcaption className="mt-2.5 max-w-prose text-sm text-ink-faint">
        The document is encrypted <em>once</em>. Only the key is wrapped per
        recipient — so all five plaintexts are identical, and decryption is the
        first and only point where copies can be told apart.
      </figcaption>
    </figure>
  );
}
