"use client";
import { motion } from "framer-motion";
import useSWR from "swr";
import {
  getMarketOverview, getFiiHistory, getVixHistory, getSectorHeatmap,
  type MarketOverview, type FiiDiiPoint, type VixPoint, type SectorPoint,
} from "@/lib/api";

// ── Helpers ───────────────────────────────────────────────────────────────────
const sectorColor = (pct: number) => {
  if (pct >= 1.5)  return "#16a34a";
  if (pct >= 0.5)  return "#22c55e";
  if (pct >= 0)    return "#4ade80";
  if (pct >= -0.5) return "#f87171";
  if (pct >= -1.5) return "#ef4444";
  return "#b91c1c";
};

const sectorBg = (pct: number) => {
  if (pct >= 1.5)  return "rgba(22,163,74,0.25)";
  if (pct >= 0.5)  return "rgba(34,197,94,0.18)";
  if (pct >= 0)    return "rgba(74,222,128,0.10)";
  if (pct >= -0.5) return "rgba(248,113,113,0.10)";
  if (pct >= -1.5) return "rgba(239,68,68,0.18)";
  return "rgba(185,28,28,0.25)";
};

// ── Inline Bar Chart (no extra library) ──────────────────────────────────────
function FiiBarChart({ data }: { data: FiiDiiPoint[] }) {
  if (!data.length) return <div style={{ color: "#475569", textAlign: "center", padding: 40 }}>No data available</div>;

  const maxAbs = Math.max(...data.map(d => Math.max(Math.abs(d.fii_net), Math.abs(d.dii_net))), 1);
  const barW = Math.max(8, Math.floor(760 / (data.length * 2.2)));
  const chartH = 180;

  return (
    <div style={{ overflowX: "auto" }}>
      <svg width={Math.max(data.length * (barW * 2 + 4), 600)} height={chartH + 50} style={{ display: "block" }}>
        {/* Zero line */}
        <line x1={0} y1={chartH / 2} x2="100%" y2={chartH / 2} stroke="rgba(255,255,255,0.08)" strokeWidth={1} />

        {data.map((d, i) => {
          const x = i * (barW * 2 + 6);
          const fiiH = (Math.abs(d.fii_net) / maxAbs) * (chartH / 2 - 8);
          const diiH = (Math.abs(d.dii_net) / maxAbs) * (chartH / 2 - 8);
          const fiiY = d.fii_net >= 0 ? chartH / 2 - fiiH : chartH / 2;
          const diiY = d.dii_net >= 0 ? chartH / 2 - diiH : chartH / 2;
          // Show label every ~5 bars
          const showLabel = i % Math.max(1, Math.floor(data.length / 6)) === 0;
          const label = d.date.slice(5); // MM-DD
          return (
            <g key={d.date}>
              {/* FII bar */}
              <rect x={x} y={fiiY} width={barW} height={Math.max(fiiH, 1)}
                fill={d.fii_net >= 0 ? "#22c55e" : "#ef4444"} rx={2} opacity={0.85} />
              {/* DII bar */}
              <rect x={x + barW + 2} y={diiY} width={barW} height={Math.max(diiH, 1)}
                fill={d.dii_net >= 0 ? "#60a5fa" : "#f97316"} rx={2} opacity={0.85} />
              {showLabel && (
                <text x={x + barW} y={chartH + 18} textAnchor="middle" fontSize={9} fill="#475569">{label}</text>
              )}
            </g>
          );
        })}
      </svg>
      {/* Legend */}
      <div style={{ display: "flex", gap: 20, marginTop: 6, paddingLeft: 4 }}>
        {[
          { color: "#22c55e", label: "FII Net Buy" },
          { color: "#ef4444", label: "FII Net Sell" },
          { color: "#60a5fa", label: "DII Net Buy" },
          { color: "#f97316", label: "DII Net Sell" },
        ].map(({ color, label }) => (
          <div key={label} style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <div style={{ width: 10, height: 10, borderRadius: 2, background: color }} />
            <span style={{ fontSize: 10, color: "#64748b" }}>{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── VIX Line Chart ────────────────────────────────────────────────────────────
function VixLineChart({ data }: { data: VixPoint[] }) {
  if (!data.length) return <div style={{ color: "#475569", textAlign: "center", padding: 40 }}>No data available</div>;

  const chartW = 760;
  const chartH = 160;
  const minV = Math.min(...data.map(d => d.vix)) - 1;
  const maxV = Math.max(...data.map(d => d.vix)) + 1;
  const range = maxV - minV || 1;

  const toX = (i: number) => (i / (data.length - 1)) * chartW;
  const toY = (v: number) => chartH - ((v - minV) / range) * chartH;

  const points = data.map((d, i) => `${toX(i)},${toY(d.vix)}`).join(" ");
  const area = `${toX(0)},${chartH} ` + points + ` ${toX(data.length - 1)},${chartH}`;

  // Zone lines
  const y15 = toY(15);
  const y20 = toY(20);

  return (
    <div style={{ overflowX: "auto" }}>
      <svg width={chartW} height={chartH + 40} style={{ display: "block", width: "100%" }}>
        {/* Danger zones */}
        <rect x={0} y={0} width={chartW} height={y15} fill="rgba(34,197,94,0.04)" />
        <rect x={0} y={y15} width={chartW} height={y20 - y15} fill="rgba(245,158,11,0.04)" />
        <rect x={0} y={y20} width={chartW} height={chartH - y20} fill="rgba(239,68,68,0.06)" />

        {/* Zone labels */}
        <text x={chartW - 4} y={y15 - 3} textAnchor="end" fontSize={9} fill="#22c55e" opacity={0.7}>Low ≤15</text>
        <text x={chartW - 4} y={y20 - 3} textAnchor="end" fontSize={9} fill="#f59e0b" opacity={0.7}>Moderate ≤20</text>
        <text x={chartW - 4} y={chartH - 4} textAnchor="end" fontSize={9} fill="#ef4444" opacity={0.7}>High ≥20</text>

        {/* Zone boundary lines */}
        <line x1={0} y1={y15} x2={chartW} y2={y15} stroke="#22c55e" strokeWidth={0.5} strokeDasharray="4,4" opacity={0.4} />
        <line x1={0} y1={y20} x2={chartW} y2={y20} stroke="#f59e0b" strokeWidth={0.5} strokeDasharray="4,4" opacity={0.4} />

        {/* Area fill */}
        <polygon points={area} fill="url(#vixGrad)" opacity={0.3} />
        <defs>
          <linearGradient id="vixGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#f59e0b" />
            <stop offset="100%" stopColor="transparent" />
          </linearGradient>
        </defs>

        {/* Line */}
        <polyline points={points} fill="none" stroke="#f59e0b" strokeWidth={2} strokeLinejoin="round" />

        {/* Date labels */}
        {data.filter((_, i) => i % Math.max(1, Math.floor(data.length / 7)) === 0).map((d, _, arr) => {
          const idx = data.indexOf(d);
          return (
            <text key={d.date} x={toX(idx)} y={chartH + 18} textAnchor="middle" fontSize={9} fill="#475569">
              {d.date.slice(5)}
            </text>
          );
        })}

        {/* Current VIX label */}
        {data.length > 0 && (
          <text
            x={toX(data.length - 1)} y={toY(data[data.length - 1].vix) - 6}
            textAnchor="middle" fontSize={11} fontWeight="700"
            fill={data[data.length - 1].vix < 15 ? "#22c55e" : data[data.length - 1].vix < 20 ? "#f59e0b" : "#ef4444"}
          >
            {data[data.length - 1].vix.toFixed(1)}
          </text>
        )}
      </svg>
    </div>
  );
}

// ── Sector Heatmap ────────────────────────────────────────────────────────────
function SectorHeatmap({ data }: { data: SectorPoint[] }) {
  if (!data.length) return <div style={{ color: "#475569", textAlign: "center", padding: 40 }}>Loading sectors…</div>;

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
      {data.map((s, i) => (
        <motion.div
          key={s.sector}
          initial={{ opacity: 0, scale: 0.92 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: i * 0.05 }}
          style={{
            padding: "16px 14px",
            borderRadius: 14,
            background: sectorBg(s.change_pct),
            border: `1px solid ${sectorColor(s.change_pct)}30`,
            textAlign: "center",
          }}
        >
          <div style={{ fontSize: 13, fontWeight: 700, color: "#f1f5f9", marginBottom: 6 }}>
            {s.sector}
          </div>
          <div style={{
            fontSize: 22, fontWeight: 800,
            color: sectorColor(s.change_pct),
          }}>
            {s.change_pct >= 0 ? "▲" : "▼"} {Math.abs(s.change_pct).toFixed(2)}%
          </div>
          <div style={{ fontSize: 11, color: "#64748b", marginTop: 4 }}>
            ₹{s.price.toLocaleString("en-IN")}
          </div>
        </motion.div>
      ))}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function MarketPage() {
  const { data, isLoading }         = useSWR<MarketOverview>("market-overview", getMarketOverview, { refreshInterval: 60000 });
  const { data: fiiHistory = [] }   = useSWR<FiiDiiPoint[]>("fii-history", () => getFiiHistory(30), { revalidateOnFocus: false });
  const { data: vixHistory = [] }   = useSWR<VixPoint[]>("vix-history", () => getVixHistory(30), { revalidateOnFocus: false });
  const { data: sectors = [] }      = useSWR<SectorPoint[]>("sector-heatmap", getSectorHeatmap, { revalidateOnFocus: false });

  const fii     = data?.fii_dii;
  const vix     = data?.india_vix;
  const breadth = data?.market_breadth;
  const indices = data?.indices ?? {};

  return (
    <div style={{ maxWidth: 1200 }}>
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 24, fontWeight: 800, color: "#f1f5f9", margin: 0 }}>Market Intelligence</h1>
        <p style={{ fontSize: 13, color: "#475569", marginTop: 4 }}>
          Real-time FII/DII flows, volatility, sector performance and market breadth
        </p>
      </motion.div>

      {/* Row 1: Indices + VIX current */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 20 }}>
        {/* Indices */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }} className="glass-card p-6">
          <h2 style={{ fontSize: 12, fontWeight: 700, color: "#64748b", letterSpacing: "0.08em", marginBottom: 16 }}>INDICES</h2>
          {isLoading
            ? [...Array(3)].map((_, i) => <div key={i} className="shimmer mb-3" style={{ height: 52, borderRadius: 10 }} />)
            : Object.entries(indices).map(([name, info]) => (
                <div key={name} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 14px", borderRadius: 10, background: "rgba(255,255,255,0.04)", marginBottom: 8 }}>
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 700, color: "#94a3b8" }}>{name}</div>
                    <div style={{ fontSize: 20, fontWeight: 800, color: "#f1f5f9" }}>₹{info.price.toLocaleString("en-IN")}</div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontSize: 16, fontWeight: 700, color: info.change_pct >= 0 ? "#22c55e" : "#ef4444" }}>
                      {info.change_pct >= 0 ? "▲" : "▼"} {Math.abs(info.change_pct).toFixed(2)}%
                    </div>
                    <div style={{ fontSize: 11, color: "#475569" }}>H: ₹{info.high.toLocaleString("en-IN")} · L: ₹{info.low.toLocaleString("en-IN")}</div>
                  </div>
                </div>
              ))}
        </motion.div>

        {/* India VIX current */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="glass-card p-6">
          <h2 style={{ fontSize: 12, fontWeight: 700, color: "#64748b", letterSpacing: "0.08em", marginBottom: 16 }}>INDIA VIX — FEAR INDEX</h2>
          {isLoading || !vix ? (
            <div className="shimmer" style={{ height: 120, borderRadius: 12 }} />
          ) : (
            <>
              <div style={{ display: "flex", alignItems: "flex-end", gap: 16, marginBottom: 16 }}>
                <div style={{ fontSize: 56, fontWeight: 800, color: vix.vix < 15 ? "#22c55e" : vix.vix < 20 ? "#f59e0b" : "#ef4444", lineHeight: 1 }}>
                  {vix.vix.toFixed(2)}
                </div>
                <div style={{ paddingBottom: 8 }}>
                  <div style={{ display: "inline-block", padding: "4px 12px", borderRadius: 99, fontSize: 12, fontWeight: 700,
                    background: vix.vix < 15 ? "rgba(34,197,94,0.15)" : vix.vix < 20 ? "rgba(245,158,11,0.15)" : "rgba(239,68,68,0.15)",
                    color: vix.vix < 15 ? "#22c55e" : vix.vix < 20 ? "#f59e0b" : "#ef4444",
                  }}>
                    {vix.risk_level}
                  </div>
                </div>
              </div>
              <div style={{ marginBottom: 16 }}>
                <div style={{ height: 8, borderRadius: 99, background: "linear-gradient(90deg, #22c55e, #f59e0b, #ef4444)", position: "relative" }}>
                  <div style={{ position: "absolute", left: `${Math.min((vix.vix / 40) * 100, 100)}%`, top: "50%", transform: "translate(-50%, -50%)", width: 14, height: 14, borderRadius: "50%", background: "#fff", border: "2px solid #0d1225", boxShadow: "0 0 8px rgba(255,255,255,0.4)" }} />
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4, fontSize: 9, color: "#334155" }}>
                  <span>0 — Low Fear</span><span>20 — Medium</span><span>40 — High Fear</span>
                </div>
              </div>
              <p style={{ fontSize: 12, color: "#94a3b8", lineHeight: 1.6 }}>{vix.risk_comment}</p>
            </>
          )}
        </motion.div>
      </div>

      {/* Row 2: FII/DII today + Market Breadth */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 20 }}>
        {/* FII/DII today */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }} className="glass-card p-6">
          <h2 style={{ fontSize: 12, fontWeight: 700, color: "#64748b", letterSpacing: "0.08em", marginBottom: 16 }}>FII / DII FLOWS (TODAY)</h2>
          {isLoading || !fii ? (
            <div className="shimmer" style={{ height: 120, borderRadius: 12 }} />
          ) : (
            [{ label: "Foreign Institutional (FII)", val: fii.fii_net, icon: "🌍" }, { label: "Domestic Institutional (DII)", val: fii.dii_net, icon: "🏦" }]
              .map(({ label, val, icon }) => (
                <div key={label} style={{ marginBottom: 16 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                    <span style={{ fontSize: 12, color: "#64748b", fontWeight: 600 }}>{icon} {label}</span>
                    <span style={{ fontSize: 18, fontWeight: 800, color: val >= 0 ? "#22c55e" : "#ef4444" }}>
                      {val >= 0 ? "+" : ""}₹{Math.abs(val).toLocaleString("en-IN")} Cr
                    </span>
                  </div>
                  <div style={{ height: 6, borderRadius: 99, background: "rgba(255,255,255,0.06)", overflow: "hidden" }}>
                    <motion.div initial={{ width: 0 }} animate={{ width: `${Math.min(Math.abs(val) / 5000 * 100, 100)}%` }} transition={{ duration: 1, ease: "easeOut" }}
                      style={{ height: "100%", background: val >= 0 ? "#22c55e" : "#ef4444", borderRadius: 99 }} />
                  </div>
                  <div style={{ fontSize: 11, color: "#334155", marginTop: 4 }}>
                    {val > 1000 ? "Strong buyers — Bullish signal" : val > 0 ? "Mild buyers" : val < -1000 ? "Heavy sellers — Caution advised" : "Mild sellers"}
                  </div>
                </div>
              ))
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
                {[{ label: "Advances", val: breadth.advances, color: "#22c55e" }, { label: "Unchanged", val: breadth.unchanged, color: "#f59e0b" }, { label: "Declines", val: breadth.declines, color: "#ef4444" }]
                  .map(({ label, val, color }) => (
                    <div key={label} style={{ textAlign: "center", padding: "14px 10px", borderRadius: 12, background: "rgba(255,255,255,0.04)" }}>
                      <div style={{ fontSize: 28, fontWeight: 800, color }}>{val}</div>
                      <div style={{ fontSize: 11, color: "#475569", fontWeight: 600, marginTop: 4 }}>{label}</div>
                    </div>
                  ))}
              </div>
              <div style={{ height: 16, borderRadius: 99, overflow: "hidden", display: "flex" }}>
                <motion.div initial={{ flex: 0 }} animate={{ flex: breadth.advances }} transition={{ duration: 1 }} style={{ background: "#22c55e" }} />
                <motion.div initial={{ flex: 0 }} animate={{ flex: breadth.unchanged }} transition={{ duration: 1 }} style={{ background: "#f59e0b" }} />
                <motion.div initial={{ flex: 0 }} animate={{ flex: breadth.declines }} transition={{ duration: 1 }} style={{ background: "#ef4444" }} />
              </div>
              <div style={{ marginTop: 16, padding: "12px 14px", borderRadius: 10, background: "rgba(255,255,255,0.04)" }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: breadth.advances > breadth.declines ? "#22c55e" : "#ef4444" }}>
                  {breadth.advances > breadth.declines ? `▲ Positive Breadth — ${breadth.advances} advancing` : `▼ Negative Breadth — ${breadth.declines} declining`}
                </div>
                <div style={{ fontSize: 11, color: "#475569", marginTop: 4 }}>
                  A/D Ratio: {breadth.declines > 0 ? (breadth.advances / breadth.declines).toFixed(2) : "∞"}
                </div>
              </div>
            </>
          )}
        </motion.div>
      </div>

      {/* Row 3: FII/DII 30-day bar chart */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }} className="glass-card p-6" style={{ marginBottom: 20 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <h2 style={{ fontSize: 12, fontWeight: 700, color: "#64748b", letterSpacing: "0.08em", margin: 0 }}>FII / DII NET FLOW — 30 DAYS (₹ Crore)</h2>
          <span style={{ fontSize: 11, color: "#334155" }}>Green = FII · Blue = DII</span>
        </div>
        {fiiHistory.length === 0
          ? <div className="shimmer" style={{ height: 220, borderRadius: 10 }} />
          : <FiiBarChart data={fiiHistory} />}
      </motion.div>

      {/* Row 4: VIX 30-day chart */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }} className="glass-card p-6" style={{ marginBottom: 20 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <h2 style={{ fontSize: 12, fontWeight: 700, color: "#64748b", letterSpacing: "0.08em", margin: 0 }}>INDIA VIX — 30-DAY TREND</h2>
          <div style={{ display: "flex", gap: 12, fontSize: 10 }}>
            {[{ color: "#22c55e", label: "Low <15" }, { color: "#f59e0b", label: "Moderate 15–20" }, { color: "#ef4444", label: "High >20" }]
              .map(({ color, label }) => (
                <div key={label} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                  <div style={{ width: 8, height: 8, borderRadius: 2, background: color }} />
                  <span style={{ color: "#64748b" }}>{label}</span>
                </div>
              ))}
          </div>
        </div>
        {vixHistory.length === 0
          ? <div className="shimmer" style={{ height: 200, borderRadius: 10 }} />
          : <VixLineChart data={vixHistory} />}
      </motion.div>

      {/* Row 5: Sector Heatmap */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35 }} className="glass-card p-6">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
          <h2 style={{ fontSize: 12, fontWeight: 700, color: "#64748b", letterSpacing: "0.08em", margin: 0 }}>SECTOR HEATMAP — TODAY</h2>
          <div style={{ display: "flex", gap: 6, fontSize: 10 }}>
            {[
              { color: "#16a34a", label: ">+1.5%" },
              { color: "#22c55e", label: "+0.5–1.5%" },
              { color: "#4ade80", label: "0–+0.5%" },
              { color: "#f87171", label: "-0–0.5%" },
              { color: "#ef4444", label: "-0.5–1.5%" },
              { color: "#b91c1c", label: "<-1.5%" },
            ].map(({ color, label }) => (
              <div key={label} style={{ display: "flex", alignItems: "center", gap: 3 }}>
                <div style={{ width: 8, height: 8, borderRadius: 2, background: color }} />
                <span style={{ color: "#64748b" }}>{label}</span>
              </div>
            ))}
          </div>
        </div>
        {sectors.length === 0
          ? <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
              {[...Array(8)].map((_, i) => <div key={i} className="shimmer" style={{ height: 90, borderRadius: 14 }} />)}
            </div>
          : <SectorHeatmap data={sectors} />}
      </motion.div>
    </div>
  );
}
