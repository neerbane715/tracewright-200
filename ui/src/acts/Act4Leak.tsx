import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useRun } from "../lib/run";
import { CryptoValue } from "../components/Crypto";
import { ApiTrace, Deep, Plain } from "../components/Layers";
import { ErrorPanel, Spinner } from "../components/States";

/** Act 4 — the document surfaces.
 *
 * This act deliberately knows nothing. The previous build ran the real
 * investigation here, cached the verdict, and let the next screen replay it
 * while calling it an extraction. Staging a leak must not compute the answer:
 * Act 5 has to find it in the file.
 */

interface Surfaced {
  path: string;
  filename: string;
  bytes: number;
  sha256: string;
  pages: number;
  title: string;
}

export default function Act4Leak() {
  const nav = useNavigate();
  const { opened, setLeaked } = useRun();
  const [item, setItem] = useState<Surfaced | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);

  const stage = async () => {
    setBusy(true);
    setErr(null);
    try {
      // Prefer a copy from this run, so the story stays continuous. Falls back
      // to whatever copies exist if the user skipped straight here.
      const source =
        opened.length > 0
          ? opened[Math.floor(Math.random() * opened.length)]!.outputPath
          : undefined;
      const r = await api.post<Surfaced>("/api/stage-leak", { source });
      setItem(r);
      setLeaked(null); // Act 5 must not inherit an answer from here
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-8">
      <header>
        <p className="font-mono text-tiny text-ink-faint">Act 4</p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">
          Three days later, the document surfaces
        </h1>
        <Plain>
          A copy of the evaluation report has appeared outside the distribution
          list. Nobody knows which recipient it came from — everyone who was
          sent it could have leaked it, and the file itself gives nothing away
          to the naked eye.
        </Plain>
      </header>

      {!item && (
        <section className="rounded-[var(--card-radius)] border border-line bg-surface p-6">
          <Scene />
          <div className="mt-6 flex flex-wrap items-center gap-4">
            <button
              onClick={stage}
              disabled={busy}
              className="rounded-md bg-[var(--btn-primary-bg)] px-4 py-2.5 text-base font-medium text-[var(--btn-primary-ink)] transition-colors duration-fast hover:bg-[var(--btn-primary-bg-hover)] disabled:opacity-45"
            >
              {busy ? "Recovering the file…" : "Recover the leaked file"}
            </button>
            <p className="text-sm text-ink-faint">
              {opened.length > 0
                ? `One of the ${opened.length} copies opened in this run.`
                : "One of the copies on record."}
            </p>
          </div>
          {err !== null && (
            <div className="mt-4">
              <ErrorPanel
                error={err}
                onRetry={stage}
                context="recovering the leaked file"
              />
            </div>
          )}
        </section>
      )}

      {busy && !item && <Spinner label="Recovering…" />}

      {item && (
        <>
          <section className="rounded-[var(--card-radius)] border border-caution/40 bg-caution/5 p-5">
            <div className="flex items-center gap-2.5">
              <span
                className="grid h-5 w-5 place-items-center rounded-full bg-caution/20 text-tiny font-bold text-caution"
                aria-hidden
              >
                !
              </span>
              <h2 className="text-base font-medium text-caution">
                Artefact recovered
              </h2>
            </div>

            <div className="mt-4 flex flex-wrap items-start gap-5">
              <img
                src={`/api/page-image?path=${encodeURIComponent(item.path)}&page=0&dpi=90`}
                alt="First page of the recovered document"
                className="w-[190px] shrink-0 rounded-md border border-line bg-white"
              />
              <div className="min-w-0 flex-1 space-y-3">
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="filename" value={item.filename} />
                  <Field
                    label="size"
                    value={`${item.bytes.toLocaleString()} bytes`}
                  />
                  <Field label="pages" value={String(item.pages)} />
                  <Field
                    label="title in the file"
                    value={item.title || "— none —"}
                  />
                </div>
                <CryptoValue
                  label="SHA-256 of the recovered file"
                  value={item.sha256}
                  head={20}
                  note="what an investigator would record first"
                />
              </div>
            </div>

            <Plain>
              <span className="mt-4 block">
                Nothing here says who leaked it. The filename is generic, the
                metadata is the same in every copy, and the pages read exactly
                as they were written. Conventional forensics stops at this
                point.
              </span>
            </Plain>

            <Deep title="What this step deliberately does not do">
              <p className="text-sm text-ink-dim">
                This screen has not examined the watermark. It copied a file and
                read its size, hash and page count — nothing more. The next act
                performs the extraction against this file, so the answer is
                found rather than remembered.
              </p>
              <ApiTrace method="POST" path="/api/stage-leak" response={item} />
            </Deep>
          </section>

          <section className="flex flex-wrap items-center gap-4 border-t border-line pt-6">
            <button
              onClick={() => {
                setLeaked(null);
                nav("/attribute", { state: { path: item.path } });
              }}
              className="rounded-md bg-[var(--btn-primary-bg)] px-4 py-2.5 text-base font-medium text-[var(--btn-primary-ink)] transition-colors duration-fast hover:bg-[var(--btn-primary-bg-hover)]"
            >
              Investigate this file
            </button>
            <button
              onClick={stage}
              className="rounded-md border border-[var(--btn-ghost-border)] px-3.5 py-2 text-sm transition-colors duration-fast hover:border-ink-faint"
            >
              Recover a different copy
            </button>
          </section>
        </>
      )}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <div className="text-micro text-ink-faint">{label}</div>
      <div className="mt-0.5 truncate font-mono text-tiny" title={value}>
        {value}
      </div>
    </div>
  );
}

/** The scene, before the file is recovered. */
function Scene() {
  return (
    <figure className="m-0">
      <svg
        viewBox="0 0 700 180"
        role="img"
        aria-label="A copy of the document has travelled outside the authorised distribution list."
        className="w-full"
      >
        <defs>
          <marker
            id="l-ar"
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M0,0 L10,5 L0,10 z" fill="var(--broken)" />
          </marker>
        </defs>

        <rect
          x="20"
          y="34"
          width="196"
          height="112"
          rx="8"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.2"
          strokeDasharray="4 3"
          opacity=".5"
        />
        <text
          x="118"
          y="56"
          textAnchor="middle"
          fontSize="11"
          fill="currentColor"
          opacity=".65"
        >
          authorised distribution
        </text>
        {["alice", "bob", "carol", "dave", "erin"].map((n, i) => (
          <g key={n}>
            <circle
              cx={48 + (i % 3) * 58}
              cy={i < 3 ? 86 : 124}
              r="7"
              fill="none"
              stroke={`var(--id-${i + 1})`}
              strokeWidth="1.4"
            />
            <text
              x={48 + (i % 3) * 58}
              y={i < 3 ? 106 : 144}
              textAnchor="middle"
              fontSize="9"
              fill={`var(--id-${i + 1})`}
            >
              {n}
            </text>
          </g>
        ))}

        <path
          d="M216,90 C 300,90 320,64 404,64"
          fill="none"
          stroke="var(--broken)"
          strokeWidth="1.5"
          strokeDasharray="5 4"
          markerEnd="url(#l-ar)"
        />
        <text
          x="310"
          y="52"
          textAnchor="middle"
          fontSize="10.5"
          fill="var(--broken)"
        >
          one copy travels
        </text>

        <rect
          x="410"
          y="42"
          width="266"
          height="96"
          rx="8"
          fill="none"
          stroke="var(--broken)"
          strokeWidth="1.4"
        />
        <text
          x="543"
          y="70"
          textAnchor="middle"
          fontSize="12.5"
          fill="var(--broken)"
          fontWeight="600"
        >
          outside the list
        </text>
        <text
          x="543"
          y="92"
          textAnchor="middle"
          fontSize="10.5"
          fill="currentColor"
          opacity=".6"
        >
          a messaging group · a journalist
        </text>
        <text
          x="543"
          y="110"
          textAnchor="middle"
          fontSize="10.5"
          fill="currentColor"
          opacity=".6"
        >
          a USB drive left behind
        </text>
        <text
          x="543"
          y="130"
          textAnchor="middle"
          fontSize="10"
          fill="var(--broken)"
          opacity=".85"
        >
          five equally plausible suspects
        </text>
      </svg>
    </figure>
  );
}
