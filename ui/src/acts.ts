/** The six acts, in order. The progress rail and routing both read this. */
export interface Act {
  n: number;
  path: string;
  short: string;
  title: string;
}

export const ACTS: Act[] = [
  { n: 0, path: "/",           short: "Brief",     title: "The problem" },
  { n: 1, path: "/distribute", short: "Seal",      title: "Encrypt & distribute" },
  { n: 2, path: "/open",       short: "Open",      title: "A recipient decrypts" },
  { n: 3, path: "/ledger",     short: "Record",    title: "The audit ledger" },
  { n: 4, path: "/leak",       short: "Breach",    title: "The document surfaces" },
  { n: 5, path: "/attribute",  short: "Verdict",   title: "Forensic attribution" },
];

/** Stable colour per recipient, used in every act so a viewer can track one
 *  person visually through the whole story. */
export const HUES = [
  "var(--id-1)", "var(--id-2)", "var(--id-3)", "var(--id-4)", "var(--id-5)",
];

export function hueFor(userId: string, all: string[]): string {
  const i = all.indexOf(userId);
  return HUES[(i < 0 ? 0 : i) % HUES.length]!;
}
