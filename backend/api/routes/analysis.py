"""
ATBot — Analysis Endpoints
Routes for getting technical, fundamental, sentiment and composite scores
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
import logging

from backend.data.market_data import fetch_ohlcv, get_current_price
from backend.data.fundamentals import fetch_fundamentals_yfinance
from backend.data.news_feed import fetch_finnhub_news
from backend.data.nse_live import get_fii_dii_data
from backend.data.scheduler import get_cache

from backend.engines.technical_engine import analyze_technical
from backend.engines.fundamental_engine import analyze_fundamental
from backend.engines.sentiment_engine import analyze_sentiment
from backend.engines.ensemble_scorer import calculate_composite

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Analysis"])

@router.get("/analyze/{symbol}")
async def get_full_analysis(symbol: str, capital: Optional[float] = None):
    """
    Perform a complete, real-time analysis of a stock across all 3 engines.
    Optionally accepts a 'capital' parameter to calculate suggested position sizing.
    """
    symbol = symbol.upper()
    
    # 1. Fetch Data
    # Get 6 months of daily OHLCV
    ohlcv_df = fetch_ohlcv(symbol, interval="1d", period="6mo")
    if ohlcv_df is None or ohlcv_df.empty:
        raise HTTPException(status_code=404, detail=f"No price data found for {symbol}")
        
    fundamentals = fetch_fundamentals_yfinance(symbol)
    news = fetch_finnhub_news(symbol)
    
    # Get FII/DII from cache or fetch
    cache = get_cache()
    fii_dii = cache.get("fii_dii") or get_fii_dii_data()
    
    # Market context for dynamic weighting
    indices = cache.get("indices") or {}
    nifty_data = indices.get("NIFTY50") or {}
    nifty_change = nifty_data.get("change_pct", 0.0)
    
    vix_data = cache.get("india_vix") or {}
    vix = vix_data.get("vix", 14.0)

    # 2. Run Engines
    tech_result = analyze_technical(ohlcv_df)
    fund_result = analyze_fundamental(fundamentals)
    sent_result = analyze_sentiment(news, fii_dii)

    # 3. Ensemble
    final_result = calculate_composite(
        tech_data=tech_result,
        fund_data=fund_result,
        sent_data=sent_result,
        nifty_change=nifty_change,
        vix=vix,
        user_capital=capital
    )

    return {
        "symbol": symbol,
        "company_name": fundamentals.get("company_name", symbol) if fundamentals else symbol,
        "current_price": tech_result.get("close"),
        "analysis": final_result,
        "details": {
            "technical": tech_result,
            "fundamental": fund_result,
            "sentiment": sent_result
        }
    }


@router.get("/score/{symbol}")
async def get_quick_score(symbol: str):
    """
    Returns only the composite score and signal.
    Useful for watchlist updates.
    """
    # For a production system with many users, this would ideally hit a cached value
    # or an async DB table populated by a background worker.
    # For now, we reuse the full analysis pipeline.
    res = await get_full_analysis(symbol)
    return {
        "symbol": symbol,
        "current_price": res["current_price"],
        "composite_score": res["analysis"]["composite_score"],
        "signal": res["analysis"]["signal"],
        "confidence": res["analysis"]["confidence"]
    }
