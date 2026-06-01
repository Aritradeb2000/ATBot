<div align="center">

# 🤖 ATBot

### AI-Powered Indian Equity Analysis Platform

*Technical + Fundamental + Sentiment intelligence → Buy/Sell signals with 5–10 day price targets*

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-14-000000?style=for-the-badge&logo=next.js&logoColor=white)](https://nextjs.org)
[![Market](https://img.shields.io/badge/Market-NSE%20%7C%20BSE-FF6B35?style=for-the-badge)](https://nseindia.com)
[![Status](https://img.shields.io/badge/Status-In%20Development-yellow?style=for-the-badge)]()

</div>

---

## 📌 What is ATBot?

**ATBot** is a personal AI-driven stock analysis tool built exclusively for the **Indian equity market (NSE/BSE)**. It analyzes every stock across three intelligence engines — Technical, Fundamental, and Sentiment — combines them into a single composite score, and tells you whether to **Buy, Hold, or Sell** with a realistic **5–10 day price target**.

> Built for traders who want data-backed conviction, not gut feel.

---

## ✨ Key Features

### 📊 Three-Engine Scoring System
| Engine | What It Analyzes | Weight |
|---|---|---|
| **Technical** | RSI, MACD, EMA crossovers, Bollinger Bands, Volume, Supertrend, Candlestick patterns | Dynamic |
| **Fundamental** | P/E, EPS growth, ROE, Debt/Equity, Promoter holding, Revenue growth | Dynamic |
| **Sentiment** | News sentiment via FinBERT NLP, FII/DII flow, Market tone | Dynamic |

> Weights automatically adjust based on market regime (Bull / Bear / Sideways)

### 🎯 Signals & Price Targets
- **5-tier signal system:** Strong Buy → Strong Sell with Confidence %
- **3-scenario price targets:** Conservative / Base / Aggressive
- **AI-determined stop loss** based on setup type and volatility
- **Risk:Reward ratio** shown for every signal
- **Position sizing suggestion** based on your capital

### 🔍 Stock Screener
- **Pre-built strategies:** Breakout Scanner | Reversal Candidates
- **Custom filters:** Signal type, Composite score, Sector, RSI range, Volume spike
- Results sorted by composite score

### 🌅 Morning Briefing (8:45 AM IST)
Daily automated report before market open:
- 🌍 Global cues (SGX Nifty, Dow, Crude Oil, Gold, USD/INR)
- 🏦 Yesterday's FII/DII net flow + 3-day trend
- 📅 Earnings scheduled this week
- 📊 India VIX level + market risk assessment

### 📰 Live News Feed
Real-time news from Economic Times, Moneycontrol, LiveMint, Business Standard — organized in 3 tabs: **My Stocks | Market | Global**

### 🔔 Smart Alerts (Browser Push)
- Signal flip on watchlist stock (e.g., HOLD → BUY)
- Unusual volume spike on watched stocks
- Market-wide FII sell-off warning

### 📈 Market Intelligence Dashboard
- FII/DII daily flow chart (30-day trend)
- India VIX tracker with risk labels
- Sector performance heatmap

---

## 🖥️ Dashboard Preview

> *Screenshots will be added once the dashboard is live*

---

## 🏗️ Architecture

```
ATBot
├── 📡 Data Layer
│   ├── yfinance          → Historical OHLCV (NSE/BSE)
│   ├── nsepython         → Live NSE quotes + FII/DII data
│   ├── RSS Feeds         → Real-time news (ET, MC, Mint, BS)
│   ├── Finnhub API       → Ticker-specific news
│   └── FMP API           → Fundamental financial data
│
├── 🧠 Intelligence Layer
│   ├── Technical Engine  → pandas-ta indicators + pattern scoring
│   ├── Fundamental Engine→ Financial ratio scoring
│   ├── Sentiment Engine  → FinBERT NLP on news headlines
│   └── Ensemble Scorer   → Dynamic weighted composite + price target
│
├── ⚡ API Layer
│   └── FastAPI           → REST endpoints + WebSocket live updates
│
└── 🎨 Frontend
    └── Next.js 14        → Dashboard, Screener, News, Market Intel
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.11+, FastAPI, Uvicorn |
| **ML / NLP** | HuggingFace Transformers (FinBERT), XGBoost, scikit-learn |
| **Technical Analysis** | pandas-ta |
| **Market Data** | yfinance, nsepython |
| **Task Scheduler** | APScheduler |
| **Database** | SQLite (dev) → PostgreSQL (production) |
| **ORM** | SQLAlchemy 2.0 |
| **Frontend** | Next.js 14, TypeScript, Tailwind CSS, Framer Motion |
| **Charts** | TradingView Lightweight Charts |
| **Deployment** | Docker + Docker Compose |

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
│   │   └── scheduler.py          # APScheduler background jobs
│   ├── engines/
│   │   ├── technical_engine.py   # TA indicators + scoring
│   │   ├── fundamental_engine.py # Ratio scoring
│   │   ├── sentiment_engine.py   # FinBERT NLP pipeline
│   │   └── ensemble_scorer.py    # Composite score + price target
│   ├── api/
│   │   ├── main.py               # FastAPI application
│   │   ├── routes/               # API endpoint routers
│   │   └── websocket.py          # Real-time WebSocket
│   ├── models/
│   │   └── schemas.py            # SQLAlchemy DB models
│   ├── config.py                 # Settings + constants
│   └── requirements.txt
├── frontend/
│   ├── app/                      # Next.js App Router pages
│   ├── components/               # Reusable UI components
│   └── lib/                      # API client utilities
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## 🚀 Getting Started

### Prerequisites
- Python 3.11+
- Node.js 18+
- Docker Desktop (optional but recommended)

### 1. Clone the Repository
```bash
git clone https://github.com/yourusername/ATBot.git
cd ATBot
```

### 2. Configure Environment
```bash
cp .env.example .env
# Edit .env and add your free API keys:
# - FINNHUB_API_KEY  → https://finnhub.io (free)
# - NEWSAPI_KEY      → https://newsapi.org (free)
# - FMP_API_KEY      → https://financialmodelingprep.com (free)
```

### 3. Install Backend Dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 4. Start the Backend
```bash
uvicorn api.main:app --reload --port 8000
```

### 5. Install & Start Frontend
```bash
cd frontend
npm install
npm run dev
```

### 6. Open ATBot
Navigate to `http://localhost:3000`

### Docker (Recommended)
```bash
docker-compose up --build
```

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/analyze/{symbol}` | Full analysis for a stock |
| GET | `/score/{symbol}` | Composite score + signal |
| GET | `/technical/{symbol}` | Technical indicators + signals |
| GET | `/fundamental/{symbol}` | Fundamental metrics |
| GET | `/news/{symbol}` | Latest news for stock |
| GET | `/target/{symbol}` | 5 & 10 day price targets |
| GET | `/screener` | Screener with filters |
| GET | `/market/breadth` | NSE advance/decline, FII/DII |
| GET | `/watchlist` | Batch analysis for watchlist |
| WS | `/ws/live` | WebSocket: real-time updates |

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

> Signals are only issued when Confidence ≥ 75% and all gate conditions pass (VIX, trend, volume, earnings blackout)

---

## ⚠️ Disclaimer

> ATBot is a **personal analysis tool** and does **not** constitute financial advice. All signals and recommendations are algorithmic outputs for informational purposes only. Always do your own research before making any investment decisions. Past signal performance does not guarantee future results.

---

## 📄 License

This project is for personal use. License TBD.

---

## 🙏 Acknowledgements

- [yfinance](https://github.com/ranaroussi/yfinance) — Market data
- [pandas-ta](https://github.com/twopirllc/pandas-ta) — Technical analysis
- [FinBERT](https://huggingface.co/ProsusAI/finbert) — Financial sentiment NLP
- [nsepython](https://github.com/stocksdeveloper/nsepython) — NSE live data
- [TradingView](https://tradingview.com) — Charting library

---

<div align="center">
  <sub>Built with ❤️ for the Indian equity market</sub>
</div>
