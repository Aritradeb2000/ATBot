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
from backend.engines.outcome_tracker import run_outcome_check
from backend.engines.meta_learner import compute_and_save_adaptive_weights, get_current_adaptive_weights
from backend.engines.ensemble_scorer import set_adaptive_weights

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
    # Nightly pre-computation status
    "nightly_status": {
        "status": "idle",          # idle | running | completed | failed
        "started_at": None,
        "completed_at": None,
        "universe": "nifty200",
        "total": 0,
        "saved": 0,
        "skipped": 0,
        "progress_pct": 0,
        "duration_s": None,
        "next_run": None,
    },
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
    Assembles: global cues, FII/DII, VIX, earnings, indices snapshot, top signals.
    """
    logger.info("🌅 [Scheduler] Generating morning briefing...")
    try:
        global_cues = fetch_global_cues()
        vix_data = get_india_vix()
        fii_dii = _cache.get("fii_dii")
        earnings = _cache.get("upcoming_earnings", [])
        indices = _cache.get("indices", {})

        # Pull recent top BUY + SELL signals from DB (last 24h)
        top_signals = []
        try:
            from backend.models.database import AsyncSessionLocal
            from backend.models.schemas import AnalysisScore
            from sqlalchemy import select
            from datetime import timedelta
            cutoff = datetime.now(IST).replace(tzinfo=None) - timedelta(hours=24)
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(AnalysisScore)
                    .where(AnalysisScore.timestamp >= cutoff)
                    .where(AnalysisScore.signal.in_(["BUY", "STRONG BUY", "SELL", "STRONG SELL"]))
                    .order_by(AnalysisScore.composite_score.desc())
                    .limit(8)
                )
                rows = result.scalars().all()
                # Deduplicate by symbol — keep highest score per unique stock
                seen: dict = {}
                for r in rows:
                    sym = r.symbol
                    if sym not in seen or (r.composite_score or 0) > seen[sym].composite_score:
                        seen[sym] = r
                top_signals = [
                    {
                        "symbol": r.symbol,
                        "signal": r.signal,
                        "score": round(r.composite_score or 0, 1),
                        "price": r.current_price,
                        "confidence": round(r.confidence or 0, 1),
                    }
                    for r in sorted(seen.values(), key=lambda x: -(x.composite_score or 0))[:8]
                ]
        except Exception as e:
            logger.warning(f"⚠ Could not fetch top signals for briefing: {e}")

        briefing = {
            "generated_at": datetime.now(IST).isoformat(),
            "global_cues": global_cues,
            "india_vix": vix_data,
            "fii_dii": fii_dii,
            "indices": {
                "nifty50": indices.get("NIFTY50"),
                "sensex": indices.get("SENSEX"),
            },
            "earnings_today": [e for e in earnings if e.get("days_away") == 0],
            "earnings_this_week": earnings,
            "top_signals": top_signals,
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


# ── Daily Auto-Screener Job ───────────────────────────────────────────────

async def job_daily_screener():
    """
    Daily at 9:30 AM IST (Mon–Fri): automatically scan all Nifty 50 stocks
    and save scores to analysis_scores table.

    This is the primary data-collection engine for the meta-learner.
    ~50 new rows per day → outcome tracker picks them up at D5 and D10
    → meta-learner adjusts weights automatically.
    No manual screener interaction needed from the user.
    """
    logger.info("🤖 [Scheduler] Starting daily auto-screener (Nifty 50)...")
    try:
        import asyncio
        from backend.data.market_data import fetch_ohlcv
        from backend.data.fundamentals import fetch_fundamentals_yfinance
        from backend.data.news_feed import fetch_finnhub_news
        from backend.engines.technical_engine import analyze_technical
        from backend.engines.fundamental_engine import analyze_fundamental
        from backend.engines.sentiment_engine import analyze_sentiment
        from backend.engines.ensemble_scorer import calculate_composite
        from backend.models.database import AsyncSessionLocal
        from backend.models.schemas import AnalysisScore
        import json

        cache        = _cache
        indices      = cache.get("indices") or {}
        nifty_data   = indices.get("NIFTY50") or {}
        nifty_change = nifty_data.get("change_pct", 0.0)
        nifty_change_20d = nifty_data.get("change_pct_20d", 0.0)
        vix_data     = cache.get("india_vix") or {}
        vix          = vix_data.get("vix", 14.0)
        fii_dii      = cache.get("fii_dii") or {}

        # Determine today's market regime for labelling (Meta-Learner v2)
        from backend.engines.ensemble_scorer import determine_market_regime
        today_regime = determine_market_regime(nifty_change, vix, nifty_change_20d)
        logger.info(f"  Auto-screener: today's regime = {today_regime}")

        BATCH_SIZE = 8
        saved = 0
        errors = 0

        async def _score_one(symbol: str):
            nonlocal saved, errors
            try:
                loop = asyncio.get_event_loop()
                ohlcv_df     = await loop.run_in_executor(None, lambda: fetch_ohlcv(symbol, interval="1d", period="6mo"))
                if ohlcv_df is None or ohlcv_df.empty:
                    return
                fundamentals = await loop.run_in_executor(None, lambda: fetch_fundamentals_yfinance(symbol))
                news         = await loop.run_in_executor(None, lambda: fetch_finnhub_news(symbol))

                tech_result  = analyze_technical(ohlcv_df)
                fund_result  = analyze_fundamental(fundamentals)
                sent_result  = analyze_sentiment(news, fii_dii)

                final = calculate_composite(
                    tech_data=tech_result, fund_data=fund_result, sent_data=sent_result,
                    nifty_change=nifty_change, nifty_change_20d=nifty_change_20d, vix=vix,
                )

                targets = final.get("targets") or {}
                record = AnalysisScore(
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
                    regime=today_regime,  # v2: label regime at time of scan
                )
                async with AsyncSessionLocal() as db:
                    db.add(record)
                    await db.commit()
                saved += 1
            except Exception as e:
                logger.warning(f"Auto-screener: skipping {symbol} — {e}")
                errors += 1

        for i in range(0, len(NIFTY50_SYMBOLS), BATCH_SIZE):
            batch = NIFTY50_SYMBOLS[i: i + BATCH_SIZE]
            await asyncio.gather(*[_score_one(s) for s in batch])
            logger.info(f"  Auto-screener: {min(i + BATCH_SIZE, len(NIFTY50_SYMBOLS))}/{len(NIFTY50_SYMBOLS)} done")

        _cache["last_updated"]["daily_screener"] = datetime.now(IST).isoformat()
        logger.info(f"✅ Daily auto-screener complete — {saved} saved, {errors} skipped")

    except Exception as e:
        logger.error(f"❌ Daily auto-screener failed: {e}")


# ── Nightly Pre-Computation Job ───────────────────────────────────────────────

async def job_nightly_precompute(universe_name: str = "nifty200"):
    """
    Daily at 4:00 PM IST (Mon–Fri): Pre-compute scores for full Nifty 200.
    Results saved to analysis_scores DB. Screener reads from there instantly.

    Progress tracked in _cache['nightly_status'] so the UI can poll it.
    Can also be triggered manually via POST /api/screener/trigger-nightly.
    """
    from backend.data.nse_universe import get_universe
    from backend.data.market_data import fetch_ohlcv
    from backend.data.fundamentals import fetch_fundamentals_yfinance
    from backend.data.news_feed import fetch_finnhub_news
    from backend.engines.technical_engine import analyze_technical
    from backend.engines.fundamental_engine import analyze_fundamental
    from backend.engines.sentiment_engine import analyze_sentiment
    from backend.engines.ensemble_scorer import calculate_composite, determine_market_regime
    from backend.models.database import AsyncSessionLocal
    from backend.models.schemas import AnalysisScore
    import asyncio, json, time

    symbols = get_universe(universe_name)
    started = datetime.now(IST)
    start_ts = time.time()

    _cache["nightly_status"].update({
        "status": "running",
        "started_at": started.isoformat(),
        "completed_at": None,
        "universe": universe_name,
        "total": len(symbols),
        "saved": 0,
        "skipped": 0,
        "progress_pct": 0,
        "duration_s": None,
    })
    logger.info(f"🌙 [Nightly] Pre-computation started: {len(symbols)} symbols ({universe_name})")

    # Grab shared market context once
    cache        = _cache
    indices      = cache.get("indices") or {}
    nifty_data   = indices.get("NIFTY50") or {}
    nifty_change = nifty_data.get("change_pct", 0.0)
    nifty_change_20d = nifty_data.get("change_pct_20d", 0.0)
    vix_data     = cache.get("india_vix") or {}
    vix          = vix_data.get("vix", 14.0)
    fii_dii      = cache.get("fii_dii") or {}

    today_regime = determine_market_regime(nifty_change, vix, nifty_change_20d)
    logger.info(f"  Nightly: today's regime = {today_regime}")

    saved   = 0
    skipped = 0
    loop    = asyncio.get_event_loop()
    BATCH   = 8

    async def _score_one(symbol: str):
        nonlocal saved, skipped
        try:
            ohlcv_df     = await loop.run_in_executor(None, lambda: fetch_ohlcv(symbol, interval="1d", period="6mo"))
            if ohlcv_df is None or ohlcv_df.empty:
                skipped += 1
                return

            fundamentals = await loop.run_in_executor(None, lambda: fetch_fundamentals_yfinance(symbol))
            news         = await loop.run_in_executor(None, lambda: fetch_finnhub_news(symbol))

            tech_result  = analyze_technical(ohlcv_df)
            fund_result  = analyze_fundamental(fundamentals)
            sent_result  = analyze_sentiment(news, fii_dii)

            final = calculate_composite(
                tech_data=tech_result, fund_data=fund_result, sent_data=sent_result,
                nifty_change=nifty_change, nifty_change_20d=nifty_change_20d, vix=vix,
            )

            targets = final.get("targets") or {}
            record = AnalysisScore(
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
                regime=today_regime,
            )
            async with AsyncSessionLocal() as db:
                db.add(record)
                await db.commit()
            saved += 1
        except Exception as e:
            logger.warning(f"  Nightly: skipping {symbol} — {e}")
            skipped += 1

    try:
        for i in range(0, len(symbols), BATCH):
            batch = symbols[i: i + BATCH]
            await asyncio.gather(*[_score_one(s) for s in batch])
            progress = round(min(100, ((i + BATCH) / len(symbols)) * 100))
            _cache["nightly_status"]["saved"]        = saved
            _cache["nightly_status"]["skipped"]      = skipped
            _cache["nightly_status"]["progress_pct"] = progress
            logger.info(f"  Nightly: {min(i + BATCH, len(symbols))}/{len(symbols)} done (saved={saved} skipped={skipped})")

        duration = round(time.time() - start_ts, 1)
        _cache["nightly_status"].update({
            "status": "completed",
            "completed_at": datetime.now(IST).isoformat(),
            "saved": saved,
            "skipped": skipped,
            "progress_pct": 100,
            "duration_s": duration,
        })
        _cache["last_updated"]["nightly_precompute"] = datetime.now(IST).isoformat()
        logger.info(f"✅ Nightly pre-computation complete — {saved} saved, {skipped} skipped in {duration}s")

    except Exception as e:
        _cache["nightly_status"]["status"] = "failed"
        logger.error(f"❌ Nightly pre-computation failed: {e}")


# ── Outcome Tracking Job ──────────────────────────────────────────────────

async def job_check_signal_outcomes():
    """
    Daily at 6:30 PM IST: check price at Day 5 & Day 10 vs each signal's
    stop loss and target. Writes results into signal_outcomes table.
    After recording outcomes, also triggers the meta-learner.
    """
    logger.info("📊 [Scheduler] Checking signal outcomes (D5/D10)...")
    try:
        count = await run_outcome_check()
        logger.info(f"✅ Signal outcomes: {count} new records written")
        _cache["last_updated"]["signal_outcomes"] = datetime.now(IST).isoformat()
    except Exception as e:
        logger.error(f"❌ Outcome check failed: {e}")

    # After outcomes are updated, re-run meta-learner to refresh adaptive weights
    try:
        new_weights = await compute_and_save_adaptive_weights()
        set_adaptive_weights(new_weights)
        _cache["adaptive_weights"] = new_weights
        _cache["last_updated"]["meta_learner"] = datetime.now(IST).isoformat()
        logger.info("✅ Adaptive weights updated after outcome check")
    except Exception as e:
        logger.error(f"❌ Meta-learner failed: {e}")

    # Auto-generate and save a PDF accuracy report for today's record
    try:
        from backend.engines.report_generator import generate_accuracy_report
        report_path = await generate_accuracy_report(days=90, check_day=10)
        logger.info(f"📄 Daily accuracy report saved: {report_path}")
        _cache["last_updated"]["daily_report"] = datetime.now(IST).isoformat()
    except Exception as e:
        logger.error(f"❌ Daily report generation failed: {e}")


# ── Startup Catch-Up ──────────────────────────────────────────────────────────

async def startup_catchup():
    """
    Called once on server startup (via FastAPI lifespan).
    Checks whether today's scheduled jobs ran. If the server was offline at
    the scheduled time, fires the missed jobs immediately so no data is lost.

    Jobs covered:
      3:15 PM  → job_daily_screener        (check: any AnalysisScore saved today?)
      4:00 PM  → job_nightly_precompute    (check: nightly_status.completed_at today?)
      6:30 PM  → job_check_signal_outcomes (check: last_updated['signal_outcomes'] today?)
    """
    import asyncio
    from backend.models.database import AsyncSessionLocal
    from backend.models.schemas import AnalysisScore
    from sqlalchemy import select, func

    now = datetime.now(IST)
    today = now.date()
    weekday = now.weekday()  # 0=Mon, 6=Sun

    # Only catch-up on weekdays (markets closed Sat/Sun)
    if weekday >= 5:
        logger.info("🟡 [Catchup] Weekend — skipping startup catch-up")
        return

    logger.info(f"🔍 [Catchup] Checking for missed jobs on {today} (current time: {now.strftime('%H:%M')} IST)...")

    async def _has_analysis_scores_today() -> bool:
        """True if any AnalysisScore was saved today in IST."""
        try:
            cutoff_start = datetime(today.year, today.month, today.day, 0, 0, 0)
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(func.count(AnalysisScore.id))
                    .where(AnalysisScore.timestamp >= cutoff_start)
                )
                count = result.scalar() or 0
            return count > 0
        except Exception as e:
            logger.warning(f"[Catchup] DB check failed: {e}")
            return False  # assume missed → safe to re-run

    tasks_fired = []

    # ── 3:15 PM: Daily Screener ──────────────────────────────────────────
    screener_scheduled = now.replace(hour=15, minute=15, second=0, microsecond=0)
    if now >= screener_scheduled:
        has_scores = await _has_analysis_scores_today()
        if not has_scores:
            logger.warning("⚡ [Catchup] Daily screener missed — firing now")
            asyncio.create_task(job_daily_screener())
            tasks_fired.append("job_daily_screener")
        else:
            logger.info("✅ [Catchup] Daily screener already ran today")

    # ── 4:00 PM: Nightly Pre-Compute ─────────────────────────────────────
    precompute_scheduled = now.replace(hour=16, minute=0, second=0, microsecond=0)
    if now >= precompute_scheduled:
        last_precompute = _cache.get("last_updated", {}).get("nightly_precompute")
        already_ran = False
        if last_precompute:
            try:
                lp_dt = datetime.fromisoformat(last_precompute)
                already_ran = lp_dt.date() == today
            except Exception:
                pass
        # Also check nightly_status in cache (populated during this session)
        if _cache["nightly_status"].get("status") == "completed":
            completed_at = _cache["nightly_status"].get("completed_at")
            if completed_at:
                try:
                    ca_dt = datetime.fromisoformat(completed_at)
                    if ca_dt.date() == today:
                        already_ran = True
                except Exception:
                    pass
        if not already_ran:
            logger.warning("⚡ [Catchup] Nightly pre-compute missed — firing now")
            asyncio.create_task(job_nightly_precompute())
            tasks_fired.append("job_nightly_precompute")
        else:
            logger.info("✅ [Catchup] Nightly pre-compute already ran today")

    # ── 6:30 PM: Outcome Check + Report ──────────────────────────────────
    outcomes_scheduled = now.replace(hour=18, minute=30, second=0, microsecond=0)
    if now >= outcomes_scheduled:
        last_outcomes = _cache.get("last_updated", {}).get("signal_outcomes")
        already_ran = False
        if last_outcomes:
            try:
                lo_dt = datetime.fromisoformat(last_outcomes)
                already_ran = lo_dt.date() == today
            except Exception:
                pass
        if not already_ran:
            logger.warning("⚡ [Catchup] Outcome check + report missed — firing now")
            asyncio.create_task(job_check_signal_outcomes())
            tasks_fired.append("job_check_signal_outcomes")
        else:
            logger.info("✅ [Catchup] Outcome check already ran today")

    if tasks_fired:
        logger.info(f"🚀 [Catchup] Fired {len(tasks_fired)} missed job(s): {', '.join(tasks_fired)}")
    else:
        logger.info("✅ [Catchup] All scheduled jobs are up-to-date — nothing to catch up")


# ── Scheduler Setup ───────────────────────────────────────────────────────

def setup_scheduler():
    """Register all scheduled jobs and configure triggers."""
    now = datetime.now(IST)

    # Every 5 min during market hours: OHLCV + index refresh
    scheduler.add_job(
        job_refresh_market_data,
        trigger=IntervalTrigger(minutes=settings.market_data_interval_minutes),
        id="market_data",
        name="Market Data Refresh",
        replace_existing=True,
        next_run_time=now if is_market_open() else None
    )

    scheduler.add_job(
        job_refresh_index_data,
        trigger=IntervalTrigger(minutes=5),
        id="index_data",
        name="Index & VIX Refresh",
        replace_existing=True,
        next_run_time=now
    )

    # Every 10 min: News feed
    scheduler.add_job(
        job_refresh_news,
        trigger=IntervalTrigger(minutes=settings.news_refresh_interval_minutes),
        id="news_feed",
        name="News Feed Refresh",
        replace_existing=True,
        next_run_time=now
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
        next_run_time=now
    )

    # Daily 9 AM IST: Earnings calendar
    scheduler.add_job(
        job_refresh_earnings,
        trigger=CronTrigger(hour=9, minute=0, timezone=IST),
        id="earnings",
        name="Earnings Calendar",
        replace_existing=True,
        next_run_time=now
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

    # Daily 6:30 PM IST: Signal outcome check (D5 & D10)
    scheduler.add_job(
        job_check_signal_outcomes,
        trigger=CronTrigger(day_of_week="mon-fri", hour=18, minute=30, timezone=IST),
        id="signal_outcomes",
        name="Signal Outcome Check",
        replace_existing=True,
    )

    # Daily 4:00 PM IST (Mon–Fri): Nightly pre-computation (Nifty 200 full scan)
    # Runs 45 min after market close (3:30 PM) so EOD prices are fully settled.
    scheduler.add_job(
        job_nightly_precompute,
        trigger=CronTrigger(day_of_week="mon-fri", hour=16, minute=0, timezone=IST),
        id="nightly_precompute",
        name="Nightly Pre-Compute (Nifty 200)",
        replace_existing=True,
    )

    # Daily 3:15 PM IST (Mon–Fri): Auto-screener — scans Nifty 50, saves to DB for meta-learner
    # 3:15 PM chosen deliberately: captures full-day EOD close prices used by all technical indicators.
    # Opening prices (9:30 AM) are noisy from gaps; closing price = final daily consensus.
    scheduler.add_job(
        job_daily_screener,
        trigger=CronTrigger(day_of_week="mon-fri", hour=15, minute=15, timezone=IST),
        id="daily_screener",
        name="Daily Auto-Screener (Nifty 50) @ EOD Close",
        replace_existing=True,
    )

    logger.info("✅ All scheduler jobs registered and initial syncs triggered")
    return scheduler


def get_cache() -> dict:
    """Return the current in-memory data cache."""
    return _cache
