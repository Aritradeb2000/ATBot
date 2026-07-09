"use client";
import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { runOptimizer, type OptimizerResult, type OptimizerAllocation } from "@/lib/api";

// ── Helpers ────────────────────────────────────────────────────────────────

const fmt = (n: number) =>
  "₹" + n.toLocaleString("en-IN", { maximumFractionDigits: 0 });

const pct = (n: number | null) =>
  n !== null && n !== undefined ? `${n >= 0 ? "+" : ""}${n.toFixed(2)}%` : "—";

const signalColor = (s: string) => {
  const u = s?.toUpperCase() ?? "";
  if (u.includes("STRONG BUY"))  return "#22c55e";
  if (u.includes("BUY"))         return "#4ade80";
  if (u.includes("STRONG SELL")) return "#ef4444";
  if (u.includes("SELL"))        return "#f87171";
  return "#f59e0b";
};

// ── Sub-components ─────────────────────────────────────────────────────────

function KpiCard({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div style={{
      background: "rgba(255,255,255,0.04)",
      border: "1px solid rgba(255,255,255,0.08)",
      borderRadius: 12,
      padding: "16px 20px",
      flex: 1,
      minWidth: 140,
    }}>
      <div style={{ fontSize: 10, color: "#475569", fontWeight: 700, letterSpacing: "0.08em", marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 800, color: color || "#f1f5f9" }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: "#64748b", marginTop: 3 }}>{sub}</div>}
    </div>
  );
}

function DonutChart({ allocations, remaining, total }: { allocations: OptimizerAllocation[]; remaining: number; total: number }) {
  const COLORS = ["#6366f1", "#3b82f6", "#06b6d4", "#8b5cf6", "#f59e0b", "#10b981", "#ef4444", "#f97316"];
  const segments: { label: string; value: number; color: string }[] = [
    ...allocations.map((a, i) => ({
      label: a.symbol.replace(".NS", ""),
      value: a.invested,
      color: COLORS[i % COLORS.length],
    })),
    { label: "Cash", value: remaining, color: "rgba(255,255,255,0.1)" },
  ];

  const size = 180;
  const cx = size / 2;
  const cy = size / 2;
  const r = 70;
  const strokeWidth = 28;

  let offset = 0;
  const circumference = 2 * Math.PI * r;

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 28 }}>
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
        {segments.map((seg, i) => {
          const dashArray = (seg.value / total) * circumference;
          const dashOffset = -offset * circumference / total;
          offset += seg.value;
          return (
            <circle
              key={i}
              cx={cx} cy={cy} r={r}
              fill="none"
              stroke={seg.color}
              strokeWidth={strokeWidth}
              strokeDasharray={`${dashArray} ${circumference - dashArray}`}
              strokeDashoffset={dashOffset}
              style={{ transition: "stroke-dasharray 0.5s ease" }}
            />
          );
        })}
      </svg>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {segments.map((seg, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ width: 10, height: 10, borderRadius: "50%", background: seg.color, flexShrink: 0 }} />
            <span style={{ fontSize: 11, color: "#94a3b8" }}>{seg.label}</span>
            <span style={{ fontSize: 11, color: "#64748b", marginLeft: "auto" }}>
              {((seg.value / total) * 100).toFixed(1)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function AllocationRow({ a, rank }: { a: OptimizerAllocation; rank: number }) {
  const [hovered, setHovered] = useState(false);
  return (
    <motion.tr
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: rank * 0.06 }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{ background: hovered ? "rgba(255,255,255,0.03)" : "transparent", cursor: "pointer" }}
      onClick={() => window.open(`/stock/${a.symbol}`, "_blank")}
    >
      <td style={td}>{rank}</td>
      <td style={td}>
        <div style={{ fontWeight: 700, color: "#f1f5f9", fontSize: 13 }}>{a.symbol.replace(".NS", "")}</div>
        <div style={{ fontSize: 10, color: "#475569", marginTop: 1 }}>{a.company_name}</div>
      </td>
      <td style={{ ...td, textAlign: "center" }}>
        <span style={{ fontSize: 10, fontWeight: 700, color: signalColor(a.signal), background: signalColor(a.signal) + "18", padding: "3px 8px", borderRadius: 6, border: `1px solid ${signalColor(a.signal)}30` }}>
          {a.signal}
        </span>
      </td>
      <td style={{ ...td, textAlign: "right" }}>{a.qty}</td>
      <td style={{ ...td, textAlign: "right" }}>{fmt(a.price)}</td>
      <td style={{ ...td, textAlign: "right", fontWeight: 700, color: "#f1f5f9" }}>{fmt(a.invested)}</td>
      <td style={{ ...td, textAlign: "right", color: "#22c55e", fontWeight: 700 }}>
        {a.target_base ? fmt(a.target_base) : "—"}
        {a.gain_pct !== null && (
          <div style={{ fontSize: 10, color: "#4ade80" }}>{pct(a.gain_pct)}</div>
        )}
      </td>
      <td style={{ ...td, textAlign: "right", color: "#ef4444" }}>
        {a.stop_loss ? fmt(a.stop_loss) : "—"}
        <div style={{ fontSize: 10, color: "#f87171" }}>−{fmt(a.sl_risk)}</div>
      </td>
      <td style={{ ...td, textAlign: "right" }}>
        <span style={{ color: a.rr_ratio && a.rr_ratio >= 2 ? "#22c55e" : "#f59e0b", fontWeight: 700 }}>
          {a.rr_ratio ? `1 : ${a.rr_ratio}` : "—"}
        </span>
      </td>
      <td style={{ ...td, textAlign: "right", color: "#818cf8" }}>{a.score}</td>
      <td style={{ ...td, textAlign: "right", color: "#64748b" }}>{a.confidence}%</td>
    </motion.tr>
  );
}

const td: React.CSSProperties = {
  padding: "12px 14px",
  fontSize: 12,
  color: "#94a3b8",
  borderBottom: "1px solid rgba(255,255,255,0.04)",
  verticalAlign: "middle",
};

const th: React.CSSProperties = {
  padding: "10px 14px",
  fontSize: 10,
  fontWeight: 700,
  color: "#475569",
  letterSpacing: "0.08em",
  textAlign: "right" as const,
  borderBottom: "1px solid rgba(255,255,255,0.08)",
  background: "rgba(0,0,0,0.3)",
};

// ── Loading Phrases ────────────────────────────────────────────────────────

const LOADING_PHRASES = [
  "Scanning Nifty 50 universe…",
  "Running technical analysis…",
  "Checking fundamentals…",
  "Reading FII/DII flows…",
  "Analysing sentiment…",
  "Computing composite scores…",
  "Applying risk constraints…",
  "Optimising capital allocation…",
  "Almost done…",
];

function LoadingState() {
  const [phraseIdx, setPhraseIdx] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setPhraseIdx(p => Math.min(p + 1, LOADING_PHRASES.length - 1)), 8000);
    return () => clearInterval(id);
  }, []);

  return (
    <div style={{ textAlign: "center", padding: "80px 0" }}>
      <motion.div
        animate={{ rotate: 360 }}
        transition={{ repeat: Infinity, duration: 2, ease: "linear" }}
        style={{ fontSize: 48, marginBottom: 24, display: "inline-block" }}
      >
        ⚙️
      </motion.div>
      <div style={{ fontSize: 16, fontWeight: 700, color: "#f1f5f9", marginBottom: 8 }}>
        Optimizing your portfolio…
      </div>
      <AnimatePresence mode="wait">
        <motion.div
          key={phraseIdx}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -6 }}
          style={{ fontSize: 13, color: "#6366f1" }}
        >
          {LOADING_PHRASES[phraseIdx]}
        </motion.div>
      </AnimatePresence>
      <div style={{ marginTop: 24, fontSize: 11, color: "#334155" }}>
        This takes 60–120 seconds for Nifty 50 (50 stocks in parallel)
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────

export default function OptimizerPage() {
  const [amount, setAmount]         = useState<string>("100000");
  const [universe, setUniverse]     = useState<"nifty50" | "watchlist">("nifty50");
  const [riskProfile, setRisk]      = useState<"conservative" | "moderate" | "aggressive">("moderate");
  const [maxStocks, setMaxStocks]   = useState<number>(5);
  const [loading, setLoading]       = useState(false);
  const [result, setResult]         = useState<OptimizerResult | null>(null);
  const [error, setError]           = useState<string | null>(null);
  const [watchlistSymbols, setWLS]  = useState<string[]>([]);

  useEffect(() => {
    try {
      const stored = localStorage.getItem("atbot_watchlist");
      if (stored) setWLS(JSON.parse(stored));
    } catch { /* no-op */ }
  }, []);

  const handleRun = async () => {
    const amt = parseFloat(amount.replace(/,/g, ""));
    if (isNaN(amt) || amt < 10000) {
      setError("Please enter a valid amount (minimum ₹10,000).");
      return;
    }
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      const res = await runOptimizer({
        amount: amt,
        universe,
        watchlist_symbols: universe === "watchlist" ? watchlistSymbols : undefined,
        risk_profile: riskProfile,
        max_stocks: maxStocks,
      });
      setResult(res);
    } catch (e: unknown) {
      setError("Optimizer failed. Please try again.");
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const RISK_PROFILES = [
    { id: "conservative", label: "🛡 Conservative", desc: "STRONG BUY only · Max 15% per stock · Min R:R 2.0" },
    { id: "moderate",     label: "⚖️ Moderate",     desc: "BUY + STRONG BUY · Max 25% per stock · Min R:R 1.5" },
    { id: "aggressive",   label: "🚀 Aggressive",   desc: "BUY + HOLD too · Max 35% per stock · Min R:R 1.0" },
  ] as const;

  return (
    <div style={{ maxWidth: 1200 }}>
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 24, fontWeight: 800, color: "#f1f5f9", margin: 0 }}>Portfolio Optimizer</h1>
        <p style={{ fontSize: 13, color: "#475569", marginTop: 4 }}>
          Input your capital → ATBot scans the market and returns an optimal allocation plan
        </p>
      </motion.div>

      {/* Input Panel */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-card"
        style={{ padding: "24px 28px", marginBottom: 24 }}
      >
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 28, alignItems: "start" }}>
          {/* Capital input */}
          <div>
            <label style={{ fontSize: 11, fontWeight: 700, color: "#475569", letterSpacing: "0.08em", display: "block", marginBottom: 8 }}>
              INVESTMENT AMOUNT (₹)
            </label>
            <div style={{ position: "relative" }}>
              <span style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)", color: "#64748b", fontSize: 16, fontWeight: 700 }}>₹</span>
              <input
                id="optimizer-amount"
                type="number"
                value={amount}
                onChange={e => setAmount(e.target.value)}
                placeholder="100000"
                min={10000}
                style={{
                  width: "100%", padding: "12px 14px 12px 32px", boxSizing: "border-box",
                  borderRadius: 10, border: "1px solid rgba(255,255,255,0.1)",
                  background: "rgba(255,255,255,0.05)", color: "#f1f5f9", fontSize: 16, fontWeight: 700, outline: "none",
                }}
              />
            </div>
            <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
              {[50000, 100000, 200000, 500000].map(v => (
                <button key={v} onClick={() => setAmount(String(v))}
                  style={{ padding: "3px 10px", borderRadius: 6, fontSize: 10, fontWeight: 700, border: "1px solid rgba(255,255,255,0.1)", background: amount === String(v) ? "rgba(99,102,241,0.2)" : "rgba(255,255,255,0.03)", color: amount === String(v) ? "#818cf8" : "#475569", cursor: "pointer" }}>
                  {(v / 1000).toFixed(0)}K
                </button>
              ))}
            </div>
          </div>

          {/* Universe + Max stocks */}
          <div>
            <label style={{ fontSize: 11, fontWeight: 700, color: "#475569", letterSpacing: "0.08em", display: "block", marginBottom: 8 }}>
              STOCK UNIVERSE
            </label>
            <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
              {[{ id: "nifty50", label: "Nifty 50" }, { id: "watchlist", label: "My Watchlist" }].map(u => (
                <button key={u.id} onClick={() => setUniverse(u.id as "nifty50" | "watchlist")}
                  style={{ flex: 1, padding: "9px 12px", borderRadius: 9, fontSize: 12, fontWeight: 700, border: "1px solid " + (universe === u.id ? "rgba(99,102,241,0.5)" : "rgba(255,255,255,0.08)"), background: universe === u.id ? "rgba(99,102,241,0.15)" : "rgba(255,255,255,0.03)", color: universe === u.id ? "#818cf8" : "#64748b", cursor: "pointer" }}>
                  {u.label}
                </button>
              ))}
            </div>
            <label style={{ fontSize: 11, fontWeight: 700, color: "#475569", letterSpacing: "0.08em", display: "block", marginBottom: 8 }}>
              MAX STOCKS: {maxStocks}
            </label>
            <input type="range" min={2} max={10} value={maxStocks} onChange={e => setMaxStocks(Number(e.target.value))}
              style={{ width: "100%", accentColor: "#6366f1" }} />
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "#334155" }}>
              <span>2</span><span>10</span>
            </div>
          </div>

          {/* Risk Profile */}
          <div>
            <label style={{ fontSize: 11, fontWeight: 700, color: "#475569", letterSpacing: "0.08em", display: "block", marginBottom: 8 }}>
              RISK PROFILE
            </label>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {RISK_PROFILES.map(p => (
                <button key={p.id} onClick={() => setRisk(p.id)}
                  style={{ padding: "10px 14px", borderRadius: 9, fontSize: 12, fontWeight: 700, textAlign: "left", border: "1px solid " + (riskProfile === p.id ? "rgba(99,102,241,0.5)" : "rgba(255,255,255,0.07)"), background: riskProfile === p.id ? "rgba(99,102,241,0.12)" : "rgba(255,255,255,0.02)", color: riskProfile === p.id ? "#c7d2fe" : "#64748b", cursor: "pointer" }}>
                  <div>{p.label}</div>
                  <div style={{ fontSize: 9, fontWeight: 400, color: riskProfile === p.id ? "#818cf8" : "#334155", marginTop: 2 }}>{p.desc}</div>
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div style={{ marginTop: 16, padding: "10px 14px", borderRadius: 8, background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)", color: "#f87171", fontSize: 12 }}>
            {error}
          </div>
        )}

        {/* Run button */}
        <div style={{ marginTop: 24, display: "flex", justifyContent: "flex-end" }}>
          <motion.button
            id="optimizer-run-btn"
            onClick={handleRun}
            disabled={loading}
            whileHover={{ scale: loading ? 1 : 1.02 }}
            whileTap={{ scale: loading ? 1 : 0.98 }}
            style={{
              padding: "12px 36px", borderRadius: 12, fontSize: 14, fontWeight: 800,
              background: loading ? "rgba(99,102,241,0.3)" : "linear-gradient(135deg, #6366f1, #3b82f6)",
              border: "none", color: "#fff", cursor: loading ? "not-allowed" : "pointer",
              boxShadow: loading ? "none" : "0 4px 20px rgba(99,102,241,0.4)",
            }}
          >
            {loading ? "⚙️ Optimizing…" : "▶ Run Optimizer"}
          </motion.button>
        </div>
      </motion.div>

      {/* Loading State */}
      {loading && (
        <div className="glass-card" style={{ padding: 32 }}>
          <LoadingState />
        </div>
      )}

      {/* Results */}
      <AnimatePresence>
        {result && !loading && (
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            {result.status === "insufficient_signals" ? (
              <div className="glass-card" style={{ padding: "48px 32px", textAlign: "center" }}>
                <div style={{ fontSize: 40, marginBottom: 16 }}>🔍</div>
                <div style={{ fontSize: 16, fontWeight: 700, color: "#f1f5f9", marginBottom: 8 }}>
                  Not Enough Strong Signals
                </div>
                <div style={{ fontSize: 13, color: "#64748b", maxWidth: 420, margin: "0 auto" }}>
                  {result.message || "Try switching to Aggressive profile or broadening your universe."}
                </div>
                <div style={{ marginTop: 12, fontSize: 11, color: "#334155" }}>
                  Scanned {result.scanned} stocks · {result.qualified} qualified
                </div>
              </div>
            ) : (
              <>
                {/* KPI Summary */}
                <div style={{ display: "flex", gap: 12, marginBottom: 20, flexWrap: "wrap" }}>
                  <KpiCard label="TOTAL INVESTMENT"  value={fmt(result.total_investment)} />
                  <KpiCard label="DEPLOYED"          value={fmt(result.deployed)} sub={`${((result.deployed / result.total_investment) * 100).toFixed(1)}% of capital`} />
                  <KpiCard label="REMAINING CASH"    value={fmt(result.remaining_cash)} color="#94a3b8" />
                  <KpiCard label="EXPECTED GAIN"     value={fmt(result.expected_gain)} sub={pct(result.expected_gain_pct)} color="#22c55e" />
                  <KpiCard label="MAX PORTFOLIO RISK" value={fmt(result.max_portfolio_risk)} sub={pct(result.max_portfolio_risk_pct)} color="#ef4444" />
                </div>

                {/* Donut + Table */}
                <div className="glass-card" style={{ padding: "24px 0", marginBottom: 20 }}>
                  {/* Chart + Stats row */}
                  <div style={{ display: "flex", gap: 32, alignItems: "center", padding: "0 28px 20px", borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                    <DonutChart allocations={result.allocations} remaining={result.remaining_cash} total={result.total_investment} />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 11, color: "#475569", fontWeight: 700, letterSpacing: "0.08em", marginBottom: 10 }}>SCAN SUMMARY</div>
                      <div style={{ display: "flex", gap: 20 }}>
                        <div><div style={{ fontSize: 22, fontWeight: 800, color: "#f1f5f9" }}>{result.scanned}</div><div style={{ fontSize: 10, color: "#475569" }}>Stocks Scanned</div></div>
                        <div><div style={{ fontSize: 22, fontWeight: 800, color: "#6366f1" }}>{result.qualified}</div><div style={{ fontSize: 10, color: "#475569" }}>Qualified</div></div>
                        <div><div style={{ fontSize: 22, fontWeight: 800, color: "#22c55e" }}>{result.allocations.length}</div><div style={{ fontSize: 10, color: "#475569" }}>Allocated</div></div>
                        <div><div style={{ fontSize: 14, fontWeight: 700, color: "#f1f5f9", textTransform: "capitalize" }}>{result.risk_profile}</div><div style={{ fontSize: 10, color: "#475569" }}>Risk Profile</div></div>
                      </div>
                    </div>
                    <button
                      onClick={handleRun}
                      style={{ padding: "9px 20px", borderRadius: 9, fontSize: 12, fontWeight: 700, background: "rgba(99,102,241,0.15)", border: "1px solid rgba(99,102,241,0.3)", color: "#818cf8", cursor: "pointer" }}
                    >
                      🔄 Refresh Plan
                    </button>
                  </div>

                  {/* Table */}
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse" }}>
                      <thead>
                        <tr>
                          <th style={{ ...th, textAlign: "left" }}>#</th>
                          <th style={{ ...th, textAlign: "left" }}>STOCK</th>
                          <th style={th}>SIGNAL</th>
                          <th style={th}>QTY</th>
                          <th style={th}>PRICE</th>
                          <th style={th}>INVESTED</th>
                          <th style={th}>TARGET</th>
                          <th style={th}>STOP LOSS</th>
                          <th style={th}>R:R</th>
                          <th style={th}>SCORE</th>
                          <th style={th}>CONF.</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.allocations.map((a, i) => (
                          <AllocationRow key={a.symbol} a={a} rank={i + 1} />
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Disclaimer */}
                <div style={{ padding: "12px 16px", borderRadius: 10, background: "rgba(245,158,11,0.05)", border: "1px solid rgba(245,158,11,0.1)", fontSize: 11, color: "#78716c", lineHeight: 1.6 }}>
                  ⚠️ <strong style={{ color: "#92400e" }}>Disclaimer:</strong> This is an AI-generated suggestion based on technical, fundamental, and sentiment signals. Prices are indicative (previous close). This is not financial advice. Always do your own research before investing.
                </div>
              </>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
