"""
ATBot — Market & Screener Endpoints
Routes for market breadth, index status, and screener functionality
"""

from fastapi import APIRouter, Query
import logging

from backend.data.scheduler import get_cache
from backend.data.market_data import fetch_ohlcv

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Market"])

@router.get("/ohlcv/{symbol}")
async def get_ohlcv(
    symbol: str,
    period: str = Query("6mo", description="yfinance period: 1mo, 3mo, 6mo, 1y"),
    interval: str = Query("1d", description="yfinance interval: 1d, 1wk"),
):
    """
    Returns OHLCV data for a symbol formatted for lightweight-charts.
    Each bar: { time: 'YYYY-MM-DD', open, high, low, close, volume }
    """
    try:
        df = fetch_ohlcv(symbol, interval=interval, period=period)
        if df is None or df.empty:
            return []

        bars = []
        for idx, row in df.iterrows():
            # idx is a Timestamp
            time_str = idx.strftime("%Y-%m-%d")
            bars.append({
                "time": time_str,
                "open":  round(float(row["Open"]),  2),
                "high":  round(float(row["High"]),  2),
                "low":   round(float(row["Low"]),   2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]) if "Volume" in row else 0,
            })

        return bars
    except Exception as e:
        logger.error(f"OHLCV fetch failed for {symbol}: {e}")
        return []

@router.get("/market/overview")
async def get_market_overview():
    """
    Returns the complete market overview for the dashboard header.
    Served instantly from the background scheduler cache.
    """
    cache = get_cache()
    return {
        "indices": cache.get("indices", {}),
        "market_breadth": cache.get("market_breadth", {}),
        "india_vix": cache.get("india_vix", {}),
        "fii_dii": cache.get("fii_dii", {}),
        "last_updated": cache.get("last_updated", {})
    }


@router.get("/market/briefing")
async def get_morning_briefing():
    """Returns today's morning briefing."""
    cache = get_cache()
    return cache.get("morning_briefing", {"status": "Briefing not generated yet"})


@router.post("/screener")
async def run_screener(filters: dict):
    """
    Run custom screener on the Nifty 50 / NSE universe.
    (Stub endpoint - will be implemented with DB queries later)
    """
    # In a full implementation, this would query the 'analysis_scores' DB table
    # using SQLAlchemy based on the provided filters.
    return {
        "message": "Screener will be fully active once historical DB population is done",
        "results": []
    }
