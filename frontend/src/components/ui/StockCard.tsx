"use client";
import { motion } from "framer-motion";
import Link from "next/link";
import SignalBadge from "./SignalBadge";
import type { Analysis } from "@/lib/api";

interface Props {
  symbol: string;
  companyName: string;
  price: number | null;
  analysis: Analysis;
  index?: number;
}

export default function StockCard({ symbol, companyName, price, analysis, index = 0 }: Props) {
  const score = analysis.composite_score;
  const regime = analysis.regime;
  const regimeColor = regime === "BULL" ? "#22c55e" : regime === "BEAR" ? "#ef4444" : "#f59e0b";

  const ticker = symbol.replace(".NS", "").replace(".BO", "");

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05, duration: 0.3 }}
      whileHover={{ y: -3, transition: { duration: 0.15 } }}
    >
      <Link href={`/stock/${encodeURIComponent(symbol)}`}>
        <div className="glass-card p-4 cursor-pointer group" style={{ minHeight: 160 }}>
          {/* Header row */}
          <div className="flex items-start justify-between mb-3">
            <div>
              <div className="flex items-center gap-2">
                <span style={{ fontSize: 16, fontWeight: 700, color: "#f1f5f9" }}>{ticker}</span>
                <span
                  className="metric-chip"
                  style={{ color: regimeColor, borderColor: regimeColor + "40", background: regimeColor + "15" }}
                >
                  {regime}
                </span>
              </div>
              <p style={{ fontSize: 11, color: "#64748b", marginTop: 2 }} className="truncate max-w-[160px]">
                {companyName}
              </p>
            </div>

            {/* Composite score circle */}
            <div
              style={{
                width: 44,
                height: 44,
                borderRadius: "50%",
                background: score >= 70 ? "rgba(34,197,94,0.15)" : score >= 50 ? "rgba(245,158,11,0.15)" : "rgba(239,68,68,0.15)",
                border: `2px solid ${score >= 70 ? "#22c55e" : score >= 50 ? "#f59e0b" : "#ef4444"}`,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
              }}
            >
              <span style={{ fontSize: 13, fontWeight: 700, color: score >= 70 ? "#22c55e" : score >= 50 ? "#f59e0b" : "#ef4444" }}>
                {Math.round(score)}
              </span>
            </div>
          </div>

          {/* Price */}
          <div className="mb-3">
            {price ? (
              <span style={{ fontSize: 22, fontWeight: 700, color: "#f1f5f9" }}>
                ₹{price.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
              </span>
            ) : (
              <span style={{ fontSize: 14, color: "#475569" }}>Price unavailable</span>
            )}
          </div>

          {/* Signal badge */}
          <SignalBadge signal={analysis.signal} confidence={analysis.confidence} size="sm" />

          {/* Engine scores bar */}
          <div className="flex gap-1 mt-3">
            {[
              { label: "T", val: analysis.components.technical },
              { label: "F", val: analysis.components.fundamental },
              { label: "S", val: analysis.components.sentiment },
            ].map(({ label, val }) => (
              <div key={label} className="flex-1">
                <div style={{ fontSize: 9, color: "#475569", textAlign: "center", marginBottom: 2 }}>{label}</div>
                <div style={{ height: 3, borderRadius: 99, background: "rgba(255,255,255,0.06)" }}>
                  <div
                    style={{
                      height: "100%",
                      width: `${val}%`,
                      borderRadius: 99,
                      background: val >= 70 ? "#22c55e" : val >= 50 ? "#f59e0b" : "#ef4444",
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      </Link>
    </motion.div>
  );
}
