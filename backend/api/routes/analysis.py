"""
ATBot — Analysis Endpoints
Routes for getting technical, fundamental, sentiment and composite scores
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
import logging

import json
from backend.data.market_data import fetch_ohlcv, get_current_price
from backend.data.fundamentals import fetch_fundamentals_yfinance
from backend.data.news_feed import fetch_finnhub_news
from backend.data.nse_live import get_fii_dii_data
from backend.data.scheduler import get_cache
from backend.models.database import get_db
from backend.models.schemas import AnalysisScore
from sqlalchemy.ext.asyncio import AsyncSession

from backend.engines.technical_engine import analyze_technical
from backend.engines.fundamental_engine import analyze_fundamental
from backend.engines.sentiment_engine import analyze_sentiment
from backend.engines.ensemble_scorer import calculate_composite

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Analysis"])

@router.get("/analyze/{symbol}")
async def get_full_analysis(symbol: str, capital: Optional[float] = None, db: AsyncSession = Depends(get_db)):
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
    nifty_change_20d = nifty_data.get("change_pct_20d", 0.0)
    
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
        nifty_change_20d=nifty_change_20d,
        vix=vix,
        user_capital=capital
    )

    # 4. Save to Database
    try:
        score_record = AnalysisScore(
            symbol=symbol,
            technical_score=final_result.get("technical_score"),
            fundamental_score=final_result.get("fundamental_score"),
            sentiment_score=final_result.get("sentiment_score"),
            composite_score=final_result.get("composite_score"),
            signal=final_result.get("signal"),
            confidence=0.8,  # Hardcoded for now until confidence is added to ensemble
            current_price=tech_result.get("close"),
            target_low_5d=final_result.get("targets", {}).get("5d_low"),
            target_base_5d=final_result.get("targets", {}).get("5d_base"),
            target_high_5d=final_result.get("targets", {}).get("5d_high"),
            target_low_10d=final_result.get("targets", {}).get("10d_low"),
            target_base_10d=final_result.get("targets", {}).get("10d_base"),
            target_high_10d=final_result.get("targets", {}).get("10d_high"),
            stop_loss=final_result.get("stop_loss"),
            active_signals=json.dumps(tech_result.get("signals", [])),
            dominant_pattern=tech_result.get("trend"),
            atr_14=tech_result.get("atr_14")
        )
        db.add(score_record)
        await db.commit()
    except Exception as e:
        logger.error(f"Failed to save AnalysisScore for {symbol}: {e}")

    return {
        "symbol": symbol,
        "company_name": fundamentals.get("company_name", symbol) if fundamentals else symbol,
        "current_price": tech_result.get("close"),
        "change": tech_result.get("change"),
        "change_pct": tech_result.get("change_pct"),
        "analysis": final_result,
        "details": {
            "technical": tech_result,
            "fundamental": fund_result,
            "sentiment": sent_result
        }
    }


@router.get("/score/{symbol}")
async def get_quick_score(symbol: str, db: AsyncSession = Depends(get_db)):
    """
    Returns only the composite score and signal.
    Useful for watchlist updates.
    """
    # For a production system with many users, this would ideally hit a cached value
    # or an async DB table populated by a background worker.
    # For now, we reuse the full analysis pipeline.
    res = await get_full_analysis(symbol, capital=None, db=db)
    return {
        "symbol": symbol,
        "current_price": res["current_price"],
        "composite_score": res["analysis"]["composite_score"],
        "signal": res["analysis"]["signal"],
        "confidence": res["analysis"]["confidence"]
    }
