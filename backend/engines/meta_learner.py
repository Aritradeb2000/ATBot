"""
ATBot — Meta-Learner (Dynamic Auto-Weighting)
Analyses the last 30 days of resolved signal_outcomes to compute
adaptive engine weights (Technical / Fundamental / Sentiment).

Algorithm:
  1. Pull all WIN/LOSS outcomes (exclude HOLD/BREAKEVEN) from last N days.
  2. For each resolved outcome, compute how well each engine's score
     predicted the direction:
       - BUY outcome WIN:  positive correlation if tech/fund/sent score > 50
       - BUY outcome LOSS: negative correlation if score > 50
  3. Compute a "predictive power" score (0–1) per engine.
  4. Normalize the three power scores into weights that sum to 1.
  5. Blend 70% learned + 30% base regime weights (prevents over-fitting on few samples).
  6. Persist the new weights to UserSettings in the database.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List

import yfinance as yf
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from backend.models.database import AsyncSessionLocal
from backend.models.schemas import SignalOutcome, UserSettings
from backend.config import IST

logger = logging.getLogger(__name__)

# Minimum outcomes before we trust the learned weights
MIN_SAMPLES = 10

# Lookback window (calendar days)
LOOKBACK_DAYS = 30

# How much to trust learned weights vs. base weights (0.0 = all base, 1.0 = all learned)
LEARNING_RATE = 0.70

# Base weights per regime (fallback if not enough data)
BASE_WEIGHTS = {
    "BULL":     {"T": 0.55, "F": 0.25, "S": 0.20},
    "BEAR":     {"T": 0.35, "F": 0.40, "S": 0.25},
    "SIDEWAYS": {"T": 0.45, "F": 0.30, "S": 0.25},
}
DEFAULT_BASE = BASE_WEIGHTS["SIDEWAYS"]


def _predictive_power(scores: list[float], outcomes: list[str]) -> float:
    """
    Compute how well an engine's score predicts signal direction.
    Returns value in [0, 1] — higher means more predictive.

    For BUY signals:
      - Engine score > 50 + WIN  → correct (bullish score, bullish outcome)
      - Engine score > 50 + LOSS → incorrect
      - Engine score < 50 + WIN  → incorrect (bearish score, bullish outcome)
      - Engine score < 50 + LOSS → correct (bearish score, bearish outcome)
    """
    if not scores:
        return 0.5  # neutral

    correct = 0
    for score, outcome in zip(scores, outcomes):
        bullish_score = score > 50
        win = outcome == "WIN"
        if bullish_score == win:
            correct += 1

    return correct / len(scores)


async def compute_and_save_adaptive_weights() -> dict:
    """
    Main entry point — called by the scheduler after the outcome check job.
    Reads recent signal_outcomes, computes adaptive weights, saves to DB.
    Returns the new weights dict.
    """
    logger.info("🧠 [MetaLearner] Starting adaptive weight computation...")

    cutoff = datetime.now(IST).replace(tzinfo=None) - timedelta(days=LOOKBACK_DAYS)

    async with AsyncSessionLocal() as db:
        # 1. Pull resolved outcomes (WIN or LOSS only — skip HOLD/BREAKEVEN/OPEN)
        result = await db.execute(
            select(SignalOutcome).where(
                and_(
                    SignalOutcome.entry_date >= cutoff,
                    SignalOutcome.outcome.in_(["WIN", "LOSS"]),
                    SignalOutcome.check_day == 5,  # Use D5 for faster feedback
                    SignalOutcome.technical_score.isnot(None),
                    SignalOutcome.fundamental_score.isnot(None),
                    SignalOutcome.sentiment_score.isnot(None),
                )
            )
        )
        outcomes = result.scalars().all()

        n = len(outcomes)
        logger.info(f"🧠 [MetaLearner] Found {n} resolved outcomes in last {LOOKBACK_DAYS} days")

        if n < MIN_SAMPLES:
            logger.info(
                f"🧠 [MetaLearner] Not enough data ({n} < {MIN_SAMPLES}). "
                "Keeping base weights."
            )
            return DEFAULT_BASE

        # 2. Extract per-engine score lists + outcome labels
        tech_scores   = [o.technical_score   for o in outcomes]
        fund_scores   = [o.fundamental_score  for o in outcomes]
        sent_scores   = [o.sentiment_score    for o in outcomes]
        outcome_labels = [o.outcome           for o in outcomes]

        # 3. Compute predictive power for each engine
        tech_power = _predictive_power(tech_scores,  outcome_labels)
        fund_power = _predictive_power(fund_scores,  outcome_labels)
        sent_power = _predictive_power(sent_scores,  outcome_labels)

        total_power = tech_power + fund_power + sent_power
        if total_power == 0:
            logger.warning("🧠 [MetaLearner] Total power = 0; falling back to base weights.")
            return DEFAULT_BASE

        # 4. Normalize learned weights
        learned = {
            "T": round(tech_power / total_power, 4),
            "F": round(fund_power / total_power, 4),
            "S": round(sent_power / total_power, 4),
        }

        # 5. Blend with base weights (prevents wild swings on small samples)
        blended = {
            "T": round(LEARNING_RATE * learned["T"] + (1 - LEARNING_RATE) * DEFAULT_BASE["T"], 4),
            "F": round(LEARNING_RATE * learned["F"] + (1 - LEARNING_RATE) * DEFAULT_BASE["F"], 4),
            "S": round(LEARNING_RATE * learned["S"] + (1 - LEARNING_RATE) * DEFAULT_BASE["S"], 4),
        }

        # Renormalize after blend to ensure they sum to exactly 1.0
        total_blended = sum(blended.values())
        blended = {k: round(v / total_blended, 4) for k, v in blended.items()}

        logger.info(
            f"🧠 [MetaLearner] Predictive power → T={tech_power:.2%} F={fund_power:.2%} S={sent_power:.2%}"
        )
        logger.info(
            f"🧠 [MetaLearner] New blended weights → T={blended['T']} F={blended['F']} S={blended['S']}"
        )

        # 6. Persist to user_settings
        settings_result = await db.execute(
            select(UserSettings).where(UserSettings.user_id == "default")
        )
        user_settings = settings_result.scalar_one_or_none()

        if user_settings is None:
            user_settings = UserSettings(user_id="default")
            db.add(user_settings)

        user_settings.meta_weight_technical    = blended["T"]
        user_settings.meta_weight_fundamental  = blended["F"]
        user_settings.meta_weight_sentiment    = blended["S"]
        user_settings.meta_last_updated        = datetime.now(IST).replace(tzinfo=None)
        user_settings.meta_sample_count        = n

        await db.commit()
        logger.info("✅ [MetaLearner] Adaptive weights saved to database.")
        return blended


async def get_current_adaptive_weights() -> Optional[dict]:
    """
    Returns the last-computed adaptive weights from the database.
    Returns None if meta-learning has not run yet.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(UserSettings).where(UserSettings.user_id == "default")
        )
        s = result.scalar_one_or_none()
        if s is None or s.meta_weight_technical is None:
            return None
        return {
            "T": s.meta_weight_technical,
            "F": s.meta_weight_fundamental,
            "S": s.meta_weight_sentiment,
            "last_updated": s.meta_last_updated.isoformat() if s.meta_last_updated else None,
            "sample_count": s.meta_sample_count,
        }
