"""
ATBot — Ensemble Scorer
Combines Technical, Fundamental, and Sentiment scores using dynamic weighting
(Market Regime aware + Meta-Learner adaptive) to output a final 0-100 Composite Score and Trade Signal.

v4 (PATCH):
  - SIDEWAYS kill switch (v2)
  - SELL-side targets & stop-loss (v2)
  - SIDEWAYS routes to reversion_score (v3)
  - NEW: shadow_signal + kill_switch_active exposed on every result. Targets
    and stops are computed from the shadow signal, so the outcome tracker can
    evaluate the "would-be" trade even while the visible signal is HOLD.
"""

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

_adaptive_weights_cache: Optional[dict] = None


# ── SIDEWAYS Kill Switch ─────────────────────────────────────────────────────
KILL_SWITCH_ENABLED      = True
SIDEWAYS_KILL_THRESHOLD  = 0.35
SIDEWAYS_KILL_MIN_TRADES = 20

_sideways_kill_state = {
    "win_rate":     None,
    "n":            0,
    "last_refresh": None,
    "active":       False,
}


def set_sideways_win_rate(win_rate: Optional[float], n: int):
    global _sideways_kill_state
    _sideways_kill_state["win_rate"]     = win_rate
    _sideways_kill_state["n"]            = n
    _sideways_kill_state["last_refresh"] = datetime.utcnow()

    active = (
        KILL_SWITCH_ENABLED
        and win_rate is not None
        and n >= SIDEWAYS_KILL_MIN_TRADES
        and win_rate < SIDEWAYS_KILL_THRESHOLD
    )
    _sideways_kill_state["active"] = active

    if active:
        logger.warning(
            f"🛑 [KillSwitch] SIDEWAYS ACTIVE — win_rate={win_rate:.1%} "
            f"over {n} trades (threshold {SIDEWAYS_KILL_THRESHOLD:.0%})"
        )
    else:
        logger.info(f"[KillSwitch] SIDEWAYS inactive (win_rate={win_rate}, n={n})")


def get_sideways_kill_state() -> dict:
    return dict(_sideways_kill_state)


def _get_adaptive_weights_sync() -> Optional[dict]:
    return _adaptive_weights_cache


def set_adaptive_weights(weights: Optional[dict]):
    global _adaptive_weights_cache
    _adaptive_weights_cache = weights
    if weights:
        g = weights.get("GLOBAL") or weights
        logger.info(
            f"🧠 [Ensemble] Adaptive weights v2 loaded: "
            f"GLOBAL T={g.get('T')} F={g.get('F')} S={g.get('S')}"
        )


def determine_market_regime(
    nifty_change: float,
    vix: float,
    nifty_change_20d: float = 0.0,
    advances_pct: float = 0.5,
    fii_net_5d: float = 0.0,
) -> str:
    score = 0.0
    trend_score = 0.0

    if nifty_change_20d >= 4.0:
        trend_score = 2.0
    elif nifty_change_20d >= 1.5:
        trend_score = 1.0
    elif nifty_change_20d <= -5.0:
        trend_score = -2.0
    elif nifty_change_20d <= -2.5:
        trend_score = -1.0

    score += trend_score

    if vix < 14.0 and nifty_change_20d >= 0:
        score += 1.0
    elif vix > 20.0:
        score -= 1.0
    elif vix > 17.0:
        score -= 0.5

    if advances_pct > 0.65:
        score += 1.0
    elif advances_pct < 0.40:
        score -= 1.0

    if fii_net_5d > 3000:
        score += 1.0
    elif fii_net_5d < -3000:
        score -= 1.0

    if score >= 2.5 and trend_score > 0:
        return "BULL"
    elif score <= -2.0 and trend_score < 0:
        return "BEAR"
    return "SIDEWAYS"


def _static_regime_weights(regime: str) -> dict:
    if regime == "BULL":
        return {"T": 0.55, "F": 0.25, "S": 0.20}
    elif regime == "BEAR":
        return {"T": 0.35, "F": 0.40, "S": 0.25}
    return {"T": 0.45, "F": 0.30, "S": 0.25}



# ── XGBoost Signal Filter (Trained on 2017-2024 Regime-Diverse Data) ──────────
_xgb_filter_cache = None

def get_xgb_signal_filter():
    """Lazily loads the production XGBoost classifier trained on 2017-2024 Nifty 200 data."""
    global _xgb_filter_cache
    if _xgb_filter_cache is None:
        try:
            import os
            import joblib
            model_path = os.path.join(
                os.path.dirname(__file__), "..", "models", "weights", "xgb_signal_filter.joblib"
            )
            if os.path.exists(model_path):
                _xgb_filter_cache = joblib.load(model_path)
                logger.info("Loaded XGBoost signal filter (2017-2024 Nifty 200 trained) successfully.")
        except Exception as e:
            logger.warning(f"Could not load xgb_signal_filter: {e}")
    return _xgb_filter_cache

def evaluate_signal_quality(tech_data: dict, is_buy: bool) -> dict:
    """
    Evaluates historical win probability for a setup using the 2017-2024 calibrated XGBoost model.
    """
    pkg = get_xgb_signal_filter()
    if not pkg:
        return {"win_prob": None, "verdict": "MODEL_UNAVAILABLE", "ai_note": None}

    features = tech_data.get("features")
    if not features:
        return {"win_prob": None, "verdict": "FEATURES_UNAVAILABLE", "ai_note": None}

    try:
        model = pkg["model"]
        feature_cols = pkg["feature_cols"]

        # Build feature vector
        row = dict(features)
        row["is_buy"] = 1.0 if is_buy else 0.0

        import numpy as np
        import pandas as pd
        vec = [row.get(col, 0.0) for col in feature_cols]
        X = pd.DataFrame([vec], columns=feature_cols).replace([np.inf, -np.inf], np.nan).fillna(0)

        win_prob = float(model.predict_proba(X)[0, 1])

        if win_prob >= 0.55:
            verdict = "HIGH_CONVICTION"
            note = f"🔥 AI Conviction: {win_prob*100:.1f}% estimated win rate (2017-2024 calibrated)"
        elif win_prob >= 0.45:
            verdict = "NEUTRAL"
            note = f"⚖️ AI Neutral: {win_prob*100:.1f}% win probability"
        else:
            verdict = "LOW_PROBABILITY"
            note = f"⚠️ AI Caution: Low historical win probability ({win_prob*100:.1f}%)"

        return {"win_prob": round(win_prob, 3), "verdict": verdict, "ai_note": note}
    except Exception as e:
        logger.warning(f"Error evaluating signal quality: {e}")
        return {"win_prob": None, "verdict": "ERROR", "ai_note": str(e)}


def calculate_composite(
    tech_data: dict,
    fund_data: dict,
    sent_data: dict,
    nifty_change: float = 0.0,
    nifty_change_20d: float = 0.0,
    vix: float = 14.0,
    user_capital: float = None,
    advances_pct: float = 0.5,
    fii_net_5d: float = 0.0,
    regime: Optional[str] = None,
) -> dict:
    # ── Regime FIRST (needed before choosing technical sub-score) ─────────────
    if regime is None:
        regime = determine_market_regime(
            nifty_change=nifty_change,
            vix=vix,
            nifty_change_20d=nifty_change_20d,
            advances_pct=advances_pct,
            fii_net_5d=fii_net_5d,
        )

    # ── Technical score selection (v3: SIDEWAYS uses reversion_score) ─────────
    if regime == "SIDEWAYS":
        t_raw = tech_data.get("reversion_score")
        if t_raw is None:
            t_raw = tech_data.get("score")
        t_used_field = "reversion_score"
    else:
        t_raw = tech_data.get("score")
        t_used_field = "score"

    # Defensive dictionary checks
    tech_data = tech_data if isinstance(tech_data, dict) else {}
    fund_data = fund_data if isinstance(fund_data, dict) else {}
    sent_data = sent_data if isinstance(sent_data, dict) else {}

    t_has_data = (t_raw is not None)
    f_val = fund_data.get("score")
    f_has_data = (f_val is not None)
    s_val = sent_data.get("score")
    s_has_data = (s_val is not None)
    missing_engines = sum(1 for x in (t_has_data, f_has_data, s_has_data) if not x)

    t_score = float(t_raw) if t_has_data else 50.0
    f_score = float(f_val) if f_has_data else 50.0
    
    # 📉 BEAR MARKET: Non-linear Fundamental Suppression
    # Do not let high fundamentals overpower a weak technical downtrend.
    if regime == "BEAR" and t_score < 50:
        f_score = min(f_score, 50.0)
    s_score = float(s_val) if s_has_data else 50.0

    # ── Weights ──────────────────────────────────────────────────────────────
    adaptive = _get_adaptive_weights_sync()
    weights_source = "static_regime"

    if adaptive:
        regime_weights = adaptive.get(regime) or adaptive.get("GLOBAL")
        if regime_weights and all(k in regime_weights for k in ("T", "F", "S")):
            weights = {"T": regime_weights["T"], "F": regime_weights["F"], "S": regime_weights["S"]}
            weights_source = f"adaptive_v2_{regime.lower()}"
        elif all(k in adaptive for k in ("T", "F", "S")):
            weights = {"T": adaptive["T"], "F": adaptive["F"], "S": adaptive["S"]}
            weights_source = "adaptive_v1_global"
        else:
            weights = _static_regime_weights(regime)
    else:
        weights = _static_regime_weights(regime)

    total_w = weights["T"] + weights["F"] + weights["S"]
    if abs(total_w - 1.0) > 0.01:
        logger.warning(f"[Ensemble] Weights sum to {total_w:.3f}, normalizing")
        weights = {k: v / total_w for k, v in weights.items()}

    engine_weights = {
        "T": weights["T"] if t_has_data else 0.0,
        "F": weights["F"] if f_has_data else 0.0,
        "S": weights["S"] if s_has_data else 0.0,
    }
    active_weight_sum = engine_weights["T"] + engine_weights["F"] + engine_weights["S"]
    if active_weight_sum > 0.0:
        engine_weights = {k: v / active_weight_sum for k, v in engine_weights.items()}
    else:
        engine_weights = weights

    comp_score = (t_score * engine_weights["T"]) + (f_score * engine_weights["F"]) + (s_score * engine_weights["S"])
    comp_score = round(comp_score, 2)

    # ── Compute shadow signal (pre-kill-switch) ──────────────────────────────
    regime_offset = {"BEAR": 10, "SIDEWAYS": 5, "BULL": 0}.get(regime, 0)

    if comp_score >= (85 + regime_offset):
        shadow_signal = "STRONG BUY"
    elif comp_score >= (75 + regime_offset):
        shadow_signal = "BUY"
    elif comp_score >= 45:
        shadow_signal = "HOLD"
    elif comp_score >= 35:
        shadow_signal = "SELL"
    else:
        shadow_signal = "STRONG SELL"

    # ── Targets & stops are computed from the SHADOW signal ──────────────────
    # This means even when the kill switch forces HOLD, the AnalysisScore row
    # still carries the targets/stops the outcome tracker needs to evaluate
    # the would-be trade.
    targets = None
    targets_5d = targets_10d = targets_50d = targets_100d = None
    stop_loss = None
    rr_ratio = None

    current_price = tech_data.get("close")
    atr = tech_data.get("atr")

    is_buy_shadow  = shadow_signal in ["BUY", "STRONG BUY"]
    is_sell_shadow = shadow_signal in ["SELL", "STRONG SELL"]

    if current_price and atr and (is_buy_shadow or is_sell_shadow):
        conviction_mult = min(1.5, 1.0 + (max(0, comp_score - 60) * 0.015))
        regime_target_mult = {"BULL": 2.2, "SIDEWAYS": 1.8, "BEAR": 1.5}.get(regime, 1.8)
        # Positive Risk:Reward: Tight stop loss (max 1.2x ATR) prevents single loss from wiping out multiple wins
        regime_stop_mult   = {"BULL": 1.2, "SIDEWAYS": 1.0, "BEAR": 1.0}.get(regime, 1.0)

        eff_target = conviction_mult * regime_target_mult
        direction  = 1.0 if is_buy_shadow else -1.0

        stop_loss = round(
            current_price - (atr * regime_stop_mult) if is_buy_shadow
            else current_price + (atr * regime_stop_mult), 2
        )

        # 5-Day Swing Targets: Base Target guarantees positive 1:1.6 to 1:2 Risk:Reward
        targets_5d = {
            "conservative": round(current_price + direction * max(atr * 1.2, atr * 0.9 * eff_target), 2),
            "base":         round(current_price + direction * (atr * 1.8 * eff_target), 2),
            "aggressive":   round(current_price + direction * (atr * 2.6 * eff_target), 2),
        }
        # 10-Day Position Targets
        targets_10d = {
            "conservative": round(current_price + direction * (atr * 1.8 * eff_target), 2),
            "base":         round(current_price + direction * (atr * 2.8 * eff_target), 2),
            "aggressive":   round(current_price + direction * (atr * 4.0 * eff_target), 2),
        }
        targets_50d = {
            "conservative": round(current_price + direction * (atr * 4.0 * eff_target), 2),
            "base":         round(current_price + direction * (atr * 6.0 * eff_target), 2),
            "aggressive":   round(current_price + direction * (atr * 9.0 * eff_target), 2),
        }
        targets_100d = {
            "conservative": round(current_price + direction * (atr * 6.0  * eff_target), 2),
            "base":         round(current_price + direction * (atr * 9.0  * eff_target), 2),
            "aggressive":   round(current_price + direction * (atr * 13.0 * eff_target), 2),
        }
        targets = targets_5d

        # Realized Risk-to-Reward Ratio: Base Target vs Strict Stop Loss
        reward_rr = abs(targets_5d["base"] - current_price)
        risk_rr   = abs(current_price - stop_loss)
        rr_ratio  = round(reward_rr / risk_rr, 2) if risk_rr > 0 else 0

    # ── Kill switch — mask the visible signal only ────────────────────────────
    kill_switch_active = False
    signal = shadow_signal
    if regime == "SIDEWAYS" and _sideways_kill_state["active"]:
        kill_switch_active = True
        signal = "HOLD"
        logger.info(
            f"[Ensemble] Kill switch forced HOLD "
            f"(shadow={shadow_signal}, sideways_win_rate="
            f"{_sideways_kill_state['win_rate']:.1%})"
        )

    # ── AI Signal Quality Assessment (XGBoost 2017-2024 Filter) ───────────────
    ai_eval = {"win_prob": None, "verdict": "NOT_EVALUATED", "ai_note": None}
    if is_buy_shadow or is_sell_shadow:
        ai_eval = evaluate_signal_quality(tech_data, is_buy=is_buy_shadow)
        # If AI model flags low probability in a sideways/bear regime, downgrade weak BUY to HOLD
        if ai_eval.get("verdict") == "LOW_PROBABILITY" and regime in ["SIDEWAYS", "BEAR"]:
            if signal == "BUY" and comp_score < 80:
                signal = "HOLD"
                logger.info(f"[Ensemble] AI XGBoost filter downgraded weak BUY to HOLD (P={ai_eval.get('win_prob')})")

    # ── Confidence ────────────────────────────────────────────────────────────
    active_scores = [s for s, has in [(t_score, t_has_data), (f_score, f_has_data), (s_score, s_has_data)] if has]

    if len(active_scores) >= 2:
        pairs = [(active_scores[i], active_scores[j])
                 for i in range(len(active_scores))
                 for j in range(i + 1, len(active_scores))]
        max_diff = max(abs(a - b) for a, b in pairs)
        confidence = max(0, min(100, 100 - max_diff))
        if ai_eval.get("verdict") == "HIGH_CONVICTION":
            confidence = min(98.0, confidence + 12.0)
        elif ai_eval.get("verdict") == "LOW_PROBABILITY":
            confidence = max(20.0, confidence - 15.0)
        if missing_engines > 0:
            confidence = min(confidence, 100 - (missing_engines * 25))
    elif len(active_scores) == 1:
        confidence = 30
    else:
        confidence = 20

    # ── Position Sizing — visible BUY only (never shadow) ────────────────────
    position_sizing = None
    is_buy_visible = signal in ["BUY", "STRONG BUY"]
    if user_capital and user_capital > 0 and is_buy_visible and stop_loss and current_price:
        regime_risk_mult = {"BULL": 1.0, "SIDEWAYS": 0.85, "BEAR": 0.60}.get(regime, 0.85)
        regime_max_alloc = {"BULL": 0.20, "SIDEWAYS": 0.15, "BEAR": 0.10}.get(regime, 0.15)

        risk_pct = (0.01 + 0.01 * (confidence / 100)) * regime_risk_mult
        capital_at_risk = user_capital * risk_pct
        risk_per_share = current_price - stop_loss

        if risk_per_share > 0:
            qty = int(capital_at_risk / risk_per_share)
            invested_amount = qty * current_price
            max_allocation = user_capital * regime_max_alloc
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
        "shadow_signal": shadow_signal,
        "kill_switch_active": kill_switch_active,
        "confidence": round(confidence, 1),
        "regime": regime,
        "targets":      targets,
        "targets_5d":   targets_5d   if targets_5d   else None,
        "targets_10d":  targets_10d  if targets_10d  else None,
        "targets_50d":  targets_50d  if targets_50d  else None,
        "targets_100d": targets_100d if targets_100d else None,
        "stop_loss": stop_loss,
        "risk_reward": rr_ratio,
        "position_sizing": position_sizing,
        "weights_used": weights,
        "weights_source": weights_source,
        "ai_signal_quality": ai_eval,
        "components": {
            "technical":   round(t_score, 2) if t_has_data else None,
            "fundamental": round(f_score, 2) if f_has_data else None,
            "sentiment":   round(s_score, 2) if s_has_data else None,
            "missing_engines": missing_engines,
            "technical_source": t_used_field,
            # v4: raw sub-scores so we can backtest without re-running
            "trend_score":     tech_data.get("trend_score"),
            "reversion_score": tech_data.get("reversion_score"),
            "adx":             tech_data.get("adx"),
        }
    }