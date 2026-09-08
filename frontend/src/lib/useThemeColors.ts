import { useTheme } from "@/components/layout/ThemeProvider";

/**
 * Returns theme-aware color mappings.
 * Pages can use these instead of hardcoded hex colors.
 *
 * Usage:
 *   const c = useThemeColors();
 *   <div style={{ color: c.textPrimary, background: c.bgCard }}>
 */
export function useThemeColors() {
  const { theme } = useTheme();
  const dark = theme === "dark";

  return {
    // Backgrounds
    bgBase:       dark ? "#070b14"  : "#f1f5f9",
    bgSurface:    dark ? "#0d1225"  : "#ffffff",
    bgCard:       dark ? "#111827"  : "#ffffff",
    bgCardHover:  dark ? "#1a2235"  : "#f1f5f9",

    // Text
    textPrimary:  dark ? "#f1f5f9"  : "#0f172a",
    textSecondary: dark ? "#94a3b8" : "#475569",
    textMuted:    dark ? "#475569"  : "#94a3b8",
    textFaint:    dark ? "#334155"  : "#cbd5e1",
    textDimmest:  dark ? "#1e293b"  : "#e2e8f0",

    // Borders
    border:       dark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.08)",
    borderBright: dark ? "rgba(255,255,255,0.15)" : "rgba(0,0,0,0.15)",

    // Misc
    hoverBg:      dark ? "rgba(255,255,255,0.04)" : "rgba(0,0,0,0.04)",
    statusBg:     dark ? "rgba(255,255,255,0.04)" : "rgba(0,0,0,0.04)",

    // Signal colors (same both modes)
    buy: "#22c55e",
    strongBuy: "#16a34a",
    hold: "#f59e0b",
    sell: "#f97316",
    strongSell: "#ef4444",

    // Accent (same both modes)
    blue: "#3b82f6",
    cyan: "#06b6d4",
    purple: "#a855f7",

    // Theme flag
    isDark: dark,
  };
}
