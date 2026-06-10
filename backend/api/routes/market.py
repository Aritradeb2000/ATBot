"""
ATBot — Market & Screener Endpoints
Routes for market breadth, index status, and screener functionality
"""

from fastapi import APIRouter, Query
import logging
import yfinance as yf

from backend.data.scheduler import get_cache
from backend.data.market_data import fetch_ohlcv
from backend.data.nse_live import get_fii_dii_history

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


# ── NEW: Market Intelligence Endpoints ───────────────────────────────────────

@router.get("/market/fii-history")
async def get_fii_dii_history_endpoint(days: int = Query(default=30, ge=5, le=90)):
    """
    Returns FII/DII net flow for the last N trading days.
    Each entry: { date, fii_net, dii_net }
    """
    try:
        history = get_fii_dii_history(days=days)
        # Reverse so oldest is first (charts go left→right)
        return list(reversed(history))
    except Exception as e:
        logger.error(f"FII/DII history endpoint failed: {e}")
        return []


@router.get("/market/vix-history")
async def get_vix_history(days: int = Query(default=30, ge=5, le=90)):
    """
    Returns India VIX closing values for the last N trading days.
    Each entry: { date: 'YYYY-MM-DD', vix: float }
    """
    try:
        ticker = yf.Ticker("^INDIAVIX")
        hist = ticker.history(period=f"{int(days * 1.5)}d", interval="1d")
        if hist.empty:
            return []

        result = []
        for idx, row in hist.tail(days).iterrows():
            result.append({
                "date": idx.strftime("%Y-%m-%d"),
                "vix": round(float(row["Close"]), 2),
            })
        return result
    except Exception as e:
        logger.error(f"VIX history endpoint failed: {e}")
        return []


# Nifty sector indices (yfinance tickers)
SECTOR_INDICES = {
    "IT":      "^CNXIT",
    "Bank":    "^NSEBANK",
    "FMCG":    "^CNXFMCG",
    "Auto":    "^CNXAUTO",
    "Pharma":  "^CNXPHARMA",
    "Realty":  "^CNXREALTY",
    "Metal":   "^CNXMETAL",
    "Energy":  "^CNXENERGY",
}


@router.get("/market/sector-heatmap")
async def get_sector_heatmap():
    """
    Returns today's % change for 8 Nifty sector indices.
    Each entry: { sector, change_pct, price }
    """
    result = []
    for sector, ticker in SECTOR_INDICES.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="5d", interval="1d")
            if hist.empty or len(hist) < 2:
                continue
            latest = hist.iloc[-1]
            prev   = hist.iloc[-2]
            change_pct = ((latest["Close"] - prev["Close"]) / prev["Close"]) * 100
            result.append({
                "sector":     sector,
                "price":      round(float(latest["Close"]), 2),
                "change_pct": round(change_pct, 2),
            })
        except Exception as e:
            logger.warning(f"Sector heatmap: skipping {sector} — {e}")

    result.sort(key=lambda x: -x["change_pct"])
    return result


@router.post("/screener")
async def run_screener_stub(filters: dict):
    """Stub endpoint — real screener is at GET /api/screener."""
    return {"message": "Use GET /api/screener", "results": []}
