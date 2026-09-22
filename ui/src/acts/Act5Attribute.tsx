import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api, type Verdict } from "../lib/api";
import { PRODUCT_NAME } from "../brand";
import { HUES } from "../acts";
import { CheckRow, CryptoValue } from "../components/Crypto";
import { ApiTrace, Deep, Plain } from "../components/Layers";
import { ErrorPanel, StagedProgress, useStageTicker } from "../components/States";
import { useRun } from "../lib/run";

/** Act 5 — the verdict.
 *
 * The extraction here is real: the bits are recovered from the file's own word
 * spacing, scored against every codeword in the ledger, and the resulting
 * record's signature and Merkle proof are verified. It takes ~14 seconds on a
 * 10-page document, which is why the wait shows what is happening rather than
 * a spinner.
 *
 * Four outcomes are first-class. A forensic tool that always names someone is
 * worse than useless, so NO_WATERMARK and LEDGER_COMPROMISED get the same
 * design care as IDENTIFIED.
 */

interface FullVerdict extends Verdict {
  source_filename?: string;
  inclusion_proof?: { index: number; tree_size: number; root: string; path: string[] } | null;
}

const STAGES = [
  "Reading the document's word spacing",
  "Recovering the embedded bits",
  "Scoring against every recipient's codeword",
  "Matching the result to a ledger record",
  "Verifying the signature and inclusion proof",
];

export default function Act5Attribute() {
  const nav = useNavigate();
  const loc = useLocation() as { state?: { path?: string } };
  const staged = loc.state?.path;
  const { reset: resetRun, chosenLeaker, setChosenLeaker } = useRun();

  const [verdict, setVerdict] = useState<FullVerdict | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const [resetting, setResetting] = useState(false);
  const [resetErr, setResetErr] = useState<unknown>(null);
  const [subject, setSubject] = useState<string | null>(staged ?? null);
  const started = useRef(false);
  const stage = useStageTicker(STAGES, busy, 2600);

  const handleBackToBeginning = async () => {
    setResetting(true);
    setResetErr(null);
    try {
      await api.post("/api/reset", undefined, 180_000);
      resetRun();
      nav("/");
    } catch (e) {
      setResetErr(e);
      setResetting(false);
    }
  };


  const runPath = async (path: string) => {
    setBusy(true);
    setErr(null);
    setVerdict(null);
    setSubject(path);
    try {
      setVerdict(
        await api.post<FullVerdict>("/api/attribute-path", { path }, 180_000),
      );
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  };

  const runUpload = async (file: File) => {
    setBusy(true);
    setErr(null);
    setVerdict(null);
    setSubject(file.name);
    // The staged-leak comparison panel below only makes sense against the
    // artefact that was actually staged in Act 4. A fresh upload here is an
    // unrelated file -- without this it kept "You staged: <name>" attached
    // to whatever verdict came back next, mislabelling the new document.
    setChosenLeaker(null);
    try {
      setVerdict(await api.upload<FullVerdict>("/api/attribute", file, 180_000));
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  };

  // Auto-run once when arriving from Act 4 with a staged artefact.
  useEffect(() => {
    if (staged && !started.current) {
      started.current = true;
      void runPath(staged);
    }
  }, [staged]);

  return (
    <div className="space-y-8">
      <header>
        <p className="font-mono text-tiny text-ink-faint">Act 5</p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">
          Who leaked it
        </h1>
        <Plain>
          {PRODUCT_NAME} reads the mark out of the recovered file, scores it
          against every recipient's codeword, and then verifies the record it
          points to. Nothing below is looked up in advance — the answer is
          recovered from the document itself.
        </Plain>
      </header>

      <Subject
        name={subject}
        busy={busy}
        onUpload={runUpload}
        onRerun={staged ? () => void runPath(staged) : undefined}
      />

      {busy && (
        <section className="rounded-[var(--card-radius)] border border-line bg-surface p-5">
          <h2 className="text-base font-medium">Examining the document</h2>
          <p className="mt-1 max-w-prose text-sm text-ink-dim">
            This takes a few seconds. The mark is spread across every page, so
            the whole document has to be measured.
          </p>
          <div className="mt-4">
            <StagedProgress stages={STAGES} active={stage} />
          </div>
        </section>
      )}

      {err !== null && (
        <ErrorPanel
          error={err}
          onRetry={subject && staged ? () => void runPath(staged) : undefined}
          context="examining the document"
        />
      )}

      {resetErr !== null && (
        <ErrorPanel
          error={resetErr}
          onRetry={handleBackToBeginning}
          context="resetting the demo & ledger"
        />
      )}

      {verdict && !busy && <VerdictPanel v={verdict} />}

      {verdict && chosenLeaker && (
        <section className="rounded-[var(--card-radius)] border border-line bg-surface p-4">
          <h3 className="text-sm font-medium">Against the ground truth</h3>
          <dl className="mt-2 grid grid-cols-2 gap-2 text-tiny">
            <dt className="text-ink-faint">You staged</dt>
            <dd className="font-mono">{chosenLeaker}</dd>
            <dt className="text-ink-faint">The system found</dt>
            <dd className="font-mono">
              {verdict.recipient.user_id ?? "— no attribution —"}
            </dd>
          </dl>
          {verdict.recipient.user_id === chosenLeaker ? (
            <p className="mt-2 text-tiny text-verified">
              Match. The name was recovered from the file's own geometry — it was
              never sent to this screen.
            </p>
          ) : verdict.outcome === "NO_WATERMARK" ? (
            <p className="mt-2 text-tiny text-ink-dim">
              No mark was found in this file, so there is nobody to name. That is
              the correct answer for a document this system never distributed.
            </p>
          ) : verdict.outcome === "LEDGER_COMPROMISED" ? (
            <p className="mt-2 text-tiny text-ink-dim">
              The ledger's integrity check failed, so attribution is withheld.
              Rebuild a clean ledger in Act 3 and try again.
            </p>
          ) : (
            <p className="mt-2 text-tiny text-ink-dim">
              These differ. With a margin near the floor the system reports what it
              can support rather than the answer you expected — see the ranking and
              notes above.
            </p>
          )}
        </section>
      )}

      {verdict && !busy && (
        <section className="flex flex-wrap items-center gap-4 border-t border-line pt-6">
          <button
            onClick={handleBackToBeginning}
            disabled={resetting}
            className="inline-flex items-center gap-2 rounded-md border border-[var(--btn-ghost-border)] px-3.5 py-2 text-sm transition-colors duration-fast hover:border-ink-faint disabled:opacity-50"
          >
            {resetting && (
              <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-accent border-t-transparent" />
            )}
            {resetting ? "Resetting demo & ledger…" : "Back to the beginning"}
          </button>
          <p className="text-sm text-ink-faint">
            {resetting
              ? "Running demo_reset.py to restore a clean, verified ledger…"
              : "Try it with your own PDF above — one that was never distributed should name nobody."}
          </p>
        </section>
      )}
    </div>
  );
}

/* ------------------------------------------------------------ subject */

function Subject({
  name,
  busy,
  onUpload,
  onRerun,
}: {
  name: string | null;
  busy: boolean;
  onUpload: (f: File) => void;
  onRerun?: () => void;
}) {
  return (
    <section className="rounded-[var(--card-radius)] border border-line bg-surface p-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
        <div className="min-w-0">
          <div className="text-micro text-ink-faint">document under examination</div>
          <div className="mt-0.5 truncate font-mono text-sm">
            {name ?? "— none selected —"}
          </div>
        </div>
        <div className="ml-auto flex flex-wrap gap-2.5">
          {onRerun && (
            <button
              onClick={onRerun}
              disabled={busy}
              className="rounded-md border border-[var(--btn-ghost-border)] px-3 py-1.5 text-tiny transition-colors duration-fast hover:border-ink-faint disabled:opacity-45"
            >
              Examine again
            </button>
          )}
          <label
            className={`cursor-pointer rounded-md border border-dashed border-line px-3 py-1.5 text-tiny transition-colors duration-fast hover:border-accent ${
              busy ? "pointer-events-none opacity-45" : ""
            }`}
          >
            <input
              type="file"
              accept="application/pdf"
              className="sr-only"
              disabled={busy}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) onUpload(f);
              }}
            />
            Examine a different PDF
          </label>
        </div>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------ verdict */

function VerdictPanel({ v }: { v: FullVerdict }) {
  const named = v.recipient.user_id;
  const tone =
    v.outcome === "IDENTIFIED"
      ? "verified"
      : v.outcome === "LEDGER_COMPROMISED"
        ? "broken"
        : "caution";

  const headline =
    v.outcome === "IDENTIFIED"
      ? named
      : v.outcome === "NO_WATERMARK"
        ? "No mark in this document"
        : v.outcome === "INCONCLUSIVE"
          ? "No single recipient stands out"
          : "Evidence base unreliable";

  const border =
    tone === "verified"
      ? "border-verified/40 bg-verified/5"
      : tone === "broken"
        ? "border-broken/45 bg-broken/5"
        : "border-caution/40 bg-caution/5";

  const ink =
    tone === "verified"
      ? "text-verified"
      : tone === "broken"
        ? "text-broken"
        : "text-caution";

  return (
    <>
      <section className={`rounded-[var(--card-radius)] border p-6 ${border}`}>
        <div className={`font-mono text-micro tracking-wide ${ink}`}>
          {v.outcome.replace(/_/g, " ")}
        </div>
        <h2
          className={`mt-2 text-4xl font-semibold tracking-tight ${ink} ${
            v.outcome === "IDENTIFIED" ? "capitalize" : ""
          }`}
        >
          {headline}
        </h2>

        {v.outcome === "IDENTIFIED" && (
          <>
            <p className="mt-2 max-w-prose text-base text-ink-dim">
              This copy was opened by{" "}
              <strong className="font-medium capitalize text-ink">{named}</strong>
              {v.event.timestamp && (
                <>
                  {" "}
                  on{" "}
                  <strong className="font-medium text-ink">
                    {v.event.timestamp.replace("T", " ").slice(0, 19)}
                  </strong>
                </>
              )}
              . They signed for it with their own private key, so they cannot
              deny having opened it.
            </p>
            <div className="mt-5 grid gap-4 sm:grid-cols-3">
              <Stat
                label="mark recovered"
                value={`${v.detection.bits_recovered} / ${v.detection.bits_expected} bits`}
              />
              <Stat
                label="ledger record"
                value={`#${v.event.ledger_index}`}
              />
              <Stat
                label="separation from the field"
                value={`${(v.detection.margin ?? 0).toFixed(2)}σ`}
              />
            </div>
          </>
        )}

        {v.outcome === "NO_WATERMARK" && (
          <p className="mt-2 max-w-prose text-base text-ink-dim">
            Nothing recoverable was found in this document's spacing. That is
            the correct answer for a file that was never distributed through{" "}
            {PRODUCT_NAME} — or one that has been flattened into an image.{" "}
            <strong className="font-medium text-ink">
              The system names nobody rather than guessing.
            </strong>
          </p>
        )}

        {v.outcome === "INCONCLUSIVE" && (
          <p className="mt-2 max-w-prose text-base text-ink-dim">
            A mark was recovered, but no single recipient is clearly separated
            from the others. That is the expected signature of several
            recipients combining their copies — see the ranking below for the
            likely group.
          </p>
        )}

        {v.outcome === "LEDGER_COMPROMISED" && (
          <p className="mt-2 max-w-prose text-base text-ink-dim">
            The ledger has been altered, so attribution is withheld. Naming
            someone from evidence known to be unreliable would be worse than
            returning no answer at all. Repair the ledger in Act 3 and examine
            this document again.
          </p>
        )}
      </section>

      {/* A ranking is only meaningful when a mark was recovered. Showing
          noise scores for an unmarked file presents nothing as evidence. */}
      {v.ranking.length > 0 && v.outcome !== "NO_WATERMARK" && <Ranking v={v} />}

      {/* The chain verifies the record the mark pointed to. With no mark
          there is no such record, so showing four green checks would be
          vouching for something unrelated to this file. */}
      {v.outcome !== "NO_WATERMARK" && <EvidenceChain v={v} />}

      {v.notes.length > 0 && (
        <section>
          {v.notes.map((n, i) => (
            <p key={i} className="max-w-measure text-sm text-ink-faint">
              {n}
            </p>
          ))}
        </section>
      )}

      <Deep title="The raw result">
        <ApiTrace
          method="POST"
          path="/api/attribute-path"
          response={v}
        />
      </Deep>
    </>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-micro text-ink-faint">{label}</div>
      <div className="mt-0.5 font-mono text-base">{value}</div>
    </div>
  );
}

/* ------------------------------------------------------------ ranking */

function Ranking({ v }: { v: FullVerdict }) {
  const scores = v.ranking.map(([, s]) => s);
  const max = Math.max(...scores.map(Math.abs), 1);
  const named = v.recipient.user_id;
  const people = v.ranking.map(([u]) => u);

  return (
    <section className="rounded-[var(--card-radius)] border border-line bg-surface p-5">
      <h2 className="text-base font-medium">How clear-cut was it</h2>
      <p className="mt-1 max-w-prose text-sm text-ink-dim">
        Every recipient's codeword is scored against the bits recovered from
        this file. Attribution is only reported when one score stands well clear
        of the rest.
      </p>

      <ol className="mt-4 space-y-2.5">
        {v.ranking.map(([user, score], i) => {
          const hit = user === named;
          const hue = HUES[people.indexOf(user) % HUES.length]!;
          const pct = Math.max(2, (Math.abs(score) / max) * 100);
          return (
            <li key={user} className="flex items-center gap-3">
              <span className="w-4 shrink-0 font-mono text-micro text-ink-faint">
                {i + 1}
              </span>
              <span
                className={`w-20 shrink-0 truncate text-sm capitalize ${
                  hit ? "font-medium text-ink" : "text-ink-dim"
                }`}
              >
                {user}
              </span>
              <span className="relative h-5 flex-1 overflow-hidden rounded-sm bg-raised">
                <span
                  className="absolute inset-y-0 left-0 rounded-sm"
                  style={{
                    width: `${pct}%`,
                    background: hit ? hue : "var(--line)",
                    // hue is this recipient's colour from Act 0 onward
                    opacity: hit ? 0.9 : 0.6,
                  }}
                />
              </span>
              <span
                className={`w-14 shrink-0 text-right font-mono text-tiny ${
                  hit ? "text-ink" : "text-ink-faint"
                }`}
              >
                {Math.round(score)}
              </span>
            </li>
          );
        })}
      </ol>

      {v.detection.threshold !== null && (
        <p className="mt-3 font-mono text-micro text-ink-faint">
          accusation threshold {Math.round(v.detection.threshold)} · top score{" "}
          {Math.round(v.detection.score ?? 0)}
        </p>
      )}

      <Deep title="Why a ranking and not a yes/no">
        <p className="text-sm text-ink-dim">
          The codewords come from a Tardos fingerprinting scheme, designed so
          that recipients who combine their copies to hide the mark still leave
          at least one of themselves at the top of this list. A flat spread is
          itself informative — it is what collusion looks like.
        </p>
      </Deep>
    </section>
  );
}

/* ------------------------------------------------------------ evidence */

function EvidenceChain({ v }: { v: FullVerdict }) {
  const e = v.evidence;
  return (
    <section className="rounded-[var(--card-radius)] border border-line bg-surface p-5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <h2 className="text-base font-medium">The chain of evidence</h2>
        <span
          className={`rounded-full px-2 py-0.5 font-mono text-micro ${
            e.cryptographically_verified
              ? "bg-verified/15 text-verified"
              : "bg-broken/15 text-broken"
          }`}
        >
          {e.cryptographically_verified
            ? "all four checks passed"
            : "incomplete"}
        </span>
      </div>
      <p className="mt-1 max-w-prose text-sm text-ink-dim">
        Four independent checks. All must hold for the verdict to stand — a
        confident answer from broken evidence would be worse than no answer.
      </p>

      <div className="mt-4">
        <CheckRow
          label="The recipient signed this decryption with their own key"
          passed={e.signature_valid}
          detail="ML-DSA-65 signature verifies under their public key"
        />
        <CheckRow
          label="The record is provably in the ledger"
          passed={e.inclusion_proof_valid}
          detail={
            v.inclusion_proof
              ? `Merkle path of ${v.inclusion_proof.path.length} hashes to root ${v.inclusion_proof.root.slice(0, 16)}…`
              : "inclusion proof checked against the signed head"
          }
        />
        <CheckRow
          label="The mark in this file is the one they signed for"
          passed={e.watermark_commitment_valid}
          detail="recovered codeword matches the commitment in the record"
        />
        <CheckRow
          label="The ledger's history has not been rewritten"
          passed={e.ledger_intact}
          detail="every record re-hashed and every signature re-verified"
        />
      </div>

      {(v.event.session_id || v.recipient.fingerprint) && (
        <Deep title="The record this points to">
          <div className="grid gap-3 sm:grid-cols-2">
            {v.recipient.fingerprint && (
              <CryptoValue
                label="recipient fingerprint"
                value={v.recipient.fingerprint}
                head={16}
              />
            )}
            {v.event.session_id && (
              <CryptoValue
                label="session"
                value={v.event.session_id}
                head={16}
                note="this opening only"
              />
            )}
            {v.event.doc_id && (
              <CryptoValue label="document id" value={v.event.doc_id} head={16} />
            )}
            {v.inclusion_proof && (
              <CryptoValue
                label="ledger root"
                value={v.inclusion_proof.root}
                head={16}
                note={`covers ${v.inclusion_proof.tree_size} records`}
                tone="verified"
              />
            )}
          </div>
          <p className="text-sm text-ink-dim">
            This is the same signature shown in Act 2 when {v.recipient.user_id}{" "}
            opened the document. You can compare the two values.
          </p>
        </Deep>
      )}
    </section>
  );
}
