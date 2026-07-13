<div align="center">

# 🤖 ATBot

### AI-Powered Indian Equity Analysis Platform

*Technical + Fundamental + Sentiment intelligence → Buy/Sell signals with 5–10 day price targets*

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-14-000000?style=for-the-badge&logo=next.js&logoColor=white)](https://nextjs.org)
[![Market](https://img.shields.io/badge/Market-NSE%20%7C%20BSE-FF6B35?style=for-the-badge)](https://nseindia.com)
[![Status](https://img.shields.io/badge/Status-Active%20Development-brightgreen?style=for-the-badge)]()

</div>

---

## 📌 What is ATBot?

**ATBot** is a personal AI-driven stock analysis platform built exclusively for the **Indian equity market (NSE/BSE)**. It analyzes every stock across three intelligence engines — Technical, Fundamental, and Sentiment — combines them into a single composite score, and generates **Buy/Sell signals with realistic 5–10 day price targets**.

What makes ATBot unique is its **self-improving Meta-Learner**: the system tracks whether its own signals succeeded or failed, and automatically rebalances how much it trusts each engine — separately for Bull, Bear, and Sideways market regimes.

> Built for traders who want data-backed conviction, not gut feel.

---

## ✨ Key Features

### 🧠 Meta-Learner v2 — Self-Improving Intelligence
The engine weights are **not fixed**. ATBot tracks every signal's outcome at Day 5 and Day 10, and re-trains its own weights nightly:

| Feature | Detail |
|---|---|
| **Regime-conditioned** | Separate weight sets for BULL / BEAR / SIDEWAYS markets |
| **EWMA Decay** | λ=0.92 → recent outcomes weighted 5× more than 3-week-old ones |
| **Confidence-weighted** | High-confidence wrong predictions penalise the engine harder |
| **Signal-type aware** | BUY and SELL signal correctness computed differently |
| **Transparent** | Learn page shows per-regime weights, sample counts, training status |

### 📊 Three-Engine Scoring System
| Engine | What It Analyzes | Default Weight |
|---|---|---|
| **Technical** | RSI, MACD, EMA crossovers, Bollinger Bands, Volume, Supertrend, Candlestick patterns | 45% |
| **Fundamental** | P/E, EPS growth, ROE, Debt/Equity, Promoter holding, Revenue growth | 30% |
| **Sentiment** | News sentiment via FinBERT NLP, FII/DII flow, Market tone | 25% |

> Weights shift automatically based on what the Meta-Learner has learned in each regime.

### ⚡ Instant Screener — Nifty 200
- **Pre-computed nightly at 4:00 PM IST** — no waiting, results load in <100ms
- **200 stocks** scanned daily (Nifty 200 universe)
- **Instant DB reads** for standard universes; live scan for custom watchlists
- Pre-built strategies: Breakout Scanner | Reversal Candidates
- Custom filters: Signal type, Composite score, RSI range

### 🎯 Signals & Price Targets
- **5-tier signal system:** Strong Buy → Strong Sell with Confidence %
- **3-scenario price targets:** Conservative / Base / Aggressive (5-day & 10-day)
- **AI-determined stop loss** based on setup type and volatility (ATR)
- **Risk:Reward ratio** displayed for every signal

### 🗓️ Fully Automated Daily Pipeline
```
3:15 PM  →  Nifty 50 meta-learner scan (regime-labelled training data)
4:00 PM  →  Nifty 200 nightly pre-computation (186+ stocks → DB)
6:30 PM  →  Outcome tracker (D5/D10 WIN/LOSS evaluation)
6:30 PM  →  Meta-Learner v2 weight update (per-regime EWMA retraining)
6:30 PM  →  PDF accuracy report auto-generated
```

### 📈 Portfolio Allocation Optimizer
- Mean-Variance Optimization (Markowitz Efficient Frontier)
- Three risk profiles: Conservative / Moderate / Aggressive
- ATBot signal-weighted allocation adjustments
- Max drawdown and Sharpe ratio estimates

### 🌅 Morning Briefing (8:45 AM IST)
Daily automated summary before market open:
- 🌍 Global cues (SGX Nifty, Dow, Crude, Gold, USD/INR)
- 🏦 FII/DII net flow + 3-day trend
- 📅 Earnings scheduled this week
- 📊 India VIX level + market risk assessment

### 📰 Live News Feed
Real-time news from Economic Times, Moneycontrol, LiveMint, Business Standard — organized in 3 tabs: **My Stocks | Market | Global**

### 📚 Learn Page — Accuracy Tracking
- Win rate by signal type (BUY / SELL / STRONG BUY…)
- Monthly win rate trend chart
- Best and worst performing stocks
- Engine score correlation (Technical vs Fundamental vs Sentiment)
- Meta-Learner v2 weight card with regime breakdown
- PDF accuracy report download (filterable by Day 5 or Day 10)

---

## 🏗️ Architecture

```
ATBot
├── 📡 Data Layer
│   ├── yfinance          → Historical OHLCV (NSE/BSE, 6-month daily)
│   ├── nsepython         → Live NSE quotes + FII/DII data
│   ├── RSS Feeds         → Real-time news (ET, MC, Mint, BS)
│   ├── Finnhub API       → Ticker-specific news
│   └── FMP API           → Fundamental financial data
│
├── 🧠 Intelligence Layer
│   ├── Technical Engine  → 15+ pandas-ta indicators + pattern scoring
│   ├── Fundamental Engine→ Financial ratio scoring + sector comparison
│   ├── Sentiment Engine  → FinBERT NLP on news headlines
│   ├── Ensemble Scorer   → Regime-aware composite score + price target
│   ├── Meta-Learner v2   → EWMA + regime-conditioned weight retraining
│   └── Outcome Tracker   → D5/D10 signal evaluation (WIN/LOSS/BREAKEVEN)
│
├── ⚡ API Layer (FastAPI)
│   ├── /api/analyze/{symbol}         → Full stock analysis
│   ├── /api/screener                 → Instant pre-computed screener
│   ├── /api/screener/status          → Nightly job status
│   ├── /api/screener/trigger-nightly → Manual trigger
│   ├── /api/learn/*                  → Win rate, outcomes, meta-weights
│   ├── /api/optimizer/run            → Portfolio optimization
│   └── /api/market/*                 → FII/DII, breadth, VIX
│
└── 🎨 Frontend (Next.js 14)
    ├── /              → Dashboard (live market overview)
    ├── /stock/[sym]   → Deep-dive analysis page
    ├── /screener      → Instant Nifty 200 screener
    ├── /market        → Market intelligence
    ├── /news          → Live news feed
    ├── /learn         → Accuracy & meta-learner tracking
    └── /optimizer     → Portfolio allocation tool
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.11+, FastAPI, Uvicorn |
| **ML / NLP** | HuggingFace Transformers (FinBERT) |
| **Technical Analysis** | pandas-ta (15+ indicators) |
| **Market Data** | yfinance, nsepython |
| **Task Scheduler** | APScheduler (IST timezone) |
| **Database** | SQLite (dev) → PostgreSQL (production) |
| **ORM** | SQLAlchemy 2.0 (async) |
| **Frontend** | Next.js 14, TypeScript, Vanilla CSS, Framer Motion |
| **Charts** | TradingView Lightweight Charts |

---

## 📁 Project Structure

```
atbot/
├── backend/
│   ├── data/
│   │   ├── market_data.py        # yfinance OHLCV fetcher
│   │   ├── nse_live.py           # Live NSE quotes + FII/DII
│   │   ├── news_feed.py          # RSS + Finnhub news ingestion
│   │   ├── fundamentals.py       # Financial ratios (yfinance + FMP)
│   │   ├── nse_universe.py       # Curated Nifty 50/100/200 symbol lists
│   │   └── scheduler.py          # APScheduler background jobs
│   ├── engines/
│   │   ├── technical_engine.py   # TA indicators + pattern scoring
│   │   ├── fundamental_engine.py # Ratio scoring
│   │   ├── sentiment_engine.py   # FinBERT NLP pipeline
│   │   ├── ensemble_scorer.py    # Composite score + price target + regime detection
│   │   ├── meta_learner.py       # v2: EWMA + regime-conditioned weight retraining
│   │   ├── outcome_tracker.py    # D5/D10 WIN/LOSS evaluation
│   │   └── report_generator.py   # PDF accuracy report (FPDF)
│   ├── api/
│   │   ├── main.py               # FastAPI application
│   │   └── routes/               # Screener, Learn, Market, Optimizer…
│   ├── models/
│   │   ├── database.py           # Async SQLAlchemy engine
│   │   └── schemas.py            # DB models (AnalysisScore, SignalOutcome, UserSettings)
│   ├── config.py                 # Settings + constants
│   └── requirements.txt
├── frontend/
│   ├── src/app/                  # Next.js App Router pages
│   ├── src/components/           # Reusable UI components
│   └── src/lib/                  # API client (api.ts)
├── .env.example
└── README.md
```

---

## 🚀 Getting Started

### Prerequisites
- Python 3.11+
- Node.js 18+

### 1. Clone the Repository
```bash
git clone https://github.com/Aritradeb2000/ATBot.git
cd ATBot
```

### 2. Configure Environment
```bash
cp .env.example .env
# Edit .env and add your free API keys:
# - FINNHUB_API_KEY  → https://finnhub.io (free tier)
# - NEWSAPI_KEY      → https://newsapi.org (free tier)
# - FMP_API_KEY      → https://financialmodelingprep.com (free tier)
```

### 3. Set Up Python Environment
```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

pip install -r backend/requirements.txt
```

### 4. Start the Backend
```bash
uvicorn backend.api.main:app --reload --port 8000
```

### 5. Install & Start Frontend
```bash
cd frontend
npm install
npm run dev
```

### 6. Open ATBot
Navigate to `http://localhost:3000`

> On first launch, the Meta-Learner has no training data. Use ATBot daily for 1–2 weeks and the adaptive weights will kick in as D5/D10 outcomes accumulate.

---

## 📡 API Reference

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/analyze/{symbol}` | Full 3-engine analysis for a stock |
| GET | `/api/screener` | Screener (pre-computed for nifty50/nifty200, live for custom) |
| GET | `/api/screener/status` | Nightly pre-computation job status |
| POST | `/api/screener/trigger-nightly` | Manually trigger Nifty 200 pre-computation |
| GET | `/api/market/breadth` | NSE advance/decline, FII/DII, VIX |
| GET | `/api/learn/stats` | Win rate, signal breakdown, monthly trend |
| GET | `/api/learn/meta-weights` | Current regime-conditioned adaptive weights |
| POST | `/api/learn/trigger-meta` | Manually re-run Meta-Learner v2 |
| GET | `/api/learn/report` | Download PDF accuracy report |
| POST | `/api/optimizer/run` | Run portfolio allocation optimization |

---

## 🆓 Free API Keys Required

| API | Purpose | Free Limit | Sign Up |
|---|---|---|---|
| Finnhub | Stock news | 60 calls/min | [finnhub.io](https://finnhub.io) |
| NewsAPI | Market news | 100 calls/day | [newsapi.org](https://newsapi.org) |
| Financial Modeling Prep | Fundamentals | 250 calls/day | [financialmodelingprep.com](https://financialmodelingprep.com) |
| yfinance | OHLCV data | Unlimited (unofficial) | No key needed |
| nsepython | Live NSE data | Unlimited (unofficial) | No key needed |

---

## 📈 Signal System

| Score | Signal | Meaning |
|---|---|---|
| 75 – 100 | 🟢 **Strong Buy** | High conviction, all engines aligned |
| 60 – 74 | 🟩 **Buy** | Good setup with positive bias |
| 45 – 59 | 🟡 **Hold** | Mixed signals, wait for clarity |
| 30 – 44 | 🟧 **Sell** | Negative bias, consider exiting |
| 0 – 29 | 🔴 **Strong Sell** | High conviction bearish signal |

---

## 🧠 How the Meta-Learner Works

```
Every day at 3:15 PM — Bot generates signals with regime label (BULL/BEAR/SIDEWAYS)
Every day at 6:30 PM — Outcome tracker evaluates: did the D5/D10 price target hit?
                         → Records WIN / LOSS / BREAKEVEN for each signal
                       — Meta-Learner v2 runs:
                         1. Pulls last 60 days of WIN/LOSS outcomes
                         2. Groups by regime (BULL / BEAR / SIDEWAYS)
                         3. Per regime: computes EWMA-decayed, confidence-weighted
                            predictive power for each engine (T / F / S)
                         4. Blends learned weights with base (α increases with sample count)
                         5. Saves 9 weights (3 engines × 3 regimes) to DB
Every stock analysis — Detects current market regime → uses that regime's weights
```

**Example**: If Fundamental engine is consistently right in BEAR markets but Technical is wrong, the bot will automatically increase Fundamental weight in BEAR regime and decrease Technical — without any manual intervention.

---

## ⚠️ Disclaimer

> ATBot is a **personal analysis tool** and does **not** constitute financial advice. All signals and recommendations are algorithmic outputs for informational purposes only. Always do your own research before making any investment decisions. Past signal performance does not guarantee future results.

---

## 📄 License

This project is for personal use. All rights reserved.

---

## 🙏 Acknowledgements

- [yfinance](https://github.com/ranaroussi/yfinance) — Market data
- [pandas-ta](https://github.com/twopirllc/pandas-ta) — Technical analysis
- [FinBERT](https://huggingface.co/ProsusAI/finbert) — Financial sentiment NLP
- [nsepython](https://github.com/stocksdeveloper/nsepython) — NSE live data
- [TradingView](https://tradingview.com) — Charting library
- [APScheduler](https://apscheduler.readthedocs.io) — Background job scheduling

---

<div align="center">
  <sub>Built with ❤️ for the Indian equity market</sub>
</div>
