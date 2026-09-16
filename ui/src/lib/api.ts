/** Typed client for the Tracewright FastAPI backend.
 *
 * Two rules this file exists to enforce:
 *
 * 1. TRANSPORT FAILURE IS NOT APPLICATION FAILURE. The previous build showed a
 *    bare "Failed to fetch" when the API was down, which during a live demo
 *    reads as "the product is broken". Every failure here is classified, so the
 *    UI can say "the backend isn't running" instead of implying the crypto
 *    failed.
 *
 * 2. RESPONSE SHAPES ARE DECLARED. The backend returns rich verdict objects;
 *    silent field drift is exactly how a UI ends up describing crypto it isn't
 *    actually showing.
 */

export type FailureKind =
  | "offline"      // no backend reachable at all
  | "timeout"      // backend reachable but did not answer in time
  | "refused"      // backend answered 4xx — we asked for something invalid
  | "faulted"      // backend answered 5xx — something broke server-side
  | "malformed";   // backend answered but not with what we expected

export class ApiError extends Error {
  constructor(
    readonly kind: FailureKind,
    message: string,
    readonly status?: number,
    readonly detail?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** What a non-technical viewer should read. Never a stack trace, never a
   *  filesystem path. */
  get humanMessage(): string {
    switch (this.kind) {
      case "offline":
        return "The Tracewright engine isn't running. Start the backend, then retry.";
      case "timeout":
        return "The engine is taking longer than expected. It may still be working.";
      case "refused":
        return this.detail ?? "That request wasn't valid.";
      case "faulted":
        return "The engine hit an internal error carrying out that step.";
      case "malformed":
        return "The engine replied with something unexpected.";
    }
  }

  get isRetryable(): boolean {
    return this.kind === "offline" || this.kind === "timeout" || this.kind === "faulted";
  }
}

const DEFAULT_TIMEOUT = 60_000;

async function request<T>(
  path: string,
  init: RequestInit = {},
  timeoutMs = DEFAULT_TIMEOUT,
): Promise<T> {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeoutMs);

  let res: Response;
  try {
    res = await fetch(path, { ...init, signal: ctl.signal });
  } catch (e) {
    clearTimeout(timer);
    if (e instanceof DOMException && e.name === "AbortError") {
      throw new ApiError("timeout", `timed out after ${timeoutMs}ms`);
    }
    // fetch() rejects for DNS/connection failures — the backend is not there.
    throw new ApiError("offline", "could not reach the backend");
  }
  clearTimeout(timer);

  if (!res.ok) {
    let detail: string | undefined;
    try {
      const body = await res.json();
      detail = typeof body?.detail === "string" ? body.detail : undefined;
    } catch {
      /* body wasn't JSON; fall through with no detail */
    }
    // Never surface a filesystem path to a viewer, whatever the server said.
    if (detail && /[A-Za-z]:\\|\/(home|Users|tmp|var)\//.test(detail)) {
      detail = undefined;
    }
    throw new ApiError(
      res.status >= 500 ? "faulted" : "refused",
      `HTTP ${res.status}`,
      res.status,
      detail,
    );
  }

  try {
    return (await res.json()) as T;
  } catch {
    throw new ApiError("malformed", "response was not valid JSON");
  }
}

export const api = {
  get: <T>(p: string, timeoutMs?: number) => request<T>(p, {}, timeoutMs),

  post: <T>(p: string, body?: unknown, timeoutMs?: number) =>
    request<T>(
      p,
      {
        method: "POST",
        headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      },
      timeoutMs,
    ),

  upload: <T>(p: string, file: File, timeoutMs?: number) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<T>(p, { method: "POST", body: fd }, timeoutMs);
  },
};

/* ------------------------------------------------------------------ types */

export interface Identity {
  user_id: string;
  fingerprint: string;
  has_secret: boolean;
}

export interface EncryptResult {
  doc_id: string;
  bundle: string;
  recipients: string[];
  capacity_bits: number;
  required_bits: number;
}

export interface DecryptionRecord {
  version: number;
  session_id: string;
  doc_id: string;
  doc_hash: string;
  recipient_fingerprint: string;
  recipient_user_id: string;
  watermark_commitment: string;
  watermark_seed: string;
  n_bits: number;
  user_index: number;
  n_users: number;
  timestamp: string;
}

export interface DecryptResult {
  output: string;
  steps: string[];
  session_id: string;
  ledger_index: number;
  bits: number;
  record: DecryptionRecord;
}

export interface LedgerRecordRow {
  index: number;
  user_id: string;
  fingerprint: string;
  doc_id: string;
  session_id: string;
  timestamp: string;
  n_bits: number;
}

export interface LedgerState {
  size: number;
  root: string;
  sth: {
    tree_size: number;
    root: string;
    signed_at: string;
    signature_bytes: number;
    valid: boolean;
  } | null;
  records: LedgerRecordRow[];
}

export interface IntegrityResult {
  tampered: boolean;
  index: number | null;
  message: string;
}

export interface TamperResult {
  edited_index: number;
  from: string;
  to: string;
  detected: boolean;
  detected_at: number | null;
  message: string;
}

export interface InclusionProof {
  index: number;
  tree_size: number;
  root: string;
  path: string[];
}

export type Outcome =
  | "IDENTIFIED"
  | "INCONCLUSIVE"
  | "NO_WATERMARK"
  | "LEDGER_COMPROMISED";

export interface Verdict {
  outcome: Outcome;
  recipient: { user_id: string | null; fingerprint: string | null };
  event: {
    session_id: string | null;
    doc_id: string | null;
    timestamp: string | null;
    ledger_index: number | null;
  };
  evidence: {
    signature_valid: boolean;
    inclusion_proof_valid: boolean;
    watermark_commitment_valid: boolean;
    ledger_intact: boolean;
    cryptographically_verified: boolean;
  };
  detection: {
    score: number | null;
    threshold: number | null;
    margin: number | null;
    bits_recovered: number;
    bits_expected: number;
  };
  ranking: [string, number][];
  notes: string[];
}
