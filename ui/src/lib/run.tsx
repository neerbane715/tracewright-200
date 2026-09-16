/** Shared state for one pass through the journey.
 *
 * Deliberately thin: it remembers only what one Act needs to hand the next
 * (which bundle, who has opened it, which file leaked). Everything
 * cryptographic is re-fetched from the backend at the moment it is shown, so
 * no Act can display a stale or invented value.
 */
import {
  createContext, useCallback, useContext, useMemo, useState, type ReactNode,
} from "react";
import type { DecryptResult, EncryptResult } from "./api";

export interface OpenedCopy {
  userId: string;
  ledgerIndex: number;
  sessionId: string;
  bits: number;
  outputPath: string;
  steps: string[];
  record: DecryptResult["record"];
}

interface RunState {
  bundle: EncryptResult | null;
  setBundle: (b: EncryptResult | null) => void;
  opened: OpenedCopy[];
  addOpened: (c: OpenedCopy) => void;
  leaked: OpenedCopy | null;
  setLeaked: (c: OpenedCopy | null) => void;
  reset: () => void;
}

const Ctx = createContext<RunState | null>(null);

export function RunProvider({ children }: { children: ReactNode }) {
  const [bundle, setBundle] = useState<EncryptResult | null>(null);
  const [opened, setOpened] = useState<OpenedCopy[]>([]);
  const [leaked, setLeaked] = useState<OpenedCopy | null>(null);

  const addOpened = useCallback((c: OpenedCopy) => {
    setOpened((prev) => [...prev.filter((p) => p.userId !== c.userId), c]);
  }, []);

  const reset = useCallback(() => {
    setBundle(null);
    setOpened([]);
    setLeaked(null);
  }, []);

  const value = useMemo(
    () => ({ bundle, setBundle, opened, addOpened, leaked, setLeaked, reset }),
    [bundle, opened, leaked, addOpened, reset],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useRun(): RunState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useRun must be used inside RunProvider");
  return v;
}
