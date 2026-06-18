"use client";
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import useSWR from "swr";
import { getMorningBriefing, triggerMorningBriefing, type MorningBriefing } from "@/lib/api";

const signalColor = (s: string) => {
  const u = s?.toUpperCase() ?? "";
  if (u.includes("STRONG BUY")) return "#22c55e";
  if (u.includes("BUY")) return "#4ade80";
  if (u.includes("STRONG SELL")) return "#ef4444";
  if (u.includes("SELL")) return "#f87171";
  return "#f59e0b";
};

function formatTime(iso?: string) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: true });
  } catch { return iso; }
}

export default function MorningBriefingPanel() {
  const [open, setOpen] = useState(false);
  const [triggering, setTriggering] = useState(false);

  const { data: briefing, isLoading, mutate } = useSWR<MorningBriefing>(
    "morning-briefing",
    getMorningBriefing,
    { revalidateOnFocus: false, refreshInterval: 0 }
  );

  const hasData = briefing && briefing.status !== "not_generated" && briefing.generated_at;

  const handleTrigger = async () => {
    setTriggering(true);
    try {
      await triggerMorningBriefing();
      await mutate();
      setOpen(true);
    } catch { /* silent */ }
    finally { setTriggering(false); }
  };

  return (
    <div style={{ marginBottom: 20 }}>
      {/* Banner / Trigger Button */}
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        style={{
          background: "linear-gradient(135deg, rgba(99,102,241,0.12), rgba(16,185,129,0.08))",
          border: "1px solid rgba(99,102,241,0.25)",
          borderRadius: 14,
          padding: "12px 18px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          cursor: "pointer",
        }}
        onClick={() => hasData && setOpen(o => !o)}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 20 }}>🌅</span>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: "#f1f5f9" }}>
              Morning Briefing
              {hasData && (
                <span style={{ marginLeft: 8, fontSize: 10, color: "#64748b", fontWeight: 400 }}>
                  Generated at {formatTime(briefing.generated_at)}
                </span>
              )}
            </div>
            {hasData && briefing.market_comment ? (
              <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 2, maxWidth: 700, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {briefing.market_comment}
              </div>
            ) : (
              <div style={{ fontSize: 11, color: "#475569", marginTop: 2 }}>
                {isLoading ? "Loading…" : "Not generated yet — click Generate below"}
              </div>
            )}
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <button
            onClick={(e) => { e.stopPropagation(); handleTrigger(); }}
            disabled={triggering}
            style={{
              padding: "5px 13px", borderRadius: 8, fontSize: 11, fontWeight: 700,
              background: "rgba(99,102,241,0.2)", border: "1px solid rgba(99,102,241,0.4)",
              color: "#818cf8", cursor: triggering ? "not-allowed" : "pointer",
            }}
          >
            {triggering ? "Generating…" : "⚡ Generate"}
          </button>
          {hasData && (
            <span style={{ fontSize: 18, color: "#475569", userSelect: "none" }}>
              {open ? "▲" : "▼"}
            </span>
          )}
        </div>
      </motion.div>

      {/* Expandable Panel */}
      <AnimatePresence>
        {open && hasData && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.25, ease: "easeOut" }}
            style={{ overflow: "hidden" }}
          >
            <div style={{
              marginTop: 10,
              background: "rgba(10,15,28,0.8)",
              border: "1px solid rgba(99,102,241,0.15)",
              borderRadius: 14,
              padding: "18px 20px",
              display: "grid",
              gridTemplateColumns: "1fr 1fr 1fr",
              gap: 18,
            }}>

              {/* Column 1: Market Snapshot */}
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, color: "#475569", letterSpacing: "0.08em", marginBottom: 12 }}>
                  MARKET SNAPSHOT
                </div>

                {/* Indices */}
                {briefing.indices && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 12 }}>
                    {briefing.indices.nifty50 && (
                      <IndexRow label="NIFTY 50" data={briefing.indices.nifty50} />
                    )}
                    {briefing.indices.sensex && (
                      <IndexRow label="SENSEX" data={briefing.indices.sensex} />
                    )}
                  </div>
                )}

                {/* VIX */}
                {briefing.india_vix && (
                  <div style={{ padding: "8px 12px", borderRadius: 8, background: "rgba(245,158,11,0.07)", border: "1px solid rgba(245,158,11,0.15)", marginBottom: 8 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontSize: 11, fontWeight: 600, color: "#fcd34d" }}>INDIA VIX</span>
                      <span style={{ fontSize: 10, color: "#f59e0b", fontWeight: 700 }}>{briefing.india_vix.risk_level}</span>
                    </div>
                    <div style={{ fontSize: 18, fontWeight: 800, color: "#fcd34d" }}>
                      {briefing.india_vix.vix?.toFixed(2)}
                    </div>
                    <div style={{ fontSize: 10, color: "#78716c", marginTop: 2 }}>{briefing.india_vix.risk_comment}</div>
                  </div>
                )}

                {/* FII/DII */}
                {briefing.fii_dii && (
                  <div style={{ display: "flex", gap: 6 }}>
                    <FiiDiiPill label="FII Net" value={briefing.fii_dii.fii_net} />
                    <FiiDiiPill label="DII Net" value={briefing.fii_dii.dii_net} />
                  </div>
                )}
              </div>

              {/* Column 2: Global Cues */}
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, color: "#475569", letterSpacing: "0.08em", marginBottom: 12 }}>
                  GLOBAL CUES
                </div>
                {briefing.global_cues && Object.keys(briefing.global_cues).length > 0 ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {Object.entries(briefing.global_cues).slice(0, 6).map(([name, cue]) => (
                      <div key={name} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 10px", borderRadius: 8, background: "rgba(255,255,255,0.03)" }}>
                        <span style={{ fontSize: 11, color: "#94a3b8", fontWeight: 600 }}>{name}</span>
                        <div style={{ textAlign: "right" }}>
                          <div style={{ fontSize: 12, fontWeight: 700, color: "#f1f5f9" }}>
                            {cue.price?.toLocaleString("en-US", { maximumFractionDigits: 2 })}
                          </div>
                          <div style={{ fontSize: 10, fontWeight: 700, color: (cue.change_pct ?? 0) >= 0 ? "#22c55e" : "#ef4444" }}>
                            {(cue.change_pct ?? 0) >= 0 ? "▲" : "▼"} {Math.abs(cue.change_pct ?? 0).toFixed(2)}%
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div style={{ fontSize: 12, color: "#334155" }}>Global cues not available</div>
                )}

                {/* Earnings today */}
                {briefing.earnings_today && briefing.earnings_today.length > 0 && (
                  <div style={{ marginTop: 12 }}>
                    <div style={{ fontSize: 10, fontWeight: 700, color: "#f59e0b", letterSpacing: "0.08em", marginBottom: 6 }}>
                      ⚡ EARNINGS TODAY
                    </div>
                    {briefing.earnings_today.map(e => (
                      <div key={e.symbol} style={{ fontSize: 11, color: "#fcd34d", padding: "4px 0", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                        {e.symbol.replace(".NS", "")} — {e.company_name}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Column 3: Top Signals */}
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, color: "#475569", letterSpacing: "0.08em", marginBottom: 12 }}>
                  TOP SIGNALS (LAST 24H)
                </div>
                {briefing.top_signals && briefing.top_signals.length > 0 ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {briefing.top_signals.map((s) => (
                      <a key={s.symbol} href={`/stock/${s.symbol}`} style={{ textDecoration: "none" }}>
                        <motion.div
                          whileHover={{ x: 2 }}
                          style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "7px 10px", borderRadius: 8, background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.05)", cursor: "pointer" }}
                        >
                          <div>
                            <div style={{ fontSize: 12, fontWeight: 700, color: "#f1f5f9" }}>
                              {s.symbol.replace(".NS", "")}
                            </div>
                            <div style={{ fontSize: 10, color: "#475569" }}>Score: {s.score}</div>
                          </div>
                          <div style={{ textAlign: "right" }}>
                            <div style={{ fontSize: 10, fontWeight: 700, color: signalColor(s.signal), background: signalColor(s.signal) + "18", padding: "2px 8px", borderRadius: 6, border: `1px solid ${signalColor(s.signal)}30` }}>
                              {s.signal}
                            </div>
                            <div style={{ fontSize: 10, color: "#64748b", marginTop: 2 }}>{s.confidence}% conf.</div>
                          </div>
                        </motion.div>
                      </a>
                    ))}
                  </div>
                ) : (
                  <div style={{ fontSize: 12, color: "#334155" }}>
                    No strong signals recorded in the last 24 hours.<br />
                    Analyze some stocks first!
                  </div>
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function IndexRow({ label, data }: { label: string; data: { price: number; change_pct: number } }) {
  const isUp = data.change_pct >= 0;
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "7px 10px", borderRadius: 8, background: "rgba(255,255,255,0.04)" }}>
      <span style={{ fontSize: 11, fontWeight: 600, color: "#94a3b8" }}>{label}</span>
      <div style={{ textAlign: "right" }}>
        <div style={{ fontSize: 13, fontWeight: 800, color: "#f1f5f9" }}>
          {data.price?.toLocaleString("en-IN")}
        </div>
        <div style={{ fontSize: 10, fontWeight: 700, color: isUp ? "#22c55e" : "#ef4444" }}>
          {isUp ? "▲" : "▼"} {Math.abs(data.change_pct).toFixed(2)}%
        </div>
      </div>
    </div>
  );
}

function FiiDiiPill({ label, value }: { label: string; value: number }) {
  const isPos = value >= 0;
  return (
    <div style={{ flex: 1, padding: "6px 10px", borderRadius: 8, background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)", textAlign: "center" }}>
      <div style={{ fontSize: 9, color: "#475569", fontWeight: 600 }}>{label}</div>
      <div style={{ fontSize: 11, fontWeight: 700, color: isPos ? "#22c55e" : "#ef4444", marginTop: 2 }}>
        {isPos ? "+" : ""}₹{Math.abs(value).toLocaleString("en-IN")} Cr
      </div>
    </div>
  );
}
