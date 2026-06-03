"use client";
import { useState } from "react";
import useSWR from "swr";
import { motion } from "framer-motion";
import StockCard from "@/components/ui/StockCard";
import SignalBadge from "@/components/ui/SignalBadge";
import { analyzeStock, getMarketOverview, type AnalysisResult, type MarketOverview } from "@/lib/api";

import { useEffect } from "react";

// Default fallback watchlist if local storage is empty
const DEFAULT_WATCHLIST = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ITC.NS", "KOTAKBANK.NS"];
const TOP_SIGNALS_SYMBOLS = ["TCS.NS", "RELIANCE.NS", "INFY.NS", "HDFCBANK.NS", "ITC.NS"];

function useTopSignals(symbols: string[]) {
  return useSWR<AnalysisResult[]>(
    ["top-signals", symbols.join(",")],
    () => Promise.all(symbols.map((s) => analyzeStock(s))),
    { revalidateOnFocus: false, dedupingInterval: 300000 }
  );
}

function WatchlistCard({ symbol, index, onRemove }: { symbol: string, index: number, onRemove: (s: string) => void }) {
  const { data, isLoading } = useSWR<AnalysisResult>(
    ["analyze", symbol],
    () => analyzeStock(symbol),
    { revalidateOnFocus: false, dedupingInterval: 300000 }
  );

  if (isLoading) return <div className="shimmer" style={{ height: 160, borderRadius: 16 }} />;
  if (!data) return null;

  return (
    <div style={{ position: "relative" }}>
      <button 
        onClick={(e) => { e.preventDefault(); e.stopPropagation(); onRemove(symbol); }}
        style={{ position: "absolute", top: 12, right: 12, zIndex: 10, background: "rgba(0,0,0,0.5)", border: "1px solid rgba(255,255,255,0.1)", color: "#94a3b8", borderRadius: "50%", width: 24, height: 24, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", paddingBottom: 2, fontSize: 14 }}
        title="Remove from watchlist"
        onMouseOver={(e) => e.currentTarget.style.color = "#ef4444"}
        onMouseOut={(e) => e.currentTarget.style.color = "#94a3b8"}
      >
        ×
      </button>
      <StockCard symbol={data.symbol} companyName={data.company_name} price={data.current_price} analysis={data.analysis} index={index} />
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
  const { data: topData } = useTopSignals(TOP_SIGNALS_SYMBOLS);

  const topBuys = topData
    ?.filter((r) => r.analysis.signal === "BUY" || r.analysis.signal === "STRONG BUY")
    .sort((a, b) => b.analysis.composite_score - a.analysis.composite_score)
    .slice(0, 5);

  return (
    <div style={{ maxWidth: 1400 }}>
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 800, color: "#f1f5f9", margin: 0 }}>Dashboard</h1>
        <p style={{ fontSize: 13, color: "#475569", marginTop: 4 }}>AI-powered signals for NSE/BSE Indian equities</p>
      </motion.div>

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

        {/* Right: Top Buy Signals */}
        <div>
          <h2 style={{ fontSize: 13, fontWeight: 700, color: "#64748b", letterSpacing: "0.08em", marginBottom: 14 }}>TOP BUY SIGNALS</h2>
          <div className="space-y-3">
            {!topBuys ? (
              [...Array(5)].map((_, i) => <div key={i} className="shimmer" style={{ height: 64, borderRadius: 12 }} />)
            ) : topBuys.length === 0 ? (
              <div className="glass-card p-4" style={{ textAlign: "center", color: "#475569", fontSize: 13 }}>
                No strong buy signals right now
              </div>
            ) : (
              topBuys.map((r, i) => (
                <motion.a
                  key={r.symbol}
                  href={`/stock/${r.symbol}`}
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.07 }}
                  className="glass-card block p-3 cursor-pointer"
                  whileHover={{ x: -2 }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 700, color: "#f1f5f9" }}>{r.symbol.replace(".NS", "")}</div>
                      <div style={{ fontSize: 11, color: "#475569", marginTop: 1 }}>Score: {Math.round(r.analysis.composite_score)}</div>
                    </div>
                    <SignalBadge signal={r.analysis.signal} size="sm" />
                  </div>
                </motion.a>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
