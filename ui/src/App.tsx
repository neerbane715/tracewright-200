import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { PRODUCT_NAME, PRODUCT_SUBTITLE } from "./brand";
import { ACTS } from "./acts";
import { DepthProvider, DepthToggle } from "./components/Layers";
import { RunProvider } from "./lib/run";
import Act0Brief from "./acts/Act0Brief";
import Act1Distribute from "./acts/Act1Distribute";
import Act2Open from "./acts/Act2Open";
import Act3Ledger from "./acts/Act3Ledger";
import Act4Leak from "./acts/Act4Leak";
import Act5Attribute from "./acts/Act5Attribute";

function ProgressRail() {
  const { pathname } = useLocation();
  const current = ACTS.find((a) => a.path === pathname)?.n ?? 0;

  return (
    <nav aria-label="Progress through the demonstration" className="w-full">
      <ol className="flex items-center gap-0">
        {ACTS.map((act, i) => {
          const state =
            act.n < current ? "done" : act.n === current ? "now" : "todo";
          return (
            <li key={act.path} className="flex shrink-0 items-center">
              <NavLink
                to={act.path}
                className="group flex min-w-0 items-center gap-2 rounded-md px-1.5 py-1"
                aria-current={state === "now" ? "step" : undefined}
              >
                <span
                  className={`grid h-[22px] w-[22px] shrink-0 place-items-center rounded-full border font-mono text-[11px] transition-colors duration-fast
                    ${
                      state === "now"
                        ? "border-accent bg-accent text-white"
                        : state === "done"
                          ? "border-verified/50 bg-verified/10 text-verified"
                          : "border-line text-ink-faint group-hover:border-ink-faint"
                    }`}
                >
                  {state === "done" ? "✓" : act.n}
                </span>
                <span
                  className={`hidden whitespace-nowrap text-tiny lg:inline ${
                    state === "now"
                      ? "font-medium text-ink"
                      : "text-ink-faint group-hover:text-ink-dim"
                  }`}
                >
                  {act.short}
                </span>
              </NavLink>
              {i < ACTS.length - 1 && (
                <span
                  className={`mx-1 h-px w-3 lg:w-4 ${
                    act.n < current ? "bg-verified/40" : "bg-line"
                  }`}
                  aria-hidden
                />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

export default function App() {
  return (
    <DepthProvider>
      <RunProvider>
        <div className="flex min-h-full flex-col">
          <header className="sticky top-0 z-20 border-b border-line bg-ground/90 backdrop-blur">
            <div className="mx-auto flex max-w-[1100px] items-center gap-4 px-5 py-3">
              <NavLink to="/" className="shrink-0">
                <div className="text-base font-semibold tracking-tight">
                  {PRODUCT_NAME}
                </div>
                <div className="font-mono text-[10px] text-ink-faint">
                  {PRODUCT_SUBTITLE}
                </div>
              </NavLink>
              <div className="mx-auto hidden md:block">
                <ProgressRail />
              </div>
              <div className="ml-auto shrink-0">
                <DepthToggle />
              </div>
            </div>
            <div className="mx-auto max-w-[1100px] px-5 pb-2.5 md:hidden">
              <ProgressRail />
            </div>
          </header>

          <main className="mx-auto w-full max-w-[1100px] flex-1 px-5 pb-8 pt-8">
            <Routes>
              <Route path="/" element={<Act0Brief />} />
              <Route path="/distribute" element={<Act1Distribute />} />
              <Route path="/open" element={<Act2Open />} />
              <Route path="/ledger" element={<Act3Ledger />} />
              <Route path="/leak" element={<Act4Leak />} />
              <Route path="/attribute" element={<Act5Attribute />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>

          <footer className="border-t border-line px-5 py-4">
            <div className="mx-auto flex max-w-[1100px] flex-wrap items-center gap-x-4 gap-y-1 text-micro text-ink-faint">
              <span className="flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-verified" aria-hidden />
                Runs offline — no cloud KMS, no public blockchain
              </span>
              <span className="ml-auto font-mono">{PRODUCT_SUBTITLE}</span>
            </div>
          </footer>
        </div>
      </RunProvider>
    </DepthProvider>
  );
}
