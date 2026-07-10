"""
ATBot — Ensemble Scorer
Combines Technical, Fundamental, and Sentiment scores using dynamic weighting
(Market Regime aware + Meta-Learner adaptive) to output a final 0-100 Composite Score and Trade Signal.
Generates Price Targets & Stop Loss.
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy-loaded adaptive weights cache — v2 structure:
# { "BULL": {T,F,S}, "BEAR": {T,F,S}, "SIDEWAYS": {T,F,S}, "GLOBAL": {T,F,S}, ... }
_adaptive_weights_cache: Optional[dict] = None


def _get_adaptive_weights_sync() -> Optional[dict]:
    """Returns full v2 cache dict or None."""
    return _adaptive_weights_cache


def set_adaptive_weights(weights: Optional[dict]):
    """Called by scheduler after meta-learner v2 runs to update in-memory cache."""
    global _adaptive_weights_cache
    _adaptive_weights_cache = weights
    if weights:
        g = weights.get("GLOBAL") or weights  # handle v1 dict too
        logger.info(
            f"🧠 [Ensemble] Adaptive weights v2 loaded: "
            f"GLOBAL T={g.get('T')} F={g.get('F')} S={g.get('S')}"
        )


def determine_market_regime(nifty_change: float, vix: float, nifty_change_20d: float = 0.0) -> str:
    """
    Determine if market is BULL, BEAR, or SIDEWAYS.
    Uses 20-day trailing Nifty % change and VIX level for a more stable,
    trend-based regime that doesn't flip on a single bad day.
    """
    if vix > 22 and nifty_change_20d < -5:
        return "BEAR"
    elif nifty_change_20d > 3:
        return "BULL"
    return "SIDEWAYS"


def _static_regime_weights(regime: str) -> dict:
    """Hard-coded base weights per regime — used when meta-learner hasn't trained yet."""
    if regime == "BULL":
        return {"T": 0.55, "F": 0.25, "S": 0.20}
    elif regime == "BEAR":
        return {"T": 0.35, "F": 0.40, "S": 0.25}
    return {"T": 0.45, "F": 0.30, "S": 0.25}


def calculate_composite(
    tech_data: dict, 
    fund_data: dict, 
    sent_data: dict,
    nifty_change: float = 0.0,
    nifty_change_20d: float = 0.0,
    vix: float = 14.0,
    user_capital: float = None
) -> dict:
    """
    Calculates final composite score and signal.
    tech_data, fund_data, sent_data are outputs from their respective engines.
    """
    t_score = tech_data.get("score", 50)
    f_score = fund_data.get("score", 50)
    s_score = sent_data.get("score", 50)

    regime = determine_market_regime(nifty_change, vix, nifty_change_20d)

    # ── Weight Selection: Regime-specific v2 > Global v2 > Regime static ──────
    adaptive = _get_adaptive_weights_sync()
    weights_source = "static_regime"

    if adaptive:
        # v2 structure: has per-regime keys
        regime_weights = adaptive.get(regime) or adaptive.get("GLOBAL")
        if regime_weights and all(k in regime_weights for k in ("T", "F", "S")):
            weights = {"T": regime_weights["T"], "F": regime_weights["F"], "S": regime_weights["S"]}
            weights_source = f"adaptive_v2_{regime.lower()}"
        elif all(k in adaptive for k in ("T", "F", "S")):  # v1 fallback
            weights = {"T": adaptive["T"], "F": adaptive["F"], "S": adaptive["S"]}
            weights_source = "adaptive_v1_global"
        else:
            # No valid adaptive weights — use static regime defaults
            weights = _static_regime_weights(regime)
    else:
        weights = _static_regime_weights(regime)

    comp_score = (t_score * weights["T"]) + (f_score * weights["F"]) + (s_score * weights["S"])
    comp_score = round(comp_score, 2)

    # Signal Thresholds
    if comp_score >= 75:
        signal = "STRONG BUY"
    elif comp_score >= 60:
        signal = "BUY"
    elif comp_score >= 45:
        signal = "HOLD"
    elif comp_score >= 30:
        signal = "SELL"
    else:
        signal = "STRONG SELL"

    # Confidence calculation: Are engines agreeing?
    # Variance between the three scores. Lower variance = higher confidence.
    max_diff = max(abs(t_score - f_score), abs(t_score - s_score), abs(f_score - s_score))
    # Map max diff of 0-100 to confidence 100%-0%
    confidence = max(0, min(100, 100 - max_diff))
    
    # Target and Stop Loss (Only for Buy/Strong Buy)
    targets = None
    stop_loss = None
    rr_ratio = None
    
    current_price = tech_data.get("close")
    atr = tech_data.get("atr")

    if current_price and atr and signal in ["BUY", "STRONG BUY"]:
        # AI-determined Stop Loss (1.5x ATR below price)
        stop_loss = current_price - (atr * 1.5)
        
        # Targets
        base_target = current_price + (atr * 2.5) # R:R ~ 1:1.6
        targets = {
            "conservative": round(current_price + (atr * 1.5), 2),
            "base": round(base_target, 2),
            "aggressive": round(current_price + (atr * 3.5), 2)
        }
        
        risk = current_price - stop_loss
        reward = base_target - current_price
        rr_ratio = round(reward / risk, 2) if risk > 0 else 0

    # Position Sizing
    position_sizing = None
    if user_capital and user_capital > 0 and signal in ["BUY", "STRONG BUY"] and stop_loss and current_price:
        # Risk Model: Risk 1% to 2% of total capital per trade based on confidence
        risk_pct = 0.01 + (0.01 * (confidence / 100))
        capital_at_risk = user_capital * risk_pct
        risk_per_share = current_price - stop_loss
        
        if risk_per_share > 0:
            qty = int(capital_at_risk / risk_per_share)
            invested_amount = qty * current_price
            
            # Ensure we don't invest more than 20% of total capital in a single stock
            max_allocation = user_capital * 0.20
            if invested_amount > max_allocation:
                qty = int(max_allocation / current_price)
                invested_amount = qty * current_price

            if qty > 0:
                position_sizing = {
                    "suggested_quantity": qty,
                    "investment_amount": round(invested_amount, 2),
                    "capital_at_risk": round(qty * risk_per_share, 2),
                    "risk_pct_of_portfolio": round((qty * risk_per_share / user_capital) * 100, 2)
                }

    return {
        "composite_score": comp_score,
        "signal": signal,
        "confidence": round(confidence, 1),
        "regime": regime,
        "targets": targets,
        "stop_loss": round(stop_loss, 2) if stop_loss else None,
        "risk_reward": rr_ratio,
        "position_sizing": position_sizing,
        "weights_used": weights,
        "weights_source": weights_source,  # "adaptive" or "regime"
        "components": {
            "technical": t_score,
            "fundamental": f_score,
            "sentiment": s_score
        }
    }
