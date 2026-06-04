import axios from "axios";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 60000,
  headers: { "Content-Type": "application/json" },
});

// ── Types ────────────────────────────────────────────────────────────────────

export interface PositionSizing {
  suggested_quantity: number;
  investment_amount: number;
  capital_at_risk: number;
  risk_pct_of_portfolio: number;
}

export interface Analysis {
  composite_score: number;
  signal: "STRONG BUY" | "BUY" | "HOLD" | "SELL" | "STRONG SELL";
  confidence: number;
  regime: "BULL" | "SIDEWAYS" | "BEAR";
  targets: { conservative: number; base: number; aggressive: number } | null;
  stop_loss: number | null;
  risk_reward: number | null;
  position_sizing: PositionSizing | null;
  weights_used: { T: number; F: number; S: number };
  components: { technical: number; fundamental: number; sentiment: number };
}

export interface AnalysisResult {
  symbol: string;
  company_name: string;
  current_price: number | null;
  change: number | null;
  change_pct: number | null;
  analysis: Analysis;
  details: {
    technical: { score: number; signals: string[]; rsi?: number; macd?: number; atr?: number; close?: number; change?: number; change_pct?: number };
    fundamental: { score: number; flags: string[] };
    sentiment: { score: number; flags: string[]; news_breakdown: { positive: number; negative: number; neutral: number } };
  };
}

export interface NewsArticle {
  id: string;
  headline: string;
  summary: string;
  url: string;
  source: string;
  published_at: string;
  symbol: string | null;
}

export interface MarketOverview {
  indices: Record<string, { price: number; change_pct: number; high: number; low: number }>;
  india_vix: { vix: number; risk_level: string; risk_comment: string } | null;
  fii_dii: { fii_net: number; dii_net: number } | null;
  market_breadth: { advances: number; declines: number; unchanged: number } | null;
  last_updated: Record<string, string>;
}

// ── API Calls ────────────────────────────────────────────────────────────────

export async function analyzeStock(symbol: string, capital?: number): Promise<AnalysisResult> {
  const params: Record<string, string | number> = {};
  if (capital) params.capital = capital;
  const res = await api.get(`/api/analyze/${symbol.toUpperCase()}`, { params });
  return res.data;
}

export async function getMarketNews(limit = 50): Promise<NewsArticle[]> {
  const res = await api.get("/api/news/market", { params: { limit } });
  return res.data;
}

export async function getStockNews(symbol: string, limit = 10): Promise<NewsArticle[]> {
  const res = await api.get(`/api/news/${symbol.toUpperCase()}`, { params: { limit } });
  return res.data;
}

export async function getMarketOverview(): Promise<MarketOverview> {
  const res = await api.get("/api/market/overview");
  return res.data;
}

export async function healthCheck(): Promise<{ status: string }> {
  const res = await api.get("/health");
  return res.data;
}
