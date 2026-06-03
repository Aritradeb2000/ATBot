"use client";
import { motion } from "framer-motion";
import useSWR from "swr";
import { getMarketOverview, type MarketOverview } from "@/lib/api";

export default function MarketPage() {
  const { data, isLoading } = useSWR<MarketOverview>("market-overview", getMarketOverview, { refreshInterval: 60000 });

  const fii = data?.fii_dii;
  const vix = data?.india_vix;
  const breadth = data?.market_breadth;
  const indices = data?.indices ?? {};

  return (
    <div style={{ maxWidth: 1100 }}>
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 800, color: "#f1f5f9", margin: 0 }}>Market Intelligence</h1>
        <p style={{ fontSize: 13, color: "#475569", marginTop: 4 }}>Real-time FII/DII flows, volatility, and market breadth</p>
      </motion.div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 20 }}>
        {/* Indices */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }} className="glass-card p-6">
          <h2 style={{ fontSize: 12, fontWeight: 700, color: "#64748b", letterSpacing: "0.08em", marginBottom: 16 }}>INDICES</h2>
          {isLoading ? (
            [...Array(3)].map((_, i) => <div key={i} className="shimmer mb-3" style={{ height: 52, borderRadius: 10 }} />)
          ) : (
            Object.entries(indices).map(([name, info]) => (
              <div key={name} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 14px", borderRadius: 10, background: "rgba(255,255,255,0.04)", marginBottom: 8 }}>
                <div>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "#94a3b8" }}>{name}</div>
                  <div style={{ fontSize: 20, fontWeight: 800, color: "#f1f5f9" }}>
                    ₹{info.price.toLocaleString("en-IN")}
                  </div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontSize: 16, fontWeight: 700, color: info.change_pct >= 0 ? "#22c55e" : "#ef4444" }}>
                    {info.change_pct >= 0 ? "▲" : "▼"} {Math.abs(info.change_pct).toFixed(2)}%
                  </div>
                  <div style={{ fontSize: 11, color: "#475569" }}>H: ₹{info.high.toLocaleString("en-IN")} · L: ₹{info.low.toLocaleString("en-IN")}</div>
                </div>
              </div>
            ))
          )}
        </motion.div>

        {/* India VIX */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="glass-card p-6">
          <h2 style={{ fontSize: 12, fontWeight: 700, color: "#64748b", letterSpacing: "0.08em", marginBottom: 16 }}>INDIA VIX — FEAR INDEX</h2>
          {isLoading || !vix ? (
            <div className="shimmer" style={{ height: 120, borderRadius: 12 }} />
          ) : (
            <>
              <div style={{ display: "flex", alignItems: "flex-end", gap: 16, marginBottom: 16 }}>
                <div style={{ fontSize: 56, fontWeight: 800, color: vix.vix < 14 ? "#22c55e" : vix.vix < 20 ? "#f59e0b" : "#ef4444", lineHeight: 1 }}>
                  {vix.vix.toFixed(2)}
                </div>
                <div style={{ paddingBottom: 8 }}>
                  <div style={{
                    display: "inline-block",
                    padding: "4px 12px",
                    borderRadius: 99,
                    fontSize: 12,
                    fontWeight: 700,
                    background: vix.vix < 14 ? "rgba(34,197,94,0.15)" : vix.vix < 20 ? "rgba(245,158,11,0.15)" : "rgba(239,68,68,0.15)",
                    color: vix.vix < 14 ? "#22c55e" : vix.vix < 20 ? "#f59e0b" : "#ef4444",
                  }}>
                    {vix.risk_level}
                  </div>
                </div>
              </div>

              {/* VIX gauge bar */}
              <div style={{ marginBottom: 16 }}>
                <div style={{ height: 8, borderRadius: 99, background: "linear-gradient(90deg, #22c55e, #f59e0b, #ef4444)", position: "relative" }}>
                  <div style={{
                    position: "absolute",
                    left: `${Math.min((vix.vix / 40) * 100, 100)}%`,
                    top: "50%",
                    transform: "translate(-50%, -50%)",
                    width: 14, height: 14,
                    borderRadius: "50%",
                    background: "#fff",
                    border: "2px solid #0d1225",
                    boxShadow: "0 0 8px rgba(255,255,255,0.4)",
                  }} />
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4, fontSize: 9, color: "#334155" }}>
                  <span>0 — Low Fear</span>
                  <span>20 — Medium</span>
                  <span>40 — High Fear</span>
                </div>
              </div>

              <p style={{ fontSize: 12, color: "#94a3b8", lineHeight: 1.6 }}>{vix.risk_comment}</p>
            </>
          )}
        </motion.div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
        {/* FII / DII */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }} className="glass-card p-6">
          <h2 style={{ fontSize: 12, fontWeight: 700, color: "#64748b", letterSpacing: "0.08em", marginBottom: 16 }}>FII / DII FLOWS (TODAY)</h2>
          {isLoading || !fii ? (
            <div className="shimmer" style={{ height: 120, borderRadius: 12 }} />
          ) : (
            <>
              {[
                { label: "Foreign Institutional (FII)", val: fii.fii_net, icon: "🌍" },
                { label: "Domestic Institutional (DII)", val: fii.dii_net, icon: "🏦" },
              ].map(({ label, val, icon }) => (
                <div key={label} style={{ marginBottom: 16 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                    <span style={{ fontSize: 12, color: "#64748b", fontWeight: 600 }}>{icon} {label}</span>
                    <span style={{ fontSize: 18, fontWeight: 800, color: val >= 0 ? "#22c55e" : "#ef4444" }}>
                      {val >= 0 ? "+" : ""}₹{Math.abs(val).toLocaleString("en-IN")} Cr
                    </span>
                  </div>
                  <div style={{ height: 6, borderRadius: 99, background: "rgba(255,255,255,0.06)", overflow: "hidden" }}>
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${Math.min(Math.abs(val) / 5000 * 100, 100)}%` }}
                      transition={{ duration: 1, ease: "easeOut" }}
                      style={{ height: "100%", background: val >= 0 ? "#22c55e" : "#ef4444", borderRadius: 99 }}
                    />
                  </div>
                  <div style={{ fontSize: 11, color: "#334155", marginTop: 4 }}>
                    {val > 1000 ? "Strong buyers — Bullish signal" : val > 0 ? "Mild buyers" : val < -1000 ? "Heavy sellers — Caution advised" : "Mild sellers"}
                  </div>
                </div>
              ))}
            </>
          )}
        </motion.div>

        {/* Market Breadth */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="glass-card p-6">
          <h2 style={{ fontSize: 12, fontWeight: 700, color: "#64748b", letterSpacing: "0.08em", marginBottom: 16 }}>MARKET BREADTH</h2>
          {isLoading || !breadth ? (
            <div className="shimmer" style={{ height: 120, borderRadius: 12 }} />
          ) : (
            <>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, marginBottom: 20 }}>
                {[
                  { label: "Advances", val: breadth.advances, color: "#22c55e" },
                  { label: "Unchanged", val: breadth.unchanged, color: "#f59e0b" },
                  { label: "Declines", val: breadth.declines, color: "#ef4444" },
                ].map(({ label, val, color }) => (
                  <div key={label} style={{ textAlign: "center", padding: "14px 10px", borderRadius: 12, background: "rgba(255,255,255,0.04)" }}>
                    <div style={{ fontSize: 28, fontWeight: 800, color }}>{val}</div>
                    <div style={{ fontSize: 11, color: "#475569", fontWeight: 600, marginTop: 4 }}>{label}</div>
                  </div>
                ))}
              </div>

              {/* Breadth bar */}
              <div style={{ height: 16, borderRadius: 99, overflow: "hidden", display: "flex" }}>
                <motion.div initial={{ flex: 0 }} animate={{ flex: breadth.advances }} transition={{ duration: 1 }} style={{ background: "#22c55e" }} />
                <motion.div initial={{ flex: 0 }} animate={{ flex: breadth.unchanged }} transition={{ duration: 1 }} style={{ background: "#f59e0b" }} />
                <motion.div initial={{ flex: 0 }} animate={{ flex: breadth.declines }} transition={{ duration: 1 }} style={{ background: "#ef4444" }} />
              </div>

              <div style={{ marginTop: 16, padding: "12px 14px", borderRadius: 10, background: "rgba(255,255,255,0.04)" }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: breadth.advances > breadth.declines ? "#22c55e" : "#ef4444" }}>
                  {breadth.advances > breadth.declines
                    ? `▲ Positive Breadth — ${breadth.advances} stocks advancing`
                    : `▼ Negative Breadth — ${breadth.declines} stocks declining`}
                </div>
                <div style={{ fontSize: 11, color: "#475569", marginTop: 4 }}>
                  Advance/Decline Ratio: {breadth.declines > 0 ? (breadth.advances / breadth.declines).toFixed(2) : "∞"}
                </div>
              </div>
            </>
          )}
        </motion.div>
      </div>
    </div>
  );
}
