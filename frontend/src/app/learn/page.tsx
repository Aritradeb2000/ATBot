"use client";
import { useState } from "react";
import { motion } from "framer-motion";
import useSWR from "swr";
import {
  getLearnStats, getRecentOutcomes, triggerOutcomeCheck,
  type LearnStats, type OutcomeRecord,
} from "@/lib/api";

// ── Meta-Learner v2 Types ─────────────────────────────────────────────────────
interface RegimeWeightInfo { T: number; F: number; S: number; samples: number; status: string; is_active: boolean; }
interface MetaWeightsV2 {
  version: string; source: string; status: string;
  current_regime: string; last_updated: string | null;
  total_samples: number; ewma: { lambda: number; half_life_days: number };
  min_samples_per_regime: number;
  regime_weights: { BULL: RegimeWeightInfo; BEAR: RegimeWeightInfo; SIDEWAYS: RegimeWeightInfo };
  global_weights: { T: number; F: number; S: number };
  message?: string;
}

// ── Meta-Learner v2 Card ──────────────────────────────────────────────────────
function MetaLearnerV2Card() {
  const { data: mw } = useSWR<MetaWeightsV2>(
    "meta-weights-v2",
    () => fetch("http://localhost:8000/api/learn/meta-weights").then(r => r.json()),
    { revalidateOnFocus: false, refreshInterval: 60000 }
  );

  const regimeColors: Record<string, string> = { BULL: "#22c55e", BEAR: "#ef4444", SIDEWAYS: "#f59e0b" };
  const regimeIcons: Record<string, string> = { BULL: "📈", BEAR: "📉", SIDEWAYS: "➡️" };
  const statusColor = (s: string) => s === "mature" ? "#22c55e" : s === "learning" ? "#f59e0b" : "#475569";
  const statusLabel = (s: string) => s === "mature" ? "Mature" : s === "learning" ? "Learning" : "Waiting";

  const minN = mw?.min_samples_per_regime ?? 3;

  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.28 }}
      className="glass-card p-6" style={{ gridColumn: "1 / -1" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: 12, fontWeight: 700, color: "#64748b", letterSpacing: "0.08em" }}>META-LEARNER v2 — ADAPTIVE WEIGHTS</div>
          <div style={{ fontSize: 11, color: "#334155", marginTop: 4 }}>
            Regime-conditioned weights · EWMA λ={mw?.ewma.lambda ?? 0.92} (half-life {mw?.ewma.half_life_days ?? 8}d) · Confidence-weighted
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {mw?.current_regime && (
            <span style={{ fontSize: 11, fontWeight: 700, padding: "4px 10px", borderRadius: 6,
              background: regimeColors[mw.current_regime] + "20",
              border: `1px solid ${regimeColors[mw.current_regime]}40`,
              color: regimeColors[mw.current_regime] }}>
              {regimeIcons[mw.current_regime]} Active: {mw.current_regime}
            </span>
          )}
          <span style={{ fontSize: 10, color: mw?.status === "active" ? "#22c55e" : "#475569",
            padding: "3px 8px", borderRadius: 4, background: "rgba(255,255,255,0.04)",
            border: "1px solid rgba(255,255,255,0.08)" }}>
            {mw?.status === "active" ? "● ACTIVE" : "○ TRAINING"}
          </span>
        </div>
      </div>

      {/* Global weights bar */}
      {mw?.global_weights && (
        <div style={{ marginBottom: 16, padding: "10px 14px", borderRadius: 8, background: "rgba(99,102,241,0.08)", border: "1px solid rgba(99,102,241,0.2)" }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: "#6366f1", marginBottom: 8, letterSpacing: "0.07em" }}>GLOBAL WEIGHTS (sample-count weighted average)</div>
          <div style={{ display: "flex", gap: 6 }}>
            {(["T", "F", "S"] as const).map(k => {
              const labels: Record<string, string> = { T: "Technical", F: "Fundamental", S: "Sentiment" };
              const pct = Math.round((mw.global_weights[k] ?? 0) * 100);
              const cols = ["#3b82f6", "#a855f7", "#10b981"];
              const ci = ["T", "F", "S"].indexOf(k);
              return (
                <div key={k} style={{ flex: 1 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "#94a3b8", marginBottom: 3 }}>
                    <span>{labels[k]}</span><span style={{ fontWeight: 700, color: cols[ci] }}>{pct}%</span>
                  </div>
                  <div style={{ height: 4, borderRadius: 99, background: "rgba(255,255,255,0.06)", overflow: "hidden" }}>
                    <motion.div initial={{ width: 0 }} animate={{ width: `${pct}%` }} transition={{ duration: 0.7 }}
                      style={{ height: "100%", background: cols[ci], borderRadius: 99 }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Per-regime grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
        {(["BULL", "BEAR", "SIDEWAYS"] as const).map(regime => {
          const rw = mw?.regime_weights?.[regime];
          const isActive = rw?.is_active ?? false;
          const samples = rw?.samples ?? 0;
          const regimeColor = regimeColors[regime];
          return (
            <div key={regime} style={{ padding: 14, borderRadius: 10,
              background: isActive ? regimeColor + "10" : "rgba(255,255,255,0.03)",
              border: isActive ? `1.5px solid ${regimeColor}50` : "1px solid rgba(255,255,255,0.07)",
              position: "relative" }}>
              {isActive && (
                <div style={{ position: "absolute", top: 8, right: 8, fontSize: 9, fontWeight: 700,
                  color: regimeColor, background: regimeColor + "20", padding: "2px 6px", borderRadius: 4 }}>ACTIVE</div>
              )}
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 10 }}>
                <span style={{ fontSize: 16 }}>{regimeIcons[regime]}</span>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 800, color: regimeColor }}>{regime}</div>
                  <div style={{ fontSize: 9, color: statusColor(rw?.status ?? "") }}>
                    {statusLabel(rw?.status ?? "")} · {samples}/{Math.max(samples, minN)} samples
                  </div>
                </div>
              </div>

              {/* Sample progress bar */}
              <div style={{ height: 3, borderRadius: 99, background: "rgba(255,255,255,0.06)", overflow: "hidden", marginBottom: 12 }}>
                <motion.div initial={{ width: 0 }}
                  animate={{ width: `${Math.min(100, (samples / Math.max(minN, 1)) * 100)}%` }}
                  transition={{ duration: 0.8 }}
                  style={{ height: "100%", background: statusColor(rw?.status ?? ""), borderRadius: 99 }} />
              </div>

              {/* Weight bars */}
              {(["T", "F", "S"] as const).map(k => {
                const labels: Record<string, string> = { T: "Tech", F: "Fund", S: "Sent" };
                const pct = Math.round(((rw?.[k] as number) ?? 0) * 100);
                const bCols = ["#3b82f6", "#a855f7", "#10b981"];
                const ci = ["T", "F", "S"].indexOf(k);
                return (
                  <div key={k} style={{ marginBottom: 6 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "#64748b", marginBottom: 2 }}>
                      <span>{labels[k]}</span>
                      <span style={{ fontWeight: 700, color: pct > 40 ? bCols[ci] : "#64748b" }}>{pct}%</span>
                    </div>
                    <div style={{ height: 5, borderRadius: 99, background: "rgba(255,255,255,0.06)", overflow: "hidden" }}>
                      <motion.div initial={{ width: 0 }} animate={{ width: `${pct}%` }} transition={{ duration: 0.6, delay: 0.1 * ci }}
                        style={{ height: "100%", background: bCols[ci], opacity: isActive ? 1 : 0.5, borderRadius: 99 }} />
                    </div>
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>

      {mw?.message && (
        <div style={{ marginTop: 12, fontSize: 11, color: "#475569", textAlign: "center" }}>{mw.message}</div>
      )}
      {mw?.last_updated && (
        <div style={{ marginTop: 8, fontSize: 10, color: "#334155", textAlign: "right" }}>
          Last trained: {new Date(mw.last_updated).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })} IST
          · {mw.total_samples} total samples
        </div>
      )}
    </motion.div>
  );
}


// ── Helpers ───────────────────────────────────────────────────────────────────
const outcomeColor = (o: string) =>
  o === "WIN" ? "#22c55e" : o === "LOSS" ? "#ef4444" : o === "BREAKEVEN" ? "#f59e0b" : "#64748b";

const signalColor = (s: string) => {
  const u = s?.toUpperCase() ?? "";
  if (u.includes("STRONG BUY") || u.includes("STRONG_BUY")) return "#22c55e";
  if (u.includes("BUY")) return "#4ade80";
  if (u.includes("STRONG SELL") || u.includes("STRONG_SELL")) return "#ef4444";
  if (u.includes("SELL")) return "#f87171";
  return "#f59e0b";
};

const pnlColor = (p: number) => (p > 0 ? "#22c55e" : p < 0 ? "#ef4444" : "#f59e0b");

// ── Stat Card ─────────────────────────────────────────────────────────────────
function StatCard({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div className="glass-card p-5">
      <div style={{ fontSize: 11, fontWeight: 700, color: "#475569", letterSpacing: "0.08em", marginBottom: 8 }}>{label}</div>
      <div style={{ fontSize: 32, fontWeight: 800, color: color ?? "#f1f5f9", lineHeight: 1 }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: "#64748b", marginTop: 6 }}>{sub}</div>}
    </div>
  );
}

// ── Mini Win-Rate Bar ──────────────────────────────────────────────────────────
function WinRateBar({ rate, wins, total }: { rate: number; wins: number; total: number }) {
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "#64748b", marginBottom: 4 }}>
        <span>{wins} wins / {total} resolved</span>
        <span style={{ fontWeight: 700, color: rate >= 60 ? "#22c55e" : rate >= 45 ? "#f59e0b" : "#ef4444" }}>{rate}%</span>
      </div>
      <div style={{ height: 6, borderRadius: 99, background: "rgba(255,255,255,0.06)", overflow: "hidden" }}>
        <motion.div initial={{ width: 0 }} animate={{ width: `${rate}%` }} transition={{ duration: 0.8, ease: "easeOut" }}
          style={{ height: "100%", background: rate >= 60 ? "#22c55e" : rate >= 45 ? "#f59e0b" : "#ef4444", borderRadius: 99 }} />
      </div>
    </div>
  );
}

// ── Monthly Trend SVG Chart ───────────────────────────────────────────────────
function MonthlyChart({ data }: { data: LearnStats["monthly_trend"] }) {
  if (!data.length) return null;
  const maxRate = 100;
  const chartH  = 120;
  const chartW  = 600;
  const barW    = Math.min(40, Math.floor(chartW / (data.length * 1.5)));

  return (
    <svg width="100%" height={chartH + 36} viewBox={`0 0 ${chartW} ${chartH + 36}`} preserveAspectRatio="xMidYMid meet">
      {/* 50% guide line */}
      <line x1={0} y1={chartH / 2} x2={chartW} y2={chartH / 2} stroke="rgba(255,255,255,0.06)" strokeWidth={1} strokeDasharray="4,4" />
      <text x={chartW - 4} y={chartH / 2 - 3} textAnchor="end" fontSize={9} fill="#334155">50%</text>

      {data.map((d, i) => {
        const x      = (i / data.length) * chartW + 8;
        const barH   = Math.max(2, (d.win_rate / maxRate) * chartH);
        const color  = d.win_rate >= 60 ? "#22c55e" : d.win_rate >= 45 ? "#f59e0b" : "#ef4444";
        return (
          <g key={d.month}>
            <rect x={x} y={chartH - barH} width={barW} height={barH} rx={3} fill={color} opacity={0.75} />
            <text x={x + barW / 2} y={chartH + 14} textAnchor="middle" fontSize={9} fill="#475569">
              {d.month.slice(5)}
            </text>
            <text x={x + barW / 2} y={chartH - barH - 4} textAnchor="middle" fontSize={9} fontWeight="700" fill={color}>
              {d.win_rate}%
            </text>
          </g>
        );
      })}
    </svg>
  );
}

// ── No Data State ─────────────────────────────────────────────────────────────
function NoDataState({ onTrigger, triggering }: { onTrigger: () => void; triggering: boolean }) {
  return (
    <div className="glass-card p-10" style={{ textAlign: "center", maxWidth: 600, margin: "60px auto" }}>
      <div style={{ fontSize: 52, marginBottom: 16 }}>📡</div>
      <div style={{ fontSize: 18, fontWeight: 800, color: "#f1f5f9", marginBottom: 10 }}>Learning in Progress</div>
      <p style={{ fontSize: 13, color: "#64748b", lineHeight: 1.7, marginBottom: 20 }}>
        ATBot hasn't tracked enough signal outcomes yet.<br />
        The outcome checker runs daily at <strong style={{ color: "#60a5fa" }}>6:30 PM IST</strong> and records
        how each signal performed at Day 5 and Day 10.
      </p>
      <p style={{ fontSize: 12, color: "#475569", marginBottom: 24 }}>
        Start using ATBot to analyze stocks — outcome data will appear here automatically.
      </p>
      <div style={{ display: "flex", gap: 10, justifyContent: "center" }}>
        <button onClick={onTrigger} disabled={triggering} style={{
          padding: "10px 22px", borderRadius: 10, border: "none", cursor: triggering ? "not-allowed" : "pointer",
          background: "linear-gradient(135deg, #3b82f6, #6366f1)", color: "#fff", fontSize: 13, fontWeight: 700,
        }}>
          {triggering ? "Running check…" : "▶ Run Outcome Check Now"}
        </button>
      </div>
      <div style={{ marginTop: 16, fontSize: 11, color: "#334155" }}>
        (This button checks signals from 1, 2, 5, or 10 trading days ago — weekends skipped automatically for BTST/D2)
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function LearnPage() {
  const [checkDay, setCheckDay]  = useState<1 | 2 | 5 | 10>(10); // default D10 — most data
  const [lookback, setLookback]  = useState(90);
  const [triggering, setTriggering] = useState(false);
  const [triggerMsg, setTriggerMsg] = useState("");

  const { data: stats, isLoading: statsLoading, mutate: mutateStats } = useSWR<LearnStats>(
    `learn-stats-${checkDay}-${lookback}`,
    () => getLearnStats(lookback, checkDay),
    { revalidateOnFocus: false }
  );
  const { data: recent = [], isLoading: recentLoading } = useSWR<OutcomeRecord[]>(
    `learn-recent-${checkDay}`,
    () => getRecentOutcomes(50, checkDay),  // Bug4: pass checkDay filter
    { revalidateOnFocus: false }
  );

  const [downloading, setDownloading] = useState(false);

  const handleTrigger = async () => {
    setTriggering(true);
    setTriggerMsg("");
    try {
      const res = await triggerOutcomeCheck();
      setTriggerMsg(`✓ Done — ${res.new_outcomes} new outcome(s) recorded`);
      mutateStats();
    } catch {
      setTriggerMsg("⚠ Check failed — see backend logs");
    } finally {
      setTriggering(false);
    }
  };

  const handleDownloadReport = async () => {
    setDownloading(true);
    try {
      // Pass the same check_day filter the user is viewing so PDF matches dashboard
      const response = await fetch(`http://localhost:8000/api/learn/report?days=${lookback}&check_day=${checkDay}`);
      if (!response.ok) throw new Error("Report generation failed");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      const date = new Date().toISOString().slice(0, 10);
      a.href = url;
      a.download = `ATBot_Accuracy_Report_D${checkDay}_${date}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      alert("Report generation failed. Make sure there is data in the Learn page.");
    } finally {
      setDownloading(false);
    }
  };

  const noData = !statsLoading && (!stats?.has_data);

  const SIGNAL_ORDER = ["STRONG BUY", "BUY", "HOLD", "SELL", "STRONG SELL"];

  return (
    <div style={{ maxWidth: 1100 }}>
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} style={{ marginBottom: 24 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <h1 style={{ fontSize: 24, fontWeight: 800, color: "#f1f5f9", margin: 0 }}>ATBot Learn</h1>
            <p style={{ fontSize: 13, color: "#475569", marginTop: 4 }}>
              Win rate, accuracy trends, and signal outcome tracking
            </p>
          </div>

          {/* Controls */}
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <div style={{ display: "flex", gap: 4 }}>
              {([
                { d: 1,  label: "BTST",        sub: "D1" },
                { d: 2,  label: "D2",           sub: "D2" },
                { d: 5,  label: "Swing",        sub: "D5" },
                { d: 10, label: "Positional",   sub: "D10" },
              ] as const).map(({ d, label, sub }) => (
                <button key={d} onClick={() => setCheckDay(d as 1 | 2 | 5 | 10)} style={{
                  padding: "6px 14px", borderRadius: 8, fontSize: 12, fontWeight: 700, cursor: "pointer",
                  background: checkDay === d ? "rgba(59,130,246,0.2)" : "rgba(255,255,255,0.04)",
                  border: checkDay === d ? "1px solid rgba(59,130,246,0.4)" : "1px solid rgba(255,255,255,0.08)",
                  color: checkDay === d ? "#60a5fa" : "#64748b",
                  display: "flex", flexDirection: "column", alignItems: "center", lineHeight: 1.2,
                }}>
                  <span>{label}</span>
                  <span style={{ fontSize: 9, opacity: 0.6 }}>{sub}</span>
                </button>
              ))}
            </div>
            <select value={lookback} onChange={e => setLookback(+e.target.value)} style={{
              padding: "6px 10px", borderRadius: 8, background: "rgba(255,255,255,0.05)",
              border: "1px solid rgba(255,255,255,0.1)", color: "#f1f5f9", fontSize: 12, outline: "none",
            }}>
              <option value={30}>Last 30 days</option>
              <option value={90}>Last 90 days</option>
              <option value={180}>Last 6 months</option>
              <option value={365}>Last 1 year</option>
            </select>
            <button onClick={handleTrigger} disabled={triggering} style={{
              padding: "6px 14px", borderRadius: 8, fontSize: 12, fontWeight: 700, cursor: triggering ? "not-allowed" : "pointer",
              background: "rgba(59,130,246,0.15)", border: "1px solid rgba(59,130,246,0.3)", color: "#60a5fa",
            }}>
              {triggering ? "Running…" : "⚡ Run Check"}
            </button>
            <button onClick={handleDownloadReport} disabled={downloading} style={{
              padding: "6px 14px", borderRadius: 8, fontSize: 12, fontWeight: 700, cursor: downloading ? "not-allowed" : "pointer",
              background: "rgba(34,197,94,0.12)", border: "1px solid rgba(34,197,94,0.3)", color: "#22c55e",
              display: "flex", alignItems: "center", gap: 5,
            }}>
              {downloading ? "Generating…" : "📥 Download Report"}
            </button>
          </div>
        </div>
        {triggerMsg && (
          <div style={{ marginTop: 10, fontSize: 12, color: "#22c55e", fontWeight: 600 }}>{triggerMsg}</div>
        )}
      </motion.div>

      {/* No data state */}
      {noData && <NoDataState onTrigger={handleTrigger} triggering={triggering} />}

      {/* Data present */}
      {!noData && stats && (
        <>
          {/* ── Row 1: Hero stats ─────────────────────────────────────── */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14, marginBottom: 20 }}>
            <StatCard
              label="OVERALL WIN RATE"
              value={`${stats.overall_win_rate}%`}
              sub={`${stats.total_resolved} resolved signals`}
              color={stats.overall_win_rate >= 60 ? "#22c55e" : stats.overall_win_rate >= 45 ? "#f59e0b" : "#ef4444"}
            />
            <StatCard
              label="AVG P&L (ALL)"
              value={`${stats.avg_pnl_pct > 0 ? "+" : ""}${stats.avg_pnl_pct}%`}
              sub="per resolved signal"
              color={pnlColor(stats.avg_pnl_pct)}
            />
            <StatCard
              label="AVG GAIN ON WINS"
              value={`+${stats.avg_pnl_wins}%`}
              sub="when signal was correct"
              color="#22c55e"
            />
            <StatCard
              label="AVG LOSS ON LOSSES"
              value={`${stats.avg_loss_pct}%`}
              sub="when signal was wrong"
              color="#ef4444"
            />
          </div>

          {/* ── Row 2: By-signal breakdown + monthly chart ─────────────── */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1.6fr", gap: 16, marginBottom: 20 }}>
            {/* By signal */}
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="glass-card p-6">
              <div style={{ fontSize: 12, fontWeight: 700, color: "#64748b", letterSpacing: "0.08em", marginBottom: 16 }}>WIN RATE BY SIGNAL TYPE</div>
              {SIGNAL_ORDER.map(sig => {
                const data = stats.by_signal[sig] ?? stats.by_signal[sig.replace(" ", "_")];
                if (!data || data.total === 0) return null;
                return (
                  <div key={sig} style={{ marginBottom: 16 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                      <span style={{ fontSize: 12, fontWeight: 700, color: signalColor(sig) }}>{sig}</span>
                      <span style={{ fontSize: 11, color: pnlColor(data.avg_pnl) }}>
                        avg {data.avg_pnl > 0 ? "+" : ""}{data.avg_pnl}%
                      </span>
                    </div>
                    <WinRateBar rate={data.win_rate} wins={data.wins} total={data.total} />
                  </div>
                );
              })}
            </motion.div>

            {/* Monthly chart */}
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }} className="glass-card p-6">
              <div style={{ fontSize: 12, fontWeight: 700, color: "#64748b", letterSpacing: "0.08em", marginBottom: 16 }}>
                MONTHLY WIN RATE TREND
              </div>
              {stats.monthly_trend.length > 0 ? (
                <MonthlyChart data={stats.monthly_trend} />
              ) : (
                <div style={{ color: "#475569", fontSize: 12, textAlign: "center", paddingTop: 40 }}>Not enough data for monthly trend yet</div>
              )}
            </motion.div>
          </div>

          {/* ── Row 3: Component correlation + top/worst stocks ────────── */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 20 }}>
            {/* Component correlation */}
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="glass-card p-6">
              <div style={{ fontSize: 12, fontWeight: 700, color: "#64748b", letterSpacing: "0.08em", marginBottom: 16 }}>
                ENGINE SCORE: WINS vs LOSSES
              </div>
              <div style={{ fontSize: 11, color: "#334155", marginBottom: 14 }}>
                Average engine scores for winning vs losing signals — higher delta = engine was more predictive
              </div>
              {(["composite", "technical", "fundamental", "sentiment"] as const).map(key => {
                const d = stats.by_component[key];
                if (!d) return null;
                const delta = d.wins_avg - d.losses_avg;
                return (
                  <div key={key} style={{ marginBottom: 14 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 5 }}>
                      <span style={{ fontWeight: 700, color: "#f1f5f9", textTransform: "capitalize" }}>{key}</span>
                      <span style={{ color: delta > 0 ? "#22c55e" : "#ef4444", fontWeight: 700 }}>
                        Δ {delta > 0 ? "+" : ""}{delta.toFixed(1)}
                      </span>
                    </div>
                    <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
                      <span style={{ fontSize: 10, color: "#22c55e", width: 50 }}>WIN {d.wins_avg}</span>
                      <div style={{ flex: 1, height: 5, borderRadius: 99, background: "rgba(255,255,255,0.06)", overflow: "hidden" }}>
                        <div style={{ width: `${d.wins_avg}%`, height: "100%", background: "#22c55e", opacity: 0.7, borderRadius: 99 }} />
                      </div>
                    </div>
                    <div style={{ display: "flex", gap: 4, alignItems: "center", marginTop: 3 }}>
                      <span style={{ fontSize: 10, color: "#ef4444", width: 50 }}>LOSS {d.losses_avg}</span>
                      <div style={{ flex: 1, height: 5, borderRadius: 99, background: "rgba(255,255,255,0.06)", overflow: "hidden" }}>
                        <div style={{ width: `${d.losses_avg}%`, height: "100%", background: "#ef4444", opacity: 0.7, borderRadius: 99 }} />
                      </div>
                    </div>
                  </div>
                );
              })}
            </motion.div>

            {/* Top / worst stocks */}
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }} className="glass-card p-6">
              <div style={{ fontSize: 12, fontWeight: 700, color: "#64748b", letterSpacing: "0.08em", marginBottom: 16 }}>
                BEST & WORST PERFORMING STOCKS
              </div>
              <div style={{ fontSize: 11, fontWeight: 700, color: "#22c55e", marginBottom: 8 }}>🏆 Most Accurate</div>
              {stats.top_stocks.map(s => (
                <div key={s.symbol} style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                  <span style={{ fontSize: 13, fontWeight: 700, color: "#f1f5f9" }}>{s.symbol.replace(".NS", "")}</span>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: "#22c55e" }}>{s.win_rate}% win rate</div>
                    <div style={{ fontSize: 10, color: pnlColor(s.avg_pnl) }}>{s.avg_pnl > 0 ? "+" : ""}{s.avg_pnl}% avg</div>
                  </div>
                </div>
              ))}
              <div style={{ fontSize: 11, fontWeight: 700, color: "#ef4444", margin: "14px 0 8px" }}>⚠ Needs Attention</div>
              {stats.worst_stocks.map(s => (
                <div key={s.symbol} style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                  <span style={{ fontSize: 13, fontWeight: 700, color: "#f1f5f9" }}>{s.symbol.replace(".NS", "")}</span>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: "#ef4444" }}>{s.win_rate}% win rate</div>
                    <div style={{ fontSize: 10, color: pnlColor(s.avg_pnl) }}>{s.avg_pnl > 0 ? "+" : ""}{s.avg_pnl}% avg</div>
                  </div>
                </div>
              ))}
            </motion.div>
          </div>

          {/* ── Meta-Learner v2 Card (full width) ───────────────────────── */}
          <MetaLearnerV2Card />

          {/* ── Row 4: Recent outcomes table ──────────────────────────── */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }} className="glass-card p-6">
            <div style={{ fontSize: 12, fontWeight: 700, color: "#64748b", letterSpacing: "0.08em", marginBottom: 16 }}>
              RECENT SIGNAL OUTCOMES
            </div>

            {recentLoading ? (
              [...Array(5)].map((_, i) => <div key={i} className="shimmer mb-2" style={{ height: 44, borderRadius: 8 }} />)
            ) : recent.length === 0 ? (
              <div style={{ color: "#475569", fontSize: 12, textAlign: "center", padding: 24 }}>No resolved outcomes yet</div>
            ) : (
              <>
                {/* Table header */}
                <div style={{ display: "grid", gridTemplateColumns: "100px 1fr 80px 70px 80px 80px 80px 100px", gap: 8, padding: "6px 10px", marginBottom: 6 }}>
                  {["SYMBOL", "SIGNAL", "ENTRY", "DAY", "ENTRY ₹", "PRICE ₹", "P&L %", "OUTCOME"].map(h => (
                    <div key={h} style={{ fontSize: 9, fontWeight: 700, color: "#334155", letterSpacing: "0.07em" }}>{h}</div>
                  ))}
                </div>

                {recent.map((r, i) => (
                  <motion.div key={i} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.02 }}
                    style={{ display: "grid", gridTemplateColumns: "100px 1fr 80px 70px 80px 80px 80px 100px", gap: 8, padding: "10px 10px", borderRadius: 8, marginBottom: 4, background: "rgba(255,255,255,0.03)", alignItems: "center" }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: "#f1f5f9" }}>{r.symbol.replace(".NS", "")}</div>
                    <div style={{ fontSize: 11, fontWeight: 700, color: signalColor(r.signal) }}>{r.signal}</div>
                    <div style={{ fontSize: 11, color: "#64748b" }}>{r.entry_date}</div>
                    <div style={{ fontSize: 11, color: "#475569" }}>D{r.check_day}</div>
                    <div style={{ fontSize: 11, color: "#94a3b8" }}>₹{r.entry_price?.toLocaleString("en-IN", { maximumFractionDigits: 1 })}</div>
                    <div style={{ fontSize: 11, color: "#94a3b8" }}>₹{r.price_at_check?.toLocaleString("en-IN", { maximumFractionDigits: 1 })}</div>
                    {/* Bug2: For SELL signals, raw pnl_percent is negative when price fell (=WIN for SELL)
                        Show adjusted display: invert sign for SELLs, add directional label */}
                    {(() => {
                      const isSell = r.signal.toUpperCase().includes("SELL");
                      const displayPnl = isSell ? -(r.pnl_percent ?? 0) : (r.pnl_percent ?? 0);
                      const displayColor = r.outcome === "WIN" ? "#22c55e" : r.outcome === "LOSS" ? "#ef4444" : "#f59e0b";
                      return (
                        <div style={{ fontSize: 12, fontWeight: 700, color: displayColor }}>
                          {displayPnl > 0 ? "+" : ""}{displayPnl.toFixed(2)}%
                          {isSell && <span style={{ fontSize: 9, color: "#64748b", marginLeft: 3 }}>(SELL)</span>}
                        </div>
                      );
                    })()}
                    <div style={{
                      fontSize: 10, fontWeight: 700, padding: "3px 8px", borderRadius: 6, textAlign: "center",
                      background: outcomeColor(r.outcome) + "20",
                      border: `1px solid ${outcomeColor(r.outcome)}40`,
                      color: outcomeColor(r.outcome),
                    }}>{r.outcome}</div>
                  </motion.div>
                ))}
              </>
            )}
          </motion.div>
        </>
      )}

      {/* Loading skeleton */}
      {statsLoading && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14 }}>
          {[...Array(4)].map((_, i) => <div key={i} className="shimmer" style={{ height: 100, borderRadius: 14 }} />)}
        </div>
      )}
    </div>
  );
}
