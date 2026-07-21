"""
ATBot — Learn Endpoint
Aggregates signal_outcomes into win-rate stats and accuracy trends
for the ATBot Learn page.

GET /api/learn/stats        → overall stats + by-signal breakdown
GET /api/learn/recent       → last N outcome records (for the table)
GET /api/learn/meta-weights → current adaptive engine weights
GET /api/learn/report       → download PDF accuracy report
POST /api/learn/trigger     → manually trigger an outcome check (dev use)
POST /api/learn/trigger-meta → manually trigger meta-learner (dev use)
"""

import logging
from datetime import datetime, timedelta
from collections import defaultdict

from fastapi import APIRouter, Query, Depends
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from backend.models.database import get_db, AsyncSessionLocal
from backend.models.schemas import SignalOutcome, AnalysisScore
from backend.engines.outcome_tracker import run_outcome_check
from backend.config import IST

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Learn"])


# ── Helper ────────────────────────────────────────────────────────────────────

def _win_rate(outcomes: list[dict]) -> float:
    """
    Weighted win rate:
      WIN     = 1.0 point
      PARTIAL = 0.5 point  (right direction, not enough)
      LOSS    = 0   points
      BREAKEVEN excluded from denominator (market noise, not scored)
    """
    decisive = [o for o in outcomes if o["outcome"] in ("WIN", "PARTIAL", "LOSS")]
    if not decisive:
        return 0.0
    score = sum(
        1.0 if o["outcome"] == "WIN" else
        0.5 if o["outcome"] == "PARTIAL" else
        0.0
        for o in decisive
    )
    return round((score / len(decisive)) * 100, 1)


def _strict_win_rate(outcomes: list[dict]) -> float:
    """Strict: WIN-only / (WIN + PARTIAL + LOSS). No weighting."""
    decisive = [o for o in outcomes if o["outcome"] in ("WIN", "PARTIAL", "LOSS")]
    if not decisive:
        return 0.0
    wins = sum(1 for o in decisive if o["outcome"] == "WIN")
    return round((wins / len(decisive)) * 100, 1)


def _directional_accuracy(outcomes: list[dict]) -> float:
    """What % of signals went in the right direction (WIN + PARTIAL + BREAKEVEN)."""
    resolved = [o for o in outcomes if o["outcome"] in ("WIN", "PARTIAL", "LOSS", "BREAKEVEN")]
    if not resolved:
        return 0.0
    correct = sum(1 for o in resolved if o["outcome"] in ("WIN", "PARTIAL", "BREAKEVEN"))
    return round((correct / len(resolved)) * 100, 1)


# ── GET /api/learn/stats ─────────────────────────────────────────────────────

@router.get("/learn/stats")
async def get_learn_stats(
    days: int = Query(default=90, ge=7, le=365, description="Look-back window in days"),
    check_day: int = Query(default=10, ge=1, le=10, description="1 (BTST), 2, 5, or 10 day outcomes"),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns aggregated win-rate statistics from the signal_outcomes table.
    """
    since = datetime.now(IST) - timedelta(days=days)

    result = await db.execute(
        select(SignalOutcome).where(
            SignalOutcome.entry_date >= since,
            SignalOutcome.check_day == check_day,
        ).order_by(SignalOutcome.entry_date.desc())
    )
    rows = result.scalars().all()

    if not rows:
        return {
            "total_signals": 0,
            "total_resolved": 0,
            "total_decisive": 0,
            "overall_win_rate": 0.0,
            "strict_win_rate": 0.0,
            "directional_accuracy": 0.0,
            "win_count": 0,
            "partial_count": 0,
            "loss_count": 0,
            "breakeven_count": 0,
            "avg_pnl_pct": 0.0,
            "avg_pnl_wins": 0.0,
            "avg_loss_pct": 0.0,
            "by_signal": {},
            "monthly_trend": [],
            "by_component": {},
            "top_stocks": [],
            "worst_stocks": [],
            "has_data": False,
        }

    all_dicts = [
        {
            "symbol":           r.symbol,
            "signal":           r.signal,
            "composite_score":  r.composite_score,
            "technical_score":  r.technical_score,
            "fundamental_score": r.fundamental_score,
            "sentiment_score":  r.sentiment_score,
            "entry_date":       r.entry_date,
            "pnl_percent":      r.pnl_percent or 0.0,
            "outcome":          r.outcome,
            "outcome_detail":   r.outcome_detail,
        }
        for r in rows
    ]

    resolved   = [d for d in all_dicts if d["outcome"] in ("WIN", "PARTIAL", "LOSS", "BREAKEVEN")]
    decisive   = [d for d in resolved  if d["outcome"] in ("WIN", "PARTIAL", "LOSS")]  # excludes BREAKEVEN
    wins       = [d for d in decisive  if d["outcome"] == "WIN"]
    partials   = [d for d in decisive  if d["outcome"] == "PARTIAL"]
    losses     = [d for d in decisive  if d["outcome"] == "LOSS"]
    breakevens = [d for d in resolved  if d["outcome"] == "BREAKEVEN"]

    # ── By signal type ────────────────────────────────────────────────────────
    by_signal: dict[str, dict] = defaultdict(lambda: {
        "total": 0, "wins": 0, "partials": 0, "losses": 0, "breakevens": 0,
        "win_rate": 0.0, "avg_pnl": 0.0
    })
    for d in resolved:
        sig = d["signal"] or "UNKNOWN"
        by_signal[sig]["total"] += 1
        if d["outcome"] == "WIN":
            by_signal[sig]["wins"] += 1
        elif d["outcome"] == "PARTIAL":
            by_signal[sig]["partials"] += 1
        elif d["outcome"] == "LOSS":
            by_signal[sig]["losses"] += 1
        elif d["outcome"] == "BREAKEVEN":
            by_signal[sig]["breakevens"] += 1

    for sig, stats in by_signal.items():
        sig_outcomes = [d for d in resolved if d["signal"] == sig]
        stats["win_rate"] = _win_rate(sig_outcomes)
        sig_decisive = [d["pnl_percent"] for d in sig_outcomes if d["outcome"] in ("WIN", "PARTIAL", "LOSS")]
        stats["avg_pnl"] = round(sum(sig_decisive) / len(sig_decisive), 2) if sig_decisive else 0.0

    # ── Monthly trend ─────────────────────────────────────────────────────────
    monthly: dict[str, list] = defaultdict(list)
    for d in resolved:
        month_key = d["entry_date"].strftime("%Y-%m") if d["entry_date"] else "unknown"
        monthly[month_key].append(d)

    monthly_trend = sorted([
        {
            "month":    month,
            "total":    len(items),
            "wins":     sum(1 for i in items if i["outcome"] == "WIN"),
            "win_rate": _win_rate(items),
            "avg_pnl":  round(sum(i["pnl_percent"] for i in items) / len(items), 2) if items else 0.0,
        }
        for month, items in monthly.items()
    ], key=lambda x: x["month"])

    # ── By component score correlation ────────────────────────────────────────
    def avg_score_for(outcome_filter, field):
        subset = [d[field] for d in resolved if d["outcome"] == outcome_filter and d[field] is not None]
        return round(sum(subset) / len(subset), 1) if subset else 0.0

    by_component = {
        "technical":    {"wins_avg": avg_score_for("WIN", "technical_score"),    "losses_avg": avg_score_for("LOSS", "technical_score")},
        "fundamental":  {"wins_avg": avg_score_for("WIN", "fundamental_score"),  "losses_avg": avg_score_for("LOSS", "fundamental_score")},
        "sentiment":    {"wins_avg": avg_score_for("WIN", "sentiment_score"),    "losses_avg": avg_score_for("LOSS", "sentiment_score")},
        "composite":    {"wins_avg": avg_score_for("WIN", "composite_score"),    "losses_avg": avg_score_for("LOSS", "composite_score")},
    }

    # ── Top / worst stocks (Bug3 fix: separate sort keys, no overlap) ────
    by_stock: dict[str, list] = defaultdict(list)
    for d in resolved:
        by_stock[d["symbol"]].append(d)

    stock_stats = [
        {
            "symbol":   sym,
            "total":    len(items),
            "win_rate": _win_rate(items),
            "avg_pnl":  round(sum(i["pnl_percent"] for i in items) / len(items), 2),
        }
        for sym, items in by_stock.items() if len(items) >= 1  # lower threshold for small datasets
    ]

    # Top stocks: highest win_rate, then best avg_pnl as tiebreaker
    top_stocks = sorted(stock_stats, key=lambda x: (-x["win_rate"], -x["avg_pnl"]))[:5]
    top_symbols = {s["symbol"] for s in top_stocks}

    # Worst stocks: lowest win_rate OR most negative avg_pnl — EXCLUDE stocks already in top
    remaining = [s for s in stock_stats if s["symbol"] not in top_symbols]
    worst_stocks = sorted(remaining, key=lambda x: (x["win_rate"], x["avg_pnl"]))[:5]

    # Weighted win rate: WIN=1.0, PARTIAL=0.5, LOSS=0, BREAKEVEN=excluded
    decisive_count = len(decisive)
    weighted_wins  = len(wins) + 0.5 * len(partials)
    weighted_rate  = round((weighted_wins / decisive_count) * 100, 1) if decisive_count else 0.0

    return {
        "total_signals":       len(all_dicts),
        "total_resolved":      len(resolved),
        "total_decisive":      decisive_count,
        "overall_win_rate":    weighted_rate,         # weighted: WIN + 0.5×PARTIAL
        "strict_win_rate":     _strict_win_rate(resolved),  # WIN only
        "directional_accuracy": _directional_accuracy(resolved),  # right direction incl. BREAKEVEN
        "win_count":           len(wins),
        "partial_count":       len(partials),
        "loss_count":          len(losses),
        "breakeven_count":     len(breakevens),
        "avg_pnl_pct":         round(sum(d["pnl_percent"] for d in decisive) / decisive_count, 2) if decisive_count else 0.0,
        "avg_pnl_wins":        round(sum(d["pnl_percent"] for d in wins) / len(wins), 2) if wins else 0.0,
        "avg_loss_pct":        round(sum(d["pnl_percent"] for d in losses) / len(losses), 2) if losses else 0.0,
        "by_signal":           dict(by_signal),
        "monthly_trend":       monthly_trend,
        "by_component":        by_component,
        "top_stocks":          top_stocks,
        "worst_stocks":        worst_stocks,
        "has_data":            True,
    }


# ── GET /api/learn/recent ─────────────────────────────────────────────────────

@router.get("/learn/recent")
async def get_recent_outcomes(
    limit: int = Query(default=50, ge=5, le=200),
    check_day: int = Query(default=10, ge=1, le=10, description="Filter by check day (1, 2, 5, or 10)"),
    db: AsyncSession = Depends(get_db),
):
    """Return the most recent resolved signal outcomes."""
    result = await db.execute(
        select(SignalOutcome)
        .where(
            SignalOutcome.outcome.in_(["WIN", "PARTIAL", "LOSS", "BREAKEVEN"]),
            SignalOutcome.check_day == check_day,
        )
        .order_by(SignalOutcome.entry_date.desc())
        .limit(limit)
    )
    rows = result.scalars().all()

    return [
        {
            "symbol":        r.symbol,
            "signal":        r.signal,
            "entry_date":    r.entry_date.strftime("%d %b %Y") if r.entry_date else "—",
            "check_day":     r.check_day,
            "entry_price":   r.entry_price,
            "price_at_check": r.price_at_check,
            "pnl_percent":   r.pnl_percent,
            "outcome":       r.outcome,
            "outcome_detail": r.outcome_detail,
            "composite_score": r.composite_score,
        }
        for r in rows
    ]


# -- POST /api/learn/trigger ---------------------------------------------------

@router.post("/learn/trigger")
async def trigger_outcome_check():
    """Manually run the outcome check job (for testing without waiting for 6:30 PM)."""
    try:
        count = await run_outcome_check()
        return {"status": "ok", "new_outcomes": count}
    except Exception as e:
        logger.error(f"Manual outcome check failed: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/learn/meta-weights")
async def get_meta_weights():
    """
    Returns v2 adaptive weights: per-regime (BULL/BEAR/SIDEWAYS), global fallback,
    sample counts, EWMA config, and current active regime.
    """
    from backend.engines.meta_learner import get_current_adaptive_weights, BASE_WEIGHTS, MIN_SAMPLES_PER_REGIME, EWMA_LAMBDA
    from backend.engines.ensemble_scorer import _get_adaptive_weights_sync, determine_market_regime
    import math

    half_life_days = round(math.log(0.5) / math.log(EWMA_LAMBDA), 1)

    # Current market regime for highlighting active weights
    try:
        from backend.data.scheduler import get_cache
        cache = get_cache()
        indices = cache.get("indices") or {}
        nifty = indices.get("NIFTY50") or {}
        vix_data = cache.get("india_vix") or {}
        current_regime = determine_market_regime(
            nifty.get("change_pct", 0.0),
            vix_data.get("vix", 14.0),
            nifty.get("change_pct_20d", 0.0),
        )
    except Exception:
        current_regime = "SIDEWAYS"

    raw = _get_adaptive_weights_sync() or await get_current_adaptive_weights()
    ewma_config = {"lambda": EWMA_LAMBDA, "half_life_days": half_life_days}

    def regime_status(n):
        if n >= 30: return "mature"
        if n >= MIN_SAMPLES_PER_REGIME: return "learning"
        return "insufficient"

    if raw and raw.get("BULL"):
        sample_counts = raw.get("sample_counts", {})
        return {
            "version": "v2", "source": "adaptive", "status": "active",
            "current_regime": current_regime,
            "last_updated": raw.get("last_updated"),
            "total_samples": raw.get("sample_count", sum(sample_counts.values())),
            "ewma": ewma_config,
            "min_samples_per_regime": MIN_SAMPLES_PER_REGIME,
            "regime_weights": {
                "BULL": {**raw["BULL"], "samples": sample_counts.get("BULL", 0),
                         "status": regime_status(sample_counts.get("BULL", 0)), "is_active": current_regime == "BULL"},
                "BEAR": {**raw["BEAR"], "samples": sample_counts.get("BEAR", 0),
                         "status": regime_status(sample_counts.get("BEAR", 0)), "is_active": current_regime == "BEAR"},
                "SIDEWAYS": {**raw["SIDEWAYS"], "samples": sample_counts.get("SIDEWAYS", 0),
                             "status": regime_status(sample_counts.get("SIDEWAYS", 0)), "is_active": current_regime == "SIDEWAYS"},
            },
            "global_weights": raw.get("GLOBAL", {"T": raw.get("T"), "F": raw.get("F"), "S": raw.get("S")}),
            "base_weights": BASE_WEIGHTS,
        }

    return {
        "version": "v2", "source": "static_base", "status": "waiting_for_data",
        "current_regime": current_regime, "last_updated": None, "total_samples": 0,
        "ewma": ewma_config, "min_samples_per_regime": MIN_SAMPLES_PER_REGIME,
        "regime_weights": {
            r: {**w, "samples": 0, "status": "insufficient", "is_active": r == current_regime}
            for r, w in BASE_WEIGHTS.items()
        },
        "global_weights": {"T": 0.45, "F": 0.30, "S": 0.25},
        "base_weights": BASE_WEIGHTS,
        "message": f"Needs {MIN_SAMPLES_PER_REGIME}+ resolved outcomes per regime. Bot accumulates data automatically at 9:30 AM daily.",
    }


# ── POST /api/learn/trigger-meta ──────────────────────────────────────────────

@router.post("/learn/trigger-meta")
async def trigger_meta_learner():
    """Manually trigger the meta-learner weight recomputation (for testing)."""
    from backend.engines.meta_learner import compute_and_save_adaptive_weights
    from backend.engines.ensemble_scorer import set_adaptive_weights
    try:
        new_weights = await compute_and_save_adaptive_weights()
        set_adaptive_weights(new_weights)
        return {
            "status": "ok",
            "new_weights": {
                "technical":   new_weights.get("T"),
                "fundamental": new_weights.get("F"),
                "sentiment":   new_weights.get("S"),
            }
        }
    except Exception as e:
        logger.error(f"Meta-learner trigger failed: {e}")
        return {"status": "error", "message": str(e)}


# ── GET /api/learn/report ─────────────────────────────────────────────────────

@router.get("/learn/report")
async def download_accuracy_report(
    days: int = Query(default=90, ge=7, le=365, description="Lookback window in days"),
    check_day: int = Query(default=10, ge=5, le=10, description="5 or 10 day outcomes — must match dashboard filter"),
):
    """
    Generate and download a PDF accuracy report.
    Shows win rate, signal breakdown, stock performance, and recent trades.
    check_day must match what you're viewing on the Learn page (Day 5 or Day 10).
    """
    from backend.engines.report_generator import generate_accuracy_report
    try:
        fpath = await generate_accuracy_report(days=days, check_day=check_day)
        import os
        fname = os.path.basename(fpath)
        return FileResponse(
            path=fpath,
            media_type="application/pdf",
            filename=fname,
            headers={"Content-Disposition": f"attachment; filename={fname}"}
        )
    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        return {"status": "error", "message": str(e)}
