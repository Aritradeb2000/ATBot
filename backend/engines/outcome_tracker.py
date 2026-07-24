"""
ATBot — Signal Outcome Tracker
Checks price at Day 5 and Day 10 after a signal was issued,
then records WIN / PARTIAL / LOSS / BREAKEVEN / OPEN.

Outcome definitions:
  WIN        → price hit ≥ 80% of conservative target gap, OR solid gain ≥ 1.5%
  PARTIAL    → moved in the right direction but small (0.5–1.5%), didn't reach target
  BREAKEVEN  → |pnl%| < 0.5% — stock barely moved, not scored
  LOSS       → price went wrong direction, or stop loss was hit
  OPEN       → HOLD signal or insufficient data

Win rate calculation in learn.py:
  WIN × 1.0 + PARTIAL × 0.5
  ─────────────────────────────
  WIN + PARTIAL + LOSS (BREAKEVEN excluded from denominator)
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

# Trading days to check: D1=BTST, D2=2-day, D5=Swing, D10=Positional, D50=LT, D100=VLT
CHECK_DAYS = [1, 2, 5, 10, 50, 100]

# ── Short-term outcome thresholds (D1–D10) ───────────────────────────────────
BREAKEVEN_THRESHOLD  = 0.5   # |P&L| < 0.5% → BREAKEVEN
SOLID_WIN_THRESHOLD  = 1.5   # P&L ≥ 1.5% → WIN even without hitting target
TARGET_PROGRESS_WIN  = 0.80  # Reached ≥ 80% of target gap → WIN (NEAR_TARGET)
PARTIAL_THRESHOLD    = 0.0   # P&L > 0 (above BREAKEVEN) → PARTIAL

# ── Long-term override thresholds per check_day ──────────────────────────────
# Gains of 1.5% over 50 days are irrelevant (could just be inflation)
# A real long-term win needs more % move.
HORIZON_THRESHOLDS = {
    # check_day: (breakeven_pct, solid_win_pct, partial_min_pct)
    1:   (0.5,  1.5,  0.5),   # BTST — current defaults
    2:   (0.5,  1.5,  0.5),
    5:   (0.5,  1.5,  0.5),
    10:  (0.5,  2.0,  0.5),
    50:  (1.5,  5.0,  1.5),   # Long-term: ≥5% = WIN, 1.5-5% = PARTIAL
    100: (2.0,  8.0,  2.0),   # Very-long-term: ≥8% = WIN, 2-8% = PARTIAL
}

# ── Long-term ATR multipliers (used when no stored target exists) ─────────────
# ATR = daily average range; over N days a stock can move ~√N × ATR
ATR_MULTIPLIERS = {
    # check_day: (conservative_mult, base_mult, aggressive_mult)
    1:   (0.5,  0.75, 1.0),
    2:   (0.6,  0.9,  1.2),
    5:   (0.75, 1.25, 1.75),
    10:  (1.5,  2.5,  3.5),
    50:  (4.0,  6.0,  9.0),   # 2.5-month horizon
    100: (6.0,  9.0,  13.0),  # 5-month horizon
}


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
    check_day: int = 5,          # ← NEW: drives horizon-aware thresholds
) -> tuple[str, str]:
    """
    Returns (outcome, outcome_detail).
    outcome: WIN / PARTIAL / LOSS / BREAKEVEN / OPEN

    WIN       — hit ≥ 80% of target gap, or solid gain ≥ solid_win_pct
    PARTIAL   — right direction but below WIN threshold
    BREAKEVEN — within ±breakeven_pct (market noise, not scored)
    LOSS      — wrong direction, or stop loss hit

    Thresholds scale with horizon: D5=1.5% solid win, D50=5%, D100=8%.
    """
    if entry_price is None or entry_price == 0:
        return "OPEN", "NO_ENTRY_PRICE"

    pnl_pct = ((price_at_check - entry_price) / entry_price) * 100
    signal_upper = signal.upper().strip()

    if signal_upper == "HOLD":
        return "OPEN", "HOLD_SIGNAL"

    is_buy_signal  = signal_upper in ("STRONG BUY", "BUY", "STRONG_BUY")
    is_sell_signal = signal_upper in ("STRONG SELL", "SELL", "STRONG_SELL")

    # Horizon-specific thresholds
    bev_pct, solid_win_pct, partial_min_pct = HORIZON_THRESHOLDS.get(
        check_day, (BREAKEVEN_THRESHOLD, SOLID_WIN_THRESHOLD, PARTIAL_THRESHOLD)
    )

    # ── BREAKEVEN: market barely moved — not scored in either direction ──────
    if abs(pnl_pct) < bev_pct:
        return "BREAKEVEN", "WITHIN_TOLERANCE"

    if is_buy_signal:
        # SL hit first — full LOSS regardless of target
        if stop_loss and price_at_check <= stop_loss:
            return "LOSS", "SL_HIT"

        if pnl_pct > 0:
            # Check target progress
            if target_conservative and target_conservative > entry_price:
                target_gap   = target_conservative - entry_price
                actual_gain  = price_at_check - entry_price
                progress_pct = actual_gain / target_gap  # 0–1+ ratio

                if progress_pct >= 1.0:
                    return "WIN", "TARGET_HIT"     # hit or exceeded target
                elif progress_pct >= TARGET_PROGRESS_WIN:
                    return "WIN", "NEAR_TARGET"    # ≥ 80% of the way — counts as WIN

            # No target data or below 80% progress:
            if pnl_pct >= solid_win_pct:
                return "WIN", "SOLID_GAIN"         # strong move even without target
            elif pnl_pct >= partial_min_pct:
                return "PARTIAL", "PARTIAL_GAIN"  # right direction but weak
            else:
                return "LOSS", "PARTIAL_LOSS"      # above BREAKEVEN but below partial
        else:
            return "LOSS", "PARTIAL_LOSS"

    if is_sell_signal:
        # For SELL: winning means price fell
        if stop_loss and price_at_check <= stop_loss:
            return "WIN", "PRICE_FELL"             # fell past SL = full win for short
        elif target_conservative and price_at_check >= target_conservative:
            return "LOSS", "PRICE_ROSE"            # rose to our entry target = loss

        if pnl_pct < 0:  # price dropped = win for sell signal
            abs_fall = abs(pnl_pct)
            if target_conservative and target_conservative < entry_price:
                target_gap   = entry_price - target_conservative
                actual_fall  = entry_price - price_at_check
                progress_pct = actual_fall / target_gap
                if progress_pct >= TARGET_PROGRESS_WIN:
                    return "WIN", "NEAR_TARGET"
            if abs_fall >= solid_win_pct:
                return "WIN", "SOLID_FALL"
            elif abs_fall >= partial_min_pct:
                return "PARTIAL", "PARTIAL_FALL"
            else:
                return "LOSS", "PARTIAL_RISE"
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

                # Select the correct target based on the check horizon
                if check_day <= 5:
                    t_conservative = score.target_low_5d  or score.target_base_5d or 0.0
                    t_base         = score.target_base_5d or score.target_low_5d  or 0.0
                    t_aggressive   = score.target_high_5d or score.target_base_5d or 0.0
                elif check_day <= 10:
                    t_conservative = score.target_low_10d  or score.target_low_5d  or 0.0
                    t_base         = score.target_base_10d or score.target_base_5d or 0.0
                    t_aggressive   = score.target_high_10d or score.target_high_5d or 0.0
                else:
                    # D50/D100: compute from ATR stored at signal time
                    # No separate DB columns — compute now using stored atr_14
                    atr = score.atr_14 or 0.0
                    mults = ATR_MULTIPLIERS.get(check_day, ATR_MULTIPLIERS[100])
                    if atr and entry_price:
                        t_conservative = round(entry_price + atr * mults[0], 2)
                        t_base         = round(entry_price + atr * mults[1], 2)
                        t_aggressive   = round(entry_price + atr * mults[2], 2)
                    else:
                        t_conservative = t_base = t_aggressive = 0.0

                outcome, detail = _classify_outcome(
                    signal             = score.signal or "HOLD",
                    entry_price        = entry_price,
                    stop_loss          = score.stop_loss or 0.0,
                    target_conservative= t_conservative,
                    price_at_check     = price,
                    check_day          = check_day,   # ← horizon-aware thresholds
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
                    target_conservative = t_conservative,
                    target_base         = t_base,
                    target_aggressive   = t_aggressive,
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
