<div align="center">

# 🤖 ATBot

### AI-Powered Indian Equity Analysis & Algorithmic Trading Platform

*Technical + Fundamental + Sentiment intelligence → 2017-calibrated XGBoost ML signal filter → Positive Risk:Reward execution*

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-14-000000?style=for-the-badge&logo=next.js&logoColor=white)](https://nextjs.org)
[![XGBoost](https://img.shields.io/badge/XGBoost-ML%20Filter-FF6600?style=for-the-badge&logo=xgboost&logoColor=white)](https://xgboost.readthedocs.io)
[![Market](https://img.shields.io/badge/Market-NSE%20%7C%20BSE-FF6B35?style=for-the-badge)](https://nseindia.com)
[![Status](https://img.shields.io/badge/Status-Active%20Development-brightgreen?style=for-the-badge)](https://github.com/Aritradeb2000/ATBot)

</div>

---

## 📌 What is ATBot?

**ATBot** is a high-performance personal AI stock analysis and algorithmic decision-support platform built exclusively for the **Indian equity market (NSE/BSE)**. 

It evaluates stocks across three specialized intelligence engines — **Technical**, **Fundamental**, and **Sentiment** — combines them into an adaptive composite score, and filters trade setups through a **production XGBoost classifier calibrated across 70,000+ trade samples from 2017 to Present**. 

ATBot enforces **strict positive Risk-to-Reward geometry (1 : 1.67 to 1 : 2.5+)**, eliminating the asymmetric trap where single losses wipe out multiple wins.

---

## ✨ Core Highlights & Recent Enhancements

### 🤖 1. XGBoost ML Signal Filter (Calibrated on 2017–2026 Data)
Rather than blindly acting on raw technical momentum, ATBot passes every candidate trade through an XGBoost classification model trained on multi-regime historical data:
- **Trained across 70,000+ simulated trades** across all Nifty 200 constituents from 2017 to 2026.
- **Learned across 5 distinct market regimes**:
  1. *2017 Bull Rally*: Momentum continuation.
  2. *2018–2019 IL&FS Midcap Bear Market*: Surviving grinding 2-year corrections.
  3. *March 2020 COVID Panic*: Flash volatility and recovery dynamics.
  4. *2020–2024 Post-COVID Mega Bull Run*: Structural trend expansions.
  5. *2025–2026 Choppy Consolidation*: Fake breakout rejection and mean-reversion.
- **Top Predictive Features**:
  - `is_buy` (long bias in cash equity)
  - `technical_score` & `above_200ema`
  - `supertrend_dir` & `bb_pct`
  - `ema21_ema50_spread` & `atr_pct`
- **Out-of-Sample Performance (2025–2026 Test Set)**:
  - Baseline (No AI Filter): 34.4% win rate | 0.86 Profit Factor (losses exceed gains)
  - High AI Conviction ($P \ge 0.56$): **51.7% win rate | 1.35 Profit Factor (+0.36% net avg return per trade)**
- **Smart Capital Protection**: Downgrades weak BUY signals ($P < 0.42$) to `HOLD` in Sideways and Bear regimes.

---

### ⚖️ 2. Positive Risk-to-Reward Geometry (Strict 1 : 1.67+ R:R)
Fixed the classic retail problem of risking 2.0x ATR to make 1.0x ATR:
- **Tight Stop Loss (Controlled Risk)**: Capped strictly at **$1.0\times$ (Bear/Sideways) to $1.2\times$ (Bull) ATR**. One loss will *never* wipe out two wins.
- **Base Targets (Expanded Reward)**: Calibrated to **$1.8\times - 2.8\times$ ATR**.
- **Realized R:R**: Every setup is dynamically computed as:
  $$\text{Realized R:R} = \frac{|\text{Base Target} - \text{Entry Price}|}{|\text{Entry Price} - \text{Stop Loss}|} \ge 1.67$$
  At $1 : 1.67$ R:R, the mathematical break-even win rate drops to **$37.5\%$**. Any win rate above $38\%$ generates compounding net profit.

---

### 📉 3. Overextension Penalty & 21-EMA Pullback Setup
- **Overextension Penalty**: Deducts **10 points** whenever price is stretched $> 3.5\%$ above the 21 EMA. ATBot refuses to buy extended green candle tops where mean-reversion triggers stop-losses.
- **21-EMA Pullback Confirmation**: Awards **+15 points** for high-conviction pullback setups:
  - Confirmed uptrend: Price > 200 EMA and 50 EMA > 200 EMA.
  - Low tests 21 EMA ($0\% - 1.5\%$ zone).
  - RSI resets to healthy momentum ($42 - 58$).
  - Bullish reversal candle closes above open.

---

### ⚡ 4. Instant Offline Local Data Provider (<1ms)
- `fetch_ohlcv` checks the local directory `nifty200_data/` before querying external APIs.
- Instant historical data loading in **<1 millisecond** completely offline.
- Bypasses Yahoo Finance rate limits, IP bans, and corporate Zscaler/proxy SSL handshake errors.

---

### 🧪 5. Vectorized Multi-Year Backtester (`backend/engines/backtester.py`)
- Standalone multi-asset backtester across all Nifty 200 daily CSVs.
- Simulates realistic 10-day swing trade execution with risk-first stop checks.
- Default horizon set to **2017 to Present** for statistically sound, regime-diverse verification.

---

### 📅 6. Production Date-Wise Logging System
- Implemented custom `DailyFileHandler` in `backend/logging_config.py`.
- **Date-stamped audit logs**:
  - `logs/requests_YYYY-MM-DD.log`: HTTP method, path, response status, execution latency.
  - `logs/errors_YYYY-MM-DD.log`: Full tracebacks and exception context.
  - `logs/app_YYYY-MM-DD.log`: Engine scoring, scheduler runs, and market data events.
- **UTF-8 safe**: Zero Windows CP1252 charmap encoding crashes.
- **Auto-purge**: Automatically prunes log files older than 30 days.

---

### 🏦 7. DII Absorption & Balanced Institutional Sentiment
- Standalone DII scoring: Awards up to **+10 points** when DII net inflows absorb foreign selling pressure.
- Net institutional flow calculated as `(FII Net + DII Net) / 2`.
- Fixed double negative formatting (`--2700Cr`), strictly capping sentiment contribution to its $\pm15$ point budget.

---

### 🧠 8. Meta-Learner v2 & Market Regime Engine
- **Regime Detection**: 4-factor scoring (NIFTY 20d trend gate, India VIX, Market Breadth, FII 5-day flow).
- **Adaptive Weighting**: Evaluates D5/D10 outcome accuracy to automatically adjust Technical, Fundamental, and Sentiment weights per regime.
- **Sideways Kill Switch**: Masks signals to `HOLD` if historical sideways win rate drops below threshold.

---

## 🏗️ System Architecture

```
ATBot
├── 📡 Data Layer
│   ├── Local Nifty 200   → Offline CSV provider (<1ms fetch)
│   ├── yfinance          → Real-time fallback OHLCV
│   ├── nsepython         → Live NSE quotes, FII/DII data, VIX
│   ├── RSS Feeds         → Real-time news (ET, Moneycontrol, LiveMint)
│   └── Finnhub / FMP     → Financial news and fundamental ratios
│
├── 🧠 Intelligence & ML Layer
│   ├── Technical Engine  → 15+ indicators + Overextension penalty + 21-EMA pullbacks
│   ├── Fundamental Engine→ P/E, EPS growth, ROE, Debt/Equity, sector peer comparison
│   ├── Sentiment Engine  → FinBERT NLP + DII Absorption + FII institutional flow
│   ├── XGBoost ML Filter → 2017-2024 calibrated classifier (win prob & quality verdict)
│   ├── Ensemble Scorer   → Regime-aware composite + positive R:R targets + position sizing
│   ├── Meta-Learner v2   → EWMA regime-conditioned weight retraining
│   └── Backtester        → Vectorized simulation across 200 stocks (2017-2026)
│
├── ⚡ API Layer (FastAPI)
│   ├── /api/analyze/{symbol}         → Full stock analysis & ML signal quality
│   ├── /api/screener                 → Instant pre-computed screener
│   ├── /api/screener/status          → Nightly scan status
│   ├── /api/market/*                 → FII/DII, breadth, VIX, regime
│   ├── /api/learn/*                  → Win rates, outcomes, meta-learner weights
│   └── /api/optimizer/run            → Mean-variance portfolio optimizer
│
└── 🎨 Frontend (Next.js 14)
    ├── /              → Dashboard (live market overview & regime)
    ├── /stock/[sym]   → Stock deep-dive (charts, gauges, targets, AI conviction)
    ├── /screener      → Instant Nifty 200 screener with custom filters
    ├── /market        → Market breadth, FII/DII absorption, VIX
    ├── /news          → Sentiment-analyzed news feed
    ├── /learn         → Historical accuracy, backtest results, meta-weights
    └── /optimizer     → Portfolio allocation tool
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.11 / 3.13, FastAPI, Uvicorn |
| **Machine Learning** | XGBoost 3.4+, scikit-learn 1.9+, HuggingFace Transformers (FinBERT) |
| **Technical Analysis** | pandas-ta, NumPy, pandas |
| **Local / Live Data** | Nifty 200 CSV dataset, yfinance, nsepython |
| **Logging** | Custom date-stamped rotating file handlers (UTF-8) |
| **Scheduler** | APScheduler (IST timezone automated jobs) |
| **Database** | SQLite (dev) / PostgreSQL (production) via async SQLAlchemy |
| **Frontend** | Next.js 14 (App Router), TypeScript, Vanilla CSS, Framer Motion |
| **Charting** | TradingView Lightweight Charts |

---

## 📁 Project Structure

```
atbot/
├── backend/
│   ├── api/
│   │   ├── main.py               # FastAPI app, date-wise logging middleware, routers
│   │   └── routes/               # Analysis, screener, market, learn, optimizer
│   ├── data/
│   │   ├── market_data.py        # Local CSV data reader + yfinance fallback
│   │   ├── nse_live.py           # Live NSE quotes, FII/DII cache, market breadth
│   │   ├── nse_universe.py       # Curated Nifty 50/100/200 symbols
│   │   ├── news_feed.py          # News aggregation
│   │   └── scheduler.py          # Nightly scan and retraining scheduler
│   ├── engines/
│   │   ├── technical_engine.py   # TA indicators, overextension penalty, 21-EMA pullbacks
│   │   ├── fundamental_engine.py # Ratio analysis and peer group scoring
│   │   ├── sentiment_engine.py   # FinBERT NLP + DII absorption scoring
│   │   ├── ensemble_scorer.py    # Composite score, XGBoost filter, positive R:R geometry
│   │   ├── backtester.py         # Multi-year vectorized backtester (2017+)
│   │   ├── meta_learner.py       # EWMA regime-conditioned weight retraining
│   │   └── outcome_tracker.py    # D5/D10 WIN/LOSS trade evaluator
│   ├── models/
│   │   ├── database.py           # Async SQLAlchemy database engine
│   │   ├── schemas.py            # DB models (AnalysisScore, SignalOutcome, etc.)
│   │   └── weights/              # xgb_signal_filter.joblib (trained artifact)
│   ├── logging_config.py         # Date-wise requests/errors/app logging configuration
│   ├── config.py                 # Application settings and environment variables
│   └── requirements.txt
├── frontend/
│   ├── src/app/                  # Next.js App Router pages
│   ├── src/components/           # Reusable UI components & charts
│   └── src/lib/api.ts            # Typed API client
├── logs/                         # Date-wise log files (requests, errors, app)
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
# Optional free API keys:
# - FINNHUB_API_KEY  → https://finnhub.io
# - NEWSAPI_KEY      → https://newsapi.org
# - FMP_API_KEY      → https://financialmodelingprep.com
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
*Date-wise logs will automatically begin streaming to `backend/logs/requests_YYYY-MM-DD.log` and `backend/logs/app_YYYY-MM-DD.log`.*

### 5. Start the Frontend
```bash
cd frontend
npm install
npm run dev
```

### 6. Access ATBot
Open your browser to:
```
http://localhost:3000
```

---

## 🧪 Running Backtests & Model Training

To run the backtester across historical Nifty 200 data from 2017:
```bash
python -c "from backend.engines.backtester import run_full_backtest; run_full_backtest(start_year=2017)"
```

To re-train the XGBoost signal filter:
```bash
python scratch/train_xgb_2017.py
```

---

## ⚠️ Disclaimer

> ATBot is a **personal algorithmic analysis platform** for research and educational purposes. It does **not** constitute financial advice. Financial markets involve substantial risk of loss. Always manage risk responsibly and conduct independent due diligence.

---

## 📄 License

Personal Use License. All rights reserved.

<div align="center">
  <sub>Built with ❤️ for data-backed conviction in Indian equities</sub>
</div>
