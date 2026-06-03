import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        base:     "#070b14",
        surface:  "#0d1225",
        card:     "#111827",
        "card-hover": "#1a2235",
        border:   "rgba(255,255,255,0.08)",
        accent:   "#3b82f6",
        cyan:     "#06b6d4",
        "signal-strong-buy":  "#16a34a",
        "signal-buy":         "#22c55e",
        "signal-hold":        "#f59e0b",
        "signal-sell":        "#f97316",
        "signal-strong-sell": "#ef4444",
        "text-secondary":     "#94a3b8",
        "text-muted":         "#475569",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      borderRadius: {
        "2xl": "16px",
        "3xl": "24px",
      },
      animation: {
        "shimmer": "shimmer 1.6s infinite",
        "pulse-ring": "pulse-ring 1.5s ease-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
