"""
ATBot — Signal Outcome Tracker

v4 (PATCH):
  - refresh_sideways_win_rate() — feeds the SIDEWAYS kill switch
  - _classify_outcome SELL branch fixed (Bugs A/B/C)
  - NEW: evaluates the SHADOW signal when the kill switch fired. AnalysisScore
    rows carry both `signal` (visible, may be HOLD) and `shadow_signal` (the
    would-be trade). When kill_switch_active = 1, we track the shadow instead
    so the reversion engine accumulates real performance evidence.
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

CHECK_DAYS = [1, 2, 5, 10, 50, 100]

BREAKEVEN_THRESHOLD  = 0.5
SOLID_WIN_THRESHOLD  = 1.5
TARGET_PROGRESS_WIN  = 0.80
PARTIAL_THRESHOLD    = 0.0

REGIME_WIN_OVERRIDES = {
    "BULL":     (2.0, 0.80),
    "SIDEWAYS": (1.0, 0.60),
    "BEAR":     (1.5, 0.80),
}

HORIZON_THRESHOLDS = {
    1:   (0.5,  1.5,  0.5),
    2:   (0.5,  1.5,  0.5),
    5:   (0.5,  1.5,  0.5),
    10:  (0.5,  2.0,  0.5),
    50:  (1.5,  5.0,  1.5),
    100: (2.0,  8.0,  2.0),
}

ATR_MULTIPLIERS = {
    1:   (0.5,  0.75, 1.0),
    2:   (0.6,  0.9,  1.2),
    5:   (0.75, 1.25, 1.75),
    10:  (1.5,  2.5,  3.5),
    50:  (4.0,  6.0,  9.0),
    100: (6.0,  9.0,  13.0),
}


def _pick_tracked_signal(score) -> tuple[str, int]:
    """
    Returns (signal_to_track, is_shadow_flag).
    If the kill switch fired and a shadow signal exists, we track the shadow
    so the reversion engine's performance is measurable.
    """
    visible = (score.signal or "").upper().strip()
    shadow = (getattr(score, "shadow_signal", None) or "").upper().strip()
    ks = bool(getattr(score, "kill_switch_active", 0))

    if ks and shadow and shadow not in ("HOLD", ""):
        return shadow, 1
    return visible or "HOLD", 0


def _fetch_close_price(symbol: str, target_date: date) -> Optional[float]:
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
    regime: str = "SIDEWAYS",
) -> tuple[str, str]:
    if entry_price is None or entry_price == 0:
        return "OPEN", "NO_ENTRY_PRICE"

    pnl_pct = ((price_at_check - entry_price) / entry_price) * 100
    signal_upper = signal.upper().strip()

    if signal_upper == "HOLD":
        return "OPEN", "HOLD_SIGNAL"

    is_buy_signal  = signal_upper in ("STRONG BUY", "BUY", "STRONG_BUY")
    is_sell_signal = signal_upper in ("STRONG SELL", "SELL", "STRONG_SELL")

    bev_pct, solid_win_pct, partial_min_pct = HORIZON_THRESHOLDS.get(
        check_day, (BREAKEVEN_THRESHOLD, SOLID_WIN_THRESHOLD, PARTIAL_THRESHOLD)
    )

    regime_solid_win, regime_target_progress = REGIME_WIN_OVERRIDES.get(
        regime or "SIDEWAYS", (solid_win_pct, TARGET_PROGRESS_WIN)
    )
    effective_solid_win = max(solid_win_pct, regime_solid_win) if check_day >= 50 else regime_solid_win
    effective_target_progress = regime_target_progress

    if abs(pnl_pct) < bev_pct:
        return "BREAKEVEN", "WITHIN_TOLERANCE"

    if is_buy_signal:
        if stop_loss and price_at_check <= stop_loss:
            return "LOSS", "SL_HIT"

        if pnl_pct > 0:
            if target_conservative and target_conservative > entry_price:
                target_gap   = target_conservative - entry_price
                actual_gain  = price_at_check - entry_price
                progress_pct = actual_gain / target_gap
                if progress_pct >= 1.0:
                    return "WIN", "TARGET_HIT"
                elif progress_pct >= effective_target_progress:
                    return "WIN", "NEAR_TARGET"

            if pnl_pct >= effective_solid_win:
                return "WIN", "SOLID_GAIN"
            elif pnl_pct >= partial_min_pct:
                return "PARTIAL", "PARTIAL_GAIN"
            else:
                return "LOSS", "PARTIAL_LOSS"
        else:
            return "LOSS", "PARTIAL_LOSS"

    if is_sell_signal:
        if stop_loss and stop_loss > entry_price and price_at_check >= stop_loss:
            return "LOSS", "SELL_SL_HIT"

        if pnl_pct < 0:
            abs_fall = abs(pnl_pct)
            if target_conservative and target_conservative < entry_price:
                target_gap   = entry_price - target_conservative
                actual_fall  = entry_price - price_at_check
                progress_pct = actual_fall / target_gap
                if progress_pct >= 1.0:
                    return "WIN", "TARGET_HIT"
                elif progress_pct >= effective_target_progress:
                    return "WIN", "NEAR_TARGET"
            if abs_fall >= effective_solid_win:
                return "WIN", "SOLID_FALL"
            elif abs_fall >= partial_min_pct:
                return "PARTIAL", "PARTIAL_FALL"
            else:
                return "LOSS", "PARTIAL_FALL"
        else:
            return "LOSS", "PARTIAL_RISE"

    return "OPEN", "UNKNOWN_SIGNAL"


async def refresh_sideways_win_rate(days: int = 30) -> tuple[Optional[float], int]:
    """
    Realized directional win rate for SIDEWAYS signals over the last N days.
    Uses only NON-shadow outcomes so the kill switch is driven by real
    (visible) signal history, not the counterfactual shadow stream.
    """
    cutoff = datetime.now(IST).replace(tzinfo=None) - timedelta(days=days)
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(SignalOutcome).where(
                and_(
                    SignalOutcome.entry_date >= cutoff,
                    SignalOutcome.regime == "SIDEWAYS",
                    SignalOutcome.pnl_percent.isnot(None),
                    SignalOutcome.check_day == 5,
                    # Only visible outcomes drive the kill switch.
                    # is_shadow may be NULL on legacy rows — treat as visible.
                    (SignalOutcome.is_shadow == 0) | (SignalOutcome.is_shadow.is_(None)),
                )
            )
        )
        rows = res.scalars().all()

    wins  = 0
    total = 0
    for r in rows:
        sig = (r.signal or "").upper().strip()
        pnl = r.pnl_percent
        if pnl is None:
            continue
        is_buy  = sig in ("BUY", "STRONG BUY", "STRONG_BUY")
        is_sell = sig in ("SELL", "STRONG SELL", "STRONG_SELL")
        if not (is_buy or is_sell):
            continue
        if abs(pnl) < 0.5:
            continue
        total += 1
        if is_buy  and pnl > 0: wins += 1
        if is_sell and pnl < 0: wins += 1

    if total == 0:
        return None, 0
    return wins / total, total


async def run_outcome_check():
    logger.info("📊 [OutcomeTracker] Starting daily outcome check...")
    today = datetime.now(IST).date()
    checked = 0

    async with AsyncSessionLocal() as db:
        for check_day in CHECK_DAYS:
            target_entry_date = today
            td_count = 0
            while td_count < check_day:
                target_entry_date -= timedelta(days=1)
                if target_entry_date.weekday() < 5:
                    td_count += 1

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

            # Deduplicate by symbol — keep most recent scan per symbol per day
            deduped: dict[str, object] = {}
            for s in scores:
                sym = s.symbol
                if sym not in deduped or s.timestamp > deduped[sym].timestamp:
                    deduped[sym] = s
            scores = list(deduped.values())
            logger.info(f"  D{check_day}: After dedup: {len(scores)} unique symbol(s)")

            for score in scores:
                tracked_signal, is_shadow = _pick_tracked_signal(score)

                # Skip if tracked signal is HOLD — nothing to score
                if tracked_signal == "HOLD":
                    continue

                # Look for existing row for this score/day/shadow-status
                existing_result = await db.execute(
                    select(SignalOutcome).where(
                        and_(
                            SignalOutcome.analysis_score_id == score.id,
                            SignalOutcome.check_day == check_day,
                            (SignalOutcome.is_shadow == is_shadow) |
                            (SignalOutcome.is_shadow.is_(None) if is_shadow == 0 else False),
                        )
                    )
                )
                existing_row = existing_result.scalar_one_or_none()
                if existing_row and existing_row.outcome != "OPEN":
                    continue

                price = _fetch_close_price(score.symbol, today)
                if price is None:
                    if not existing_row:
                        db.add(SignalOutcome(
                            analysis_score_id = score.id,
                            symbol            = score.symbol,
                            signal            = tracked_signal,
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
                            is_shadow         = is_shadow,
                        ))
                    logger.warning(f"  Skipping {score.symbol} — could not fetch price")
                    continue

                entry_price = score.current_price or 0.0
                pnl_amount  = round(price - entry_price, 2) if entry_price else None
                pnl_percent = round(((price - entry_price) / entry_price) * 100, 2) if entry_price else None

                if check_day <= 5:
                    t_conservative = score.target_low_5d  or score.target_base_5d or 0.0
                    t_base         = score.target_base_5d or score.target_low_5d  or 0.0
                    t_aggressive   = score.target_high_5d or score.target_base_5d or 0.0
                elif check_day <= 10:
                    t_conservative = score.target_low_10d  or score.target_low_5d  or 0.0
                    t_base         = score.target_base_10d or score.target_base_5d or 0.0
                    t_aggressive   = score.target_high_10d or score.target_high_5d or 0.0
                else:
                    atr = score.atr_14 or 0.0
                    mults = ATR_MULTIPLIERS.get(check_day, ATR_MULTIPLIERS[100])
                    if atr and entry_price:
                        sig_upper = tracked_signal
                        is_sell_hist = sig_upper in ("SELL", "STRONG SELL", "STRONG_SELL")
                        direction = -1.0 if is_sell_hist else 1.0
                        t_conservative = round(entry_price + direction * atr * mults[0], 2)
                        t_base         = round(entry_price + direction * atr * mults[1], 2)
                        t_aggressive   = round(entry_price + direction * atr * mults[2], 2)
                    else:
                        t_conservative = t_base = t_aggressive = 0.0

                outcome, detail = _classify_outcome(
                    signal              = tracked_signal,
                    entry_price         = entry_price,
                    stop_loss           = score.stop_loss or 0.0,
                    target_conservative = t_conservative,
                    price_at_check      = price,
                    check_day           = check_day,
                    regime              = getattr(score, "regime", None) or "SIDEWAYS",
                )

                if existing_row:
                    existing_row.price_at_check      = price
                    existing_row.pnl_amount          = pnl_amount
                    existing_row.pnl_percent         = pnl_percent
                    existing_row.outcome             = outcome
                    existing_row.outcome_detail      = detail
                    existing_row.target_conservative = t_conservative
                    existing_row.target_base         = t_base
                    existing_row.target_aggressive   = t_aggressive
                    existing_row.check_date          = datetime.now(IST)
                    logger.info(f"  Resolved stuck OPEN: {score.symbol} D{check_day} shadow={is_shadow} → {outcome}")
                else:
                    db.add(SignalOutcome(
                        analysis_score_id   = score.id,
                        symbol              = score.symbol,
                        signal              = tracked_signal,
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
                        regime              = getattr(score, "regime", None) or "SIDEWAYS",
                        is_shadow           = is_shadow,
                    ))
                checked += 1

        await db.commit()

    # Refresh kill switch after commit — visible outcomes only
    try:
        win_rate, n = await refresh_sideways_win_rate(days=30)
        from backend.engines.ensemble_scorer import set_sideways_win_rate
        set_sideways_win_rate(win_rate, n)
    except Exception as e:
        logger.error(f"[OutcomeTracker] Kill switch refresh failed: {e}")

    logger.info(f"✅ [OutcomeTracker] Done — {checked} new outcome(s) recorded")
    return checked