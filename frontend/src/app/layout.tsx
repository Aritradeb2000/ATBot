import "./globals.css";
import Sidebar from "@/components/layout/Sidebar";
import MarketTicker from "@/components/layout/MarketTicker";
import ThemeWrapper from "@/components/layout/ThemeWrapper";

export const metadata = {
  title: "ATBot — AI Trade Intelligence | NSE & BSE India",
  description: "AI-powered stock analysis for Indian equities. Real-time buy/sell signals, price targets, sentiment analysis, and market intelligence for NSE & BSE stocks.",
  keywords: "stock trading bot, NSE, BSE, India equity, AI trading, technical analysis, sentiment analysis",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body style={{ margin: 0, overflowX: "hidden" }}>
        <ThemeWrapper>
          <Sidebar />
          <div style={{ marginLeft: 220, minHeight: "100vh", display: "flex", flexDirection: "column" }}>
            <MarketTicker />
            <main style={{ flex: 1, padding: "24px 28px" }}>
              {children}
            </main>
          </div>
        </ThemeWrapper>
      </body>
    </html>
  );
}
