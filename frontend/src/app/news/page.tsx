"use client";
import useSWR from "swr";
import { motion } from "framer-motion";
import { getMarketNews, type NewsArticle } from "@/lib/api";
import { useState } from "react";

const fetcher = (limit: number) => getMarketNews(limit);

export default function NewsPage() {
  const [activeTab, setActiveTab] = useState<"market" | "my-stocks">("market");
  const { data: articles, isLoading } = useSWR<NewsArticle[]>(
    "market-news",
    () => getMarketNews(100),
    { refreshInterval: 60000 }
  );

  const tabs = [
    { id: "market" as const,    label: "📰 Market News" },
    { id: "my-stocks" as const, label: "⭐ My Stocks" },
  ];

  const displayArticles = articles ?? [];
  const myStockSymbols = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS"];
  const filtered = activeTab === "my-stocks"
    ? displayArticles.filter((a) => a.symbol && myStockSymbols.includes(a.symbol))
    : displayArticles;

  return (
    <div style={{ maxWidth: 900 }}>
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <h1 style={{ fontSize: 24, fontWeight: 800, color: "#f1f5f9", marginBottom: 4 }}>News Feed</h1>
        <p style={{ fontSize: 13, color: "#475569", marginBottom: 24 }}>Live market news from Economic Times, Moneycontrol & Finnhub</p>
      </motion.div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 8, marginBottom: 20, borderBottom: "1px solid rgba(255,255,255,0.06)", paddingBottom: 12 }}>
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              padding: "8px 18px",
              borderRadius: 8,
              background: activeTab === tab.id ? "rgba(59,130,246,0.15)" : "transparent",
              border: activeTab === tab.id ? "1px solid rgba(59,130,246,0.35)" : "1px solid transparent",
              color: activeTab === tab.id ? "#60a5fa" : "#64748b",
              fontSize: 13,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            {tab.label}
          </button>
        ))}
        {articles && (
          <span style={{ marginLeft: "auto", fontSize: 12, color: "#334155", alignSelf: "center" }}>
            {filtered.length} articles
          </span>
        )}
      </div>

      {/* Articles */}
      {isLoading ? (
        <div className="space-y-3">
          {[...Array(8)].map((_, i) => <div key={i} className="shimmer" style={{ height: 80, borderRadius: 12 }} />)}
        </div>
      ) : filtered.length === 0 ? (
        <div className="glass-card p-8" style={{ textAlign: "center" }}>
          <div style={{ fontSize: 36, marginBottom: 12 }}>📭</div>
          <p style={{ color: "#64748b", fontSize: 13 }}>
            {activeTab === "my-stocks"
              ? "No news found for your watchlist stocks. Backend may be fetching..."
              : "No articles loaded yet. The news feed refreshes every 10 minutes."}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((article, i) => (
            <motion.a
              key={article.id}
              href={article.url}
              target="_blank"
              rel="noopener noreferrer"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.02 }}
              className="glass-card block p-4"
              style={{ textDecoration: "none" }}
              whileHover={{ x: 4 }}
            >
              <div style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
                <div style={{ flex: 1 }}>
                  <p style={{ fontSize: 14, fontWeight: 600, color: "#e2e8f0", margin: "0 0 6px", lineHeight: 1.45 }}>
                    {article.headline}
                  </p>
                  {article.summary && (
                    <p style={{ fontSize: 12, color: "#64748b", margin: "0 0 8px", lineHeight: 1.4 }}>
                      {article.summary.slice(0, 180)}{article.summary.length > 180 ? "…" : ""}
                    </p>
                  )}
                  <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                    <span style={{ fontSize: 11, color: "#3b82f6", fontWeight: 600 }}>{article.source}</span>
                    {article.symbol && (
                      <span className="metric-chip" style={{ color: "#60a5fa" }}>
                        {article.symbol.replace(".NS", "").replace(".BO", "")}
                      </span>
                    )}
                    <span style={{ fontSize: 11, color: "#334155", marginLeft: "auto" }}>
                      {article.published_at
                        ? new Date(article.published_at).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })
                        : ""}
                    </span>
                  </div>
                </div>
                <span style={{ fontSize: 18, flexShrink: 0, color: "#1e3a5f" }}>↗</span>
              </div>
            </motion.a>
          ))}
        </div>
      )}
    </div>
  );
}
