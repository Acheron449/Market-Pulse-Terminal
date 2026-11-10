/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        up: "#00E676",
        down: "#FF5252",
        caution: "#F0B429",
        volume: "#22D3EE",
        surface: "#0E1116",
        panel: "#141922",
        edge: "#232A36",
        ink: "#E6EAF2",
        muted: "#8B96A8",
      },
      fontFamily: {
        // Two families only: a UI sans and a numeral-first mono (AGENTS.md §7).
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      maxWidth: {
        terminal: "1320px",
      },
    },
  },
  plugins: [],
};
