"use client";
import { motion } from "framer-motion";
import type { Analysis } from "@/lib/api";

type Signal = Analysis["signal"];

const CONFIG: Record<Signal, { label: string; bg: string; text: string; border: string; dot: string; pulse: boolean }> = {
  "STRONG BUY":  { label: "⚡ Strong Buy",  bg: "rgba(22,163,74,0.15)",  text: "#4ade80", border: "rgba(22,163,74,0.4)",  dot: "#16a34a", pulse: true },
  "BUY":         { label: "▲ Buy",          bg: "rgba(34,197,94,0.12)",  text: "#86efac", border: "rgba(34,197,94,0.35)", dot: "#22c55e", pulse: false },
  "HOLD":        { label: "◆ Hold",         bg: "rgba(245,158,11,0.12)", text: "#fcd34d", border: "rgba(245,158,11,0.35)",dot: "#f59e0b", pulse: false },
  "SELL":        { label: "▼ Sell",         bg: "rgba(249,115,22,0.12)", text: "#fdba74", border: "rgba(249,115,22,0.35)",dot: "#f97316", pulse: false },
  "STRONG SELL": { label: "⚠ Strong Sell", bg: "rgba(239,68,68,0.15)",  text: "#f87171", border: "rgba(239,68,68,0.4)",  dot: "#ef4444", pulse: true },
};

interface Props {
  signal: Signal;
  confidence?: number;
  size?: "sm" | "md" | "lg";
}

export default function SignalBadge({ signal, confidence, size = "md" }: Props) {
  const c = CONFIG[signal];
  const pad = size === "lg" ? "px-4 py-2" : size === "sm" ? "px-2 py-0.5" : "px-3 py-1";
  const font = size === "lg" ? "text-base font-bold" : size === "sm" ? "text-xs font-semibold" : "text-sm font-semibold";

  return (
    <motion.div
      initial={{ scale: 0.9, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      className={`inline-flex items-center gap-2 rounded-full ${pad} ${font}`}
      style={{ background: c.bg, border: `1px solid ${c.border}`, color: c.text }}
    >
      {/* Pulse dot */}
      <span className="relative flex items-center justify-center" style={{ width: 8, height: 8 }}>
        <span
          className="absolute rounded-full"
          style={{
            width: 8, height: 8,
            background: c.dot,
            opacity: 0.9,
          }}
        />
        {c.pulse && (
          <span
            className="absolute rounded-full animate-ping"
            style={{ width: 8, height: 8, background: c.dot, opacity: 0.5 }}
          />
        )}
      </span>
      {c.label}
      {confidence !== undefined && (
        <span style={{ opacity: 0.7, fontSize: "0.8em" }}>{Math.round(confidence)}%</span>
      )}
    </motion.div>
  );
}
