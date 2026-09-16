/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Semantic layer only -- primitives live in tokens.css.
        ground: "var(--ground)",
        surface: "var(--surface)",
        raised: "var(--raised)",
        line: "var(--line)",
        "line-soft": "var(--line-soft)",
        ink: "var(--ink)",
        "ink-dim": "var(--ink-dim)",
        "ink-faint": "var(--ink-faint)",
        accent: "var(--accent)",
        "accent-dim": "var(--accent-dim)",
        verified: "var(--verified)",
        broken: "var(--broken)",
        caution: "var(--caution)",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      fontSize: {
        micro: ["11px", { lineHeight: "1.45", letterSpacing: "0.01em" }],
        tiny: ["12px", { lineHeight: "1.5" }],
        sm: ["13px", { lineHeight: "1.55" }],
        base: ["14px", { lineHeight: "1.6" }],
        lg: ["16px", { lineHeight: "1.6" }],
        xl: ["19px", { lineHeight: "1.4", letterSpacing: "-0.01em" }],
        "2xl": ["24px", { lineHeight: "1.3", letterSpacing: "-0.015em" }],
        "3xl": ["32px", { lineHeight: "1.2", letterSpacing: "-0.02em" }],
        "4xl": ["44px", { lineHeight: "1.1", letterSpacing: "-0.025em" }],
      },
      maxWidth: { prose: "64ch", measure: "72ch" },
      transitionDuration: { fast: "120ms", base: "200ms" },
    },
  },
  plugins: [],
};
