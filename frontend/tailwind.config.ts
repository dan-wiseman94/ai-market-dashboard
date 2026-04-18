import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        display: ["Fraunces", "Iowan Old Style", "Georgia", "serif"],
        sans: ["Geist", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      colors: {
        ink: {
          void: "var(--ink-void)",
          950: "var(--ink-950)",
          900: "var(--ink-900)",
          850: "var(--ink-850)",
          800: "var(--ink-800)",
          700: "var(--ink-700)",
          600: "var(--ink-600)",
          500: "var(--ink-500)",
          400: "var(--ink-400)",
          300: "var(--ink-300)",
          200: "var(--ink-200)",
          100: "var(--ink-100)",
          50:  "var(--ink-50)",
        },
        copper: {
          50:  "var(--copper-50)",
          100: "var(--copper-100)",
          200: "var(--copper-200)",
          300: "var(--copper-300)",
          400: "var(--copper-400)",
          500: "var(--copper-500)",
          600: "var(--copper-600)",
          700: "var(--copper-700)",
          800: "var(--copper-800)",
        },
        gain: {
          300: "var(--gain-300)",
          400: "var(--gain-400)",
          500: "var(--gain-500)",
        },
        loss: {
          300: "var(--loss-300)",
          400: "var(--loss-400)",
          500: "var(--loss-500)",
        },
      },
      letterSpacing: {
        tight2: "-0.02em",
        loose2: "0.22em",
      },
      borderRadius: {
        ledger: "2px",
      },
      boxShadow: {
        ledger: "0 1px 0 rgba(0,0,0,0.4), 0 20px 40px -24px rgba(0,0,0,0.6)",
        "copper-glow": "0 0 40px -12px rgba(200,150,88,0.55)",
      },
      transitionTimingFunction: {
        ledger: "cubic-bezier(0.2, 0.65, 0.2, 1)",
      },
    },
  },
  plugins: [],
} satisfies Config;
