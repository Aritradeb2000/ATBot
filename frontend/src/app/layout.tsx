import type { Metadata } from "next";
import "./globals.css";
import Sidebar from "@/components/layout/Sidebar";
import MarketTicker from "@/components/layout/MarketTicker";

export const metadata: Metadata = {
  title: "ATBot — AI Trade Intelligence | NSE & BSE India",
  description: "AI-powered stock analysis for Indian equities. Real-time buy/sell signals, price targets, sentiment analysis, and market intelligence for NSE & BSE stocks.",
  keywords: "stock trading bot, NSE, BSE, India equity, AI trading, technical analysis, sentiment analysis",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ background: "#070b14", margin: 0, overflowX: "hidden" }}>
        <Sidebar />
        <div style={{ marginLeft: 220, minHeight: "100vh", display: "flex", flexDirection: "column" }}>
          <MarketTicker />
          <main style={{ flex: 1, padding: "24px 28px" }}>
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
