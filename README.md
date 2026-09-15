<div align="center">

# 🤖 ATBot

### AI-Powered Indian Equity Analysis Platform

*Technical + Fundamental + Sentiment intelligence → Regime-aware Buy/Sell signals with conviction-scaled price targets*

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-14-000000?style=for-the-badge&logo=next.js&logoColor=white)](https://nextjs.org)
[![Market](https://img.shields.io/badge/Market-NSE%20%7C%20BSE-FF6B35?style=for-the-badge)](https://nseindia.com)
[![Status](https://img.shields.io/badge/Status-Active%20Development-brightgreen?style=for-the-badge)](https://github.com/Aritradeb2000/ATBot)

</div>

---

## 📌 What is ATBot?

**ATBot** is a personal AI-driven stock analysis platform built exclusively for the **Indian equity market (NSE/BSE)**. It analyzes every stock across three intelligence engines — Technical, Fundamental, and Sentiment — combines them into a single composite score, and generates **regime-aware Buy/Sell signals with conviction-scaled price targets and position sizing**.

What makes ATBot unique is its **self-improving Meta-Learner v2**: the system tracks whether its own signals succeeded or failed at Day 5 and Day 10, and automatically rebalances how much it trusts each engine — separately for Bull, Bear, and Sideways market regimes.

> Built for traders who want data-backed conviction, not gut feel.

---

## ✨ Key Features

### 🧠 Meta-Learner v2 — Self-Improving Intelligence
Engine weights are **not fixed**. ATBot tracks every signal's outcome at D5 and D10, and re-trains its own weights nightly:

| Feature | Detail |
|---|---|
| **Regime-conditioned** | Separate weight sets for BULL / BEAR / SIDEWAYS markets |
| **EWMA Decay** | λ=0.92 → recent outcomes weighted ~5× more than 3-week-old data |
| **Confidence-weighted** | High-confidence wrong predictions penalise the engine harder |
| **Signal-type aware** | BUY and SELL signal correctness evaluated independently |
| **Transparent** | Learn page shows per-regime weights, sample counts, training status |

### 🌐 Multi-Factor Market Regime Detection v2
Regime is not a simple threshold — it is a **4-factor point scoring system**:

| Factor | BULL | BEAR | Notes |
|---|---|---|---|
| NIFTY 20-day trend | ≥ +4% → +2 pts | ≤ -5% → -2 pts | Primary gate: non-trend factors cannot override |
| India VIX | < 14 (only if trend ≥ 0) → +1 | > 20 → -1 | Asymmetric: calm selloffs are still selloffs |
| Market breadth | > 65% advancing → +1 | < 40% advancing → -1 | Asymmetric thresholds (BULL harder to earn) |
| FII 5-day flow | > ₹3,000 Cr net buy → +1 | < -₹3,000 Cr net sell → -1 | Sourced from live cache |

**Trend gate:** A regime of BULL or BEAR requires the trend factor to have a non-zero contribution in the correct direction. Extreme VIX + FII alone cannot force a BEAR call on a flat market.

### 📊 Three-Engine Scoring System
| Engine | What It Analyzes | Default Weight |
|---|---|---|
| **Technical** | RSI, MACD, EMA crossovers, Bollinger Bands, Volume, Supertrend, Candlestick patterns | 45% |
| **Fundamental** | P/E, EPS growth, ROE, Debt/Equity, Promoter holding, Revenue growth | 30% |
| **Sentiment** | News sentiment via FinBERT NLP, FII/DII flow, Market tone | 25% |

> Weights shift automatically based on what the Meta-Learner has learned in each regime.
> Missing engines are **excluded from the composite** and their weight redistributed across present engines — absent data does not silently pull scores toward the middle.

### 🎯 Conviction-Scaled Signals & Price Targets

**Signal thresholds are regime-aware:**
| Score | Signal (BULL / SIDEWAYS) | Signal (BEAR — +10 threshold) |
|---|---|---|
| 85 – 100 | — | 🟢 **Strong Buy** |
| 75 – 100 | 🟢 **Strong Buy** | (requires 85+ in BEAR) |
| 70 – 84 | — | 🟩 **Buy** |
| 60 – 74 | 🟩 **Buy** | (requires 70+ in BEAR) |
| 45 – 59 | 🟡 **Hold** | 🟡 **Hold** |
| 30 – 44 | 🟧 **Sell** | 🟧 **Sell** |
| 0 – 29 | 🔴 **Strong Sell** | 🔴 **Strong Sell** |

**Price targets scale with conviction and regime:**
- `conviction_mult` = 1.0x at score 60 → 1.6x at score 100
- Targets in BULL are 10% wider than SIDEWAYS; BEAR targets are 20% tighter
- Stop loss: BULL = 1.7×ATR | SIDEWAYS = 1.5×ATR | BEAR = 1.2×ATR (tighter exit)

### 💰 Regime-Aware Position Sizing
Position size is intentionally smaller in downtrends — not larger. A tighter BEAR stop is offset by three sizing constraints:

| Parameter | BULL | SIDEWAYS | BEAR |
|---|---|---|---|
| Risk % of capital | Up to 2.0% | Up to 1.7% | Up to 1.2% |
| Max single-stock allocation | 20% | 15% | 10% |

This prevents the mechanical inversion where a tighter stop (smaller denominator in qty calculation) would silently increase share count in a regime that warrants *less* exposure.

### 🔒 Composite Score Integrity
- **Weight normalization**: Adaptive weights are renormalized before use — if the meta-learner emits weights summing to ≠ 1.0 due to any drift, they are corrected before the composite is calculated.
- **Missing engine handling**: When an engine returns no data, its weight is redistributed across the engines that did respond. The phantom default (50) is never blended into the final score.

### ⚡ Instant Screener — Nifty 200
- **Pre-computed nightly at 4:00 PM IST** — results load in <100ms
- 200 stocks scanned daily (Nifty 200 universe)
- Pre-built strategies: Breakout Scanner | Reversal Candidates
- Custom filters: Signal type, Composite score, RSI range

### 🗓️ Fully Automated Daily Pipeline
```
8:45 AM  →  Morning Briefing (global cues, FII/DII, earnings calendar)
3:15 PM  →  Nifty 50 meta-learner scan (regime-labelled training data)
4:00 PM  →  Nifty 200 nightly pre-computation (200 stocks → DB)
6:30 PM  →  FII/DII data refresh
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
- Win rate by signal type (STRONG BUY / BUY / SELL / STRONG SELL)
- Monthly win rate trend chart
- Best and worst performing stocks by win rate
- Engine score correlation (Technical vs Fundamental vs Sentiment)
- Meta-Learner v2 weight card with per-regime breakdown and sample counts
- PDF accuracy report download (filterable by D5 or D10)

### 🎨 Dark / Light Mode
Full theme toggle with CSS variable system — all pages, charts, and components adapt.

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
│   ├── Ensemble Scorer   → Regime-aware composite + conviction-scaled targets
│   │                       + position sizing + weight normalization guard
│   ├── Regime Detector   → 4-factor point scoring (trend gate + VIX + breadth + FII)
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
│   └── /api/market/*                 → FII/DII, breadth, VIX, regime
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
│   │   ├── ensemble_scorer.py    # Composite + regime-aware targets + position sizing
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
│   ├── src/components/           # Reusable UI components (ThemeProvider, Sidebar…)
│   └── src/lib/                  # API client (api.ts)
├── reports/                      # Auto-generated PDF accuracy reports
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
| GET | `/api/market/overview` | Live indices, FII/DII, VIX, market breadth |
| GET | `/api/market/breadth` | NSE advance/decline ratio |
| POST | `/api/market/refresh-fii` | Manually refresh FII/DII data in live cache |
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

**Example:** If the Fundamental engine is consistently correct in BEAR markets but Technical is noisy, the bot automatically increases Fundamental weight in BEAR and decreases Technical — without any manual intervention.

---

## 🌡️ How Regime Detection Works

```
Score is computed from 4 independent factors (max range: -5 to +5)

  Trend (20d NIFTY):  +2 if ≥+4%  |  +1 if ≥+1.5%  |  -1 if ≤-2.5%  |  -2 if ≤-5%
  VIX:                +1 if <14 AND trend positive (asymmetric — calm selloffs are still selloffs)
                      -0.5 if >17  |  -1 if >20
  Breadth:            +1 if >65% advancing  |  -1 if <40% advancing
  FII flow (5-day):   +1 if net buy >₹3000Cr  |  -1 if net sell >₹3000Cr

  Score ≥ +2.5 AND trend > 0  →  BULL
  Score ≤ -2.0 AND trend < 0  →  BEAR
  Otherwise                   →  SIDEWAYS
```

The **trend gate** ensures that non-trend factors (VIX spike + FII selling on a flat NIFTY) cannot force a BEAR call. The primary factor must support the direction.

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
