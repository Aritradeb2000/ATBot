"""
ATBot — Signal Outcome Tracker
Checks price at Day 5 and Day 10 after a signal was issued,
then records WIN / LOSS / BREAKEVEN / OPEN in the signal_outcomes table.

Logic:
  BUY / STRONG BUY:
    WIN        → price >= target_conservative (hit at least the low target)
    LOSS       → price <= stop_loss
    BREAKEVEN  → |pnl%| < 0.5%
    OPEN       → neither target nor SL hit yet

  SELL / STRONG SELL:
    WIN        → price <= stop_loss (bearish: price fell as expected)
    LOSS       → price >= target_conservative (rose against the signal)
    BREAKEVEN  → |pnl%| < 0.5%

  HOLD: always recorded as OPEN (no directional bias to evaluate)
"""

import asyncio
import logging
from datetime import datetime, timedelta, date
from typing import Optional

import yfinance as yf
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from backend.models.database import AsyncSessionLocal
from backend.models.schemas import AnalysisScore, SignalOutcome
from backend.config import IST

logger = logging.getLogger(__name__)

# Trading days to check
CHECK_DAYS = [5, 10]

# Tolerance for BREAKEVEN (within ±0.5%)
BREAKEVEN_THRESHOLD = 0.5


def _get_trading_day_offset(from_date: datetime, n_trading_days: int) -> date:
    """Return the date n trading days after from_date (skips weekends)."""
    d = from_date.date()
    count = 0
    while count < n_trading_days:
        d += timedelta(days=1)
        if d.weekday() < 5:  # Mon–Fri only
            count += 1
    return d


def _fetch_close_price(symbol: str, target_date: date) -> Optional[float]:
    """
    Fetch the closing price on or just after target_date.
    Uses a 5-day window to handle holidays.
    """
    try:
        ticker = yf.Ticker(symbol)
        start = target_date
        end   = target_date + timedelta(days=5)
        hist  = ticker.history(start=start.isoformat(), end=end.isoformat(), interval="1d")
        if hist.empty:
            return None
        return round(float(hist["Close"].iloc[0]), 2)
    except Exception as e:
        logger.warning(f"Price fetch failed for {symbol} on {target_date}: {e}")
        return None


def _classify_outcome(
    signal: str,
    entry_price: float,
    stop_loss: float,
    target_conservative: float,
    price_at_check: float,
) -> tuple[str, str]:
    """
    Returns (outcome, outcome_detail).
    outcome: WIN / LOSS / BREAKEVEN / OPEN
    """
    if entry_price is None or entry_price == 0:
        return "OPEN", "NO_ENTRY_PRICE"

    pnl_pct = ((price_at_check - entry_price) / entry_price) * 100
    signal_upper = signal.upper().replace(" ", "_")

    if signal_upper in ("HOLD", "HOLD"):
        return "OPEN", "HOLD_SIGNAL"

    is_buy_signal  = signal_upper in ("STRONG_BUY", "BUY", "STRONG BUY")
    is_sell_signal = signal_upper in ("STRONG_SELL", "SELL", "STRONG SELL")

    if abs(pnl_pct) < BREAKEVEN_THRESHOLD:
        return "BREAKEVEN", "WITHIN_TOLERANCE"

    if is_buy_signal:
        if target_conservative and price_at_check >= target_conservative:
            return "WIN", "TARGET_HIT"
        elif stop_loss and price_at_check <= stop_loss:
            return "LOSS", "SL_HIT"
        elif pnl_pct > 0:
            return "WIN", "PARTIAL_GAIN"
        else:
            return "LOSS", "PARTIAL_LOSS"

    if is_sell_signal:
        if stop_loss and price_at_check <= stop_loss:
            return "WIN", "PRICE_FELL"
        elif target_conservative and price_at_check >= target_conservative:
            return "LOSS", "PRICE_ROSE"
        elif pnl_pct < 0:
            return "WIN", "PARTIAL_FALL"
        else:
            return "LOSS", "PARTIAL_RISE"

    return "OPEN", "UNKNOWN_SIGNAL"


async def run_outcome_check():
    """
    Main entry point — called by the scheduler daily at 6:30 PM IST.
    Finds all AnalysisScore records from D-5 and D-10 trading days ago,
    checks the price, and upserts into signal_outcomes.
    """
    logger.info("📊 [OutcomeTracker] Starting daily outcome check...")
    today = datetime.now(IST).date()
    checked = 0

    async with AsyncSessionLocal() as db:
        for check_day in CHECK_DAYS:
            # Find the calendar date that is check_day trading days before today
            target_entry_date = today
            td_count = 0
            while td_count < check_day:
                target_entry_date -= timedelta(days=1)
                if target_entry_date.weekday() < 5:
                    td_count += 1

            # Find analysis records from that date (within a 1-day window)
            window_start = datetime.combine(target_entry_date, datetime.min.time())
            window_end   = window_start + timedelta(days=1)

            result = await db.execute(
                select(AnalysisScore).where(
                    and_(
                        AnalysisScore.timestamp >= window_start,
                        AnalysisScore.timestamp <  window_end,
                    )
                )
            )
            scores = result.scalars().all()

            if not scores:
                logger.info(f"  D{check_day}: No signals found for {target_entry_date}")
                continue

            logger.info(f"  D{check_day}: Found {len(scores)} signal(s) for {target_entry_date}")

            # Bug5 fix: deduplicate by symbol — keep only the most recent scan per symbol per day
            # This prevents multiple screener runs from creating duplicate outcome rows
            deduped: dict[str, object] = {}
            for s in scores:
                sym = s.symbol
                if sym not in deduped or s.timestamp > deduped[sym].timestamp:
                    deduped[sym] = s
            scores = list(deduped.values())
            logger.info(f"  D{check_day}: After dedup: {len(scores)} unique symbol(s)")

            for score in scores:
                # Skip if already checked for this check_day
                existing = await db.execute(
                    select(SignalOutcome).where(
                        and_(
                            SignalOutcome.analysis_score_id == score.id,
                            SignalOutcome.check_day == check_day,
                        )
                    )
                )
                if existing.scalar_one_or_none():
                    continue  # Already recorded

                # Fetch price at today's date
                price = _fetch_close_price(score.symbol, today)
                if price is None:
                    logger.warning(f"  Skipping {score.symbol} — could not fetch price")
                    continue

                entry_price = score.current_price or 0.0
                pnl_amount  = round(price - entry_price, 2) if entry_price else None
                pnl_percent = round(((price - entry_price) / entry_price) * 100, 2) if entry_price else None

                outcome, detail = _classify_outcome(
                    signal             = score.signal or "HOLD",
                    entry_price        = entry_price,
                    stop_loss          = score.stop_loss or 0.0,
                    target_conservative= score.target_low_5d or score.target_base_5d or 0.0,
                    price_at_check     = price,
                )

                outcome_row = SignalOutcome(
                    analysis_score_id   = score.id,
                    symbol              = score.symbol,
                    signal              = score.signal,
                    composite_score     = score.composite_score,
                    technical_score     = score.technical_score,
                    fundamental_score   = score.fundamental_score,
                    sentiment_score     = score.sentiment_score,
                    confidence          = score.confidence,
                    entry_date          = score.timestamp,
                    entry_price         = entry_price,
                    stop_loss           = score.stop_loss,
                    target_conservative = score.target_low_5d,
                    target_base         = score.target_base_5d,
                    target_aggressive   = score.target_high_5d,
                    check_day           = check_day,
                    check_date          = datetime.now(IST),
                    price_at_check      = price,
                    pnl_amount          = pnl_amount,
                    pnl_percent         = pnl_percent,
                    outcome             = outcome,
                    outcome_detail      = detail,
                    regime              = getattr(score, "regime", None) or "SIDEWAYS",  # v2
                )
                db.add(outcome_row)
                checked += 1

        await db.commit()

    logger.info(f"✅ [OutcomeTracker] Done — {checked} new outcome(s) recorded")
    return checked
