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

  const pctNum = (val: number) => ((val - min) / range) * 100;
  const pct    = (val: number) => `${pctNum(val).toFixed(1)}%`;

  // Assign markers in bar order
  const rawMarkers = [
    { val: stopLoss,     label: "SL",  color: "#ef4444", textColor: "#f87171" },
    { val: currentPrice, label: "CMP", color: "#60a5fa", textColor: "#93c5fd" },
    { val: conservative, label: "T1",  color: "#86efac", textColor: "#86efac" },
    { val: base,         label: "T2",  color: "#4ade80", textColor: "#4ade80" },
    { val: aggressive,   label: "T3",  color: "#16a34a", textColor: "#34d399" },
  ];

  // Auto-stagger: if two adjacent markers are within 12% of bar width, push second to row 1
  const MIN_GAP = 12; // percent
  const markers = rawMarkers.map((m, i) => {
    if (i === 0) return { ...m, row: 0 };
    const prev = rawMarkers[i - 1];
    const gap = Math.abs(pctNum(m.val) - pctNum(prev.val));
    // If gap is tight, alternate rows with the previous marker
    const prevRow = i > 0 ? (rawMarkers[i - 1] as any)._row ?? 0 : 0;
    const row = gap < MIN_GAP ? (prevRow === 0 ? 1 : 0) : 0;
    (m as any)._row = row;
    return { ...m, row };
  });

  const ROW_HEIGHT = 22; // px per row
  const CONTAINER_H = 52;

  return (
    <div className="w-full" style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {/* Bar */}
      <div className="relative h-3 rounded-full" style={{ background: "rgba(255,255,255,0.06)" }}>
        {/* Filled region (CMP → T3) */}
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
        {/* Dot markers */}
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

      {/* Labels — staggered into two rows */}
      <div style={{ position: "relative", height: CONTAINER_H }}>
        {markers.map((m) => {
          const topOffset = m.row * ROW_HEIGHT;
          return (
            <div
              key={m.label}
              style={{
                position: "absolute",
                left: pct(m.val),
                top: topOffset,
                transform: "translateX(-50%)",
                textAlign: "center",
                whiteSpace: "nowrap",
              }}
            >
              <div style={{ fontSize: 10, fontWeight: 700, color: m.textColor, lineHeight: 1.2 }}>
                {m.label}
              </div>
              <div style={{ fontSize: 9, color: "#64748b", lineHeight: 1.2 }}>
                ₹{m.val.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
