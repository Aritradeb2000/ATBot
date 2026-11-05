"""
ATBot — News Endpoints
Routes for serving cached RSS news, Zerodha Pulse feeds, and stock-specific news.
"""

from fastapi import APIRouter
from typing import Optional
import logging

from backend.data.scheduler import get_cache
from backend.data.news_feed import fetch_finnhub_news, fetch_zerodha_pulse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["News"])


@router.get("/news/market")
async def get_market_news(limit: int = 50):
    """
    Get general market and economic news from aggregated RSS feeds (including Zerodha Pulse).
    Served instantly from cache.
    """
    cache = get_cache()
    news = cache.get("news", [])
    if not news:
        # If cache is still cold on startup, fetch live from Zerodha Pulse
        news = fetch_zerodha_pulse(max_articles=limit)
    return news[:limit]


@router.get("/news/pulse")
async def get_pulse_news(symbol: Optional[str] = None, limit: int = 50):
    """
    Get latest curated market news directly from Zerodha Pulse (https://pulse.zerodha.com).
    Optionally filtered by stock ticker symbol.
    """
    return fetch_zerodha_pulse(symbol=symbol, max_articles=limit)


@router.get("/news/{symbol}")
async def get_stock_news(symbol: str, limit: int = 10):
    """
    Get company-specific news.
    First searches cached market feeds, then queries Zerodha Pulse and Finnhub/fallback.
    """
    sym_upper = symbol.upper()
    cache = get_cache()

    # 1. Check cache for matched articles
    cached_news = [n for n in cache.get("news", []) if n.get("symbol") == sym_upper]
    seen_urls = {n.get("url") for n in cached_news if n.get("url")}

    # 2. If not enough in cache, query Zerodha Pulse specifically for this symbol
    if len(cached_news) < limit:
        pulse_news = fetch_zerodha_pulse(symbol=sym_upper, max_articles=limit)
        for pn in pulse_news:
            if pn.get("url") not in seen_urls:
                seen_urls.add(pn.get("url"))
                cached_news.append(pn)

    # 3. If still below limit, query Finnhub / Google News fallback
    if len(cached_news) < limit:
        finnhub_news = fetch_finnhub_news(sym_upper, days_back=7, max_articles=limit)
        for fn in finnhub_news:
            if fn.get("url") not in seen_urls:
                seen_urls.add(fn.get("url"))
                cached_news.append(fn)

    # Sort by published date descending
    cached_news.sort(
        key=lambda x: str(x.get("published_at") or ""),
        reverse=True
    )
    return cached_news[:limit]
