"""
ATBot — Background Scheduler
APScheduler jobs for all data refresh tasks:
- Every 5 min (market hours): OHLCV + live quotes
- Every 10 min: News feed refresh
- Daily 6 PM IST: Fundamentals + FII/DII update
- Daily 8:45 AM IST: Morning briefing generation
- Daily 9 AM IST: Market holiday + VIX check
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import logging

from backend.config import settings, IST, NIFTY50_SYMBOLS
from backend.data.market_data import (
    fetch_multiple_ohlcv, fetch_index_data,
    fetch_global_cues, is_market_open
)
from backend.data.nse_live import get_fii_dii_data, get_market_breadth, get_india_vix
from backend.data.news_feed import fetch_all_rss_feeds
from backend.data.fundamentals import fetch_fundamentals_yfinance, get_upcoming_earnings

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = AsyncIOScheduler(timezone=IST)

# In-memory cache for latest data (until DB is available)
_cache = {
    "ohlcv": {},
    "indices": {},
    "global_cues": {},
    "fii_dii": None,
    "market_breadth": None,
    "india_vix": None,
    "news": [],
    "fundamentals": {},
    "upcoming_earnings": [],
    "morning_briefing": None,
    "last_updated": {},
}


# ── Market Data Jobs ──────────────────────────────────────────────────────

async def job_refresh_market_data():
    """
    Refresh OHLCV data + index levels.
    Runs every 5 minutes during market hours only.
    """
    if not is_market_open():
        return   # Skip outside market hours

    logger.info("🔄 [Scheduler] Refreshing market data...")
    try:
        # Refresh Nifty 50 OHLCV
        data = fetch_multiple_ohlcv(NIFTY50_SYMBOLS[:10], interval="5m", period="1d")
        _cache["ohlcv"].update(data)

        # Refresh index levels
        indices = fetch_index_data()
        _cache["indices"] = indices

        _cache["last_updated"]["market_data"] = datetime.now(IST).isoformat()
        logger.info(f"✅ Market data refreshed — {len(data)} symbols updated")

    except Exception as e:
        logger.error(f"❌ Market data refresh failed: {e}")


async def job_refresh_index_data():
    """Refresh Nifty, Sensex, VIX levels. Runs every 5 min."""
    try:
        _cache["indices"] = fetch_index_data()
        _cache["india_vix"] = get_india_vix()
        _cache["market_breadth"] = get_market_breadth()
        _cache["last_updated"]["indices"] = datetime.now(IST).isoformat()
    except Exception as e:
        logger.error(f"❌ Index refresh failed: {e}")


# ── News Jobs ─────────────────────────────────────────────────────────────

async def job_refresh_news():
    """
    Refresh news from all RSS feeds.
    Runs every 10 minutes continuously (not just market hours).
    """
    logger.info("📰 [Scheduler] Refreshing news feeds...")
    try:
        articles = fetch_all_rss_feeds()
        # Prepend new articles, keep last 500
        existing_ids = {a["id"] for a in _cache["news"]}
        new_articles = [a for a in articles if a["id"] not in existing_ids]

        if new_articles:
            _cache["news"] = (new_articles + _cache["news"])[:500]
            logger.info(f"📰 Added {len(new_articles)} new articles")

        _cache["last_updated"]["news"] = datetime.now(IST).isoformat()

    except Exception as e:
        logger.error(f"❌ News refresh failed: {e}")


# ── Fundamentals Jobs ─────────────────────────────────────────────────────

async def job_refresh_fundamentals():
    """
    Refresh fundamental data for all Nifty 50 stocks.
    Runs daily at 6 PM IST after market close.
    """
    logger.info("📊 [Scheduler] Refreshing fundamentals...")
    count = 0
    for symbol in NIFTY50_SYMBOLS:
        try:
            data = fetch_fundamentals_yfinance(symbol)
            if data:
                _cache["fundamentals"][symbol] = data
                count += 1
        except Exception as e:
            logger.warning(f"Fundamentals failed for {symbol}: {e}")

    logger.info(f"✅ Fundamentals refreshed for {count} symbols")
    _cache["last_updated"]["fundamentals"] = datetime.now(IST).isoformat()


async def job_refresh_fii_dii():
    """
    Refresh FII/DII flow data.
    Runs daily at 6 PM IST (NSE publishes after market close).
    """
    logger.info("🏦 [Scheduler] Refreshing FII/DII data...")
    try:
        data = get_fii_dii_data()
        if data:
            _cache["fii_dii"] = data
            logger.info(f"✅ FII net: ₹{data.get('fii_net')} Cr | DII net: ₹{data.get('dii_net')} Cr")
        _cache["last_updated"]["fii_dii"] = datetime.now(IST).isoformat()
    except Exception as e:
        logger.error(f"❌ FII/DII refresh failed: {e}")


# ── Earnings Job ──────────────────────────────────────────────────────────

async def job_refresh_earnings():
    """
    Check upcoming earnings for the week.
    Runs daily at 9 AM IST.
    """
    logger.info("📅 [Scheduler] Checking upcoming earnings...")
    try:
        earnings = get_upcoming_earnings(NIFTY50_SYMBOLS)
        _cache["upcoming_earnings"] = earnings
        if earnings:
            logger.info(f"📅 {len(earnings)} earnings events this week")
        _cache["last_updated"]["earnings"] = datetime.now(IST).isoformat()
    except Exception as e:
        logger.error(f"❌ Earnings refresh failed: {e}")


# ── Morning Briefing Job ──────────────────────────────────────────────────

async def job_morning_briefing():
    """
    Generate the daily morning briefing at 8:45 AM IST.
    Assembles: global cues, FII/DII, VIX, earnings, top signals.
    """
    logger.info("🌅 [Scheduler] Generating morning briefing...")
    try:
        global_cues = fetch_global_cues()
        vix_data = get_india_vix()
        fii_dii = _cache.get("fii_dii")
        earnings = _cache.get("upcoming_earnings", [])

        briefing = {
            "generated_at": datetime.now(IST).isoformat(),
            "global_cues": global_cues,
            "india_vix": vix_data,
            "fii_dii": fii_dii,
            "earnings_today": [e for e in earnings if e.get("days_away") == 0],
            "earnings_this_week": earnings,
            "market_comment": _generate_market_comment(vix_data, fii_dii),
        }

        _cache["morning_briefing"] = briefing
        logger.info("✅ Morning briefing generated")

    except Exception as e:
        logger.error(f"❌ Morning briefing failed: {e}")


def _generate_market_comment(vix_data: dict, fii_dii: dict) -> str:
    """Generate a plain-English market comment for the morning briefing."""
    comments = []

    if vix_data:
        comments.append(vix_data.get("risk_comment", ""))

    if fii_dii:
        fii_net = fii_dii.get("fii_net", 0)
        if fii_net > 1000:
            comments.append(f"FIIs were strong net buyers (₹{fii_net:,.0f} Cr) — bullish signal.")
        elif fii_net > 0:
            comments.append(f"FIIs were mild net buyers (₹{fii_net:,.0f} Cr).")
        elif fii_net < -1000:
            comments.append(f"FIIs were heavy net sellers (₹{abs(fii_net):,.0f} Cr) — caution advised.")
        else:
            comments.append(f"FIIs were mild net sellers (₹{abs(fii_net):,.0f} Cr).")

    return " ".join(filter(None, comments))


# ── Scheduler Setup ───────────────────────────────────────────────────────

def setup_scheduler():
    """Register all scheduled jobs and configure triggers."""

    # Every 5 min during market hours: OHLCV + index refresh
    scheduler.add_job(
        job_refresh_market_data,
        trigger=IntervalTrigger(minutes=settings.market_data_interval_minutes),
        id="market_data",
        name="Market Data Refresh",
        replace_existing=True,
    )

    scheduler.add_job(
        job_refresh_index_data,
        trigger=IntervalTrigger(minutes=5),
        id="index_data",
        name="Index & VIX Refresh",
        replace_existing=True,
    )

    # Every 10 min: News feed
    scheduler.add_job(
        job_refresh_news,
        trigger=IntervalTrigger(minutes=settings.news_refresh_interval_minutes),
        id="news_feed",
        name="News Feed Refresh",
        replace_existing=True,
    )

    # Daily 6 PM IST: Fundamentals + FII/DII
    scheduler.add_job(
        job_refresh_fundamentals,
        trigger=CronTrigger(hour=settings.fundamentals_refresh_hour, minute=0, timezone=IST),
        id="fundamentals",
        name="Fundamentals Refresh",
        replace_existing=True,
    )

    scheduler.add_job(
        job_refresh_fii_dii,
        trigger=CronTrigger(hour=18, minute=15, timezone=IST),
        id="fii_dii",
        name="FII/DII Data Refresh",
        replace_existing=True,
    )

    # Daily 9 AM IST: Earnings calendar
    scheduler.add_job(
        job_refresh_earnings,
        trigger=CronTrigger(hour=9, minute=0, timezone=IST),
        id="earnings",
        name="Earnings Calendar",
        replace_existing=True,
    )

    # Daily 8:45 AM IST: Morning briefing
    scheduler.add_job(
        job_morning_briefing,
        trigger=CronTrigger(
            hour=settings.morning_briefing_hour,
            minute=settings.morning_briefing_minute,
            timezone=IST
        ),
        id="morning_briefing",
        name="Morning Briefing",
        replace_existing=True,
    )

    logger.info("✅ All scheduler jobs registered")
    return scheduler


def get_cache() -> dict:
    """Return the current in-memory data cache."""
    return _cache
