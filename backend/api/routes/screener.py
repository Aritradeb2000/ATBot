"""
ATBot — Screener Endpoint
Supports two modes:
  1. Pre-computed (default for nifty50/nifty200): reads latest analysis_scores from DB → instant
  2. Live (universe=custom or ?live=true): runs real-time analysis → slow but always fresh

Endpoints:
  GET  /api/screener               — main screener (pre-computed or live)
  GET  /api/screener/status        — nightly job status + last run info
  POST /api/screener/trigger-nightly — manually trigger Nifty 200 pre-computation
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Query
from sqlalchemy import select, func

from backend.config import NIFTY50_SYMBOLS
from backend.data.nse_universe import get_universe
from backend.data.market_data import fetch_ohlcv
from backend.data.fundamentals import fetch_fundamentals_yfinance
from backend.data.news_feed import fetch_finnhub_news
from backend.data.nse_live import get_fii_dii_data
from backend.data.scheduler import get_cache
from backend.engines.technical_engine import analyze_technical
from backend.engines.fundamental_engine import analyze_fundamental
from backend.engines.sentiment_engine import analyze_sentiment
from backend.engines.ensemble_scorer import calculate_composite
from backend.models.database import AsyncSessionLocal
from backend.models.schemas import AnalysisScore
from backend.config import IST

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Screener"])

BATCH_SIZE = 8  # concurrent yfinance calls

# How old can a pre-computed record be and still be served (in hours)
PRECOMPUTE_MAX_AGE_H = 26   # covers weekends (Mon 4 PM → Wed 4 PM = 48h, but next day is Tue)


# ── Live analysis helper (used for custom universe or ?live=true) ──────────────

async def _analyze_one(symbol: str, cache: dict) -> Optional[dict]:
    """
    Run the full 3-engine analysis for one symbol and return a slim result dict.
    Returns None if analysis fails (symbol skipped silently).
    """
    try:
        indices       = cache.get("indices") or {}
        nifty_data    = indices.get("NIFTY50") or {}
        nifty_change  = nifty_data.get("change_pct", 0.0)
        nifty_change_20d = nifty_data.get("change_pct_20d", 0.0)
        vix_data      = cache.get("india_vix") or {}
        vix           = vix_data.get("vix", 14.0)
        fii_dii       = cache.get("fii_dii") or get_fii_dii_data()

        loop = asyncio.get_event_loop()

        ohlcv_df     = await loop.run_in_executor(None, lambda: fetch_ohlcv(symbol, interval="1d", period="6mo"))
        if ohlcv_df is None or ohlcv_df.empty:
            return None

        fundamentals = await loop.run_in_executor(None, lambda: fetch_fundamentals_yfinance(symbol))
        news         = await loop.run_in_executor(None, lambda: fetch_finnhub_news(symbol))

        tech_result  = analyze_technical(ohlcv_df)
        fund_result  = analyze_fundamental(fundamentals)
        sent_result  = analyze_sentiment(news, fii_dii)

        final = calculate_composite(
            tech_data=tech_result,
            fund_data=fund_result,
            sent_data=sent_result,
            nifty_change=nifty_change,
            nifty_change_20d=nifty_change_20d,
            vix=vix,
        )

        # Persist to DB
        try:
            import json
            targets = final.get("targets") or {}
            score_record = AnalysisScore(
                symbol=symbol,
                technical_score=final.get("components", {}).get("technical"),
                fundamental_score=final.get("components", {}).get("fundamental"),
                sentiment_score=final.get("components", {}).get("sentiment"),
                composite_score=final.get("composite_score"),
                signal=final.get("signal"),
                confidence=final.get("confidence", 0.8),
                current_price=tech_result.get("close"),
                target_low_5d=targets.get("conservative"),
                target_base_5d=targets.get("base"),
                target_high_5d=targets.get("aggressive"),
                target_low_10d=targets.get("conservative"),
                target_base_10d=targets.get("base"),
                target_high_10d=targets.get("aggressive"),
                stop_loss=final.get("stop_loss"),
                active_signals=json.dumps(tech_result.get("signals", [])),
                dominant_pattern=tech_result.get("trend"),
                atr_14=tech_result.get("atr"),
                regime=final.get("regime"),
            )
            async with AsyncSessionLocal() as db:
                db.add(score_record)
                await db.commit()
        except Exception as e:
            logger.warning(f"Screener: failed to save DB record for {symbol} — {e}")

        return {
            "symbol":       symbol,
            "company_name": (fundamentals or {}).get("company_name", symbol),
            "price":        tech_result.get("close"),
            "change":       tech_result.get("change"),
            "change_pct":   tech_result.get("change_pct"),
            "score":        final["composite_score"],
            "signal":       final["signal"],
            "confidence":   final["confidence"],
            "regime":       final["regime"],
            "rsi":          tech_result.get("rsi"),
            "atr":          tech_result.get("atr"),
            "components":   final["components"],
            "signals":      tech_result.get("signals", []),
        }

    except Exception as e:
        logger.warning(f"Screener: skipping {symbol} — {e}")
        return None


async def _run_live_batch(symbols: List[str], cache: dict) -> List[dict]:
    """Run live analysis in parallel batches of BATCH_SIZE."""
    results = []
    for i in range(0, len(symbols), BATCH_SIZE):
        batch = symbols[i: i + BATCH_SIZE]
        batch_results = await asyncio.gather(*[_analyze_one(s, cache) for s in batch])
        results.extend([r for r in batch_results if r is not None])
        logger.info(f"Screener (live): processed {min(i + BATCH_SIZE, len(symbols))}/{len(symbols)}")
    return results


# ── Pre-computed read (instant) ───────────────────────────────────────────────

async def _read_precomputed(symbols: List[str]) -> tuple[List[dict], str | None]:
    """
    Read latest AnalysisScore records for each symbol from DB.
    Returns (results_list, last_computed_timestamp_str).
    Only returns records from the last PRECOMPUTE_MAX_AGE_H hours.
    """
    import json
    cutoff = datetime.utcnow() - timedelta(hours=PRECOMPUTE_MAX_AGE_H)

    async with AsyncSessionLocal() as db:
        # Get the latest record per symbol (subquery: max timestamp per symbol)
        subq = (
            select(
                AnalysisScore.symbol,
                func.max(AnalysisScore.timestamp).label("max_ts")
            )
            .where(
                AnalysisScore.symbol.in_(symbols),
                AnalysisScore.timestamp >= cutoff,
            )
            .group_by(AnalysisScore.symbol)
            .subquery()
        )
        result = await db.execute(
            select(AnalysisScore).join(
                subq,
                (AnalysisScore.symbol == subq.c.symbol) &
                (AnalysisScore.timestamp == subq.c.max_ts)
            )
        )
        rows = result.scalars().all()

    results = []
    last_ts = None
    for r in rows:
        if last_ts is None or r.timestamp > last_ts:
            last_ts = r.timestamp

        active_sigs = []
        try:
            active_sigs = json.loads(r.active_signals or "[]")
        except Exception:
            pass

        results.append({
            "symbol":       r.symbol,
            "company_name": r.symbol.replace(".NS", ""),
            "price":        r.current_price,
            "change":       None,
            "change_pct":   None,
            "score":        r.composite_score or 0,
            "signal":       r.signal or "HOLD",
            "confidence":   r.confidence or 0,
            "regime":       r.regime or "SIDEWAYS",
            "rsi":          None,
            "atr":          r.atr_14,
            "components": {
                "technical":   r.technical_score,
                "fundamental": r.fundamental_score,
                "sentiment":   r.sentiment_score,
            },
            "signals": active_sigs,
            "computed_at": r.timestamp.isoformat() if r.timestamp else None,
        })

    last_ts_str = last_ts.replace(tzinfo=None).isoformat() if last_ts else None
    return results, last_ts_str


# ── Filters ───────────────────────────────────────────────────────────────────

def _apply_filters(
    results: List[dict],
    signal: str,
    min_score: float,
    min_rsi: float,
    max_rsi: float,
    preset: str,
    sort_by: str,
) -> List[dict]:
    """Apply filter + preset + sort server-side."""
    out = []
    for r in results:
        if signal != "ALL" and r["signal"] != signal:
            continue
        if r["score"] < min_score:
            continue
        rsi = r.get("rsi")
        if rsi is not None and (rsi < min_rsi or rsi > max_rsi):
            continue

        if preset == "breakout":
            sigs = r.get("signals", [])
            is_buy = r["signal"] in ("BUY", "STRONG BUY")
            has_breakout = any(
                kw in s for s in sigs for kw in ("Volume", "Supertrend", "MACD Bullish", "EMA Bullish")
            )
            if not (is_buy and has_breakout):
                continue

        if preset == "reversal":
            rsi_val = rsi if rsi is not None else 50
            if not (rsi_val < 35 and r["signal"] in ("BUY", "STRONG BUY")):
                continue

        out.append(r)

    if sort_by == "rsi":
        out.sort(key=lambda x: (x.get("rsi") is None, x.get("rsi") or 0))
    elif sort_by == "change_pct":
        out.sort(key=lambda x: -(x.get("change_pct") or 0))
    elif sort_by == "symbol":
        out.sort(key=lambda x: x["symbol"])
    else:
        out.sort(key=lambda x: -x["score"])

    return out


# ── GET /api/screener ─────────────────────────────────────────────────────────

@router.get("/screener")
async def run_screener(
    universe: str  = Query(default="nifty50",  description="nifty50 | nifty200 | custom"),
    symbols:  Optional[str] = Query(default=None, description="Comma-separated when universe=custom"),
    signal:   str  = Query(default="ALL"),
    min_score: float = Query(default=0, ge=0, le=100),
    min_rsi:   float = Query(default=0,  ge=0, le=100),
    max_rsi:   float = Query(default=100, ge=0, le=100),
    preset:    str   = Query(default="custom"),
    sort_by:   str   = Query(default="score"),
    limit:     int   = Query(default=50, ge=1, le=250),
    live:      bool  = Query(default=False, description="Force live computation even for standard universes"),
):
    """
    Scan a universe of stocks and return filtered, ranked results.
    - nifty50 / nifty200: reads pre-computed DB records (instant)
    - custom or ?live=true: triggers live real-time analysis
    """
    is_custom = universe == "custom" or live

    if is_custom:
        sym_list = [s.strip().upper() for s in (symbols or "").split(",") if s.strip()] or NIFTY50_SYMBOLS
        sym_list = sym_list[:limit]
        cache = get_cache()
        logger.info(f"Screener (LIVE): {len(sym_list)} symbols")
        raw_results = await _run_live_batch(sym_list, cache)
        data_source = "live"
        last_computed = datetime.now(IST).isoformat()
    else:
        sym_list = get_universe(universe)[:limit]
        logger.info(f"Screener (PRE-COMPUTED): reading {len(sym_list)} symbols from DB")
        raw_results, last_computed = await _read_precomputed(sym_list)

        # Fallback to live if no pre-computed data
        if not raw_results:
            logger.warning("Screener: no pre-computed data found, falling back to live scan")
            cache = get_cache()
            raw_results = await _run_live_batch(sym_list[:50], cache)  # cap at 50 for live fallback
            data_source = "live_fallback"
            last_computed = datetime.now(IST).isoformat()
        else:
            data_source = "precomputed"

    filtered = _apply_filters(raw_results, signal, min_score, min_rsi, max_rsi, preset, sort_by)

    return {
        "total_scanned":  len(sym_list),
        "total_found":    len(raw_results),
        "total_filtered": len(filtered),
        "preset":         preset,
        "universe":       universe,
        "data_source":    data_source,
        "last_computed":  last_computed,
        "results":        filtered,
    }

# ── GET /api/screener/top-signals ─────────────────────────────────────────────

@router.get("/screener/top-signals")
async def get_top_signals(
    limit:    int  = Query(default=5, ge=1, le=20),
    signal:   str  = Query(default="BUY,STRONG BUY", description="Comma-separated signals to include"),
    universe: str  = Query(default="nifty200", description="nifty50 | nifty200"),
):
    """
    Returns top N stocks by composite score from the nightly pre-computed DB.
    Designed for the Dashboard 'Top Buy Signals Today' right panel.
    """
    import json as _json
    from backend.data.nse_universe import get_universe
    from backend.models.database import AsyncSessionLocal
    from backend.models.schemas import AnalysisScore
    from sqlalchemy import select, func as sqlfunc
    from datetime import datetime, timedelta

    allowed_signals = [s.strip() for s in signal.split(",") if s.strip()]
    sym_list = get_universe(universe)
    cutoff = datetime.utcnow() - timedelta(hours=PRECOMPUTE_MAX_AGE_H)

    try:
        async with AsyncSessionLocal() as db:
            subq = (
                select(
                    AnalysisScore.symbol,
                    sqlfunc.max(AnalysisScore.timestamp).label("max_ts")
                )
                .where(
                    AnalysisScore.symbol.in_(sym_list),
                    AnalysisScore.timestamp >= cutoff,
                    AnalysisScore.signal.in_(allowed_signals),
                )
                .group_by(AnalysisScore.symbol)
                .subquery()
            )
            result = await db.execute(
                select(AnalysisScore)
                .join(
                    subq,
                    (AnalysisScore.symbol == subq.c.symbol) &
                    (AnalysisScore.timestamp == subq.c.max_ts)
                )
                .order_by(AnalysisScore.composite_score.desc())
                .limit(limit)
            )
            rows = result.scalars().all()

        signals_out = []
        last_ts = None
        for r in rows:
            if last_ts is None or (r.timestamp and r.timestamp > last_ts):
                last_ts = r.timestamp
            active_sigs = []
            try:
                active_sigs = _json.loads(r.active_signals or "[]")
            except Exception:
                pass
            conf = r.confidence or 0
            signals_out.append({
                "symbol":         r.symbol,
                "ticker":         r.symbol.replace(".NS", "").replace(".BO", ""),
                "score":          round(r.composite_score or 0, 1),
                "signal":         r.signal or "HOLD",
                "confidence":     round(conf * 100) if conf <= 1 else round(conf),
                "regime":         r.regime or "SIDEWAYS",
                "price":          r.current_price,
                "stop_loss":      r.stop_loss,
                "target_base_5d": r.target_base_5d,
                "components": {
                    "technical":   round(r.technical_score or 0),
                    "fundamental": round(r.fundamental_score or 0),
                    "sentiment":   round(r.sentiment_score or 0),
                },
                "active_signals": active_sigs[:3],
                "computed_at":    r.timestamp.isoformat() if r.timestamp else None,
            })

        return {
            "count":         len(signals_out),
            "universe":      universe,
            "data_source":   "precomputed" if signals_out else "empty",
            "last_computed": last_ts.isoformat() if last_ts else None,
            "results":       signals_out,
        }
    except Exception as e:
        logger.error(f"top-signals endpoint failed: {e}")
        return {"count": 0, "universe": universe, "data_source": "error", "last_computed": None, "results": []}


# ── GET /api/screener/status ──────────────────────────────────────────────────

@router.get("/screener/status")
async def get_screener_status():
    """Returns nightly pre-computation job status and last run metadata."""
    cache = get_cache()
    status = cache.get("nightly_status", {})
    last_updated = cache.get("last_updated", {})

    # Compute next scheduled run (next weekday 4:00 PM IST)
    now = datetime.now(IST)
    next_run = None
    for days_ahead in range(1, 8):
        candidate = now.replace(hour=16, minute=0, second=0, microsecond=0)
        candidate = candidate.__class__(
            candidate.year, candidate.month, candidate.day,
            16, 0, 0, 0, IST
        )
        from datetime import timedelta as td
        candidate = (now + td(days=days_ahead)).replace(hour=16, minute=0, second=0, microsecond=0)
        if candidate.weekday() < 5:  # Mon–Fri
            next_run = candidate.isoformat()
            break

    return {
        **status,
        "next_scheduled_run": next_run,
        "last_nightly_precompute": last_updated.get("nightly_precompute"),
    }


# ── POST /api/screener/trigger-nightly ───────────────────────────────────────

@router.post("/screener/trigger-nightly")
async def trigger_nightly_precompute(universe: str = Query(default="nifty200")):
    """
    Manually trigger the nightly pre-computation (for testing without waiting for 4 PM).
    Runs in background — poll /api/screener/status for progress.
    """
    from backend.data.scheduler import job_nightly_precompute
    cache = get_cache()

    if cache.get("nightly_status", {}).get("status") == "running":
        return {"status": "already_running", "message": "Nightly job is already in progress"}

    # Fire and forget
    asyncio.create_task(job_nightly_precompute(universe))
    return {
        "status": "started",
        "universe": universe,
        "message": f"Nightly pre-computation started for {universe}. Poll /api/screener/status for progress.",
    }
