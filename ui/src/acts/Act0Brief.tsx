import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { PRODUCT_NAME, PRODUCT_TAGLINE } from "../brand";
import { useDepth } from "../components/Layers";

/** Act 0 — the problem, before any cryptography.
 *
 * A viewer who leaves this screen should be able to say: "one file, five
 * readers, identical copies, so a leak has five equal suspects." Everything
 * later only makes sense against that.
 */
export default function Act0Brief() {
  const nav = useNavigate();
  const { deep } = useDepth();
  const [limitsOpen, setLimitsOpen] = useState(false);

  return (
    <div className="space-y-12">
      {/* ---------------------------------------------------- hero */}
      <section>
        <h1 className="text-4xl font-semibold tracking-tight">
          You send one confidential file to five people.
          <br />
          <span className="text-ink-dim">It leaks. Who did it?</span>
        </h1>
        <p className="mt-5 max-w-prose text-lg text-ink-dim">
          Every recipient decrypted the same document and got back byte-for-byte
          identical content. Nothing in the leaked copy points at anyone.{" "}
          <strong className="font-medium text-ink">
            {PRODUCT_NAME} makes each copy forensically distinct at the moment it
            is opened
          </strong>{" "}
          — so a leak names exactly one person, and they cannot deny it.
        </p>
        <p className="mt-2 font-mono text-tiny text-accent">
          {PRODUCT_TAGLINE}
        </p>
      </section>

      {/* ---------------------------------------------------- the problem */}
      <section>
        <ProblemDiagram />
      </section>

      {/* ---------------------------------------------------- why not obvious */}
      <section className="grid gap-4 md:grid-cols-2">
        <FailedFix
          title="Server access logs"
          body="They record who opened the file — but an administrator with database access can edit them. The evidence sits in exactly the place a privileged insider controls."
        />
        <FailedFix
          title="A watermark added before sending"
          body="Every recipient receives the same mark, so the leaked copy still matches all five. It reproduces the problem it was meant to solve."
        />
      </section>

      {/* ---------------------------------------------------- the answer */}
      <section>
        <h2 className="text-2xl font-semibold tracking-tight">
          What {PRODUCT_NAME} does instead
        </h2>
        <p className="mt-2 max-w-prose text-base text-ink-dim">
          The mark is created <em className="text-ink">as the file is opened</em>,
          not before it is sent. That single change is what makes attribution
          possible.
        </p>

        <ol className="mt-6 space-y-0">
          {CHAIN.map((step, i) => (
            <li key={step.title} className="relative flex gap-4 pb-6 last:pb-0">
              {i < CHAIN.length - 1 && (
                <span
                  className="absolute left-[13px] top-7 h-full w-px bg-line"
                  aria-hidden
                />
              )}
              <span className="relative z-10 grid h-[27px] w-[27px] shrink-0 place-items-center rounded-full border border-line bg-surface font-mono text-tiny text-ink-dim">
                {i + 1}
              </span>
              <div className="min-w-0 pt-0.5">
                <h3 className="text-base font-medium">{step.title}</h3>
                <p className="mt-0.5 max-w-prose text-sm text-ink-dim">
                  {step.body}
                </p>
                {deep && (
                  <p className="mt-1 font-mono text-micro text-accent">
                    {step.tech}
                  </p>
                )}
              </div>
            </li>
          ))}
        </ol>
      </section>

      {/* ---------------------------------------------------- start */}
      <section className="flex flex-wrap items-center gap-4 border-t border-line pt-8">
        <button
          onClick={() => nav("/distribute")}
          className="rounded-md bg-[var(--btn-primary-bg)] px-4 py-2.5 text-base font-medium text-[var(--btn-primary-ink)] transition-colors duration-fast hover:bg-[var(--btn-primary-bg-hover)]"
        >
          Start the walkthrough
        </button>
        <p className="text-sm text-ink-faint">
          Six steps. Everything you see is produced by the real system.
        </p>
      </section>

      {/* ---------------------------------------------------- limits */}
      <section className="border-t border-line pt-6">
        <button
          onClick={() => setLimitsOpen((o) => !o)}
          className="text-sm text-ink-faint underline decoration-line underline-offset-4 hover:text-ink-dim"
          aria-expanded={limitsOpen}
        >
          {limitsOpen ? "Hide" : "What this does not do"}
        </button>
        {limitsOpen && (
          <div className="mt-4 space-y-3">
            {LIMITS.map((l) => (
              <div key={l.title} className="max-w-measure">
                <h4 className="text-sm font-medium text-ink">{l.title}</h4>
                <p className="mt-0.5 text-sm text-ink-dim">{l.body}</p>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

/* --------------------------------------------------------------- pieces */

function FailedFix({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-[var(--card-radius)] border border-line bg-surface p-4">
      <div className="flex items-center gap-2">
        <span className="grid h-4 w-4 place-items-center rounded-full bg-broken/15 text-[10px] font-bold text-broken" aria-hidden>
          ✕
        </span>
        <h3 className="text-base font-medium">{title}</h3>
      </div>
      <p className="mt-2 text-sm text-ink-dim">{body}</p>
    </div>
  );
}

function ProblemDiagram() {
  return (
    <figure className="m-0">
      <svg
        viewBox="0 0 760 232"
        role="img"
        aria-label="One encrypted file decrypts to five identical copies; when one leaks, all five recipients are equally plausible suspects."
        className="w-full rounded-[var(--card-radius)] border border-line bg-surface"
      >
        <defs>
          <marker id="p-ar" viewBox="0 0 10 10" refX="9" refY="5"
                  markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill="currentColor" />
          </marker>
          <marker id="p-ar-r" viewBox="0 0 10 10" refX="9" refY="5"
                  markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill="var(--broken)" />
          </marker>
        </defs>

        <rect x="22" y="88" width="112" height="52" rx="7"
              fill="none" stroke="currentColor" strokeWidth="1.3" opacity=".85" />
        <text x="78" y="110" textAnchor="middle" fontSize="12.5"
              fill="currentColor" fontWeight="600">report.pdf</text>
        <text x="78" y="127" textAnchor="middle" fontSize="10.5"
              fill="currentColor" opacity=".55">encrypted once</text>

        <line x1="134" y1="114" x2="186" y2="114" stroke="currentColor"
              strokeWidth="1.3" markerEnd="url(#p-ar)" opacity=".7" />

        {[0, 1, 2, 3, 4].map((i) => (
          <g key={i}>
            <rect x="190" y={14 + i * 40} width="122" height="32" rx="6"
                  fill="none" stroke={`var(--id-${i + 1})`} strokeWidth="1.2"
                  opacity=".8" />
            <text x="251" y={34 + i * 40} textAnchor="middle" fontSize="11.5"
                  fill={`var(--id-${i + 1})`}>
              {["alice", "bob", "carol", "dave", "erin"][i]}
            </text>
          </g>
        ))}
        <text x="251" y="222" textAnchor="middle" fontSize="10.5"
              fill="currentColor" opacity=".55">
          all five copies are byte-identical
        </text>

        <line x1="316" y1="114" x2="396" y2="114" stroke="currentColor"
              strokeWidth="1.3" markerEnd="url(#p-ar)" opacity=".7" />
        <text x="356" y="107" textAnchor="middle" fontSize="10.5"
              fill="currentColor" opacity=".6">one leaks</text>

        <rect x="400" y="86" width="126" height="56" rx="7"
              fill="none" stroke="var(--broken)" strokeWidth="1.5" />
        <text x="463" y="110" textAnchor="middle" fontSize="12.5"
              fill="var(--broken)" fontWeight="600">leaked copy</text>
        <text x="463" y="127" textAnchor="middle" fontSize="10.5"
              fill="var(--broken)" opacity=".8">no trace of origin</text>

        <line x1="526" y1="114" x2="580" y2="114" stroke="var(--broken)"
              strokeWidth="1.3" markerEnd="url(#p-ar-r)" />

        {[0, 1, 2, 3, 4].map((i) => (
          <text key={i} x="592" y={74 + i * 20} fontSize="11.5"
                fill="currentColor" opacity=".6">
            {["alice", "bob", "carol", "dave", "erin"][i]}?
          </text>
        ))}
        <text x="592" y="186" fontSize="11" fill="var(--broken)">
          five equal suspects
        </text>
      </svg>
      <figcaption className="mt-2.5 max-w-prose text-sm text-ink-faint">
        One encryption, five identical decryptions. The leaked file carries
        nothing that distinguishes one recipient from another.
      </figcaption>
    </figure>
  );
}

const CHAIN = [
  {
    title: "Encrypt once, for many",
    body: "The document is sealed a single time. The key to open it is wrapped separately for each recipient, so only they can unwrap their own.",
    tech: "ML-KEM-768 (FIPS 203) key encapsulation · AES-256-GCM body",
  },
  {
    title: "Mark at the moment of opening",
    body: "As a recipient decrypts, an invisible mark unique to them and to that session is woven into the word spacing. The page looks identical.",
    tech: "differential inter-word spacing, ±0.35pt · Tardos fingerprinting code",
  },
  {
    title: "The recipient signs for it",
    body: "They sign a record of the decryption with their own private key. Only they hold it, so they cannot later deny having opened the file.",
    tech: "ML-DSA-65 (FIPS 204) · 3309-byte signature over the canonical record",
  },
  {
    title: "The record is locked into a ledger",
    body: "Each record joins an append-only log. Editing any earlier entry breaks the chain visibly — even for an administrator with full database access.",
    tech: "RFC 6962 Merkle tree · signed tree head · RFC 9162 consistency proofs",
  },
  {
    title: "A leaked file names its source",
    body: "The mark is recovered from the leaked copy, matched against the ledger, and the whole chain of evidence is verified in front of you.",
    tech: "correlation against every codeword · signature + inclusion proof verified live",
  },
];

const LIMITS = [
  {
    title: "A screenshot or photograph cannot be traced",
    body: "The mark lives in the geometry of the text layer. Turning the page into pixels destroys it. Covering that would need a different, pixel-level marking technique.",
  },
  {
    title: "A determined recipient could modify the software",
    body: "Marking happens on the recipient's own machine, as the problem statement requires, so the code runs where an adversary has control. Preventing that needs hardware support. Note though that a leaked file carrying no valid mark is itself evidence — the ledger still records who was able to decrypt.",
  },
  {
    title: "Signatures prove a key was used, not a person's intent",
    body: "This is true of all digital signatures. Non-repudiation rests on the duty to protect your own key, not on mathematics alone.",
  },
  {
    title: "Very short documents are refused",
    body: "A mark needs room to hide. Rather than half-mark a file it could not later defend, the system declines and says so.",
  },
];
