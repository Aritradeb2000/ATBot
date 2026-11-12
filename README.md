# ATBot

Personal Indian-equity research and decision-support application built with FastAPI and Next.js. ATBot combines technical, fundamental, and news-sentiment scores, screens NSE stock universes, proposes allocation plans, and tracks signal outcomes and simulated paper positions.

**ATBot does not connect to a broker or place real orders.** BUY/SELL signals, target prices, model probabilities, and paper P&L are research outputs, not execution guarantees or financial advice.

## Features

| Page | Purpose |
| --- | --- |
| `/` | Dashboard with market overview, top signals, morning briefing, and a browser-local watchlist |
| `/stock/[symbol]` | Stock analysis, daily/intraday charts, component scores, targets, stops, and optional position sizing |
| `/screener` | Precomputed or live stock screening with signal, score, RSI, and preset filters |
| `/optimizer` | Score-weighted allocation proposals for Nifty 50, custom symbols, or the browser watchlist |
| `/market` | Index overview, market breadth, FII/DII flows, India VIX, and sector changes |
| `/news` | Market and symbol-related news |
| `/learn` | Recorded signal outcomes, accuracy statistics, adaptive weights, and PDF report download |
| `/settings` | Saved capital, risk profile, and notification preferences |

Notification preferences are stored settings; they do not establish that email, Telegram, or browser alert delivery is implemented.

## Architecture

```text
Next.js browser client
    | HTTP /api/*                  | WebSocket /ws/live
    v                              v
FastAPI routes and cached market snapshots
    |
    +-- Data providers: Yahoo Finance, NSE HTTP endpoints, RSS, optional APIs
    +-- Engines: technical + fundamental + lexicon sentiment -> ensemble
    +-- Allocation: on-demand optimizer / scheduled paper portfolio
    +-- Async SQLAlchemy: scores, outcomes, paper positions, settings
    +-- In-process APScheduler: refreshes, scans, outcome checks, reports
```

This is a modular monolith, not a distributed worker system. Analysis fetch-and-score work runs in Starlette's bounded thread pool, while database operations remain asynchronous. Synchronous chart/history/sector routes run in FastAPI's worker pool, and recurring provider refreshes also offload network calls. Other analysis paths still have separate orchestration; this is not a guarantee that every computation is nonblocking.

The WebSocket sends an initial cache snapshot followed by cache heartbeats every five seconds. It is not an exchange tick feed; underlying data refreshes independently.

| Area | Implementation |
| --- | --- |
| API | FastAPI, Uvicorn, Pydantic settings |
| Frontend | Next.js 14.2.35 (App Router), React 18, TypeScript 5, SWR, Axios, Tailwind CSS, Framer Motion |
| Charts | TradingView Lightweight Charts 5 |
| Analysis | pandas, NumPy, pandas-ta; optional XGBoost artifact |
| Sentiment | Financial phrase/word lexicons with negation and intensifier handling; no FinBERT/PyTorch runtime |
| Persistence | Async SQLAlchemy with SQLite/aiosqlite by default |
| Scheduling | APScheduler with Asia/Kolkata cron jobs |
| Reports | FPDF API, requiring the additional `fpdf2` package |

Backend dependencies use lower bounds or unpinned versions in [backend/requirements.txt](backend/requirements.txt). Frontend dependencies and scripts are defined in [frontend/package.json](frontend/package.json), with a lockfile for reproducible npm installation.

## Getting Started

### Prerequisites

- Python 3.13 is the runtime used for the current backend regression checks. Compatibility with older Python versions depends on the dependency versions resolved, particularly pandas-ta.
- A supported Node.js LTS release compatible with Next.js 14; Node.js 20+ is a practical baseline.
- Internet access for provider requests. Fresh local CSVs can satisfy some daily-price requests, but the full application is not offline-only.

Run backend commands from the directory containing this README, [backend/](backend/), and [frontend/](frontend/). In the current workspace this is the inner `atbot` directory. This working directory controls `.env` loading, the default SQLite file, and the universe cache.

### Backend (Windows PowerShell)

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r backend/requirements.txt
Copy-Item .env.example .env
```

Before starting, review the copied configuration. Replace any example credentials with your own, or leave optional provider keys blank. Do not reuse credentials from the template or commit a populated `.env`.

For PDF report generation, also install the dependency currently missing from the requirements list:

```powershell
.\venv\Scripts\python.exe -m pip install fpdf2
```

Start the backend:

```powershell
.\venv\Scripts\python.exe -m uvicorn backend.api.main:app --reload --host 127.0.0.1 --port 8000
```

Startup creates missing database tables, starts the scheduler, warms market/news/FII-DII caches, restores adaptive weights, and initializes the sideways kill-switch state. External requests can delay readiness. Weekday startup catch-up may launch scans and outcome jobs immediately if their scheduled times have passed.

On macOS/Linux, create the same environment with `python3 -m venv venv` and substitute `./venv/bin/python` for the Windows executable path.

### Frontend

In a second terminal, starting from the same project directory:

```powershell
cd frontend
npm ci
npm run dev
```

| Service | Default URL |
| --- | --- |
| Application | http://localhost:3000 |
| Backend health | http://localhost:8000/health |
| Swagger API documentation | http://localhost:8000/docs |
| OpenAPI schema | http://localhost:8000/openapi.json |

The shared frontend clients support these values in `frontend/.env.local`:

```dotenv
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws/live
```

Some screener and learning-page fetches still hardcode `http://localhost:8000`; changing the environment variables alone does not fully support a remote backend. Restart the frontend after changing its environment.

## Configuration

Settings are defined in [backend/config.py](backend/config.py). Environment variables override defaults; [.env.example](.env.example) lists the available template values.

| Setting | Default or behavior |
| --- | --- |
| `DATABASE_URL` | `sqlite+aiosqlite:///./atbot.db`, relative to the backend working directory |
| `DEBUG` | `true`; disable explicitly outside development |
| `APP_ENV`, `APP_SECRET_KEY` | Application settings only; they do not enable authentication |
| `FINNHUB_API_KEY` | Optional company news; missing/failed/empty results use Pulse and Google News RSS fallbacks |
| `FMP_API_KEY` | Optional supplemental fundamentals in the combined fundamentals provider |
| `NEWSAPI_KEY` | Optional NewsAPI helper; the scheduled news refresh currently uses RSS |
| `MARKET_DATA_INTERVAL_MINUTES` | `5` |
| `NEWS_REFRESH_INTERVAL_MINUTES` | `10` |
| `FUNDAMENTALS_REFRESH_HOUR` | `18` |
| `MORNING_BRIEFING_HOUR`, `MORNING_BRIEFING_MINUTE` | `8`, `45` |
| `MARKET_TIMEZONE` | `Asia/Kolkata` |
| Market open/close fields | Weekdays, 09:15 to 15:30 in the configured timezone |

The settings API uses one shared user ID, `default`. Watchlists and some UI preferences live in browser `localStorage`, not the database watchlist table. The `WEIGHT_*` environment fields exist, but active composite weights come from the scorer's regime defaults or saved adaptive weights; editing those fields is not a universal scoring override.

PostgreSQL requires a compatible async URL such as `postgresql+asyncpg://...` and an additional `asyncpg` installation. It is not configured or certified by the default SQLite setup. Startup uses `create_all()` to create missing tables, not migrate existing columns; back up databases before schema changes.

## Analysis and Learning

- **Technical:** RSI, MACD, EMAs, ATR, Bollinger/Keltner channels, Supertrend, ADX, OBV, candlestick patterns, weekly trend, relative strength, and trend/reversion sub-scores. Some inputs, including delivery data, are supplied only by particular scan paths.
- **Fundamental:** rule-based valuation, EPS/revenue growth, debt/equity, ROE, insider holding, and margin scoring. Missing fundamentals currently produce a neutral score with a warning flag.
- **Sentiment:** scores up to ten articles using financial phrases, tokens, negations, and intensifiers. FII/DII adjustments are capped at +/-15 points. No articles produce a missing sentiment score.
- **Ensemble:** combines available component scores with BULL/BEAR/SIDEWAYS weights, uses the reversion sub-score in sideways conditions, and calculates ATR-based targets and stops. Confidence is an agreement heuristic on a 0-100 scale, not a calibrated win probability.
- **Targets:** analysis can return 5-, 10-, 50-, and 100-day projections, plus a textual execution plan and optional visible-BUY sizing when capital is supplied. These are projections, not guaranteed fills or realized reward/risk.
- **Kill switch:** sideways signals are forced to HOLD when the tracked directional win rate is below 35% with at least 20 eligible trades. Shadow signals can retain the counterfactual setup for evaluation.
- **Outcomes:** tracked at 1, 2, 5, 10, 50, and 100 weekday horizons. These records feed the learning UI and adaptive-weight calculation; they are not broker trade confirmations.
- **Meta-learner:** EWMA and horizon-weighted component-weight adaptation with regime/global fallbacks and holdout checks. The current training cutoff is September 19, 2026; older outcomes are excluded from weight learning. This does not retrain the XGBoost classifier.

Interactive analysis, live screening, optimization, and scheduled scans do not yet share one analysis service. Their supplied market context and persisted fields can differ, so identical symbols need not yield identical results across workflows.

### Optional XGBoost Filter

The scorer looks for `backend/models/weights/xgb_signal_filter.joblib`. Its payload must contain `model` and `feature_cols`, and the classifier must provide `predict_proba`. Use only trusted artifacts: loading joblib/pickle data can execute code.

When no usable artifact is available, quality evaluation returns `MODEL_UNAVAILABLE`; ordinary scoring can continue. Successful evaluation reports HIGH_CONVICTION, NEUTRAL, or LOW_PROBABILITY and can influence confidence and weak-BUY filtering. Artifact/library compatibility is required.

The repository does not currently include the previously documented training script or a reproducible training/evaluation workflow. No historical sample-count, profit-factor, or win-rate claims are asserted here.

## Allocation and Paper Positions

The on-demand optimizer and the scheduled paper portfolio are different systems:

| Workflow | Behavior |
| --- | --- |
| Optimizer | Scans candidates, filters by risk profile, ranks by score/confidence/reward-risk, and returns a score-weighted allocation proposal. It is not mean-variance optimization and does not create paper positions or broker orders. |
| Paper portfolio | Runs after the daily scan, uses saved capital (fallback INR 100,000), and persists simulated long positions in `paper_positions`. |

The paper allocator selects the latest score per symbol, accepts visible BUY/STRONG BUY signals, rejects kill-switch signals and invalid stops, and checks prior allocations/open symbols before creating another entry. Limits are five open positions and two per stored sector; missing sectors share the `Unknown` bucket. Sizing uses regime-adjusted risk and per-position caps, with capital already committed to open positions deducted from the available budget.

Paper positions retain their source score, quantity, sector, entry, stop, target, regime, and eventual exit/P&L across restarts. Outcome checks reconcile open positions, model a breakeven stop after the conservative target, and close on a modeled stop or ten-session horizon when enough bars exist. Intraday event ordering cannot be established from daily candles. `is_deployed` in outcome records means a persisted paper allocation, not real-money execution.

The textual partial-profit/runner plan returned by analysis is not a fully implemented execution engine. Neither simulated results nor sizing caps guarantee losses under gaps, slippage, fees, or unavailable data. Paper positions currently have no dedicated UI or CRUD API.

## Market Data and Screening

Use Yahoo-format tickers such as `RELIANCE.NS` or `TCS.NS`; BSE tickers use `.BO`. Named universes are NSE-based. Universe lists resolve through a fresh disk cache, NSE index CSVs, stale cache, then a bundled fallback snapshot. Their cache is under `.cache/universe` in the working directory.

### Local Daily CSVs

The local loader and standalone backtester currently contain machine-specific paths. Before using a dataset elsewhere, update `LOCAL_DATA_DIR` in [backend/data/market_data.py](backend/data/market_data.py) and `DATA_DIR` in [backend/engines/backtester.py](backend/engines/backtester.py). These are code constants, not environment settings.

Use plain-symbol filenames such as `RELIANCE.csv` with columns:

```csv
Date,Open,High,Low,Close,Volume
2026-11-11,100,103,99,102,100000
```

- Local CSVs are eligible only for daily bars outside market hours, and only if the latest positive-price/positive-volume bar matches the most recently completed weekday session.
- During market hours, daily requests bypass static CSVs. Intraday and weekly requests also use Yahoo Finance.
- Missing, stale, invalid, or future-dated local data falls back to Yahoo. Failed online requests do not return stale local CSVs as current prices.
- Friday bars can be reused on weekends and Monday before the open. Exchange holidays and special sessions are not modeled; missing weekday bars conservatively trigger the online provider.
- The loader does not automatically download or update these CSV files. Cached market context and saved analysis scores have their own refresh behavior, separate from CSV freshness.

### Screener Modes

Standard universes normally read the latest saved scores with a 26-hour age limit. Custom symbols or `live=true` trigger analysis. If no precomputed rows are available, the automatic live fallback scans at most 100 symbols; this can be slow and is not necessarily the complete Nifty 200 universe. Check `data_source`, result counts, and `last_computed` rather than assuming a complete fresh scan. Precomputed rows do not include every live field, such as RSI or daily change.

## Background Schedule

Cron jobs use Asia/Kolkata by default. These are the current registrations in [backend/data/scheduler.py](backend/data/scheduler.py), not exchange-holiday-aware schedules.

| Job | Schedule |
| --- | --- |
| Market-hours OHLCV refresh | Configured 5-minute interval; currently the first ten Nifty 50 symbols |
| Index, VIX, and breadth refresh | Every 5 minutes |
| RSS news refresh | Configured 10-minute interval |
| Morning briefing | Daily 08:45 |
| Earnings calendar | Daily 09:00; also initialized on startup |
| Daily Nifty 200 scan and paper allocation | Monday-Friday 15:15, before the configured 15:30 market close |
| Precomputation | Monday-Friday 16:00; default Nifty 200 |
| Fundamental refresh | Daily 18:00; Nifty 50 |
| FII/DII refresh | Daily 18:30 and retry at 20:00; also attempted on startup |
| Outcomes, adaptive weights, and PDF report | Monday-Friday 18:30 |

Keep the backend running for scheduled work. Catch-up is best-effort, not a durable job queue or complete historical backfill. Completion/progress state is partly in memory, and restarts can repeat work. The market-hours OHLCV job is registered paused when startup occurs outside market hours; the independently registered index refresh still runs. Do not assume that OHLCV job will resume automatically at the next open.

## API Reference

See `/docs` for request fields and response schemas. HTTP routes below are relative to the backend origin.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Process health/version, not provider-readiness verification |
| GET | `/api/analyze/{symbol}` | Full analysis; optional `capital` query parameter |
| GET | `/api/score/{symbol}` | Compact score; still runs and saves full analysis |
| GET | `/api/ohlcv/{symbol}` | Chart bars by `period` and `interval` |
| GET | `/api/screener` | Filtered precomputed/live screener |
| GET | `/api/screener/top-signals` | Latest ranked saved BUY signals |
| GET | `/api/screener/status` | In-process precomputation progress |
| POST | `/api/screener/trigger-daily` | Start the daily scan/paper-allocation workflow |
| POST | `/api/screener/trigger-nightly` | Start precomputation; optional `universe` |
| GET | `/api/market/overview` | Cached indices, VIX, breadth, FII/DII, and update times |
| GET | `/api/market/briefing` | Cached morning briefing |
| POST | `/api/market/briefing/trigger` | Generate a briefing |
| POST | `/api/market/refresh-fii` | Start an FII/DII refresh |
| GET | `/api/market/fii-history` | Provider-supplied FII/DII history |
| GET | `/api/market/vix-history` | India VIX historical closes |
| GET | `/api/market/sector-heatmap` | Sector-index changes |
| GET | `/api/news/market`, `/api/news/pulse`, `/api/news/{symbol}` | Market, Pulse, or symbol news |
| GET, PUT | `/api/settings` | Read/update shared settings |
| POST | `/api/optimizer/run` | Return an allocation proposal |
| GET | `/api/learn/stats`, `/api/learn/recent` | Recorded outcome statistics and records |
| GET | `/api/learn/meta-weights` | Adaptive weights and learning metadata |
| POST | `/api/learn/trigger`, `/api/learn/trigger-meta` | Run outcomes or weight recomputation |
| GET | `/api/learn/report` | Generate/download a PDF report |
| WebSocket | `/ws/live` | Cached market snapshots and five-second heartbeats |

GET analysis/score requests persist records and are not read-only cache lookups. The legacy `POST /api/screener` is only a stub; use GET for actual screening. Trigger endpoints can perform substantial provider and database work.

## Tests and Backtests

From the project directory:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s . -p test_backend_regressions.py -v
```

The regression suite uses temporary databases/files and mocked providers. Coverage includes SQLite transaction isolation, local-price freshness, direct async allocation, paper-position persistence and caps, outcome linkage, HTTP event-loop responsiveness, and scheduled refresh offloading. It does not certify external API availability, model accuracy, production deployment, or frontend behavior.

### Historical Backtester

[backend/engines/backtester.py](backend/engines/backtester.py) runs an offline, technical-only simulation across local daily OHLCV CSVs. It does not call Yahoo Finance, the live analysis API, or the database. Its scoring rules are separate from the live technical engine and ensemble.

#### Inputs and Parameters

Set the module's `DATA_DIR` to the directory containing the CSVs described under [Local Daily CSVs](#local-daily-csvs). Each filename becomes the trade's symbol: `RELIANCE.csv` produces `RELIANCE`, without automatically adding `.NS`. The runner reads every `.csv` file in that directory, parses and sorts `Date`, and skips files with fewer than 250 rows. Per-file processing failures are logged and skipped; a missing dataset directory fails before that per-file error handling.

The entry point is `run_full_backtest(sample_size=None, start_year=2017, holding_days=10)`:

| Parameter | Default | Meaning |
| --- | --- | --- |
| `sample_size` | `None` | Process all CSV files. A positive integer selects the first N files in filesystem listing order, not a random or sorted sample. |
| `start_year` | `2017` | Retain trades whose entry date is on or after January 1 of this year. Earlier rows still contribute indicator warm-up; the dataset is not truncated before indicator calculation. |
| `holding_days` | `10` | Maximum number of subsequent dataset bars inspected per entry, not calendar days. Supply a positive integer. |

The lower-level `simulate_trades()` additionally accepts `target_atr_mult=2.0` and `stop_atr_mult=1.2`. The full runner does not expose those multipliers; use the lower-level pipeline to customize them.

#### Indicator and Signal Pipeline

The runner calls three functions in sequence for each eligible file:

1. `compute_indicators(df)` calculates EMA 9/21/50/200, RSI 14, MACD 12/26/9, ATR 14, Bollinger Bands 20/2, Supertrend 10/3, ADX 14, and a 20-bar volume SMA. Some calculated indicators are returned as context rather than used directly in signal scoring.
2. `generate_signals(df)` starts each bar at 50 points, applies the rules below, clips the result to 0-100, and adds `technical_score` and `signal` columns.
3. `simulate_trades(df, symbol, ...)` evaluates eligible signals after the warm-up and returns a list of independent trade records. The runner then applies the `start_year` filter and combines the records into one DataFrame.

| Scoring condition | Adjustment |
| --- | --- |
| MACD above its signal with positive histogram | +15; the corresponding bearish condition gives -15; otherwise 0 |
| Close above EMA 200 | +5; otherwise -5 |
| EMA 21 above EMA 50 | +10; otherwise -10 |
| Supertrend direction equals 1 | +10; otherwise -10 |
| RSI between 55 and 70, inclusive | +10; RSI above 70 gives -5; otherwise 0 |
| Volume strictly above twice its 20-bar SMA | +10 for a close above the open, -10 for a close below the open; otherwise 0 |

| Technical score | Signal |
| --- | --- |
| 75-100 | `STRONG BUY` |
| 65 to below 75 | `BUY` |
| Above 40 to below 65 | `HOLD` |
| Above 30 to 40 | `SELL` |
| 0-30 | `STRONG SELL` |

These are the backtester's thresholds, not the live ensemble's regime-adjusted thresholds.

#### Trade Simulation Rules

- Entries start at zero-based row 200, leaving the first 200 bars for warm-up. The final `holding_days` rows cannot start trades because their complete forward window is unavailable.
- Every BUY/STRONG BUY is a simulated long, and every SELL/STRONG SELL is a simulated short. HOLD bars are ignored. Entries with missing/nonpositive ATR or nonpositive price are skipped.
- Entry price is the signal bar's close. With default parameters, a long targets entry plus 2.0 times entry ATR and stops at entry minus 1.2 times ATR; a short reverses those directions. Levels remain fixed throughout that trade.
- Checks begin on the next bar, not the entry bar. For each future bar, stop loss is checked before target. If both are touched in the same bar, the outcome is `LOSS`.
- A target touch gives `WIN`; a stop touch gives `LOSS`. Exits are recorded at the exact target/stop level, without gap-open or slippage adjustment.
- If neither level is touched, the trade exits at the closing price of the final holding bar with outcome `EXPIRED`. That label is not a P&L classification: an expired trade may make money, lose money, or break even.
- Percentage P&L is direction-adjusted: a price decline profits a short. `exit_day` is the number of bars after entry, starting at 1.
- Signals are evaluated independently. Multiple trades in the same symbol can overlap; there is no one-position-at-a-time rule, cash balance, position sizing, or portfolio exposure constraint.

#### Running and Customizing

Run the full dataset from the project directory after configuring `DATA_DIR`:

```powershell
.\venv\Scripts\python.exe -c "from backend.engines.backtester import run_full_backtest; trades = run_full_backtest(start_year=2017, holding_days=10); print(trades.tail())"
```

For a small run, override the path in memory without editing application code:

```powershell
.\venv\Scripts\python.exe -c "from backend.engines import backtester; backtester.DATA_DIR = '../nifty200_data'; trades = backtester.run_full_backtest(sample_size=5, start_year=2020, holding_days=5); print(trades.tail())"
```

For custom ATR multipliers, use this Python pipeline with your own CSV path:

```python
import pandas as pd
from backend.engines import backtester

bars = pd.read_csv("../nifty200_data/RELIANCE.csv")
bars["Date"] = pd.to_datetime(bars["Date"])
bars = bars.sort_values("Date").reset_index(drop=True)
bars = backtester.compute_indicators(bars)
bars = backtester.generate_signals(bars)
trades = pd.DataFrame(backtester.simulate_trades(
    bars,
    symbol="RELIANCE",
    holding_days=10,
    target_atr_mult=2.5,
    stop_atr_mult=1.0,
))
print(trades.tail())
```

Calling `python -m backend.engines.backtester` alone does not run a backtest: the module defines functions but has no command-line entry point.

#### Returned Data

`run_full_backtest()` prints progress and elapsed time, then returns one row per simulated trade. It does not automatically write CSVs, produce PDF reports, calculate aggregate performance metrics, or train a model. If there are no trades, it returns an empty DataFrame that may have no columns.

| Output columns | Contents |
| --- | --- |
| `symbol`, `signal`, `direction` | Source filename symbol, entry signal, and `LONG`/`SHORT` direction |
| `entry_date`, `exit_date`, `exit_day` | Signal date, exit date, and holding bars to exit |
| `entry_price`, `exit_price`, `target_price`, `stop_price` | Entry and modeled execution levels |
| `outcome`, `pnl_pct` | `WIN`, `LOSS`, or `EXPIRED`, plus direction-adjusted percentage return |
| `technical_score`, `rsi_14`, `adx_14`, `macd_hist` | Signal-bar analysis values |
| `atr_pct`, `above_200ema`, `supertrend_dir`, `vol_ratio` | Entry ATR as a percentage of price, EMA alignment flag, trend direction, and volume relative to its SMA |

Returns are per-trade percentages, not capital-weighted portfolio returns. The implementation omits brokerage, taxes, slippage, borrowing/short-sale constraints, survivorship-bias controls, and corporate-action verification. It also omits live fundamentals, sentiment, adaptive weights, the optional XGBoost filter, and paper-position breakeven/trailing logic. Do not treat these results as a reproduction of live strategy performance.

### Frontend Build

Frontend build check:

```powershell
cd frontend
npm run build
```

## Project Layout

```text
atbot/                         # Directory containing this README
|-- backend/
|   |-- api/                   # FastAPI app, routes, WebSocket
|   |-- data/                  # Providers, universe cache, scheduler
|   |-- engines/               # Scoring, learning, paper allocation, optimizer, reports, backtester
|   |-- models/                # SQLAlchemy tables and async sessions
|   |-- config.py              # Settings, symbols, schedules, risk caps
|   |-- logging_config.py      # Daily UTF-8 logs and retention
|   `-- requirements.txt
|-- frontend/
|   |-- src/app/               # Next.js pages
|   |-- src/components/        # Layout, charts, controls
|   `-- src/lib/               # HTTP client/types and WebSocket hook
|-- test_backend_regressions.py
|-- .env.example
|-- logs/                      # Runtime output
`-- reports/                   # Generated PDF output
```

The optional dataset and model artifact are separate from source-code setup. A local `nifty200_data` directory or `backend/models/weights` folder should not be assumed present in a fresh checkout.

Logs are written under the project-level `logs/` directory, not `backend/logs/`: `requests_YYYY-MM-DD.log`, `errors_YYYY-MM-DD.log`, and `app_YYYY-MM-DD.log`. The handlers use UTF-8 and prune their own dated files older than 30 days. PDFs are generated under `reports/`.

## Operational Limits and Security

- Intended for trusted local, single-user research. Settings and operational routes have no authentication; the CORS policy is development-wide. Do not expose this service publicly without access control and deployment hardening.
- Use one backend worker. Every process starts its own scheduler and owns separate caches, adaptive-weight state, kill-switch state, and job status; multiple workers can duplicate jobs and race allocations.
- Default SQLite uses SQLAlchemy's normal async connection pooling rather than a forced shared `StaticPool`. SQLite still serializes writes; it is not a substitute for job ownership or distributed locking.
- Provider data may be delayed, incomplete, blocked, or rate-limited. Check timestamps and missing-data flags. Proxy/network failures can prevent analysis, cache warming, and reports from completing.
- Exchange holidays, complete timestamp normalization across older paths, durable task ownership, schema migrations, and consistent shared analysis orchestration remain areas for improvement.
- Keep `.env`, databases, caches, downloaded models, logs, and reports out of unrelated source commits. Rotate any real credentials that have been committed, including credential-like values in configuration templates.

## Disclaimer

ATBot is for personal research and education, not financial advice. Historical and simulated results do not predict future returns. Daily-candle simulations cannot establish exact intraday fills, and stops do not cap actual losses during gaps or liquidity events. Verify data and manage risk independently.

## License

Personal Use License. All rights reserved.
