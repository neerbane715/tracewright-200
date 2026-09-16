import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type DecryptResult, type Identity } from "../lib/api";
import { useRun, type OpenedCopy } from "../lib/run";
import { HUES } from "../acts";
import { CryptoValue, IdentityCard } from "../components/Crypto";
import { ApiTrace, Deep, Plain, useDepth } from "../components/Layers";
import { ErrorPanel, Spinner, StagedProgress } from "../components/States";

/** Act 2 — provenance being created.
 *
 * The two things this screen must achieve:
 *   1. Make the six pipeline steps feel like something being *made*, not
 *      reported after the fact.
 *   2. PROVE the core claim rather than assert it — two copies, byte-distinct,
 *      word-for-word identical, zero baseline shift. Those numbers come from
 *      /api/compare measuring the actual files.
 */
export default function Act2Open() {
  const nav = useNavigate();
  const { opened, addOpened } = useRun();
  const { deep } = useDepth();

  const [ids, setIds] = useState<Identity[] | null>(null);
  const [loadErr, setLoadErr] = useState<unknown>(null);
  const [who, setWho] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState(0);
  const [err, setErr] = useState<unknown>(null);
  const [last, setLast] = useState<DecryptResult | null>(null);
  const [bundle, setBundle] = useState<string | null>(null);

  const load = async () => {
    setLoadErr(null);
    try {
      const [people, bundles] = await Promise.all([
        api.get<Identity[]>("/api/identities"),
        api.get<{ name: string }[]>("/api/bundles"),
      ]);
      setIds(people);
      // Whatever was sealed most recently. Hardcoding a filename broke
      // whenever someone reached this act without walking through Act 1.
      setBundle(bundles[0]?.name ?? null);
    } catch (e) {
      setLoadErr(e);
    }
  };
  useEffect(() => {
    void load();
  }, []);

  const open = async (userId: string) => {
    if (!bundle) {
      setErr(new Error("no sealed document is available yet"));
      return;
    }
    setWho(userId);
    setBusy(true);
    setErr(null);
    setLast(null);
    setStage(0);

    // Pace the stage list while the real request runs. It never reports a step
    // the backend has not actually returned -- on completion we replace the
    // estimate with the real step list.
    const tick = setInterval(() => setStage((s) => Math.min(s + 1, 4)), 260);

    try {
      const r = await api.post<DecryptResult>("/api/decrypt", {
        bundle,
        identity: userId,
      });
      clearInterval(tick);
      setStage(r.steps.length);
      setLast(r);
      const copy: OpenedCopy = {
        userId,
        ledgerIndex: r.ledger_index,
        sessionId: r.session_id,
        bits: r.bits,
        outputPath: r.output.split(/[\\/]/).pop() ?? `${userId}-copy.pdf`,
        steps: r.steps,
        record: r.record,
      };
      addOpened(copy);
    } catch (e) {
      clearInterval(tick);
      setErr(e);
    } finally {
      setBusy(false);
    }
  };

  const hueOf = (u: string) =>
    HUES[(ids?.findIndex((i) => i.user_id === u) ?? 0) % HUES.length]!;

  return (
    <div className="space-y-8">
      <header>
        <p className="font-mono text-tiny text-ink-faint">Act 2</p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">
          A recipient opens the file
        </h1>
        <Plain>
          Opening is not a passive read. As the document is decrypted, a mark
          unique to this person and this session is woven into it, they sign a
          record of having opened it, and that record is locked into the ledger —
          all before the file reaches them.
        </Plain>
      </header>

      {loadErr !== null && (
        <ErrorPanel error={loadErr} onRetry={load} context="loading recipients" />
      )}
      {!ids && loadErr === null && <Spinner label="Loading recipients…" />}

      {ids && (
        <section>
          <h2 className="text-base font-medium">Open as…</h2>
          <p className="mt-1 max-w-prose text-sm text-ink-dim">
            Pick someone to play. You can open it as several people — each gets
            a different mark.
          </p>
          <div className="mt-4 grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
            {ids.map((id, i) => {
              const done = opened.find((o) => o.userId === id.user_id);
              return (
                <div key={id.user_id} className="relative">
                  <IdentityCard
                    userId={id.user_id}
                    fingerprint={id.fingerprint}
                    hue={HUES[i % HUES.length]!}
                    selected={who === id.user_id}
                    disabled={busy}
                    onToggle={() => void open(id.user_id)}
                  />
                  {done && (
                    <span className="pointer-events-none absolute right-3 top-3 rounded-full bg-verified/15 px-1.5 py-0.5 font-mono text-[10px] text-verified">
                      opened · #{done.ledgerIndex}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {err !== null && (
        <ErrorPanel
          error={err}
          onRetry={who ? () => void open(who) : undefined}
          context="opening the document"
        />
      )}

      {(busy || last) && who && (
        <section className="rounded-[var(--card-radius)] border border-line bg-surface p-5">
          <div className="flex items-center gap-2.5">
            <span
              className="h-2.5 w-2.5 rounded-full"
              style={{ background: hueOf(who) }}
              aria-hidden
            />
            <h2 className="text-base font-medium">
              <span className="capitalize">{who}</span> is opening the document
            </h2>
          </div>

          <div className="mt-4">
            <StagedProgress
              stages={(last ? last.steps : PLACEHOLDER_STAGES).map(tidy)}
              active={busy ? stage : (last?.steps.length ?? 0)}
            />
          </div>

          {last && (
            <>
              <div className="mt-5 grid gap-4 border-t border-line-soft pt-4 sm:grid-cols-3">
                <div>
                  <div className="text-micro text-ink-faint">watermark</div>
                  <div className="mt-1 font-mono text-tiny text-verified">
                    {last.bits.toLocaleString()} bits embedded
                  </div>
                </div>
                <div>
                  <div className="text-micro text-ink-faint">ledger position</div>
                  <div className="mt-1 font-mono text-tiny">
                    record #{last.ledger_index}
                  </div>
                </div>
                <CryptoValue
                  label="session"
                  value={last.session_id}
                  head={12}
                  note="this opening only"
                />
              </div>

              <Plain>
                <span className="mt-4 block">
                  <strong className="font-medium text-ink capitalize">
                    {who}
                  </strong>{" "}
                  now holds a copy that looks exactly like everyone else's — and
                  is the only copy carrying this mark. They signed for it with
                  their own key, so they cannot later say they never opened it.
                </span>
              </Plain>

              <Deep title="The record they signed">
                <SignedRecordDetail index={last.ledger_index} />
                <ApiTrace method="POST" path="/api/decrypt" response={last} />
              </Deep>
            </>
          )}
        </section>
      )}

      {opened.length >= 2 && <ProofPanel opened={opened} hueOf={hueOf} />}

      {opened.length >= 1 && (
        <div className="flex flex-wrap items-center gap-4 border-t border-line pt-6">
          <button
            onClick={() => nav("/ledger")}
            className="rounded-md bg-[var(--btn-primary-bg)] px-4 py-2.5 text-base font-medium text-[var(--btn-primary-ink)] transition-colors duration-fast hover:bg-[var(--btn-primary-bg-hover)]"
          >
            Next — see the ledger
          </button>
          {opened.length < 2 && (
            <p className="text-sm text-ink-faint">
              Open it as a second person to compare two copies side by side.
            </p>
          )}
        </div>
      )}

      {deep && opened.length === 0 && (
        <p className="text-sm text-ink-faint">
          Nothing has been opened yet, so the ledger has no new records from
          this run.
        </p>
      )}
    </div>
  );
}

/** The backend's step strings are written for a terminal. Keep every word --
 *  they are the real pipeline output -- but fix the punctuation so they read
 *  as prose rather than log lines. */
function tidy(step: string): string {
  return step.replace(/\s--\s/g, " — ").replace(/\s+/g, " ").trim();
}

const PLACEHOLDER_STAGES = [
  "Checking this recipient is authorised",
  "Unwrapping the content key",
  "Decrypting the document",
  "Weaving in a session-unique mark",
  "Signing the record",
  "Committing to the ledger",
];

/* ------------------------------------------------------- signed record */

function SignedRecordDetail({ index }: { index: number }) {
  const [data, setData] = useState<any | null>(null);
  const [err, setErr] = useState<unknown>(null);

  useEffect(() => {
    let alive = true;
    api
      .get<any>(`/api/event/${index}`)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setErr(e));
    return () => {
      alive = false;
    };
  }, [index]);

  if (err !== null) return <ErrorPanel error={err} context="loading the record" />;
  if (!data) return <Spinner label="Loading the signed record…" />;

  return (
    <div className="space-y-3">
      <p className="text-sm text-ink-dim">
        This is the exact record {data.record.recipient_user_id} signed. Act 5
        verifies this same signature against this same public key — you can
        compare the values.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        <CryptoValue
          label="signature"
          value={data.signature_hex}
          head={16}
          note={`${data.algorithm} · ${data.signature_len} bytes`}
          tone="accent"
        />
        <CryptoValue
          label="signing public key"
          value={data.sig_public}
          head={16}
          note={`${data.sig_public_len} bytes`}
        />
        <CryptoValue
          label="watermark commitment"
          value={data.record.watermark_commitment}
          head={16}
          note="SHA-256 over the codeword"
        />
        <CryptoValue
          label="leaf hash in the ledger"
          value={data.leaf_hash}
          head={16}
          note={`Merkle path of ${data.inclusion_proof.path.length} hashes`}
        />
      </div>
      <details>
        <summary className="cursor-pointer text-micro text-ink-faint hover:text-ink">
          the exact bytes that were signed
        </summary>
        <pre className="mt-1.5 max-h-40 overflow-auto rounded-md border border-line bg-ground p-2.5 font-mono text-[10.5px] leading-relaxed text-ink-dim">
          {data.signed_bytes}
        </pre>
      </details>
    </div>
  );
}

/* ------------------------------------------------------------- proof */

interface CompareResult {
  a: { name: string; bytes: number; sha256: string };
  b: { name: string; bytes: number; sha256: string };
  byte_identical: boolean;
  differing_byte_positions: number;
  same_words: boolean;
  word_count: number;
  max_baseline_shift_pt: number | null;
  pixel_mean_abs_diff: number | null;
  ink_delta: number | null;
  page: number;
}

/** The claim, proven rather than asserted. */
function ProofPanel({
  opened,
  hueOf,
}: {
  opened: OpenedCopy[];
  hueOf: (u: string) => string;
}) {
  const a = opened[opened.length - 2]!;
  const b = opened[opened.length - 1]!;
  const [cmp, setCmp] = useState<CompareResult | null>(null);
  const [err, setErr] = useState<unknown>(null);

  const run = async () => {
    setErr(null);
    setCmp(null);
    try {
      setCmp(
        await api.post<CompareResult>("/api/compare", {
          a: a.outputPath,
          b: b.outputPath,
        }),
      );
    } catch (e) {
      setErr(e);
    }
  };

  useEffect(() => {
    void run();
  }, [a.outputPath, b.outputPath]);

  return (
    <section className="rounded-[var(--card-radius)] border border-line bg-surface p-5">
      <h2 className="text-xl font-semibold tracking-tight">
        Identical to read. Different underneath.
      </h2>
      <Plain>
        <span className="mt-1 block">
          Here are <span className="capitalize">{a.userId}</span>'s and{" "}
          <span className="capitalize">{b.userId}</span>'s copies, rendered from
          the actual files. Every measurement below is taken from those two
          files — nothing is asserted.
        </span>
      </Plain>

      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        {[a, b].map((c) => (
          <figure key={c.userId} className="m-0">
            <figcaption className="mb-2 flex items-center gap-2">
              <span
                className="h-2.5 w-2.5 rounded-full"
                style={{ background: hueOf(c.userId) }}
                aria-hidden
              />
              <span className="text-sm font-medium capitalize">{c.userId}</span>
              <span className="font-mono text-micro text-ink-faint">
                record #{c.ledgerIndex}
              </span>
            </figcaption>
            <img
              src={`/api/page-image?path=${encodeURIComponent(c.outputPath)}&page=0&dpi=110`}
              alt={`First page of ${c.userId}'s copy`}
              className="w-full rounded-md border border-line bg-white"
              loading="lazy"
            />
          </figure>
        ))}
      </div>

      {err !== null && (
        <div className="mt-4">
          <ErrorPanel error={err} onRetry={run} context="comparing the copies" />
        </div>
      )}
      {!cmp && err === null && (
        <div className="mt-4">
          <Spinner label="Measuring both files…" />
        </div>
      )}

      {cmp && (
        <div className="mt-5 border-t border-line-soft pt-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <Measure
              ok={!cmp.byte_identical}
              label="The files are not the same bytes"
              value={`${cmp.differing_byte_positions.toLocaleString()} byte positions differ`}
              kind="distinct"
            />
            <Measure
              ok={cmp.same_words}
              label="Every word is unchanged"
              value={`${cmp.word_count} words, identical in both`}
              kind="same"
            />
            <Measure
              ok={cmp.max_baseline_shift_pt === 0}
              label="No line moved"
              value={`${cmp.max_baseline_shift_pt ?? "—"} pt maximum shift`}
              kind="same"
            />
            <Measure
              ok={(cmp.ink_delta ?? 1) < 0.001}
              label="Same amount of ink on the page"
              value={`${(cmp.ink_delta ?? 0).toExponential(1)} difference`}
              kind="same"
            />
          </div>

          <p className="mt-4 max-w-prose text-sm text-ink-dim">
            A reader cannot tell these apart. The forensic system can tell them
            apart with certainty — because the difference is in the spacing
            between words, shifted by a third of a point.
          </p>

          <Deep title="The two files">
            <div className="grid gap-3 sm:grid-cols-2">
              <CryptoValue
                label={`${a.userId} · SHA-256`}
                value={cmp.a.sha256}
                head={16}
                note={`${cmp.a.bytes.toLocaleString()} bytes`}
              />
              <CryptoValue
                label={`${b.userId} · SHA-256`}
                value={cmp.b.sha256}
                head={16}
                note={`${cmp.b.bytes.toLocaleString()} bytes`}
              />
            </div>
            <p className="text-sm text-ink-dim">
              Rendered pixels differ by a mean of{" "}
              {(cmp.pixel_mean_abs_diff ?? 0).toFixed(2)} of 255 — sub-pixel
              horizontal shifts only. Total ink is conserved because each bit
              widens one gap and narrows the next by the same amount, so the
              line width never changes.
            </p>
            <ApiTrace method="POST" path="/api/compare" response={cmp} />
          </Deep>
        </div>
      )}
    </section>
  );
}

function Measure({
  ok,
  label,
  value,
  kind,
}: {
  ok: boolean;
  label: string;
  value: string;
  kind: "same" | "distinct";
}) {
  return (
    <div className="flex items-start gap-2.5">
      <span
        className={`mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full text-[10px] font-bold ${
          ok ? "bg-verified/15 text-verified" : "bg-caution/15 text-caution"
        }`}
        aria-hidden
      >
        {ok ? "✓" : "!"}
      </span>
      <div className="min-w-0">
        <div className="text-sm">{label}</div>
        <div
          className={`font-mono text-micro ${
            kind === "distinct" ? "text-accent" : "text-ink-faint"
          }`}
        >
          {value}
        </div>
      </div>
    </div>
  );
}
