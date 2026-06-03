"use client";
import { motion } from "framer-motion";

interface Props {
  currentPrice: number;
  stopLoss: number;
  conservative: number;
  base: number;
  aggressive: number;
}

export default function PriceTargetBar({ currentPrice, stopLoss, conservative, base, aggressive }: Props) {
  const min = Math.min(stopLoss, currentPrice) * 0.995;
  const max = aggressive * 1.005;
  const range = max - min;

  const pct = (val: number) => `${(((val - min) / range) * 100).toFixed(1)}%`;

  const markers = [
    { val: stopLoss,     label: "SL",          color: "#ef4444", textColor: "#f87171" },
    { val: currentPrice, label: "CMP",          color: "#60a5fa", textColor: "#93c5fd" },
    { val: conservative, label: "T1",           color: "#86efac", textColor: "#86efac" },
    { val: base,         label: "T2",           color: "#4ade80", textColor: "#4ade80" },
    { val: aggressive,   label: "T3",           color: "#16a34a", textColor: "#34d399" },
  ];

  return (
    <div className="w-full space-y-4">
      {/* Bar */}
      <div className="relative h-3 rounded-full" style={{ background: "rgba(255,255,255,0.06)" }}>
        {/* Filled region (SL → Aggressive) */}
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${(((aggressive - currentPrice) / range) * 100).toFixed(1)}%` }}
          transition={{ duration: 1, ease: "easeOut" }}
          style={{
            position: "absolute",
            left: pct(currentPrice),
            height: "100%",
            background: "linear-gradient(90deg, #22c55e40, #16a34a)",
            borderRadius: "0 99px 99px 0",
          }}
        />
        {/* Markers */}
        {markers.map((m) => (
          <div
            key={m.label}
            style={{
              position: "absolute",
              left: pct(m.val),
              top: "50%",
              transform: "translate(-50%, -50%)",
              width: 12,
              height: 12,
              borderRadius: "50%",
              background: m.color,
              border: "2px solid var(--bg-card)",
              boxShadow: `0 0 8px ${m.color}`,
              zIndex: 2,
            }}
          />
        ))}
      </div>

      {/* Labels below */}
      <div className="relative" style={{ height: 40 }}>
        {markers.map((m) => (
          <div
            key={m.label}
            style={{
              position: "absolute",
              left: pct(m.val),
              transform: "translateX(-50%)",
              textAlign: "center",
            }}
          >
            <div style={{ fontSize: 10, fontWeight: 700, color: m.textColor }}>{m.label}</div>
            <div style={{ fontSize: 10, color: "#64748b" }}>₹{m.val.toLocaleString("en-IN")}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
