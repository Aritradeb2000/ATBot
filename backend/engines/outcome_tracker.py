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

# ── Regime-specific WIN criteria overrides ───────────────────────────────────
# In SIDEWAYS markets the index has no strong trend, so ATR-based targets are harder
# to reach within 5 days. Lowering the bar from 1.5% to 1.0% and target progress from
# 80% to 60% means a correct-direction move still counts as a WIN even if it doesn't
# reach the full ATR target — more accurately reflecting directional skill.
# In BULL markets raise the bar slightly: trending stocks routinely move 2%+ in a week
# so a higher threshold keeps WIN meaningful.
REGIME_WIN_OVERRIDES = {
    # regime: (solid_win_pct, target_progress_win)
    "BULL":     (2.0, 0.80),   # higher bar — bull runs support larger moves
    "SIDEWAYS": (1.0, 0.60),   # lower bar  — no trend, targets are harder to reach
    "BEAR":     (1.5, 0.80),   # unchanged  — bear bounces can be sharp
}

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
    check_day: int = 5,
    regime: str = "SIDEWAYS",   # regime-aware WIN thresholds
) -> tuple[str, str]:
    """
    Returns (outcome, outcome_detail).
    outcome: WIN / PARTIAL / LOSS / BREAKEVEN / OPEN

    WIN       -- hit >= solid_win_pct gain, or >= target_progress_win of target gap
    PARTIAL   -- right direction but below WIN threshold
    BREAKEVEN -- within +-breakeven_pct (market noise, not scored)
    LOSS      -- wrong direction, or stop loss hit

    Thresholds scale with horizon (D5/D10/D50/D100) AND with regime:
      SIDEWAYS: solid_win=1.0%, target_progress=60% (ATR targets harder to hit flat)
      BULL:     solid_win=2.0%, target_progress=80% (trending stocks move more)
      BEAR:     solid_win=1.5%, target_progress=80% (unchanged)
    """
    if entry_price is None or entry_price == 0:
        return "OPEN", "NO_ENTRY_PRICE"

    pnl_pct = ((price_at_check - entry_price) / entry_price) * 100
    signal_upper = signal.upper().strip()

    if signal_upper == "HOLD":
        return "OPEN", "HOLD_SIGNAL"

    is_buy_signal  = signal_upper in ("STRONG BUY", "BUY", "STRONG_BUY")
    is_sell_signal = signal_upper in ("STRONG SELL", "SELL", "STRONG_SELL")

    # Horizon-specific thresholds (long-term horizons need larger moves)
    bev_pct, solid_win_pct, partial_min_pct = HORIZON_THRESHOLDS.get(
        check_day, (BREAKEVEN_THRESHOLD, SOLID_WIN_THRESHOLD, PARTIAL_THRESHOLD)
    )

    # Regime override: apply SIDEWAYS / BULL / BEAR solid_win and target_progress
    regime_solid_win, regime_target_progress = REGIME_WIN_OVERRIDES.get(
        regime or "SIDEWAYS", (solid_win_pct, TARGET_PROGRESS_WIN)
    )
    # For long-term horizons (D50/D100) keep the horizon threshold as the floor
    # so SIDEWAYS doesn't lower the bar below the horizon minimum
    effective_solid_win = max(solid_win_pct, regime_solid_win) if check_day >= 50 else regime_solid_win
    effective_target_progress = regime_target_progress

    # -- BREAKEVEN: market barely moved -- not scored in either direction --------
    if abs(pnl_pct) < bev_pct:
        return "BREAKEVEN", "WITHIN_TOLERANCE"

    if is_buy_signal:
        # SL hit first -- full LOSS regardless of target
        if stop_loss and price_at_check <= stop_loss:
            return "LOSS", "SL_HIT"

        if pnl_pct > 0:
            # Check target progress using regime-adjusted progress threshold
            if target_conservative and target_conservative > entry_price:
                target_gap   = target_conservative - entry_price
                actual_gain  = price_at_check - entry_price
                progress_pct = actual_gain / target_gap

                if progress_pct >= 1.0:
                    return "WIN", "TARGET_HIT"
                elif progress_pct >= effective_target_progress:
                    return "WIN", "NEAR_TARGET"

            # Regime-adjusted solid win threshold
            if pnl_pct >= effective_solid_win:
                return "WIN", "SOLID_GAIN"
            elif pnl_pct >= partial_min_pct:
                return "PARTIAL", "PARTIAL_GAIN"
            else:
                return "LOSS", "PARTIAL_LOSS"
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
                # Skip ONLY if already RESOLVED (WIN/LOSS/PARTIAL/BREAKEVEN).
                # OPEN records = price-fetch failures that should be retried each run.
                existing_result = await db.execute(
                    select(SignalOutcome).where(
                        and_(
                            SignalOutcome.analysis_score_id == score.id,
                            SignalOutcome.check_day == check_day,
                        )
                    )
                )
                existing_row = existing_result.scalar_one_or_none()
                if existing_row and existing_row.outcome != "OPEN":
                    continue  # Already resolved — don't overwrite

                # Fetch price at today's date (or the check date for overdue retries)
                price = _fetch_close_price(score.symbol, today)
                if price is None:
                    if not existing_row:
                        # No record yet and no price — create placeholder OPEN row
                        # so we know this signal was attempted (and retry next run)
                        db.add(SignalOutcome(
                            analysis_score_id = score.id,
                            symbol            = score.symbol,
                            signal            = score.signal,
                            composite_score   = score.composite_score,
                            technical_score   = score.technical_score,
                            fundamental_score = score.fundamental_score,
                            sentiment_score   = score.sentiment_score,
                            confidence        = score.confidence,
                            entry_date        = score.timestamp,
                            entry_price       = score.current_price or 0.0,
                            stop_loss         = score.stop_loss,
                            check_day         = check_day,
                            check_date        = datetime.now(IST),
                            outcome           = "OPEN",
                            outcome_detail    = "PRICE_UNAVAILABLE",
                            regime            = getattr(score, "regime", None) or "SIDEWAYS",
                        ))
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
                    signal              = score.signal or "HOLD",
                    entry_price         = entry_price,
                    stop_loss           = score.stop_loss or 0.0,
                    target_conservative = t_conservative,
                    price_at_check      = price,
                    check_day           = check_day,
                    regime              = getattr(score, "regime", None) or "SIDEWAYS",
                )

                if existing_row:
                    # UPDATE the stuck OPEN row in-place
                    existing_row.price_at_check      = price
                    existing_row.pnl_amount          = pnl_amount
                    existing_row.pnl_percent         = pnl_percent
                    existing_row.outcome             = outcome
                    existing_row.outcome_detail      = detail
                    existing_row.target_conservative = t_conservative
                    existing_row.target_base         = t_base
                    existing_row.target_aggressive   = t_aggressive
                    existing_row.check_date          = datetime.now(IST)
                    logger.info(f"  Resolved stuck OPEN: {score.symbol} D{check_day} → {outcome}")
                else:
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
