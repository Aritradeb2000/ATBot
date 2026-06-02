"""
ATBot — Market & Screener Endpoints
Routes for market breadth, index status, and screener functionality
"""

from fastapi import APIRouter
import logging

from backend.data.scheduler import get_cache

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Market"])

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
