"""
ATBot — Meta-Learner v2 (Regime-Conditioned + EWMA + Confidence-Weighted)

Algorithm:
  1. Pull D5 + D10 WIN/LOSS outcomes from last 60 days.
  2. Each outcome carries:
       - decay weight  = λ^(days_ago)          [λ=0.92, 8-day half-life]
       - confidence    = confidence at time of signal (0–100)
       - regime label  = BULL / BEAR / SIDEWAYS at signal time
  3. Split outcomes into 3 regime buckets.
  4. For each bucket, compute weighted predictive power per engine:
       power_T = Σ( decay_i × conf_i × correct_T_i ) / Σ( decay_i × conf_i )
  5. Normalize → learned weights summing to 1.0.
  6. Blend with hard-coded base weights:
       blended = α × learned + (1-α) × base        [α = 0.5 when n<30, 0.8 when n≥30]
  7. Also compute and save v1-compatible global weights (harmonic mean of regimes).
  8. Persist all 9 weights (3 per regime) + 3 sample counts to DB.
"""

import math
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import AsyncSessionLocal
from backend.models.schemas import SignalOutcome, UserSettings
from backend.config import IST

logger = logging.getLogger(__name__)

# ── Hyper-parameters ──────────────────────────────────────────────────────────

MIN_SAMPLES_PER_REGIME = 3    # need at least this many per regime to trust it
MIN_SAMPLES_GLOBAL     = 10   # global threshold (v1 compat)
LOOKBACK_DAYS          = 60   # extend to 60 days to get more data across regimes

EWMA_LAMBDA            = 0.92  # decay per calendar day (half-life ~8 days)
D10_WEIGHT             = 0.85  # D10 outcomes count slightly less (slower feedback)
D5_WEIGHT              = 1.00

# Blending ratio: how much to trust learned vs base weights
# Increases from 0.50 at 3 samples to 0.80 at 30+ samples
def _alpha(n: int) -> float:
    """Blend ratio — increases with sample size, caps at 0.85."""
    return min(0.85, 0.50 + 0.012 * max(0, n - 3))

# Hard-coded base weights per regime (fallback / prior)
BASE_WEIGHTS = {
    "BULL":     {"T": 0.55, "F": 0.25, "S": 0.20},
    "BEAR":     {"T": 0.35, "F": 0.40, "S": 0.25},
    "SIDEWAYS": {"T": 0.45, "F": 0.30, "S": 0.25},
}
GLOBAL_BASE = {"T": 0.45, "F": 0.30, "S": 0.25}


# ── Core helpers ──────────────────────────────────────────────────────────────

def _ewma_decay(entry_date: datetime, now: datetime) -> float:
    """Exponential decay weight based on how many days ago the outcome was."""
    days_ago = max(0, (now - entry_date.replace(tzinfo=None)).days)
    return EWMA_LAMBDA ** days_ago


def _is_correct(score: float, outcome: str, signal: str) -> bool:
    """
    Returns True if the engine's score correctly predicted the outcome direction.
    For BUY-family:  score>50 → expect WIN, score≤50 → expect LOSS
    For SELL-family: score<50 → expect WIN (price fell), score≥50 → expect LOSS
    """
    sig = (signal or "").upper().replace("_", " ")
    is_sell = "SELL" in sig

    if is_sell:
        bullish_score = score < 50   # for SELL, low score = bearish = correct
    else:
        bullish_score = score > 50

    return bullish_score == (outcome == "WIN")


def _weighted_predictive_power(
    scores: list[float],
    outcomes: list[str],
    signals: list[str],
    decay_weights: list[float],
    confidences: list[float],
) -> float:
    """
    Compute weighted predictive power for one engine.
    Returns [0, 1] — 0.5 means no better than random.
    """
    if not scores:
        return 0.5

    total_w = 0.0
    correct_w = 0.0
    for score, outcome, signal, dw, conf in zip(scores, outcomes, signals, decay_weights, confidences):
        # Confidence normalized to [0,1] range from [0,100]
        c = max(0.0, min(1.0, conf / 100.0)) if conf is not None else 0.5
        w = dw * (0.5 + 0.5 * c)   # min weight 0.5×dw even at zero confidence
        total_w += w
        if _is_correct(score, outcome, signal):
            correct_w += w

    if total_w == 0:
        return 0.5
    return correct_w / total_w


def _normalize(weights: dict) -> dict:
    """Ensure T+F+S = 1.0 exactly."""
    total = sum(weights.values())
    if total == 0:
        return {"T": 1/3, "F": 1/3, "S": 1/3}
    return {k: round(v / total, 4) for k, v in weights.items()}


def _blend(learned: dict, base: dict, alpha: float) -> dict:
    """Blend learned weights with base: alpha*learned + (1-alpha)*base, renormalized."""
    blended = {
        "T": alpha * learned["T"] + (1 - alpha) * base["T"],
        "F": alpha * learned["F"] + (1 - alpha) * base["F"],
        "S": alpha * learned["S"] + (1 - alpha) * base["S"],
    }
    return _normalize(blended)


def _compute_regime_weights(outcomes: list, now: datetime, regime: str) -> tuple[dict, int]:
    """
    Given a list of SignalOutcome rows for one regime,
    compute EWMA + confidence weighted adaptive weights.
    Returns (weights_dict, sample_count).
    """
    n = len(outcomes)
    if n < MIN_SAMPLES_PER_REGIME:
        return BASE_WEIGHTS[regime].copy(), n

    tech_scores  = [o.technical_score   for o in outcomes]
    fund_scores  = [o.fundamental_score  for o in outcomes]
    sent_scores  = [o.sentiment_score    for o in outcomes]
    outcome_lbls = [o.outcome            for o in outcomes]
    signals      = [o.signal             for o in outcomes]
    confidences  = [o.confidence or 50.0 for o in outcomes]

    # Per-outcome decay weight (incorporating D5/D10 discount)
    decay_ws = []
    for o in outcomes:
        base_decay = _ewma_decay(o.entry_date, now)
        day_factor = D5_WEIGHT if o.check_day == 5 else D10_WEIGHT
        decay_ws.append(base_decay * day_factor)

    tech_power = _weighted_predictive_power(tech_scores,  outcome_lbls, signals, decay_ws, confidences)
    fund_power = _weighted_predictive_power(fund_scores,  outcome_lbls, signals, decay_ws, confidences)
    sent_power = _weighted_predictive_power(sent_scores,  outcome_lbls, signals, decay_ws, confidences)

    # Normalize power → raw learned weights
    learned = _normalize({"T": tech_power, "F": fund_power, "S": sent_power})

    # Blend with regime base (more data = more trust)
    alpha = _alpha(n)
    weights = _blend(learned, BASE_WEIGHTS[regime], alpha)

    logger.info(
        f"  [{regime}] n={n} α={alpha:.2f} "
        f"power: T={tech_power:.3f} F={fund_power:.3f} S={sent_power:.3f} | "
        f"weights: T={weights['T']} F={weights['F']} S={weights['S']}"
    )
    return weights, n


# ── Main Entry Point ──────────────────────────────────────────────────────────

async def compute_and_save_adaptive_weights() -> dict:
    """
    v2 main entry — called by scheduler after outcome check.
    Returns a dict with per-regime weights AND global fallback weights.
    Shape:
    {
        "BULL":     {"T": 0.58, "F": 0.22, "S": 0.20},
        "BEAR":     {"T": 0.37, "F": 0.38, "S": 0.25},
        "SIDEWAYS": {"T": 0.46, "F": 0.29, "S": 0.25},
        "GLOBAL":   {"T": 0.47, "F": 0.30, "S": 0.23},   # weighted harmonic mean
        "sample_counts": {"BULL": 5, "BEAR": 12, "SIDEWAYS": 8},
        "last_updated": "2026-07-10T...",
    }
    """
    logger.info("🧠 [MetaLearnerV2] Starting regime-conditioned weight computation...")

    now = datetime.now(IST).replace(tzinfo=None)
    cutoff = now - timedelta(days=LOOKBACK_DAYS)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(SignalOutcome).where(
                and_(
                    SignalOutcome.entry_date >= cutoff,
                    SignalOutcome.outcome.in_(["WIN", "LOSS"]),
                    SignalOutcome.technical_score.isnot(None),
                    SignalOutcome.fundamental_score.isnot(None),
                    SignalOutcome.sentiment_score.isnot(None),
                )
            ).order_by(SignalOutcome.entry_date.desc())
        )
        all_outcomes = result.scalars().all()

    n_total = len(all_outcomes)
    logger.info(f"🧠 [MetaLearnerV2] Total WIN/LOSS outcomes available: {n_total}")

    # ── Split into regime buckets ─────────────────────────────────────────────
    buckets: dict[str, list] = {"BULL": [], "BEAR": [], "SIDEWAYS": []}
    for o in all_outcomes:
        regime = (o.regime or "SIDEWAYS").upper()
        if regime not in buckets:
            regime = "SIDEWAYS"
        buckets[regime].append(o)

    logger.info(
        f"🧠 Regime buckets: BULL={len(buckets['BULL'])} "
        f"BEAR={len(buckets['BEAR'])} SIDEWAYS={len(buckets['SIDEWAYS'])}"
    )

    # ── Compute weights per regime ────────────────────────────────────────────
    bull_weights, bull_n = _compute_regime_weights(buckets["BULL"],     now, "BULL")
    bear_weights, bear_n = _compute_regime_weights(buckets["BEAR"],     now, "BEAR")
    side_weights, side_n = _compute_regime_weights(buckets["SIDEWAYS"], now, "SIDEWAYS")

    # ── Global fallback = sample-count weighted average across regimes ────────
    total_n = bull_n + bear_n + side_n
    if total_n >= MIN_SAMPLES_GLOBAL:
        global_weights = _normalize({
            "T": (bull_weights["T"] * bull_n + bear_weights["T"] * bear_n + side_weights["T"] * side_n) / max(total_n, 1),
            "F": (bull_weights["F"] * bull_n + bear_weights["F"] * bear_n + side_weights["F"] * side_n) / max(total_n, 1),
            "S": (bull_weights["S"] * bull_n + bear_weights["S"] * bear_n + side_weights["S"] * side_n) / max(total_n, 1),
        })
    else:
        global_weights = GLOBAL_BASE.copy()
        logger.info(f"🧠 [MetaLearnerV2] Not enough global data ({total_n} < {MIN_SAMPLES_GLOBAL}). Using base.")

    # ── Persist to DB ─────────────────────────────────────────────────────────
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(UserSettings).where(UserSettings.user_id == "default")
        )
        us = result.scalar_one_or_none()
        if us is None:
            us = UserSettings(user_id="default")
            db.add(us)

        # v1 compat: store global as the v1 fields
        us.meta_weight_technical   = global_weights["T"]
        us.meta_weight_fundamental = global_weights["F"]
        us.meta_weight_sentiment   = global_weights["S"]
        us.meta_last_updated       = now
        us.meta_sample_count       = total_n

        # v2 per-regime weights
        us.meta_bull_T = bull_weights["T"]
        us.meta_bull_F = bull_weights["F"]
        us.meta_bull_S = bull_weights["S"]
        us.meta_bull_n = bull_n

        us.meta_bear_T = bear_weights["T"]
        us.meta_bear_F = bear_weights["F"]
        us.meta_bear_S = bear_weights["S"]
        us.meta_bear_n = bear_n

        us.meta_side_T = side_weights["T"]
        us.meta_side_F = side_weights["F"]
        us.meta_side_S = side_weights["S"]
        us.meta_side_n = side_n

        await db.commit()

    logger.info(
        f"✅ [MetaLearnerV2] Saved. Global: T={global_weights['T']} F={global_weights['F']} S={global_weights['S']}"
    )

    return {
        "BULL":     bull_weights,
        "BEAR":     bear_weights,
        "SIDEWAYS": side_weights,
        "GLOBAL":   global_weights,
        "sample_counts": {"BULL": bull_n, "BEAR": bear_n, "SIDEWAYS": side_n},
        "last_updated": now.isoformat(),
        # v1 compat keys
        "T": global_weights["T"],
        "F": global_weights["F"],
        "S": global_weights["S"],
    }


# ── Read current weights ──────────────────────────────────────────────────────

async def get_current_adaptive_weights() -> Optional[dict]:
    """
    Returns full v2 weight structure from DB, or None if not yet trained.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(UserSettings).where(UserSettings.user_id == "default")
        )
        s = result.scalar_one_or_none()
        if s is None or s.meta_weight_technical is None:
            return None

        return {
            "BULL": {
                "T": s.meta_bull_T or BASE_WEIGHTS["BULL"]["T"],
                "F": s.meta_bull_F or BASE_WEIGHTS["BULL"]["F"],
                "S": s.meta_bull_S or BASE_WEIGHTS["BULL"]["S"],
            },
            "BEAR": {
                "T": s.meta_bear_T or BASE_WEIGHTS["BEAR"]["T"],
                "F": s.meta_bear_F or BASE_WEIGHTS["BEAR"]["F"],
                "S": s.meta_bear_S or BASE_WEIGHTS["BEAR"]["S"],
            },
            "SIDEWAYS": {
                "T": s.meta_side_T or BASE_WEIGHTS["SIDEWAYS"]["T"],
                "F": s.meta_side_F or BASE_WEIGHTS["SIDEWAYS"]["F"],
                "S": s.meta_side_S or BASE_WEIGHTS["SIDEWAYS"]["S"],
            },
            "GLOBAL": {
                "T": s.meta_weight_technical,
                "F": s.meta_weight_fundamental,
                "S": s.meta_weight_sentiment,
            },
            "sample_counts": {
                "BULL":     s.meta_bull_n or 0,
                "BEAR":     s.meta_bear_n or 0,
                "SIDEWAYS": s.meta_side_n or 0,
            },
            "last_updated": s.meta_last_updated.isoformat() if s.meta_last_updated else None,
            "sample_count": s.meta_sample_count or 0,
            # v1 compat
            "T": s.meta_weight_technical,
            "F": s.meta_weight_fundamental,
            "S": s.meta_weight_sentiment,
        }
