"""
ATBot — Ensemble Scorer
Combines Technical, Fundamental, and Sentiment scores using dynamic weighting
(Market Regime aware + Meta-Learner adaptive) to output a final 0-100 Composite Score and Trade Signal.
Generates Price Targets & Stop Loss.
"""

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


def determine_market_regime(
    nifty_change: float,             # reserved: 1-day momentum — not used in scoring yet
    vix: float,
    nifty_change_20d: float = 0.0,
    advances_pct: float = 0.5,
    fii_net_5d: float = 0.0,
) -> str:
    """
    Determine market regime using a multi-factor point system.
    Trend is the primary gate: the market cannot be called BULL/BEAR unless
    the 20-day trend supports that direction. Confirming factors (VIX, breadth, FII)
    only adjust magnitude within an eligible trend.
    """
    score = 0.0
    trend_score = 0.0

    # Factor 1: 20-day trend (±2 points)
    # Using >= to avoid boundary ambiguity at exactly 4.0%
    if nifty_change_20d >= 4.0:
        trend_score = 2.0
    elif nifty_change_20d >= 1.5:
        trend_score = 1.0
    elif nifty_change_20d <= -5.0:    # clear downtrend = BEAR alone
        trend_score = -2.0
    elif nifty_change_20d <= -2.5:    # mild downtrend = needs confirming
        trend_score = -1.0

    score += trend_score

    # Factor 2: VIX — ASYMMETRIC
    # Low VIX only rewards uptrends. Calm selloffs are still selloffs.
    if vix < 14.0 and nifty_change_20d >= 0:
        score += 1.0
    elif vix > 20.0:
        score -= 1.0
    elif vix > 17.0:
        score -= 0.5

    # Factor 3: Breadth
    # Asymmetric thresholds: making it harder to earn a BULL point (>0.65)
    # than a BEAR point (<0.40) to combat the BULL over-expansion issue.
    if advances_pct > 0.65:
        score += 1.0
    elif advances_pct < 0.40:
        score -= 1.0

    # Factor 4: FII 5-day cumulative
    if fii_net_5d > 3000:
        score += 1.0
    elif fii_net_5d < -3000:
        score -= 1.0

    # Gate: The final call MUST be supported by the trend.
    # Non-trend factors alone cannot force a BULL/BEAR regime.
    if score >= 2.5 and trend_score > 0:
        return "BULL"
    elif score <= -2.0 and trend_score < 0:
        return "BEAR"

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
    nifty_change: float = 0.0,       # reserved: 1-day momentum, not yet used by regime logic
    nifty_change_20d: float = 0.0,
    vix: float = 14.0,
    user_capital: float = None,
    advances_pct: float = 0.5,
    fii_net_5d: float = 0.0,
    regime: Optional[str] = None,    # pass pre-computed regime to skip per-stock recomputation
) -> dict:
    """
    Calculates final composite score and signal.
    tech_data, fund_data, sent_data are outputs from their respective engines.
    Pass `regime` to avoid recomputing it for every stock in a batch.
    """
    # ── Track which engines actually returned data ─────────────────────────────
    # Default of 50 for missing engines would collapse variance → false confidence.
    t_has_data = tech_data.get("score") is not None
    f_has_data = fund_data.get("score") is not None
    s_has_data = sent_data.get("score") is not None
    missing_engines = sum(1 for x in (t_has_data, f_has_data, s_has_data) if not x)

    t_score = tech_data.get("score", 50)
    f_score = fund_data.get("score", 50)
    s_score = sent_data.get("score", 50)

    # ── Regime (compute once per batch when possible) ──────────────────────────
    if regime is None:
        regime = determine_market_regime(
            nifty_change=nifty_change,
            vix=vix,
            nifty_change_20d=nifty_change_20d,
            advances_pct=advances_pct,
            fii_net_5d=fii_net_5d,
        )

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
            weights = _static_regime_weights(regime)
    else:
        weights = _static_regime_weights(regime)

    # ── Normalize weights to guard against meta-learner drift ─────────────────
    total_w = weights["T"] + weights["F"] + weights["S"]
    if abs(total_w - 1.0) > 0.01:
        logger.warning(f"[Ensemble] Weights sum to {total_w:.3f}, normalizing")
        weights = {k: v / total_w for k, v in weights.items()}

    # ── Composite Score — renormalize weights over engines that returned data ──
    # Dropping missing engines and redistributing their weight prevents phantom
    # 50s from dragging real signals toward the middle.
    engine_weights = {
        "T": weights["T"] if t_has_data else 0.0,
        "F": weights["F"] if f_has_data else 0.0,
        "S": weights["S"] if s_has_data else 0.0,
    }
    active_weight_sum = engine_weights["T"] + engine_weights["F"] + engine_weights["S"]
    if active_weight_sum > 0.0:
        # Renormalize so the available engines carry full weight
        engine_weights = {k: v / active_weight_sum for k, v in engine_weights.items()}
    else:
        # All engines missing — fall back to defaults (confidence will be 20)
        engine_weights = weights

    comp_score = (t_score * engine_weights["T"]) + (f_score * engine_weights["F"]) + (s_score * engine_weights["S"])
    comp_score = round(comp_score, 2)

    # -- Signal Thresholds -- regime-aware -------------------------------------------
    # BEAR:     +10 offset -- fewer false BUYs in confirmed downtrends
    # SIDEWAYS: +5  offset -- reduce marginal signals; data shows 60-65 band has
    #                         flat 27.2% win rate, barely below the 65-70 band (28.5%)
    # BULL:      0  offset -- standard thresholds
    regime_offset = {"BEAR": 10, "SIDEWAYS": 5, "BULL": 0}.get(regime, 0)

    if comp_score >= (75 + regime_offset):
        signal = "STRONG BUY"
    elif comp_score >= (60 + regime_offset):
        signal = "BUY"
    elif comp_score >= 45:
        signal = "HOLD"
    elif comp_score >= 30:
        signal = "SELL"
    else:
        signal = "STRONG SELL"

    # ── Confidence — exclude missing engines from variance calc ───────────────
    active_scores = [s for s, has in [(t_score, t_has_data), (f_score, f_has_data), (s_score, s_has_data)] if has]

    if len(active_scores) >= 2:
        pairs = [(active_scores[i], active_scores[j])
                 for i in range(len(active_scores))
                 for j in range(i + 1, len(active_scores))]
        max_diff = max(abs(a - b) for a, b in pairs)
        confidence = max(0, min(100, 100 - max_diff))
        # Penalize missing data — cap confidence proportionally
        if missing_engines > 0:
            confidence = min(confidence, 100 - (missing_engines * 25))
    elif len(active_scores) == 1:
        confidence = 30   # single engine, no cross-check possible
    else:
        confidence = 20   # all engines missing

    # ── Conviction-scaled Targets & Stop Loss ─────────────────────────────────
    targets = None
    targets_5d  = None
    targets_10d = None
    targets_50d  = None
    targets_100d = None
    stop_loss = None
    rr_ratio = None

    current_price = tech_data.get("close")
    atr = tech_data.get("atr")

    if current_price and atr and signal in ["BUY", "STRONG BUY"]:
        # Conviction multiplier: scales how far targets stretch with score.
        # Score 60 → 1.0x  |  Score 75 → 1.225x  |  Score 92 → 1.48x (cap 1.6x)
        conviction_mult = min(1.6, 1.0 + (max(0, comp_score - 60) * 0.015))

        # Regime adjustment: in BEAR tighten stop (get out fast if wrong),
        # tighten targets (don't project far in a downtrend).
        regime_target_mult = {"BULL": 1.1, "SIDEWAYS": 1.0, "BEAR": 0.80}.get(regime, 1.0)
        regime_stop_mult   = {"BULL": 1.7, "SIDEWAYS": 1.5, "BEAR": 1.2}.get(regime, 1.5)

        # Effective multiplier for targets: conviction × regime
        # Effective multiplier for stop: regime only (conviction doesn't widen your risk)
        eff_target = conviction_mult * regime_target_mult

        stop_loss = round(current_price - (atr * regime_stop_mult), 2)

        # 5-day targets — tighter: stock has 5 sessions to move
        targets_5d = {
            "conservative": round(current_price + (atr * 0.75 * eff_target), 2),
            "base":         round(current_price + (atr * 1.25 * eff_target), 2),
            "aggressive":   round(current_price + (atr * 1.75 * eff_target), 2),
        }

        # 10-day targets — wider: two weeks for the thesis to play out
        targets_10d = {
            "conservative": round(current_price + (atr * 1.5 * eff_target), 2),
            "base":         round(current_price + (atr * 2.5 * eff_target), 2),
            "aggressive":   round(current_price + (atr * 3.5 * eff_target), 2),
        }

        # 50-day targets — long-term: ~2.5 months, fundamentals drive returns
        targets_50d = {
            "conservative": round(current_price + (atr * 4.0 * eff_target), 2),
            "base":         round(current_price + (atr * 6.0 * eff_target), 2),
            "aggressive":   round(current_price + (atr * 9.0 * eff_target), 2),
        }

        # 100-day targets — very long-term: ~5 months, deep value / sector thesis
        targets_100d = {
            "conservative": round(current_price + (atr * 6.0  * eff_target), 2),
            "base":         round(current_price + (atr * 9.0  * eff_target), 2),
            "aggressive":   round(current_price + (atr * 13.0 * eff_target), 2),
        }

        # Default `targets` = 5d for backward compat with screener / watchlist cards
        targets = targets_5d

        # RR: uses a convention 1.5×ATR base as the denominator (regime-neutral)
        # so that BULL (wider targets) shows higher RR than BEAR (narrower targets)
        # at equivalent conviction — not the inversion that happens when the
        # regime-tightened stop is in the denominator.
        # NOTE: this is still ATR-based; true per-stock RR would need resistance
        # levels or realized-move percentiles as the reward input.
        reward_rr = atr * 2.5 * eff_target   # conviction × regime target stretch
        risk_rr   = atr * 1.5                 # convention base, regime-neutral
        rr_ratio = round(reward_rr / risk_rr, 2) if risk_rr > 0 else 0

    # ── Position Sizing ────────────────────────────────────────────────────────
    position_sizing = None
    if user_capital and user_capital > 0 and signal in ["BUY", "STRONG BUY"] and stop_loss and current_price:
        # Regime scales down both risk% and max allocation in BEAR.
        # Without this, a tighter BEAR stop shrinks risk_per_share (the denominator)
        # and silently increases qty — exactly backwards from what a downtrend warrants.
        regime_risk_mult = {"BULL": 1.0, "SIDEWAYS": 0.85, "BEAR": 0.60}.get(regime, 0.85)
        regime_max_alloc = {"BULL": 0.20, "SIDEWAYS": 0.15, "BEAR": 0.10}.get(regime, 0.15)

        # Risk Model: 1%–2% of capital per trade scaled by confidence, then by regime
        risk_pct = (0.01 + 0.01 * (confidence / 100)) * regime_risk_mult
        capital_at_risk = user_capital * risk_pct
        risk_per_share = current_price - stop_loss

        if risk_per_share > 0:
            qty = int(capital_at_risk / risk_per_share)
            invested_amount = qty * current_price

            # Regime-specific max single-stock allocation
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
        "confidence": round(confidence, 1),
        "regime": regime,
        "targets":      targets,       # 5-day (default, for cards/screener)
        "targets_5d":   targets_5d   if targets_5d   else None,
        "targets_10d":  targets_10d  if targets_10d  else None,
        "targets_50d":  targets_50d  if targets_50d  else None,
        "targets_100d": targets_100d if targets_100d else None,
        "stop_loss": stop_loss,
        "risk_reward": rr_ratio,
        "position_sizing": position_sizing,
        "weights_used": weights,
        "weights_source": weights_source,
        "components": {
            "technical":   t_score,
            "fundamental": f_score,
            "sentiment":   s_score,
            "missing_engines": missing_engines,
        }
    }
