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

export interface ScreenerResult {
  symbol: string;
  company_name: string;
  price: number | null;
  change: number | null;
  change_pct: number | null;
  score: number;
  signal: "STRONG BUY" | "BUY" | "HOLD" | "SELL" | "STRONG SELL";
  confidence: number;
  regime: "BULL" | "SIDEWAYS" | "BEAR";
  rsi: number | null;
  atr: number | null;
  components: { technical: number; fundamental: number; sentiment: number };
  signals: string[];
}

export interface ScreenerResponse {
  total_scanned: number;
  total_found: number;
  total_filtered: number;
  preset: string;
  universe: string;
  results: ScreenerResult[];
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

export interface ScreenerParams {
  universe?: string;
  symbols?: string;   // comma-separated when universe=custom
  signal?: string;
  min_score?: number;
  min_rsi?: number;
  max_rsi?: number;
  preset?: string;
  sort_by?: string;
  limit?: number;
}

export async function runScreener(params: ScreenerParams = {}): Promise<ScreenerResponse> {
  const res = await api.get("/api/screener", {
    params,
    timeout: 120000,  // 2 min timeout for full Nifty 50 scan
  });
  return res.data;
}

// -- Market Intelligence --
export interface FiiDiiPoint { date: string; fii_net: number; dii_net: number; }
export interface VixPoint { date: string; vix: number; }
export interface SectorPoint { sector: string; price: number; change_pct: number; }
export async function getFiiHistory(days = 30): Promise<FiiDiiPoint[]> { const res = await api.get('/api/market/fii-history', { params: { days } }); return res.data; }
export async function getVixHistory(days = 30): Promise<VixPoint[]> { const res = await api.get('/api/market/vix-history', { params: { days } }); return res.data; }
export async function getSectorHeatmap(): Promise<SectorPoint[]> { const res = await api.get('/api/market/sector-heatmap'); return res.data; }

// -- Settings --
export interface UserSettings { user_id: string; capital: number; risk_profile: string; alert_signal_change: boolean; alert_strong_signals_only: boolean; alert_volume_spike: boolean; alert_vix_threshold: number; alert_fii_threshold: number; notify_browser: boolean; notify_telegram: boolean; telegram_chat_id: string | null; screener_default_universe: string; screener_default_sort: string; updated_at: string | null; }
export async function getSettings(): Promise<UserSettings> { const res = await api.get('/api/settings'); return res.data; }
export async function saveSettings(data: Partial<UserSettings>): Promise<{ status: string; settings: UserSettings }> { const res = await api.put('/api/settings', data); return res.data; }

// -- Learn --
export interface LearnStats { total_signals: number; total_resolved: number; overall_win_rate: number; avg_pnl_pct: number; avg_pnl_wins: number; avg_loss_pct: number; by_signal: Record<string, { total: number; wins: number; losses: number; win_rate: number; avg_pnl: number }>; monthly_trend: Array<{ month: string; total: number; wins: number; win_rate: number; avg_pnl: number }>; by_component: Record<string, { wins_avg: number; losses_avg: number }>; top_stocks: Array<{ symbol: string; total: number; win_rate: number; avg_pnl: number }>; worst_stocks: Array<{ symbol: string; total: number; win_rate: number; avg_pnl: number }>; has_data: boolean; }
export interface OutcomeRecord { symbol: string; signal: string; entry_date: string; check_day: number; entry_price: number; price_at_check: number; pnl_percent: number; outcome: string; outcome_detail: string; composite_score: number; }
export async function getLearnStats(days?: number, checkDay?: number): Promise<LearnStats> { const res = await api.get('/api/learn/stats', { params: { days, check_day: checkDay } }); return res.data; }
export async function getRecentOutcomes(limit?: number): Promise<OutcomeRecord[]> { const res = await api.get('/api/learn/recent', { params: { limit } }); return res.data; }
export async function triggerOutcomeCheck(): Promise<{ status: string; new_outcomes: number }> { const res = await api.post('/api/learn/trigger'); return res.data; }
