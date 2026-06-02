"""
ATBot — News Endpoints
Routes for serving cached news feeds to the dashboard
"""

from fastapi import APIRouter
from typing import Optional
import logging

from backend.data.scheduler import get_cache
from backend.data.news_feed import fetch_finnhub_news

logger = logging.getLogger(__name__)

router = APIRouter(tags=["News"])

@router.get("/news/market")
async def get_market_news(limit: int = 50):
    """
    Get general market and economic news from RSS feeds.
    Served instantly from cache.
    """
    cache = get_cache()
    news = cache.get("news", [])
    return news[:limit]


@router.get("/news/{symbol}")
async def get_stock_news(symbol: str, limit: int = 10):
    """
    Get company-specific news.
    """
    # 1. Check cache for matches
    cache = get_cache()
    cached_news = [n for n in cache.get("news", []) if n.get("symbol") == symbol.upper()]
    
    # 2. If not enough in cache, fetch from Finnhub
    if len(cached_news) < limit:
        finnhub_news = fetch_finnhub_news(symbol.upper(), days_back=7)
        # Combine and deduplicate
        seen_urls = {n.get("url") for n in cached_news}
        for fn in finnhub_news:
            if fn.get("url") not in seen_urls:
                cached_news.append(fn)
                
    # Sort by date
    cached_news.sort(key=lambda x: x.get("published_at"), reverse=True)
    return cached_news[:limit]
