"use client";
import useSWR from "swr";
import { getMarketOverview, type MarketOverview } from "@/lib/api";

const fetcher = () => getMarketOverview();

export default function MarketTicker() {
  const { data } = useSWR<MarketOverview>("market-overview", fetcher, { refreshInterval: 60000 });

  const items = data
    ? Object.entries(data.indices)
        .filter(([name]) => name !== "GIFT_NIFTY")  // GIFT Nifty not yet on yfinance
        .map(([name, info]) => ({
          label: name.replace(/_/g, " "),  // INDIA_VIX -> INDIA VIX
          price: info.price,
          change: info.change_pct,
          isVix: name.includes("VIX"),
        }))
    : [
        { label: "NIFTY 50",  price: null, change: 0, isVix: false },
        { label: "SENSEX",    price: null, change: 0, isVix: false },
        { label: "INDIA VIX", price: null, change: 0, isVix: true },
      ];

  // Duplicate for seamless loop
  const all = [...items, ...items];

  return (
    <div
      style={{
        height: 40,
        background: "var(--ticker-bg)",
        borderBottom: "1px solid var(--ticker-border)",
        overflow: "hidden",
        display: "flex",
        alignItems: "center",
        transition: "background-color 0.3s ease",
      }}
    >
      <div
        className="ticker-animate"
        style={{ display: "flex", alignItems: "center", whiteSpace: "nowrap" }}
      >
        {all.map((item, i) => (
          <div
            key={i}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              padding: "0 32px",
              borderRight: "1px solid var(--ticker-border)",
            }}
          >
            <span style={{ fontSize: 11, fontWeight: 700, color: "var(--ticker-text)", letterSpacing: "0.05em" }}>{item.label}</span>
            {item.price != null ? (
              <>
                <span style={{ fontSize: 12, fontWeight: 700, color: "var(--text-primary)" }}>
                  {item.isVix ? item.price.toFixed(2) : `₹${item.price.toLocaleString("en-IN")}`}
                </span>
                {item.change !== 0 && (
                  <span
                    style={{
                      fontSize: 11,
                      fontWeight: 600,
                      color: item.change >= 0 ? "#22c55e" : "#ef4444",
                    }}
                  >
                    {item.change >= 0 ? "+" : ""}{item.change.toFixed(2)}%
                  </span>
                )}
              </>
            ) : (
              <span style={{ width: 60, height: 10 }} className="shimmer" />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
