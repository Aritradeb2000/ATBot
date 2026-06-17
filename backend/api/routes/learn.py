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
    """Win rate % from a list of outcome dicts."""
    resolved = [o for o in outcomes if o["outcome"] in ("WIN", "LOSS", "BREAKEVEN")]
    if not resolved:
        return 0.0
    wins = sum(1 for o in resolved if o["outcome"] == "WIN")
    return round((wins / len(resolved)) * 100, 1)


# ── GET /api/learn/stats ─────────────────────────────────────────────────────

@router.get("/learn/stats")
async def get_learn_stats(
    days: int = Query(default=90, ge=7, le=365, description="Look-back window in days"),
    check_day: int = Query(default=5, ge=5, le=10, description="5 or 10 day outcomes"),
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
            "overall_win_rate": 0.0,
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

    resolved = [d for d in all_dicts if d["outcome"] in ("WIN", "LOSS", "BREAKEVEN")]
    wins     = [d for d in resolved if d["outcome"] == "WIN"]
    losses   = [d for d in resolved if d["outcome"] == "LOSS"]

    # ── By signal type ────────────────────────────────────────────────────────
    by_signal: dict[str, dict] = defaultdict(lambda: {"total": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "avg_pnl": 0.0})
    for d in resolved:
        sig = d["signal"] or "UNKNOWN"
        by_signal[sig]["total"] += 1
        if d["outcome"] == "WIN":
            by_signal[sig]["wins"] += 1
        elif d["outcome"] == "LOSS":
            by_signal[sig]["losses"] += 1

    for sig, stats in by_signal.items():
        if stats["total"] > 0:
            stats["win_rate"] = round((stats["wins"] / stats["total"]) * 100, 1)
        sig_resolved = [d["pnl_percent"] for d in resolved if d["signal"] == sig]
        stats["avg_pnl"] = round(sum(sig_resolved) / len(sig_resolved), 2) if sig_resolved else 0.0

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

    # ── Top / worst stocks ────────────────────────────────────────────────────
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
        for sym, items in by_stock.items() if len(items) >= 2
    ]
    stock_stats.sort(key=lambda x: -x["win_rate"])

    return {
        "total_signals":   len(all_dicts),
        "total_resolved":  len(resolved),
        "overall_win_rate": round((len(wins) / len(resolved)) * 100, 1) if resolved else 0.0,
        "avg_pnl_pct":     round(sum(d["pnl_percent"] for d in resolved) / len(resolved), 2) if resolved else 0.0,
        "avg_pnl_wins":    round(sum(d["pnl_percent"] for d in wins) / len(wins), 2) if wins else 0.0,
        "avg_loss_pct":    round(sum(d["pnl_percent"] for d in losses) / len(losses), 2) if losses else 0.0,
        "by_signal":       dict(by_signal),
        "monthly_trend":   monthly_trend,
        "by_component":    by_component,
        "top_stocks":      stock_stats[:5],
        "worst_stocks":    list(reversed(stock_stats))[:5],
        "has_data":        True,
    }


# ── GET /api/learn/recent ─────────────────────────────────────────────────────

@router.get("/learn/recent")
async def get_recent_outcomes(
    limit: int = Query(default=50, ge=5, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Return the most recent resolved signal outcomes."""
    result = await db.execute(
        select(SignalOutcome)
        .where(SignalOutcome.outcome.in_(["WIN", "LOSS", "BREAKEVEN"]))
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


# ── POST /api/learn/trigger ───────────────────────────────────────────────────

@router.post("/learn/trigger")
async def trigger_outcome_check():
    """Manually run the outcome check job (for testing without waiting for 6:30 PM)."""
    try:
        count = await run_outcome_check()
        return {"status": "ok", "new_outcomes": count}
    except Exception as e:
        logger.error(f"Manual outcome check failed: {e}")
        return {"status": "error", "message": str(e)}


# ── GET /api/learn/meta-weights ───────────────────────────────────────────────

@router.get("/learn/meta-weights")
async def get_meta_weights():
    """
    Returns the current adaptive engine weights computed by the meta-learner.
    If meta-learning hasn't run yet, returns the static regime-based defaults.
    """
    from backend.engines.meta_learner import get_current_adaptive_weights
    from backend.engines.ensemble_scorer import _get_adaptive_weights_sync

    # Try in-memory first (fastest)
    in_memory = _get_adaptive_weights_sync()
    if in_memory:
        return {
            "source": "adaptive",
            "weights": {
                "technical":   in_memory["T"],
                "fundamental": in_memory["F"],
                "sentiment":   in_memory["S"],
            },
            "last_updated": in_memory.get("last_updated"),
            "sample_count":  in_memory.get("sample_count"),
            "status": "active",
        }

    # Fall back to DB
    db_weights = await get_current_adaptive_weights()
    if db_weights:
        return {
            "source": "adaptive",
            "weights": {
                "technical":   db_weights["T"],
                "fundamental": db_weights["F"],
                "sentiment":   db_weights["S"],
            },
            "last_updated": db_weights.get("last_updated"),
            "sample_count":  db_weights.get("sample_count"),
            "status": "active",
        }

    # No adaptive weights yet — return defaults
    return {
        "source": "regime_default",
        "weights": {
            "technical":   0.45,
            "fundamental": 0.30,
            "sentiment":   0.25,
        },
        "last_updated": None,
        "sample_count": 0,
        "status": "waiting_for_data",
        "message": f"Meta-learner needs at least 10 resolved outcomes. Keep using ATBot and it will adapt automatically!"
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
):
    """
    Generate and download a PDF accuracy report.
    Shows win rate, signal breakdown, stock performance, and recent trades.
    """
    from backend.engines.report_generator import generate_accuracy_report
    try:
        fpath = await generate_accuracy_report(days=days)
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
