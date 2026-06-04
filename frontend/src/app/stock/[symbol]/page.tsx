"use client";
import { useState, useEffect } from "react";
import useSWR from "swr";
import { motion } from "framer-motion";
import dynamic from "next/dynamic";
import ScoreGauge from "@/components/ui/ScoreGauge";
import SignalBadge from "@/components/ui/SignalBadge";
import PriceTargetBar from "@/components/ui/PriceTargetBar";
import { analyzeStock, getStockNews, type AnalysisResult, type NewsArticle } from "@/lib/api";

// TradingView chart is client-only (no SSR)
const TradingViewChart = dynamic(() => import("@/components/charts/TradingViewChart"), { ssr: false });

interface Props {
  params: { symbol: string };
}

export default function StockDetailPage({ params }: Props) {
  const { symbol } = params;
  const decodedSymbol = decodeURIComponent(symbol).toUpperCase();

  // Read capital from localStorage
  const capital = typeof window !== "undefined"
    ? parseFloat(localStorage.getItem("atbot_capital") || "0") || undefined
    : undefined;

  const [inWatchlist, setInWatchlist] = useState(false);
  const [mounted, setMounted] = useState(false);

  const RANGES = [
    { label: "1M", period: "1mo", interval: "1d" },
    { label: "3M", period: "3mo", interval: "1d" },
    { label: "6M", period: "6mo", interval: "1d" },
    { label: "1Y", period: "1y",  interval: "1wk" },
  ];
  const [activeRange, setActiveRange] = useState(RANGES[2]);

  useEffect(() => {
    const stored = localStorage.getItem("atbot_watchlist");
    if (stored) {
      try {
        const wl = JSON.parse(stored);
        setInWatchlist(wl.includes(decodedSymbol));
      } catch { }
    }
    setMounted(true);
  }, [decodedSymbol]);

  const toggleWatchlist = () => {
    try {
      const stored = localStorage.getItem("atbot_watchlist");
      let wl = stored ? JSON.parse(stored) : ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ITC.NS", "KOTAKBANK.NS"];
      if (inWatchlist) {
        wl = wl.filter((s: string) => s !== decodedSymbol);
      } else {
        if (!wl.includes(decodedSymbol)) wl = [decodedSymbol, ...wl];
      }
      localStorage.setItem("atbot_watchlist", JSON.stringify(wl));
      setInWatchlist(!inWatchlist);
    } catch (e) {
      console.error("Failed to update watchlist", e);
    }
  };

  const { data, isLoading, error } = useSWR<AnalysisResult>(
    ["analyze", decodedSymbol, capital],
    () => analyzeStock(decodedSymbol, capital),
    { revalidateOnFocus: false }
  );

  const { data: newsData } = useSWR<NewsArticle[]>(
    ["news", decodedSymbol],
    () => getStockNews(decodedSymbol, 5),
    { revalidateOnFocus: false }
  );

  const [activeTab, setActiveTab] = useState<"signals" | "fundamental" | "sentiment">("signals");

  if (isLoading) {
    return (
      <div style={{ maxWidth: 1200 }}>
        <div className="shimmer" style={{ height: 32, width: 260, borderRadius: 8, marginBottom: 24 }} />
        <div className="shimmer" style={{ height: 420, borderRadius: 16, marginBottom: 20 }} />
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 20 }}>
          {[...Array(3)].map((_, i) => <div key={i} className="shimmer" style={{ height: 280, borderRadius: 16 }} />)}
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="glass-card p-8" style={{ textAlign: "center", maxWidth: 480, margin: "80px auto" }}>
        <div style={{ fontSize: 40, marginBottom: 16 }}>⚠️</div>
        <h2 style={{ color: "#f1f5f9", marginBottom: 8 }}>Could not analyze {decodedSymbol}</h2>
        <p style={{ color: "#64748b", fontSize: 13 }}>Make sure the backend is running and the symbol is valid (e.g. RELIANCE.NS)</p>
        <a href="/" style={{ display: "inline-block", marginTop: 16, color: "#60a5fa", fontSize: 13 }}>← Back to Dashboard</a>
      </div>
    );
  }

  const { analysis, details, company_name, current_price } = data;
  const ticker = decodedSymbol.replace(".NS", "").replace(".BO", "");

  // Build a simple chart placeholder (OHLCV would need a separate endpoint)
  const placeholderData: { time: string; open: number; high: number; low: number; close: number }[] = [];

  return (
    <div style={{ maxWidth: 1200 }}>
      {/* Breadcrumb */}
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} style={{ marginBottom: 20 }}>
        <a href="/" style={{ fontSize: 12, color: "#475569" }}>Dashboard</a>
        <span style={{ color: "#334155", margin: "0 6px" }}>›</span>
        <span style={{ fontSize: 12, color: "#94a3b8" }}>{ticker}</span>
      </motion.div>

      {/* Stock Header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 20 }}
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
            <h1 style={{ fontSize: 28, fontWeight: 800, color: "#f1f5f9", margin: 0 }}>{ticker}</h1>
            {mounted && (
              <button
                onClick={toggleWatchlist}
                style={{
                  background: inWatchlist ? "rgba(245,158,11,0.1)" : "rgba(255,255,255,0.05)",
                  border: `1px solid ${inWatchlist ? "rgba(245,158,11,0.3)" : "rgba(255,255,255,0.1)"}`,
                  color: inWatchlist ? "#fcd34d" : "#94a3b8",
                  padding: "6px 12px",
                  borderRadius: 20,
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  transition: "all 0.2s"
                }}
              >
                {inWatchlist ? "★ Saved" : "☆ Add to Watchlist"}
              </button>
            )}
            <SignalBadge signal={analysis.signal} confidence={analysis.confidence} size="lg" />
            <span
              className="metric-chip"
              style={{
                color: analysis.regime === "BULL" ? "#22c55e" : analysis.regime === "BEAR" ? "#ef4444" : "#f59e0b",
              }}
            >
              {analysis.regime} Market
            </span>
          </div>
          <p style={{ fontSize: 13, color: "#64748b", marginTop: 4 }}>{company_name}</p>
        </div>
        <div style={{ textAlign: "right" }}>
          {current_price && (
            <div style={{ fontSize: 32, fontWeight: 800, color: "#f1f5f9" }}>
              ₹{current_price.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
            </div>
          )}
          <div style={{ fontSize: 12, color: "#475569", marginTop: 2 }}>
            ATR: ₹{details.technical.atr?.toFixed(2) ?? "—"}
          </div>
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.1 }}
        className="glass-card"
        style={{ marginBottom: 20, overflow: "hidden" }}
      >
        <div style={{ padding: "12px 20px", borderBottom: "1px solid rgba(255,255,255,0.06)", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10 }}>
          <div>
            <span style={{ fontSize: 13, fontWeight: 600, color: "#94a3b8" }}>
              📊 {ticker} — Interactive Chart
            </span>
            <span style={{ fontSize: 11, color: "#475569", marginLeft: 10 }}>
              Candlestick · Target lines (SL, T1, T2, T3) shown if available
            </span>
          </div>
          {/* Range toggle pills */}
          <div style={{ display: "flex", gap: 4, background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 20, padding: "3px 4px" }}>
            {RANGES.map((r) => {
              const isActive = r.label === activeRange.label;
              return (
                <button
                  key={r.label}
                  onClick={() => setActiveRange(r)}
                  style={{
                    padding: "4px 13px",
                    borderRadius: 16,
                    border: "none",
                    cursor: "pointer",
                    fontSize: 11,
                    fontWeight: 700,
                    letterSpacing: "0.04em",
                    transition: "all 0.18s",
                    background: isActive ? "linear-gradient(135deg, #3b82f6, #6366f1)" : "transparent",
                    color: isActive ? "#fff" : "#64748b",
                  }}
                >
                  {r.label}
                </button>
              );
            })}
          </div>
        </div>
        <TradingViewChart 
          symbol={decodedSymbol}
          period={activeRange.period}
          interval={activeRange.interval}
          height={480} 
          targets={analysis.targets && analysis.stop_loss ? {
            stopLoss: analysis.stop_loss,
            conservative: analysis.targets.conservative,
            base: analysis.targets.base,
            aggressive: analysis.targets.aggressive,
          } : undefined}
        />
      </motion.div>

      {/* 3-col info grid */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 20 }}>

        {/* Score Gauges */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }} className="glass-card p-6">
          <h3 style={{ fontSize: 12, fontWeight: 700, color: "#64748b", letterSpacing: "0.08em", marginBottom: 20 }}>ENGINE SCORES</h3>
          <div style={{ display: "flex", justifyContent: "space-around", marginBottom: 20 }}>
            <ScoreGauge score={analysis.components.technical}    label="Technical"    size={100} />
            <ScoreGauge score={analysis.components.fundamental}  label="Fundamental"  size={100} />
            <ScoreGauge score={analysis.components.sentiment}    label="Sentiment"    size={100} />
          </div>

          {/* Engine weights */}
          <div style={{ borderTop: "1px solid rgba(255,255,255,0.06)", paddingTop: 14 }}>
            <div style={{ fontSize: 11, color: "#475569", marginBottom: 8, fontWeight: 600 }}>DYNAMIC WEIGHTS</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 6 }}>
              {[
                { label: "Technical", val: analysis.weights_used.T },
                { label: "Fundamental", val: analysis.weights_used.F },
                { label: "Sentiment", val: analysis.weights_used.S },
              ].map(({ label, val }) => (
                <div key={label} style={{ textAlign: "center", padding: "6px 4px", background: "rgba(255,255,255,0.04)", borderRadius: 8 }}>
                  <div style={{ fontSize: 16, fontWeight: 700, color: "#60a5fa" }}>{Math.round(val * 100)}%</div>
                  <div style={{ fontSize: 9, color: "#475569", fontWeight: 600 }}>{label.toUpperCase().slice(0, 4)}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Tab: signals / fundamental / sentiment */}
          <div style={{ marginTop: 16, borderTop: "1px solid rgba(255,255,255,0.06)", paddingTop: 14 }}>
            <div style={{ display: "flex", gap: 4, marginBottom: 12 }}>
              {(["signals", "fundamental", "sentiment"] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  style={{
                    fontSize: 10, fontWeight: 600, padding: "4px 10px", borderRadius: 6,
                    background: activeTab === tab ? "rgba(59,130,246,0.2)" : "transparent",
                    border: activeTab === tab ? "1px solid rgba(59,130,246,0.4)" : "1px solid transparent",
                    color: activeTab === tab ? "#60a5fa" : "#475569",
                    cursor: "pointer",
                    textTransform: "capitalize",
                  }}
                >
                  {tab}
                </button>
              ))}
            </div>
            {activeTab === "signals" && (
              <ul style={{ listStyle: "none", padding: 0, margin: 0, space: 4 }}>
                {details.technical.signals.map((s, i) => (
                  <li key={i} style={{ fontSize: 11, color: "#94a3b8", padding: "3px 0", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                    {s.startsWith("Error") ? `⚠ ${s}` : `• ${s}`}
                  </li>
                ))}
              </ul>
            )}
            {activeTab === "fundamental" && (
              <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                {details.fundamental.flags.map((f, i) => {
                  const isNegative = f.includes("Negative") || f.includes("Expensive") || f.includes("High Debt") || f.includes("Low ROE") || f.includes("Low Promoter") || f.includes("Low Profit");
                  return (
                    <li key={i} style={{ fontSize: 11, color: isNegative ? "#ef4444" : "#86efac", padding: "3px 0", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                      {isNegative ? "✗ " : "✓ "} {f.replace("⚠️ ", "")}
                    </li>
                  );
                })}
              </ul>
            )}
            {activeTab === "sentiment" && (
              <div style={{ space: 8 }}>
                {details.sentiment.flags.map((f, i) => (
                  <div key={i} style={{ fontSize: 11, color: "#94a3b8", padding: "3px 0" }}>• {f}</div>
                ))}
                <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                  {Object.entries(details.sentiment.news_breakdown).map(([k, v]) => (
                    <div key={k} style={{ flex: 1, textAlign: "center", background: "rgba(255,255,255,0.04)", borderRadius: 8, padding: "6px 4px" }}>
                      <div style={{ fontSize: 16, fontWeight: 700, color: k === "positive" ? "#22c55e" : k === "negative" ? "#ef4444" : "#f59e0b" }}>{v}</div>
                      <div style={{ fontSize: 9, color: "#475569", textTransform: "uppercase" }}>{k}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </motion.div>

        {/* Price Targets + Position Sizing */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="glass-card p-6">
          <h3 style={{ fontSize: 12, fontWeight: 700, color: "#64748b", letterSpacing: "0.08em", marginBottom: 20 }}>PRICE TARGETS</h3>

          {analysis.targets && analysis.stop_loss && current_price ? (
            <>
              <PriceTargetBar
                currentPrice={current_price}
                stopLoss={analysis.stop_loss}
                conservative={analysis.targets.conservative}
                base={analysis.targets.base}
                aggressive={analysis.targets.aggressive}
              />

              <div style={{ marginTop: 20, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                {[
                  { label: "Stop Loss", val: analysis.stop_loss, color: "#ef4444" },
                  { label: "Risk/Reward", val: null, raw: `1 : ${analysis.risk_reward}`, color: "#60a5fa" },
                  { label: "T1 (Conservative)", val: analysis.targets.conservative, color: "#86efac" },
                  { label: "T2 (Base)", val: analysis.targets.base, color: "#4ade80" },
                  { label: "T3 (Aggressive)", val: analysis.targets.aggressive, color: "#22c55e" },
                ].map(({ label, val, raw, color }) => (
                  <div key={label} style={{ padding: "8px 10px", borderRadius: 8, background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}>
                    <div style={{ fontSize: 9, color: "#475569", fontWeight: 600, marginBottom: 2 }}>{label}</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color }}>
                      {raw ?? (val ? `₹${val.toLocaleString("en-IN")}` : "—")}
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div style={{ textAlign: "center", color: "#475569", fontSize: 13, padding: "40px 0" }}>
              Price targets are shown for BUY signals only.<br />
              <span style={{ fontSize: 11, marginTop: 6, display: "block" }}>Current signal: {analysis.signal}</span>
            </div>
          )}

          {/* Position Sizing */}
          {analysis.position_sizing && (
            <div style={{ marginTop: 20, padding: "14px", borderRadius: 12, background: "rgba(59,130,246,0.08)", border: "1px solid rgba(59,130,246,0.2)" }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: "#60a5fa", marginBottom: 10 }}>💼 POSITION SIZING</div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                {[
                  { label: "Qty", val: `${analysis.position_sizing.suggested_quantity} shares` },
                  { label: "Invest", val: `₹${analysis.position_sizing.investment_amount.toLocaleString("en-IN")}` },
                  { label: "Capital at Risk", val: `₹${analysis.position_sizing.capital_at_risk.toLocaleString("en-IN")}` },
                  { label: "Portfolio Risk", val: `${analysis.position_sizing.risk_pct_of_portfolio}%` },
                ].map(({ label, val }) => (
                  <div key={label}>
                    <div style={{ fontSize: 9, color: "#475569" }}>{label}</div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: "#93c5fd" }}>{val}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </motion.div>

        {/* News */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }} className="glass-card p-6">
          <h3 style={{ fontSize: 12, fontWeight: 700, color: "#64748b", letterSpacing: "0.08em", marginBottom: 16 }}>RECENT NEWS</h3>
          <div className="space-y-3">
            {!newsData || newsData.length === 0 ? (
              <p style={{ fontSize: 12, color: "#475569" }}>No news found for {ticker}. Finnhub API key may be needed.</p>
            ) : (
              newsData.map((article) => (
                <a key={article.id} href={article.url} target="_blank" rel="noopener noreferrer" style={{ display: "block", textDecoration: "none" }}>
                  <div style={{ padding: "10px 12px", borderRadius: 10, background: "rgba(255,255,255,0.04)", border: "1px solid transparent", transition: "border-color 0.15s" }}
                    onMouseEnter={(e) => (e.currentTarget.style.borderColor = "rgba(59,130,246,0.3)")}
                    onMouseLeave={(e) => (e.currentTarget.style.borderColor = "transparent")}
                  >
                    <p style={{ fontSize: 12, fontWeight: 600, color: "#e2e8f0", margin: "0 0 6px", lineHeight: 1.4 }}>{article.headline}</p>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "#475569" }}>
                      <span>{article.source}</span>
                      <span>{new Date(article.published_at).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}</span>
                    </div>
                  </div>
                </a>
              ))
            )}
          </div>
        </motion.div>
      </div>
    </div>
  );
}
