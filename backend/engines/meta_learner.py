"""
ATBot — Meta-Learner v3.2 (Cutoff + Horizon-Weighted Training)

What changed from v3.1:
  - TRAINING_EPOCH: training data before this date is permanently excluded.
    Pre-fix signals used trend-following scoring in SIDEWAYS, which we proved
    was inverted (holdout 26.57%). Excluding them forces the learner to train
    only on post-fix (reversion-routed SIDEWAYS) outcomes.
  - Per-horizon day_weight: D1/D2/D50/D100 no longer share the D10 weight.
    D5 remains the primary training horizon; D10 is strong secondary; D50/D100
    contribute but with reduced influence; D1/D2 are treated as noise.

Why this matters:
  The old day_weight mapping was:
    df["day_weight"] = df["check_day"].apply(
        lambda d: d5_weight if d == 5 else d10_weight
    )
  Every non-D5 check_day — including D1, D2, D50, D100 — received the D10
  weight (0.85). That meant 1-day noise and 100-day drift counted equally with
  10-day confirmation in training. The mapping is now explicit per horizon.

  The cutoff exists because the meta-learner was re-learning from the same
  corrupted SIDEWAYS outcomes that the fix is meant to replace. Even after
  fix #2 (directional agreement) surfaced the inversion, the learner could not
  move off base weights — because reverting on a 26.57%-accuracy holdout is
  the correct protective behavior. Post-epoch data is the only way to break
  the deadlock: new outcomes, new labels, new signal.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import pandas as pd
import numpy as np
from sqlalchemy import select, and_

from backend.models.database import AsyncSessionLocal
from backend.models.schemas import SignalOutcome, UserSettings
from backend.config import IST

logger = logging.getLogger(__name__)


# ── Training epoch ────────────────────────────────────────────────────────────
# Data with entry_date < TRAINING_EPOCH is excluded from meta-learner training.
# It remains in signal_outcomes for forensics and for the kill switch, but it
# is invisible to weight learning.
#
# Rationale: signals generated before 2026-09-19 used trend-following logic in
# SIDEWAYS markets (a regime where trend signals are inverted). Including them
# would teach the learner that all engines are ~0.42-0.46 predictive power,
# which is precisely the corrupted signal we are trying to escape.
#
# Set to None to disable the cutoff (train on the full lookback window).
TRAINING_EPOCH: Optional[datetime] = datetime(2026, 9, 19, 0, 0, 0)


# ── Configuration ──────────────────────────────────────────────────────────────

@dataclass
class MetaLearnerConfig:
    lookback_days: int = 90
    ewma_lambda: float = 0.92

    # Per-horizon weights for training samples.
    # Higher = more influence on learned engine powers.
    #   D1  — noise floor; gap reactions and single-bar whipsaws
    #   D2  — still very short; small weight
    #   D5  — primary decision horizon (targets are calibrated here)
    #   D10 — secondary confirmation; thesis has time to play out
    #   D50 — mid-term drift; useful but slow
    #   D100 — long-term drift; smallest weight — dominated by macro/sector
    d1_weight:   float = 0.50
    d2_weight:   float = 0.70
    d5_weight:   float = 1.00
    d10_weight:  float = 0.85
    d50_weight:  float = 0.60
    d100_weight: float = 0.50

    min_samples_per_regime: int = 5
    min_samples_global: int = 15
    alpha_min: float = 0.40
    alpha_max: float = 0.85
    alpha_ramp_start: int = 5
    alpha_ramp_end: int = 40
    holdout_ratio: float = 0.20
    # Raised from 0.25 → 0.35 to allow the learner to meaningfully downweight a
    # broken engine without immediately reverting to base.
    max_weight_drift: float = 0.35
    regime_lookback_days: int = 5
    # Scores within ±score_neutral_band of 50 are treated as "no opinion"
    # and receive near-zero weight in the agreement calculation.
    score_neutral_band: float = 5.0
    # Scores at ±score_full_opinion from 50 get full weight.
    score_full_opinion: float = 25.0
    base_weights: Dict[str, Dict[str, float]] = field(default_factory=lambda: {
        "BULL":     {"T": 0.55, "F": 0.25, "S": 0.20},
        "BEAR":     {"T": 0.35, "F": 0.40, "S": 0.25},
        "SIDEWAYS": {"T": 0.45, "F": 0.30, "S": 0.25},
    })


CONFIG = MetaLearnerConfig()
GLOBAL_BASE = {"T": 0.45, "F": 0.30, "S": 0.25}

# Resolved lookup for check_day → weight. Any unmapped horizon defaults to 0.5.
DAY_WEIGHTS: Dict[int, float] = {
    1:   CONFIG.d1_weight,
    2:   CONFIG.d2_weight,
    5:   CONFIG.d5_weight,
    10:  CONFIG.d10_weight,
    50:  CONFIG.d50_weight,
    100: CONFIG.d100_weight,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _alpha(n: int) -> float:
    if n < CONFIG.alpha_ramp_start:
        return CONFIG.alpha_min
    if n >= CONFIG.alpha_ramp_end:
        return CONFIG.alpha_max
    p = (n - CONFIG.alpha_ramp_start) / (CONFIG.alpha_ramp_end - CONFIG.alpha_ramp_start)
    return CONFIG.alpha_min + p * (CONFIG.alpha_max - CONFIG.alpha_min)


def _normalize(w: Dict[str, float]) -> Dict[str, float]:
    total = sum(w.values())
    if total <= 0:
        return {"T": 1/3, "F": 1/3, "S": 1/3}
    return {k: round(v / total, 6) for k, v in w.items()}


def _blend(learned: Dict[str, float], base: Dict[str, float], alpha: float) -> Dict[str, float]:
    raw = {k: alpha * learned[k] + (1 - alpha) * base[k] for k in ["T", "F", "S"]}
    n = _normalize(raw)
    clamped = {k: max(0.05, min(0.75, v)) for k, v in n.items()}
    return _normalize(clamped)


def _opinion_weight(scores: np.ndarray) -> np.ndarray:
    """
    Returns a weight in [0, 1] for how strongly an engine leaned.
    Scores near 50 → 0 (neutral, ignore). Scores far from 50 → 1 (strong opinion).
    Uses a linear ramp between neutral_band and full_opinion.
    """
    distance = np.abs(scores - 50.0)
    neutral = CONFIG.score_neutral_band
    full = CONFIG.score_full_opinion
    return np.clip((distance - neutral) / (full - neutral), 0.0, 1.0)


def _engine_power(df: pd.DataFrame, col: str) -> float:
    """
    Measures how well this engine's scores predict actual signed returns.

    Returns a value in [0, 1]:
      > 0.5  → engine has predictive power (higher score → higher return)
      = 0.5  → engine is a coin flip (no information)
      < 0.5  → engine is inverted (higher score → LOWER return) ← possible broken engine

    Metric: magnitude-weighted directional agreement between
    (score - 50) and pnl_percent. Scores near 50 are downweighted because
    they represent no opinion.
    """
    if df.empty:
        return 0.5

    scores = df[col].values.astype(float)
    pnl = df["pnl_percent"].fillna(0).values.astype(float)

    # Directional agreement: +1 if engine's lean matched the return, -1 if not.
    score_dir = np.sign(scores - 50.0)
    pnl_dir = np.sign(pnl)
    agreement = score_dir * pnl_dir  # -1, 0, or +1

    # Weight: how strongly the engine leaned × recency decay × day-weight × confidence
    weight = (
        _opinion_weight(scores)
        * df["decay"].values
        * df["day_weight"].values
        * (0.5 + 0.5 * df["confidence"].clip(0, 1).values)
    )

    total_w = weight.sum()
    if total_w == 0:
        return 0.5

    weighted_agreement = float((weight * agreement).sum() / total_w)
    # Map [-1, +1] → [0, 1]
    return 0.5 + 0.5 * weighted_agreement


def _holdout_accuracy(
    learned: Dict[str, float],
    test: pd.DataFrame,
    base: Dict[str, float],
    alpha: float,
) -> float:
    """
    Evaluate blended weights on held-out data using the same directional metric.
    Returns [0, 1] where 0.5 = no signal.
    """
    if test.empty:
        return 0.5

    b = _blend(learned, base, alpha)
    t = test
    composite = (
        b["T"] * t["technical_score"].values
        + b["F"] * t["fundamental_score"].values
        + b["S"] * t["sentiment_score"].values
    )
    pnl = t["pnl_percent"].fillna(0).values.astype(float)

    score_dir = np.sign(composite - 50.0)
    pnl_dir = np.sign(pnl)
    agreement = score_dir * pnl_dir

    opinion = _opinion_weight(composite)
    if opinion.sum() == 0:
        return 0.5

    weighted = float((opinion * agreement).sum() / opinion.sum())
    return 0.5 + 0.5 * weighted


def _detect_regime_shift(df: pd.DataFrame) -> bool:
    if len(df) < CONFIG.regime_lookback_days * 2:
        return False
    s = df.sort_values("entry_date")
    recent = s.tail(CONFIG.regime_lookback_days)["regime"].mode()
    prior = s.iloc[-CONFIG.regime_lookback_days * 2:-CONFIG.regime_lookback_days]["regime"].mode()
    r = recent.iloc[0] if not recent.empty else None
    p = prior.iloc[0] if not prior.empty else None
    if r and p and r != p:
        logger.info(f"Regime shift detected: {p} -> {r}")
        return True
    return False


# ── Main computation ──────────────────────────────────────────────────────────

async def compute_and_save_adaptive_weights() -> Dict[str, Any]:
    logger.info("[MetaLearnerV3.2] Starting...")
    now = datetime.now(IST).replace(tzinfo=None)

    # ── Cutoff: max(lookback floor, TRAINING_EPOCH) ───────────────────────────
    lookback_cutoff = now - timedelta(days=CONFIG.lookback_days)
    cutoff = lookback_cutoff
    if TRAINING_EPOCH is not None and TRAINING_EPOCH > cutoff:
        cutoff = TRAINING_EPOCH
        logger.info(
            f"[MetaLearnerV3.2] Training epoch active: excluding entry_date "
            f"< {TRAINING_EPOCH.date()} (was lookback cutoff "
            f"{lookback_cutoff.date()})"
        )

    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(SignalOutcome).where(
                and_(
                    SignalOutcome.entry_date >= cutoff,
                    # Include PARTIAL because we use pnl_percent directly.
                    # BREAKEVEN excluded (|pnl| < 0.5% is noise).
                    SignalOutcome.outcome.in_(["WIN", "LOSS", "PARTIAL"]),
                    SignalOutcome.pnl_percent.isnot(None),
                    SignalOutcome.technical_score.isnot(None),
                    SignalOutcome.fundamental_score.isnot(None),
                    SignalOutcome.sentiment_score.isnot(None),
                    SignalOutcome.confidence.isnot(None),
                    # Exclude shadow outcomes — they're counterfactual evidence
                    # for the reversion engine, not training data for weights.
                    # is_shadow may be NULL on legacy rows; treat as visible.
                    (SignalOutcome.is_shadow == 0) | (SignalOutcome.is_shadow.is_(None)),
                )
            ).order_by(SignalOutcome.entry_date.desc())
        )
        outcomes = res.scalars().all()

    if len(outcomes) < CONFIG.min_samples_global:
        logger.warning(
            f"Insufficient data ({len(outcomes)} post-epoch outcomes). "
            f"Need {CONFIG.min_samples_global}. Skipping."
        )
        return await _get_existing_weights_or_base()

    logger.info(f"Fetched {len(outcomes)} resolved outcomes (WIN/LOSS/PARTIAL).")

    df = pd.DataFrame([{
        "entry_date": o.entry_date,
        "check_day": o.check_day,
        "outcome": o.outcome,
        "signal": o.signal or "HOLD",
        "pnl_percent": float(o.pnl_percent or 0.0),
        "confidence": (o.confidence or 50.0) / 100.0,
        "regime": (o.regime or "SIDEWAYS").upper(),
        "technical_score": o.technical_score,
        "fundamental_score": o.fundamental_score,
        "sentiment_score": o.sentiment_score,
    } for o in outcomes])

    df["regime"] = df["regime"].apply(lambda x: x if x in ["BULL", "BEAR", "SIDEWAYS"] else "SIDEWAYS")
    df["entry_date"] = pd.to_datetime(df["entry_date"])
    df["days_ago"] = (now - df["entry_date"]).dt.days.clip(lower=0)
    df["decay"] = CONFIG.ewma_lambda ** df["days_ago"]

    # ── Per-horizon day weights ───────────────────────────────────────────────
    # Was: d5_weight if d == 5 else d10_weight  →  every non-D5 got D10 weight.
    # Now: explicit per-check_day mapping. Unmapped horizons fall back to 0.5.
    df["day_weight"] = df["check_day"].map(DAY_WEIGHTS).fillna(0.5)

    df_s = df.sort_values("entry_date").reset_index(drop=True)
    split = int(len(df_s) * (1 - CONFIG.holdout_ratio))
    train_df, test_df = df_s.iloc[:split], df_s.iloc[split:]
    logger.info(f"Train: {len(train_df)} | Test: {len(test_df)}")

    regime_shift = _detect_regime_shift(df)
    alpha_boost = 0.10 if regime_shift else 0.0

    regimes = ["BULL", "BEAR", "SIDEWAYS"]
    results: Dict[str, Dict] = {}
    sample_counts: Dict[str, int] = {}
    holdout_accs: Dict[str, float] = {}

    for regime in regimes:
        tr = train_df[train_df["regime"] == regime]
        n = len(tr)
        sample_counts[regime] = n

        if n < CONFIG.min_samples_per_regime:
            logger.info(f"  [{regime}] n={n} -> base weights")
            results[regime] = CONFIG.base_weights[regime].copy()
            holdout_accs[regime] = 0.5
            continue

        t_power = _engine_power(tr, "technical_score")
        f_power = _engine_power(tr, "fundamental_score")
        s_power = _engine_power(tr, "sentiment_score")

        logger.info(
            f"  [{regime}] n={n} | engine predictive power: "
            f"T={t_power:.3f}  F={f_power:.3f}  S={s_power:.3f}"
        )

        learned = _normalize({"T": t_power, "F": f_power, "S": s_power})
        alpha = min(CONFIG.alpha_max, _alpha(n) + alpha_boost)

        te = test_df[test_df["regime"] == regime]
        acc = _holdout_accuracy(learned, te, CONFIG.base_weights[regime], alpha)
        holdout_accs[regime] = acc
        logger.info(
            f"  [{regime}] alpha={alpha:.2f} holdout_acc={acc:.2%} "
            f"(learned T={learned['T']:.3f} F={learned['F']:.3f} S={learned['S']:.3f})"
        )

        if not te.empty and acc < 0.45:
            logger.warning(f"  [{regime}] holdout {acc:.2%} < 45% -> base")
            results[regime] = CONFIG.base_weights[regime].copy()
            continue

        weights = _blend(learned, CONFIG.base_weights[regime], alpha)
        base = CONFIG.base_weights[regime]
        drift = max(abs(weights[k] - base[k]) for k in ["T", "F", "S"])
        if drift > CONFIG.max_weight_drift:
            logger.warning(
                f"  [{regime}] drift {drift:.3f} > {CONFIG.max_weight_drift} -> base "
                f"(weights={weights}, base={base})"
            )
            results[regime] = base.copy()
        else:
            results[regime] = weights
            logger.info(
                f"  [{regime}] FINAL T={weights['T']:.3f} "
                f"F={weights['F']:.3f} S={weights['S']:.3f} (drift={drift:.3f})"
            )

    total_n = sum(sample_counts.values())
    if total_n >= CONFIG.min_samples_global:
        global_weights = _normalize({
            "T": sum(results[r]["T"] * sample_counts[r] for r in regimes) / total_n,
            "F": sum(results[r]["F"] * sample_counts[r] for r in regimes) / total_n,
            "S": sum(results[r]["S"] * sample_counts[r] for r in regimes) / total_n,
        })
    else:
        global_weights = GLOBAL_BASE.copy()

    overall_holdout = float(np.mean(list(holdout_accs.values())))

    # ── Persist to DB ─────────────────────────────────────────────────────────
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(UserSettings).where(UserSettings.user_id == "default"))
        us = res.scalar_one_or_none()
        if us is None:
            us = UserSettings(user_id="default")
            db.add(us)

        us.meta_weight_technical = global_weights["T"]
        us.meta_weight_fundamental = global_weights["F"]
        us.meta_weight_sentiment = global_weights["S"]
        us.meta_last_updated = now
        us.meta_sample_count = total_n

        us.meta_bull_T = results["BULL"]["T"]
        us.meta_bull_F = results["BULL"]["F"]
        us.meta_bull_S = results["BULL"]["S"]
        us.meta_bull_n = sample_counts["BULL"]

        us.meta_bear_T = results["BEAR"]["T"]
        us.meta_bear_F = results["BEAR"]["F"]
        us.meta_bear_S = results["BEAR"]["S"]
        us.meta_bear_n = sample_counts["BEAR"]

        us.meta_side_T = results["SIDEWAYS"]["T"]
        us.meta_side_F = results["SIDEWAYS"]["F"]
        us.meta_side_S = results["SIDEWAYS"]["S"]
        us.meta_side_n = sample_counts["SIDEWAYS"]

        us.meta_validation_accuracy = round(overall_holdout, 4)
        us.meta_regime_shift_detected = int(regime_shift)

        await db.commit()

    logger.info(
        f"[MetaLearnerV3.2] Done. "
        f"GLOBAL T={global_weights['T']:.3f} "
        f"F={global_weights['F']:.3f} "
        f"S={global_weights['S']:.3f} | "
        f"holdout={overall_holdout:.2%} | shift={regime_shift}"
    )

    return {
        "BULL": results["BULL"],
        "BEAR": results["BEAR"],
        "SIDEWAYS": results["SIDEWAYS"],
        "GLOBAL": global_weights,
        "sample_counts": sample_counts,
        "last_updated": now.isoformat(),
        "regime_shift_detected": regime_shift,
        "validation_accuracy": overall_holdout,
        "T": global_weights["T"],
        "F": global_weights["F"],
        "S": global_weights["S"],
    }


async def _get_existing_weights_or_base() -> Dict[str, Any]:
    existing = await get_current_adaptive_weights()
    if existing:
        return existing
    return {
        "BULL": CONFIG.base_weights["BULL"],
        "BEAR": CONFIG.base_weights["BEAR"],
        "SIDEWAYS": CONFIG.base_weights["SIDEWAYS"],
        "GLOBAL": GLOBAL_BASE,
        "sample_counts": {"BULL": 0, "BEAR": 0, "SIDEWAYS": 0},
        "last_updated": None,
        "regime_shift_detected": False,
        "validation_accuracy": None,
        "T": GLOBAL_BASE["T"],
        "F": GLOBAL_BASE["F"],
        "S": GLOBAL_BASE["S"],
    }


async def get_current_adaptive_weights() -> Optional[Dict[str, Any]]:
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(UserSettings).where(UserSettings.user_id == "default"))
        s = res.scalar_one_or_none()
        if s is None or s.meta_weight_technical is None:
            return None
        return {
            "BULL": {
                "T": s.meta_bull_T or CONFIG.base_weights["BULL"]["T"],
                "F": s.meta_bull_F or CONFIG.base_weights["BULL"]["F"],
                "S": s.meta_bull_S or CONFIG.base_weights["BULL"]["S"],
            },
            "BEAR": {
                "T": s.meta_bear_T or CONFIG.base_weights["BEAR"]["T"],
                "F": s.meta_bear_F or CONFIG.base_weights["BEAR"]["F"],
                "S": s.meta_bear_S or CONFIG.base_weights["BEAR"]["S"],
            },
            "SIDEWAYS": {
                "T": s.meta_side_T or CONFIG.base_weights["SIDEWAYS"]["T"],
                "F": s.meta_side_F or CONFIG.base_weights["SIDEWAYS"]["F"],
                "S": s.meta_side_S or CONFIG.base_weights["SIDEWAYS"]["S"],
            },
            "GLOBAL": {
                "T": s.meta_weight_technical,
                "F": s.meta_weight_fundamental,
                "S": s.meta_weight_sentiment,
            },
            "sample_counts": {
                "BULL": s.meta_bull_n or 0,
                "BEAR": s.meta_bear_n or 0,
                "SIDEWAYS": s.meta_side_n or 0,
            },
            "last_updated": s.meta_last_updated.isoformat() if s.meta_last_updated else None,
            "sample_count": s.meta_sample_count or 0,
            "validation_accuracy": s.meta_validation_accuracy,
            "regime_shift_detected": bool(s.meta_regime_shift_detected),
            "T": s.meta_weight_technical,
            "F": s.meta_weight_fundamental,
            "S": s.meta_weight_sentiment,
        }