"""
ATBot — Screener Endpoint
Runs a batch analysis of a stock universe (Nifty 50 or custom list)
and returns ranked, filtered results.
"""

import asyncio
import logging
from typing import Optional, List
from fastapi import APIRouter, Query

from backend.config import NIFTY50_SYMBOLS
from backend.data.market_data import fetch_ohlcv
from backend.data.fundamentals import fetch_fundamentals_yfinance
from backend.data.news_feed import fetch_finnhub_news
from backend.data.nse_live import get_fii_dii_data
from backend.data.scheduler import get_cache
from backend.engines.technical_engine import analyze_technical
from backend.engines.fundamental_engine import analyze_fundamental
from backend.engines.sentiment_engine import analyze_sentiment
from backend.engines.ensemble_scorer import calculate_composite

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Screener"])

BATCH_SIZE = 8  # concurrent yfinance calls


async def _analyze_one(symbol: str, cache: dict) -> Optional[dict]:
    """
    Run the full 3-engine analysis for one symbol and return a slim result dict.
    Returns None if analysis fails (symbol skipped silently).
    """
    try:
        # Pull shared market context from cache (computed once, reused for all stocks)
        indices       = cache.get("indices") or {}
        nifty_data    = indices.get("NIFTY50") or {}
        nifty_change  = nifty_data.get("change_pct", 0.0)
        nifty_change_20d = nifty_data.get("change_pct_20d", 0.0)
        vix_data      = cache.get("india_vix") or {}
        vix           = vix_data.get("vix", 14.0)
        fii_dii       = cache.get("fii_dii") or get_fii_dii_data()

        # Run blocking IO in thread pool so we don't block the event loop
        loop = asyncio.get_event_loop()

        ohlcv_df     = await loop.run_in_executor(None, lambda: fetch_ohlcv(symbol, interval="1d", period="6mo"))
        if ohlcv_df is None or ohlcv_df.empty:
            return None

        fundamentals = await loop.run_in_executor(None, lambda: fetch_fundamentals_yfinance(symbol))
        news         = await loop.run_in_executor(None, lambda: fetch_finnhub_news(symbol))

        # Engines (CPU-bound but fast — run in same thread is fine)
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


async def _run_batch(symbols: List[str], cache: dict) -> List[dict]:
    """Run analysis in parallel batches of BATCH_SIZE."""
    results = []
    for i in range(0, len(symbols), BATCH_SIZE):
        batch = symbols[i: i + BATCH_SIZE]
        batch_results = await asyncio.gather(*[_analyze_one(s, cache) for s in batch])
        results.extend([r for r in batch_results if r is not None])
        logger.info(f"Screener: processed {min(i + BATCH_SIZE, len(symbols))}/{len(symbols)}")
    return results


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
        # Signal filter
        if signal != "ALL" and r["signal"] != signal:
            continue
        # Score filter
        if r["score"] < min_score:
            continue
        # RSI filter
        rsi = r.get("rsi")
        if rsi is not None and (rsi < min_rsi or rsi > max_rsi):
            continue

        # Preset filters
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

    # Sort
    if sort_by == "rsi":
        out.sort(key=lambda x: (x.get("rsi") is None, x.get("rsi") or 0))
    elif sort_by == "change_pct":
        out.sort(key=lambda x: -(x.get("change_pct") or 0))
    elif sort_by == "symbol":
        out.sort(key=lambda x: x["symbol"])
    else:  # default: score desc
        out.sort(key=lambda x: -x["score"])

    return out


@router.get("/screener")
async def run_screener(
    universe: str = Query(default="nifty50", description="nifty50 | custom"),
    symbols: Optional[str] = Query(default=None, description="Comma-separated symbols when universe=custom"),
    signal: str  = Query(default="ALL"),
    min_score: float = Query(default=0, ge=0, le=100),
    min_rsi:   float = Query(default=0,  ge=0, le=100),
    max_rsi:   float = Query(default=100, ge=0, le=100),
    preset:    str   = Query(default="custom", description="custom | breakout | reversal"),
    sort_by:   str   = Query(default="score",  description="score | rsi | change_pct | symbol"),
    limit:     int   = Query(default=50, ge=1, le=100),
):
    """
    Scan a universe of stocks and return filtered, ranked analysis results.
    """
    # Resolve universe
    if universe == "custom" and symbols:
        sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    else:
        sym_list = NIFTY50_SYMBOLS

    sym_list = sym_list[:limit]

    # Grab shared market context once
    cache = get_cache()

    logger.info(f"Screener: scanning {len(sym_list)} symbols (universe={universe}, preset={preset})")
    raw_results = await _run_batch(sym_list, cache)

    filtered = _apply_filters(raw_results, signal, min_score, min_rsi, max_rsi, preset, sort_by)

    return {
        "total_scanned": len(sym_list),
        "total_found":   len(raw_results),
        "total_filtered": len(filtered),
        "preset":  preset,
        "universe": universe,
        "results": filtered,
    }
