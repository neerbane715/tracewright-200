/** The layered-depth explanation system.
 *
 * Every significant moment carries two coexisting layers:
 *   Plain  — what just happened, in leak-attribution terms, always visible.
 *   Deep   — algorithms, byte lengths, real values, the actual API exchange.
 *
 * Depth is a LENS, never a GATE: turning it off never blocks progress, and
 * turning it on never hides the plain layer. It persists across the whole
 * journey so a technical judge sets it once.
 */
import {
  createContext, useCallback, useContext, useEffect, useState, type ReactNode,
} from "react";

const KEY = "tracewright.depth";

const DepthCtx = createContext<{ deep: boolean; setDeep: (v: boolean) => void }>({
  deep: false,
  setDeep: () => {},
});

export function DepthProvider({ children }: { children: ReactNode }) {
  const [deep, setDeepState] = useState(() => {
    try {
      return localStorage.getItem(KEY) === "1";
    } catch {
      return false; // private mode / blocked storage
    }
  });

  const setDeep = useCallback((v: boolean) => {
    setDeepState(v);
    try {
      localStorage.setItem(KEY, v ? "1" : "0");
    } catch {
      /* preference simply won't persist */
    }
  }, []);

  useEffect(() => {
    document.documentElement.dataset.depth = deep ? "deep" : "plain";
  }, [deep]);

  return <DepthCtx.Provider value={{ deep, setDeep }}>{children}</DepthCtx.Provider>;
}

export const useDepth = () => useContext(DepthCtx);

export function DepthToggle() {
  const { deep, setDeep } = useDepth();
  return (
    <button
      type="button"
      role="switch"
      aria-checked={deep}
      onClick={() => setDeep(!deep)}
      className="flex items-center gap-2 rounded-md border border-line px-2.5 py-1.5 text-tiny text-ink-dim transition-colors duration-fast hover:border-ink-faint hover:text-ink"
    >
      <span
        className={`relative h-3.5 w-6 rounded-full transition-colors duration-base ${
          deep ? "bg-accent" : "bg-line"
        }`}
        aria-hidden
      >
        <span
          className={`absolute top-0.5 h-2.5 w-2.5 rounded-full bg-white transition-all duration-base ${
            deep ? "left-3" : "left-0.5"
          }`}
        />
      </span>
      Technical detail
    </button>
  );
}

/** Plain-language layer. Always rendered. */
export function Plain({ children }: { children: ReactNode }) {
  return (
    <p className="max-w-prose text-base leading-relaxed text-ink-dim">{children}</p>
  );
}

/** Technical layer. Rendered only when depth is on — and it is additive, it
 *  never replaces the plain layer above it. */
export function Deep({
  title = "What actually happened",
  children,
}: {
  title?: string;
  children: ReactNode;
}) {
  const { deep } = useDepth();
  if (!deep) return null;
  return (
    <div className="mt-3 rounded-[var(--card-radius)] border border-line bg-raised/60 p-3.5">
      <div className="mb-2.5 flex items-center gap-2">
        <span className="h-1 w-1 rounded-full bg-accent" aria-hidden />
        <span className="text-micro font-medium uppercase tracking-wider text-accent">
          {title}
        </span>
      </div>
      <div className="space-y-2.5">{children}</div>
    </div>
  );
}

/** Shows the real HTTP exchange for an action, so a judge can see the UI is
 *  reporting the backend rather than inventing. */
export function ApiTrace({
  method,
  path,
  response,
}: {
  method: string;
  path: string;
  response: unknown;
}) {
  const { deep } = useDepth();
  const [open, setOpen] = useState(false);
  if (!deep) return null;

  return (
    <div className="mt-2">
      <button
        onClick={() => setOpen((o) => !o)}
        className="font-mono text-micro text-ink-faint hover:text-ink"
      >
        {open ? "▾" : "▸"} {method} {path}
      </button>
      {open && (
        <pre className="mt-1.5 max-h-56 overflow-auto rounded-md border border-line bg-ground p-2.5 font-mono text-[10.5px] leading-relaxed text-ink-dim">
          {JSON.stringify(response, null, 2)}
        </pre>
      )}
    </div>
  );
}
