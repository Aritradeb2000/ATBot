"use client";
import { useState, useEffect } from "react";
import useSWR from "swr";
import { motion } from "framer-motion";
import Link from "next/link";
import StockCard from "@/components/ui/StockCard";
import SignalBadge from "@/components/ui/SignalBadge";
import MorningBriefingPanel from "@/components/ui/MorningBriefingPanel";
import { analyzeStock, getMarketOverview, type MarketOverview } from "@/lib/api";

// Default fallback watchlist if local storage is empty
const DEFAULT_WATCHLIST = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ITC.NS", "KOTAKBANK.NS"];

// Types for the Top Buy Signals panel
interface TopSignal {
  symbol: string; ticker: string; score: number; signal: string;
  confidence: number; regime: string; price: number | null;
  stop_loss: number | null; target_base_5d: number | null;
  components: { technical: number; fundamental: number; sentiment: number };
  active_signals: string[];
  computed_at: string | null;
}
interface TopSignalsResponse {
  count: number; universe: string; data_source: string;
  last_computed: string | null; results: TopSignal[];
}

function WatchlistCard({ symbol, index, onRemove }: { symbol: string, index: number, onRemove: (s: string) => void }) {
  const { data, error, isLoading } = useSWR<AnalysisResult>(
    ["analyze", symbol],
    () => analyzeStock(symbol),
    { revalidateOnFocus: false, dedupingInterval: 300000 }
  );

  if (isLoading) return <div className="shimmer" style={{ height: 160, borderRadius: 16 }} />;
  
  const removeButton = (
    <button 
      onClick={(e) => { e.preventDefault(); e.stopPropagation(); onRemove(symbol); }}
      style={{ position: "absolute", top: 12, right: 12, zIndex: 10, background: "rgba(0,0,0,0.5)", border: "1px solid rgba(255,255,255,0.1)", color: "#94a3b8", borderRadius: "50%", width: 24, height: 24, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", paddingBottom: 2, fontSize: 14 }}
      title="Remove from watchlist"
      onMouseOver={(e) => e.currentTarget.style.color = "#ef4444"}
      onMouseOut={(e) => e.currentTarget.style.color = "#94a3b8"}
    >
      ×
    </button>
  );

  if (error || !data) {
    return (
      <div style={{ position: "relative", minHeight: 160, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }} className="glass-card p-4 text-center">
        {removeButton}
        <div style={{ fontSize: 16, fontWeight: 700, color: "#f1f5f9", marginBottom: 8 }}>{symbol.replace(".NS", "").replace(".BO", "")}</div>
        <div style={{ fontSize: 13, color: "#ef4444" }}>Failed to load data</div>
      </div>
    );
  }

  return (
    <div style={{ position: "relative" }}>
      {removeButton}
      <StockCard symbol={data.symbol} companyName={data.company_name} price={data.current_price} change={data.change} changePct={data.change_pct} analysis={data.analysis} index={index} />
    </div>
  );
}

function MarketOverviewCard({ data }: { data: MarketOverview | undefined }) {
  if (!data) {
    return (
      <div className="glass-card p-5">
        <h2 style={{ fontSize: 14, fontWeight: 700, color: "#94a3b8", letterSpacing: "0.08em", marginBottom: 16 }}>MARKET OVERVIEW</h2>
        {[...Array(4)].map((_, i) => <div key={i} className="shimmer mb-3" style={{ height: 36 }} />)}
      </div>
    );
  }

  const nifty = data.indices["NIFTY50"];
  const sensex = data.indices["SENSEX"];
  const vix = data.india_vix;
  const fii = data.fii_dii;
  const breadth = data.market_breadth;

  return (
    <div className="glass-card p-5 space-y-4">
      <h2 style={{ fontSize: 13, fontWeight: 700, color: "#64748b", letterSpacing: "0.08em" }}>MARKET OVERVIEW</h2>

      {/* Indices */}
      {[{ name: "NIFTY 50", d: nifty }, { name: "SENSEX", d: sensex }].map(({ name, d }) => d && (
        <div key={name} style={{ padding: "10px 14px", borderRadius: 10, background: "rgba(255,255,255,0.04)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: "#94a3b8" }}>{name}</span>
            <span style={{ fontSize: 12, fontWeight: 700, color: d.change_pct >= 0 ? "#22c55e" : "#ef4444" }}>
              {d.change_pct >= 0 ? "▲" : "▼"} {Math.abs(d.change_pct).toFixed(2)}%
            </span>
          </div>
          <div style={{ fontSize: 20, fontWeight: 800, color: "#f1f5f9", marginTop: 2 }}>
            ₹{d.price.toLocaleString("en-IN")}
          </div>
        </div>
      ))}

      {/* VIX */}
      {vix && (
        <div style={{ padding: "10px 14px", borderRadius: 10, background: "rgba(245,158,11,0.07)", border: "1px solid rgba(245,158,11,0.15)" }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: "#fcd34d" }}>INDIA VIX</span>
            <span style={{ fontSize: 11, color: "#f59e0b", fontWeight: 600 }}>{vix.risk_level}</span>
          </div>
          <div style={{ fontSize: 22, fontWeight: 800, color: "#fcd34d" }}>{vix.vix.toFixed(2)}</div>
          <p style={{ fontSize: 11, color: "#78716c", marginTop: 4 }}>{vix.risk_comment}</p>
        </div>
      )}

      {/* FII/DII */}
      {fii && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          {[
            { label: "FII Net", val: fii.fii_net, color: fii.fii_net >= 0 ? "#22c55e" : "#ef4444" },
            { label: "DII Net", val: fii.dii_net, color: fii.dii_net >= 0 ? "#22c55e" : "#ef4444" },
          ].map(({ label, val, color }) => (
            <div key={label} style={{ padding: "8px 12px", borderRadius: 8, background: "rgba(255,255,255,0.04)", textAlign: "center" }}>
              <div style={{ fontSize: 10, color: "#64748b", fontWeight: 600 }}>{label}</div>
              <div style={{ fontSize: 13, fontWeight: 700, color }}>
                {val >= 0 ? "+" : ""}₹{Math.abs(val).toLocaleString("en-IN")} Cr
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Market breadth */}
      {breadth && (
        <div>
          <div style={{ fontSize: 11, color: "#475569", marginBottom: 6, fontWeight: 600 }}>MARKET BREADTH</div>
          <div style={{ display: "flex", gap: 1, borderRadius: 6, overflow: "hidden", height: 8 }}>
            <div style={{ flex: breadth.advances, background: "#22c55e" }} />
            <div style={{ flex: breadth.unchanged, background: "#f59e0b" }} />
            <div style={{ flex: breadth.declines, background: "#ef4444" }} />
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}>
            <span style={{ fontSize: 10, color: "#22c55e" }}>▲ {breadth.advances}</span>
            <span style={{ fontSize: 10, color: "#f59e0b" }}>— {breadth.unchanged}</span>
            <span style={{ fontSize: 10, color: "#ef4444" }}>▼ {breadth.declines}</span>
          </div>
        </div>
      )}
    </div>
  );
}

export default function DashboardPage() {
  const [search, setSearch] = useState("");
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem("atbot_watchlist");
    if (stored) {
      try { setWatchlist(JSON.parse(stored)); } catch { setWatchlist(DEFAULT_WATCHLIST); }
    } else {
      setWatchlist(DEFAULT_WATCHLIST);
    }
    setMounted(true);
  }, []);

  const handleAddWatchlist = () => {
    const sym = search.trim().toUpperCase();
    if (sym && !watchlist.includes(sym)) {
      const nw = [sym, ...watchlist];
      setWatchlist(nw);
      localStorage.setItem("atbot_watchlist", JSON.stringify(nw));
    }
  };

  const handleRemoveWatchlist = (sym: string) => {
    const nw = watchlist.filter(s => s !== sym);
    setWatchlist(nw);
    localStorage.setItem("atbot_watchlist", JSON.stringify(nw));
  };

  const { data: marketData } = useSWR<MarketOverview>("market-overview", getMarketOverview, { refreshInterval: 60000 });
  const { data: topSignalsData } = useSWR<TopSignalsResponse>(
    "top-signals-panel",
    () => fetch("http://localhost:8000/api/screener/top-signals?limit=5").then(r => r.json()),
    { revalidateOnFocus: false, refreshInterval: 300000 }
  );

  const topSignals = topSignalsData?.results ?? [];
  const regimeColor = (r: string) => r === "BULL" ? "#22c55e" : r === "BEAR" ? "#ef4444" : "#f59e0b";
  const scoreColor = (s: number) => s >= 75 ? "#22c55e" : s >= 60 ? "#f59e0b" : "#ef4444";

  return (
    <div style={{ maxWidth: 1400 }}>
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} style={{ marginBottom: 20 }}>
        <h1 style={{ fontSize: 24, fontWeight: 800, color: "#f1f5f9", margin: 0 }}>Dashboard</h1>
        <p style={{ fontSize: 13, color: "#475569", marginTop: 4 }}>AI-powered signals for NSE/BSE Indian equities</p>
      </motion.div>

      {/* Morning Briefing Panel */}
      <MorningBriefingPanel />

      {/* Search bar */}
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.1 }} style={{ marginBottom: 24 }}>
        <div style={{ display: "flex", gap: 10, maxWidth: 480 }}>
          <input
            type="text"
            placeholder="Search stock... e.g. RELIANCE.NS"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && search.trim()) window.location.href = `/stock/${search.trim().toUpperCase()}`; }}
            style={{
              flex: 1,
              padding: "10px 16px",
              borderRadius: 10,
              border: "1px solid rgba(255,255,255,0.1)",
              background: "rgba(255,255,255,0.05)",
              color: "#f1f5f9",
              fontSize: 13,
              outline: "none",
            }}
          />
          <button
            onClick={() => search.trim() && (window.location.href = `/stock/${search.trim().toUpperCase()}`)}
            style={{
              padding: "10px 20px",
              borderRadius: 10,
              background: "linear-gradient(135deg, #3b82f6, #6366f1)",
              border: "none",
              color: "#fff",
              fontSize: 13,
              fontWeight: 700,
              cursor: "pointer",
            }}
          >
            Analyze
          </button>
          <button
            onClick={handleAddWatchlist}
            style={{
              padding: "10px 16px",
              borderRadius: 10,
              background: "rgba(255,255,255,0.05)",
              border: "1px solid rgba(255,255,255,0.1)",
              color: "#f1f5f9",
              fontSize: 13,
              fontWeight: 700,
              cursor: "pointer",
            }}
            title="Add to Watchlist"
          >
            + Add
          </button>
        </div>
      </motion.div>

      {/* 3-column layout */}
      <div style={{ display: "grid", gridTemplateColumns: "260px 1fr 260px", gap: 20 }}>
        {/* Left: Market Overview */}
        <MarketOverviewCard data={marketData} />

        {/* Center: Watchlist */}
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
            <h2 style={{ fontSize: 13, fontWeight: 700, color: "#64748b", letterSpacing: "0.08em", margin: 0 }}>MY WATCHLIST</h2>
            <span style={{ fontSize: 11, color: "#334155" }}>{mounted ? watchlist.length : 0} stocks</span>
          </div>
          {!mounted ? (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 12 }}>
              {[...Array(6)].map((_, i) => (
                <div key={i} className="shimmer" style={{ height: 160, borderRadius: 16 }} />
              ))}
            </div>
          ) : watchlist.length === 0 ? (
            <div className="glass-card p-6" style={{ textAlign: "center", color: "#475569" }}>
              Your watchlist is empty.<br/>Search a stock and click + Add
            </div>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 12 }}>
              {watchlist.map((sym, i) => (
                <WatchlistCard key={sym} symbol={sym} index={i} onRemove={handleRemoveWatchlist} />
              ))}
            </div>
          )}
        </div>

        {/* Right: Top Buy Signals (from full Nifty 200) */}
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
            <h2 style={{ fontSize: 13, fontWeight: 700, color: "#64748b", letterSpacing: "0.08em", margin: 0 }}>TOP BUY SIGNALS</h2>
            {topSignalsData?.last_computed && (
              <span style={{ fontSize: 9, color: "#334155" }}>
                {new Date(topSignalsData.last_computed).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit" })} IST
              </span>
            )}
          </div>

          {/* Source badge */}
          {topSignalsData && (
            <div style={{ marginBottom: 10, fontSize: 10, color: topSignalsData.data_source === "precomputed" ? "#22c55e" : "#f59e0b",
              display: "flex", alignItems: "center", gap: 4 }}>
              <span style={{ fontWeight: 700 }}>
                {topSignalsData.data_source === "precomputed" ? "⚡ Nifty 200" : "🔴 Live"}
              </span>
              <span style={{ color: "#334155" }}>· {topSignalsData.count} signals found</span>
            </div>
          )}

          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {!topSignalsData ? (
              [...Array(5)].map((_, i) => <div key={i} className="shimmer" style={{ height: 80, borderRadius: 12 }} />)
            ) : topSignals.length === 0 ? (
              <div className="glass-card p-4" style={{ textAlign: "center", color: "#475569", fontSize: 13 }}>
                <div style={{ fontSize: 24, marginBottom: 6 }}>🟡</div>
                No strong buy signals right now
                <div style={{ fontSize: 11, color: "#334155", marginTop: 4 }}>Next nightly scan at 4:00 PM IST</div>
              </div>
            ) : (
              topSignals.map((r, i) => (
                <motion.div
                  key={r.symbol}
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.07 }}
                >
                  <Link href={`/stock/${r.symbol}`} style={{ textDecoration: "none" }}>
                    <div className="glass-card p-3 cursor-pointer"
                      style={{ transition: "border-color 0.15s" }}
                      onMouseEnter={(e) => e.currentTarget.style.borderColor = "rgba(59,130,246,0.4)"}
                      onMouseLeave={(e) => e.currentTarget.style.borderColor = "rgba(255,255,255,0.08)"}>
                      {/* Row 1: ticker + signal */}
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                        <div>
                          <span style={{ fontSize: 14, fontWeight: 800, color: "#f1f5f9" }}>{r.ticker}</span>
                          <span style={{ marginLeft: 6, fontSize: 9, fontWeight: 700, padding: "2px 5px", borderRadius: 4,
                            background: regimeColor(r.regime) + "18", color: regimeColor(r.regime) }}>{r.regime}</span>
                        </div>
                        <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                          <span style={{ fontSize: 16, fontWeight: 800, color: scoreColor(r.score) }}>{r.score}</span>
                          <SignalBadge signal={r.signal} size="sm" />
                        </div>
                      </div>
                      {/* Row 2: price + target */}
                      {r.price && (
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "#64748b", marginBottom: 5 }}>
                          <span>₹{r.price.toLocaleString("en-IN", { maximumFractionDigits: 1 })}</span>
                          {r.target_base_5d && (
                            <span style={{ color: "#22c55e" }}>→ ₹{r.target_base_5d.toLocaleString("en-IN", { maximumFractionDigits: 1 })} (5d)</span>
                          )}
                        </div>
                      )}
                      {/* Row 3: T/F/S mini bars */}
                      <div style={{ display: "flex", gap: 4 }}>
                        {(["T", "F", "S"] as const).map((k, j) => {
                          const vals: Record<string, number> = { T: r.components.technical, F: r.components.fundamental, S: r.components.sentiment };
                          const cols = ["#3b82f6", "#a855f7", "#10b981"];
                          return (
                            <div key={k} style={{ flex: 1 }}>
                              <div style={{ fontSize: 9, color: "#475569", marginBottom: 2 }}>{k} {vals[k]}</div>
                              <div style={{ height: 3, borderRadius: 99, background: "rgba(255,255,255,0.06)" }}>
                                <div style={{ height: "100%", width: `${vals[k]}%`, background: cols[j], borderRadius: 99 }} />
                              </div>
                            </div>
                          );
                        })}
                      </div>
                      {/* Row 4: top signal reason */}
                      {r.active_signals[0] && (
                        <div style={{ marginTop: 5, fontSize: 9, color: "#334155" }}>
                          ✔ {r.active_signals[0]}
                          {r.active_signals[1] && <> · {r.active_signals[1]}</>}
                        </div>
                      )}
                    </div>
                  </Link>
                </motion.div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
