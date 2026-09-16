/** Presentation of cryptographic material.
 *
 * The rule, applied everywhere without exception: a viewer never sees a bare
 * hex dump. Every value gets a human label, a truncated form, a copy action,
 * and the full value on demand. The old console printed 64-character hashes
 * inline, which is unreadable and is not how any real security product
 * presents this.
 */
import { useState } from "react";

function useCopy() {
  const [done, setDone] = useState(false);
  return {
    done,
    copy: async (text: string) => {
      try {
        await navigator.clipboard.writeText(text);
      } catch {
        // Clipboard is unavailable in some offline/insecure contexts. Fall
        // back to a selection so the value is still obtainable.
        const ta = document.createElement("textarea");
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        ta.remove();
      }
      setDone(true);
      setTimeout(() => setDone(false), 1400);
    },
  };
}

export function CryptoValue({
  label,
  value,
  head = 10,
  note,
  tone = "default",
}: {
  label: string;
  value: string;
  head?: number;
  note?: string;
  tone?: "default" | "accent" | "verified" | "broken";
}) {
  const [open, setOpen] = useState(false);
  const { copy, done } = useCopy();
  const truncated = value.length > head * 2;
  const shown = open || !truncated ? value : `${value.slice(0, head)}…`;

  const toneClass = {
    default: "text-[var(--crypto-ink)]",
    accent: "text-accent",
    verified: "text-verified",
    broken: "text-broken",
  }[tone];

  return (
    <div className="min-w-0">
      <div className="flex items-baseline gap-2">
        <span className="text-micro text-ink-faint">{label}</span>
        {note && <span className="text-micro text-ink-faint/70">{note}</span>}
      </div>
      <div className="mt-1 flex items-start gap-1.5">
        <code
          className={`font-mono text-tiny ${toneClass} break-all leading-relaxed`}
          title={truncated && !open ? "truncated — expand to see all" : undefined}
        >
          {shown}
        </code>
        <div className="flex shrink-0 gap-0.5 pt-px">
          {truncated && (
            <button
              onClick={() => setOpen((o) => !o)}
              className="rounded px-1 text-micro text-ink-faint hover:text-ink"
              aria-label={open ? `Collapse ${label}` : `Expand ${label}`}
            >
              {open ? "less" : "all"}
            </button>
          )}
          <button
            onClick={() => copy(value)}
            className="rounded px-1 text-micro text-ink-faint hover:text-ink"
            aria-label={`Copy ${label}`}
          >
            {done ? "✓" : "copy"}
          </button>
        </div>
      </div>
    </div>
  );
}

/** A recipient's cryptographic identity, presented as a card rather than a
 *  table row — they are key material, not names in a list. */
export function IdentityCard({
  userId,
  fingerprint,
  hue,
  selected,
  onToggle,
  disabled,
}: {
  userId: string;
  fingerprint: string;
  hue: string;
  selected?: boolean;
  onToggle?: () => void;
  disabled?: boolean;
}) {
  const interactive = !!onToggle && !disabled;
  const Tag = interactive ? "button" : "div";

  return (
    <Tag
      {...(interactive
        ? { onClick: onToggle, "aria-pressed": !!selected, type: "button" as const }
        : {})}
      className={`group relative w-full rounded-[var(--card-radius)] border p-3 text-left transition-colors duration-fast
        ${selected ? "border-accent bg-raised" : "border-line bg-surface"}
        ${interactive ? "hover:border-ink-faint cursor-pointer" : ""}
        ${disabled ? "opacity-50" : ""}`}
    >
      <span
        className="absolute left-0 top-3 bottom-3 w-[3px] rounded-r"
        style={{ background: hue }}
        aria-hidden
      />
      <div className="pl-2.5">
        <div className="flex items-center justify-between gap-2">
          <span className="text-base font-medium capitalize">{userId}</span>
          {selected !== undefined && (
            <span
              className={`grid h-4 w-4 shrink-0 place-items-center rounded-[3px] border text-[10px]
                ${selected ? "border-accent bg-accent text-white" : "border-line"}`}
              aria-hidden
            >
              {selected ? "✓" : ""}
            </span>
          )}
        </div>
        <div className="mt-1.5 font-mono text-micro text-ink-faint">
          <span className="text-ink-faint/70">fingerprint</span>{" "}
          {fingerprint.slice(0, 16)}
        </div>
        <div className="mt-0.5 text-micro text-ink-faint/70">
          ML-KEM-768 · ML-DSA-65 keypair
        </div>
      </div>
    </Tag>
  );
}

/** One cryptographic check, pass or fail, with what it proves. */
export function CheckRow({
  label,
  passed,
  detail,
}: {
  label: string;
  passed: boolean;
  detail?: string;
}) {
  return (
    <div className="flex items-start gap-3 border-b border-line-soft py-2.5 last:border-0">
      <span
        className={`mt-1 grid h-4 w-4 shrink-0 place-items-center rounded-full text-[10px] font-bold
          ${passed ? "bg-verified/15 text-verified" : "bg-broken/15 text-broken"}`}
        aria-hidden
      >
        {passed ? "✓" : "✕"}
      </span>
      <div className="min-w-0">
        <div className={`text-sm ${passed ? "text-ink" : "text-broken"}`}>
          {label}
        </div>
        {detail && (
          <div className="mt-0.5 font-mono text-micro text-ink-faint">{detail}</div>
        )}
      </div>
      <span
        className={`ml-auto shrink-0 font-mono text-micro ${
          passed ? "text-verified" : "text-broken"
        }`}
      >
        {passed ? "VERIFIED" : "FAILED"}
      </span>
    </div>
  );
}
