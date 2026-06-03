"use client";
import { useState } from "react";
import { motion } from "framer-motion";
import useSWR from "swr";
import SignalBadge from "@/components/ui/SignalBadge";
import { analyzeStock, type AnalysisResult } from "@/lib/api";
import Link from "next/link";

const NIFTY50 = [
  "RELIANCE.NS","TCS.NS","HDFCBANK.NS","INFY.NS","ICICIBANK.NS",
  "HINDUNILVR.NS","ITC.NS","SBIN.NS","KOTAKBANK.NS","AXISBANK.NS",
  "LT.NS","WIPRO.NS","ONGC.NS","MARUTI.NS","NTPC.NS",
  "POWERGRID.NS","TITAN.NS","BAJFINANCE.NS","HCLTECH.NS","TECHM.NS",
];

type SignalFilter = "ALL" | "STRONG BUY" | "BUY" | "HOLD" | "SELL" | "STRONG SELL";

function useScreener(symbols: string[]) {
  return useSWR<AnalysisResult[]>(
    ["screener", symbols.join(",")],
    () => Promise.all(symbols.map((s) => analyzeStock(s).catch(() => null as unknown as AnalysisResult))),
    { revalidateOnFocus: false, dedupingInterval: 600000 }
  );
}

export default function ScreenerPage() {
  const [signalFilter, setSignalFilter] = useState<SignalFilter>("ALL");
  const [minScore, setMinScore] = useState(0);
  const [minRsi, setMinRsi] = useState(0);
  const [maxRsi, setMaxRsi] = useState(100);
  const [sortBy, setSortBy] = useState<"score" | "rsi" | "symbol">("score");
  const [preset, setPreset] = useState<"custom" | "breakout" | "reversal">("custom");

  const { data, isLoading } = useScreener(NIFTY50);

  const results = (data?.filter(Boolean) ?? [])
    .filter((r) => {
      if (signalFilter !== "ALL" && r.analysis.signal !== signalFilter) return false;
      if (r.analysis.composite_score < minScore) return false;
      const rsi = r.details.technical.rsi;
      if (rsi != null && (rsi < minRsi || rsi > maxRsi)) return false;

      // Presets
      if (preset === "breakout") {
        const sigs = r.details.technical.signals;
        return (
          (r.analysis.signal === "BUY" || r.analysis.signal === "STRONG BUY") &&
          sigs.some((s) => s.includes("Volume") || s.includes("Supertrend") || s.includes("MACD Bullish"))
        );
      }
      if (preset === "reversal") {
        const rsiVal = r.details.technical.rsi ?? 50;
        return rsiVal < 35 && (r.analysis.signal === "BUY" || r.analysis.signal === "STRONG BUY");
      }
      return true;
    })
    .sort((a, b) => {
      if (sortBy === "score") return b.analysis.composite_score - a.analysis.composite_score;
      if (sortBy === "rsi") return (a.details.technical.rsi ?? 0) - (b.details.technical.rsi ?? 0);
      return a.symbol.localeCompare(b.symbol);
    });

  return (
    <div style={{ maxWidth: 1200 }}>
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 800, color: "#f1f5f9", margin: 0 }}>Screener</h1>
        <p style={{ fontSize: 13, color: "#475569", marginTop: 4 }}>Filter and rank NSE stocks by AI composite score</p>
      </motion.div>

      {/* Preset strategies */}
      <div style={{ display: "flex", gap: 10, marginBottom: 20 }}>
        {[
          { id: "custom" as const,   icon: "⊙", label: "Custom Filters" },
          { id: "breakout" as const, icon: "🚀", label: "Breakout Setups" },
          { id: "reversal" as const, icon: "🔄", label: "Reversal Candidates" },
        ].map((p) => (
          <button
            key={p.id}
            onClick={() => setPreset(p.id)}
            style={{
              padding: "8px 18px",
              borderRadius: 10,
              background: preset === p.id ? "rgba(59,130,246,0.15)" : "rgba(255,255,255,0.04)",
              border: preset === p.id ? "1px solid rgba(59,130,246,0.4)" : "1px solid rgba(255,255,255,0.08)",
              color: preset === p.id ? "#60a5fa" : "#64748b",
              fontSize: 13,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            {p.icon} {p.label}
          </button>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "240px 1fr", gap: 20 }}>
        {/* Filters panel */}
        <div className="glass-card p-5 h-fit">
          <div style={{ fontSize: 12, fontWeight: 700, color: "#64748b", letterSpacing: "0.08em", marginBottom: 16 }}>FILTERS</div>

          {/* Signal */}
          <div style={{ marginBottom: 20 }}>
            <label style={{ fontSize: 11, color: "#475569", fontWeight: 600 }}>SIGNAL TYPE</label>
            <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 8 }}>
              {(["ALL","STRONG BUY","BUY","HOLD","SELL","STRONG SELL"] as SignalFilter[]).map((s) => (
                <button
                  key={s}
                  onClick={() => setSignalFilter(s)}
                  style={{
                    padding: "6px 12px",
                    borderRadius: 8,
                    textAlign: "left",
                    background: signalFilter === s ? "rgba(59,130,246,0.1)" : "transparent",
                    border: signalFilter === s ? "1px solid rgba(59,130,246,0.3)" : "1px solid transparent",
                    color: signalFilter === s ? "#60a5fa" : "#64748b",
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: "pointer",
                  }}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>

          {/* Min Score */}
          <div style={{ marginBottom: 20 }}>
            <label style={{ fontSize: 11, color: "#475569", fontWeight: 600 }}>MIN SCORE: {minScore}</label>
            <input
              type="range" min={0} max={90} value={minScore}
              onChange={(e) => setMinScore(+e.target.value)}
              style={{ width: "100%", marginTop: 8, accentColor: "#3b82f6" }}
            />
          </div>

          {/* RSI Range */}
          <div style={{ marginBottom: 20 }}>
            <label style={{ fontSize: 11, color: "#475569", fontWeight: 600 }}>RSI RANGE: {minRsi} – {maxRsi}</label>
            <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
              <input type="number" value={minRsi} min={0} max={100} onChange={(e) => setMinRsi(+e.target.value)}
                style={{ width: "100%", padding: "6px 10px", borderRadius: 8, background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", color: "#f1f5f9", fontSize: 12, outline: "none" }} />
              <input type="number" value={maxRsi} min={0} max={100} onChange={(e) => setMaxRsi(+e.target.value)}
                style={{ width: "100%", padding: "6px 10px", borderRadius: 8, background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", color: "#f1f5f9", fontSize: 12, outline: "none" }} />
            </div>
          </div>

          {/* Sort */}
          <div>
            <label style={{ fontSize: 11, color: "#475569", fontWeight: 600 }}>SORT BY</label>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
              style={{ width: "100%", marginTop: 8, padding: "8px 10px", borderRadius: 8, background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", color: "#f1f5f9", fontSize: 12, outline: "none" }}
            >
              <option value="score">Composite Score</option>
              <option value="rsi">RSI (Low→High)</option>
              <option value="symbol">Symbol A→Z</option>
            </select>
          </div>
        </div>

        {/* Results table */}
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
            <span style={{ fontSize: 13, color: "#475569" }}>
              {isLoading ? "Loading 20 stocks…" : `${results.length} results`}
            </span>
          </div>

          {isLoading ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {[...Array(8)].map((_, i) => <div key={i} className="shimmer" style={{ height: 60, borderRadius: 12 }} />)}
            </div>
          ) : results.length === 0 ? (
            <div className="glass-card p-8" style={{ textAlign: "center" }}>
              <div style={{ fontSize: 32, marginBottom: 10 }}>🔍</div>
              <p style={{ color: "#64748b", fontSize: 13 }}>No stocks match your current filters.</p>
            </div>
          ) : (
            <>
              {/* Table header */}
              <div style={{ display: "grid", gridTemplateColumns: "140px 1fr 80px 60px 60px 60px 100px", gap: 8, padding: "8px 16px", marginBottom: 4 }}>
                {["SYMBOL","COMPANY","SCORE","T","F","S","SIGNAL"].map((h) => (
                  <div key={h} style={{ fontSize: 10, fontWeight: 700, color: "#334155", letterSpacing: "0.08em" }}>{h}</div>
                ))}
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {results.map((r, i) => {
                  const ticker = r.symbol.replace(".NS","").replace(".BO","");
                  const score = r.analysis.composite_score;
                  return (
                    <motion.div
                      key={r.symbol}
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.03 }}
                    >
                      <Link href={`/stock/${encodeURIComponent(r.symbol)}`}>
                        <div className="glass-card"
                          style={{ display: "grid", gridTemplateColumns: "140px 1fr 80px 60px 60px 60px 100px", gap: 8, padding: "12px 16px", alignItems: "center", cursor: "pointer" }}
                          onMouseEnter={(e) => e.currentTarget.style.borderColor = "rgba(59,130,246,0.3)"}
                          onMouseLeave={(e) => e.currentTarget.style.borderColor = "rgba(255,255,255,0.08)"}
                        >
                          <div style={{ fontSize: 14, fontWeight: 700, color: "#f1f5f9" }}>{ticker}</div>
                          <div style={{ fontSize: 11, color: "#64748b" }} className="truncate">{r.company_name}</div>
                          <div style={{ fontSize: 15, fontWeight: 800, color: score >= 70 ? "#22c55e" : score >= 50 ? "#f59e0b" : "#ef4444" }}>{Math.round(score)}</div>
                          {[r.analysis.components.technical, r.analysis.components.fundamental, r.analysis.components.sentiment].map((s, j) => (
                            <div key={j} style={{ fontSize: 12, fontWeight: 600, color: s >= 70 ? "#22c55e" : s >= 50 ? "#f59e0b" : "#ef4444" }}>{Math.round(s)}</div>
                          ))}
                          <SignalBadge signal={r.analysis.signal} size="sm" />
                        </div>
                      </Link>
                    </motion.div>
                  );
                })}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
