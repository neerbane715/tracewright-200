/** Loading, error and empty states.
 *
 * Finding 5a from the audit: the previous build rendered a bare red
 * "Failed to fetch" when the backend was down. During a live jury demo that
 * reads as "the product is broken" — the single worst thing this UI can say.
 * Transport failure is separated from application failure everywhere.
 */
import { useEffect, useState, type ReactNode } from "react";
import { ApiError } from "../lib/api";

export function ErrorPanel({
  error,
  onRetry,
  context,
}: {
  error: unknown;
  onRetry?: () => void;
  context?: string;
}) {
  const api = error instanceof ApiError ? error : null;
  const offline = api?.kind === "offline";

  const heading = offline
    ? "The engine isn't running"
    : api?.kind === "timeout"
      ? "This is taking longer than expected"
      : api?.kind === "refused"
        ? "That request wasn't accepted"
        : "Something went wrong in the engine";

  const message =
    api?.humanMessage ??
    (error instanceof Error ? error.message : "An unexpected error occurred.");

  return (
    <div
      role="alert"
      className={`rounded-[var(--card-radius)] border p-4 ${
        offline ? "border-caution/40 bg-caution/5" : "border-broken/40 bg-broken/5"
      }`}
    >
      <div className="flex items-start gap-3">
        <span
          className={`mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full text-tiny font-bold ${
            offline ? "bg-caution/15 text-caution" : "bg-broken/15 text-broken"
          }`}
          aria-hidden
        >
          !
        </span>
        <div className="min-w-0 flex-1">
          <h3
            className={`text-base font-medium ${
              offline ? "text-caution" : "text-broken"
            }`}
          >
            {heading}
          </h3>
          <p className="mt-1 max-w-prose text-sm text-ink-dim">{message}</p>

          {offline && (
            <div className="mt-3 rounded-md border border-line bg-ground p-2.5">
              <p className="mb-1.5 text-micro text-ink-faint">
                Start it from the project root:
              </p>
              <code className="block font-mono text-tiny text-ink">
                python -m uvicorn pqfw_api.main:app --port 8000
              </code>
            </div>
          )}

          {context && (
            <p className="mt-2 text-micro text-ink-faint">While {context}.</p>
          )}

          {onRetry && (api?.isRetryable ?? true) && (
            <button
              onClick={onRetry}
              className="mt-3 rounded-md border border-line px-3 py-1.5 text-tiny text-ink transition-colors duration-fast hover:border-ink-faint"
            >
              Try again
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/** Progress for work that genuinely takes seconds. Shows WHAT is happening,
 *  not a spinner — extraction really does take ~10s on a long document and a
 *  viewer should see the stages rather than wonder if it hung. */
export function StagedProgress({
  stages,
  active,
  className = "",
}: {
  stages: string[];
  active: number;
  className?: string;
}) {
  return (
    <ol className={`space-y-2 ${className}`}>
      {stages.map((s, i) => {
        const state = i < active ? "done" : i === active ? "now" : "todo";
        return (
          <li key={s} className="flex items-center gap-2.5">
            <span
              className={`grid h-4 w-4 shrink-0 place-items-center rounded-full text-[9px] font-bold ${
                state === "done"
                  ? "bg-verified/15 text-verified"
                  : state === "now"
                    ? "bg-accent/15 text-accent"
                    : "bg-line/40 text-ink-faint"
              }`}
              aria-hidden
            >
              {state === "done" ? "✓" : state === "now" ? "•" : ""}
            </span>
            <span
              className={`text-sm ${
                state === "todo" ? "text-ink-faint" : "text-ink"
              }`}
            >
              {s}
            </span>
            {state === "now" && (
              <span className="ml-1 flex gap-0.5" aria-hidden>
                {[0, 1, 2].map((d) => (
                  <span
                    key={d}
                    className="h-1 w-1 animate-pulse rounded-full bg-accent"
                    style={{ animationDelay: `${d * 160}ms` }}
                  />
                ))}
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
}

/** Cycles a stage list on a timer while real work runs. The stages are the
 *  real pipeline steps; only the pacing is estimated, and it never claims
 *  completion the backend has not reported. */
export function useStageTicker(stages: string[], running: boolean, msEach = 1400) {
  const [i, setI] = useState(0);
  useEffect(() => {
    if (!running) {
      setI(0);
      return;
    }
    const t = setInterval(
      () => setI((v) => Math.min(v + 1, stages.length - 1)),
      msEach,
    );
    return () => clearInterval(t);
  }, [running, stages.length, msEach]);
  return i;
}

export function Empty({
  title,
  body,
  action,
}: {
  title: string;
  body: string;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-[var(--card-radius)] border border-dashed border-line px-6 py-10 text-center">
      <h3 className="text-base font-medium text-ink">{title}</h3>
      <p className="mx-auto mt-1.5 max-w-prose text-sm text-ink-dim">{body}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2.5 text-sm text-ink-dim">
      <span
        className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-line border-t-accent"
        aria-hidden
      />
      {label ?? "Working…"}
    </div>
  );
}
