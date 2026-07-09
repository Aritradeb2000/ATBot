"""
ATBot — Portfolio Allocation Optimizer Engine

Takes a capital amount + stock universe and returns an optimal
score-weighted allocation plan across the best qualifying stocks.

Algorithm:
  1. Run full 3-engine analysis on all symbols in parallel batches
  2. Filter by signal quality + confidence + R:R threshold (per risk profile)
  3. Rank by composite_score × confidence × risk_reward
  4. Score-weighted capital allocation with hard per-position caps
  5. Adjust quantity so each position's SL risk ≤ 3% of total capital
  6. Return structured allocation plan with portfolio-level summary
"""

import asyncio
import logging
from typing import Optional

from backend.config import NIFTY50_SYMBOLS
from backend.data.market_data import fetch_ohlcv
from backend.data.fundamentals import fetch_fundamentals_yfinance
from backend.data.news_feed import fetch_finnhub_news
from backend.data.nse_live import get_fii_dii_data
from backend.data.scheduler import get_cache
from backend.engines.technical_engine import analyze_technical
from backend.engines.fundamental_engine import analyze_fundamental
from backend.engines.sentiment_engine import analyze_sentiment
from backend.engines.ensemble_scorer import calculate_composite

logger = logging.getLogger(__name__)

BATCH_SIZE = 5  # parallel yfinance calls per batch
MAX_SL_RISK_PCT = 0.03  # max 3% of total investment at risk per position
MIN_ALLOCATION = 5000   # minimum ₹5,000 per position (avoids noise)

# Risk profile configuration
RISK_PROFILES = {
    "conservative": {
        "max_pct_per_stock": 0.15,
        "allowed_signals":   {"STRONG BUY"},
        "min_rr":            2.0,
        "min_confidence":    70.0,
    },
    "moderate": {
        "max_pct_per_stock": 0.25,
        "allowed_signals":   {"STRONG BUY", "BUY"},
        "min_rr":            1.5,
        "min_confidence":    60.0,
    },
    "aggressive": {
        "max_pct_per_stock": 0.35,
        "allowed_signals":   {"STRONG BUY", "BUY", "HOLD"},
        "min_rr":            1.0,
        "min_confidence":    40.0,
    },
}


async def _analyze_one_for_optimizer(symbol: str, cache: dict) -> Optional[dict]:
    """
    Run full 3-engine analysis for a single symbol.
    Returns a rich dict including targets, stop_loss, and risk_reward.
    Returns None on failure.
    """
    try:
        indices          = cache.get("indices") or {}
        nifty_data       = indices.get("NIFTY50") or {}
        nifty_change     = nifty_data.get("change_pct", 0.0)
        nifty_change_20d = nifty_data.get("change_pct_20d", 0.0)
        vix_data         = cache.get("india_vix") or {}
        vix              = vix_data.get("vix", 14.0)
        fii_dii          = cache.get("fii_dii") or get_fii_dii_data()

        loop = asyncio.get_event_loop()

        ohlcv_df = await loop.run_in_executor(None, lambda: fetch_ohlcv(symbol, interval="1d", period="6mo"))
        if ohlcv_df is None or ohlcv_df.empty:
            return None

        fundamentals = await loop.run_in_executor(None, lambda: fetch_fundamentals_yfinance(symbol))
        news         = await loop.run_in_executor(None, lambda: fetch_finnhub_news(symbol))

        tech_result  = analyze_technical(ohlcv_df)
        fund_result  = analyze_fundamental(fundamentals)
        sent_result  = analyze_sentiment(news, fii_dii)

        final = calculate_composite(
            tech_data=tech_result,
            fund_data=fund_result,
            sent_data=sent_result,
            nifty_change=nifty_change,
            nifty_change_20d=nifty_change_20d,
            vix=vix,
        )

        price      = tech_result.get("close")
        stop_loss  = final.get("stop_loss")
        targets    = final.get("targets") or {}
        target_base = targets.get("base")
        rr_ratio   = final.get("risk_reward")

        if price is None or price <= 0:
            return None

        return {
            "symbol":       symbol,
            "company_name": (fundamentals or {}).get("company_name", symbol),
            "price":        price,
            "score":        final["composite_score"],
            "signal":       final["signal"],
            "confidence":   final["confidence"],
            "regime":       final["regime"],
            "stop_loss":    stop_loss,
            "target_base":  target_base,
            "rr_ratio":     rr_ratio,
            "components":   final["components"],
        }

    except Exception as e:
        logger.warning(f"Optimizer: skipping {symbol} — {e}")
        return None


async def _scan_universe(symbols: list[str], cache: dict) -> list[dict]:
    """Scan all symbols in parallel batches."""
    results = []
    for i in range(0, len(symbols), BATCH_SIZE):
        batch = symbols[i: i + BATCH_SIZE]
        batch_results = await asyncio.gather(*[_analyze_one_for_optimizer(s, cache) for s in batch])
        results.extend([r for r in batch_results if r is not None])
        logger.info(f"Optimizer scan: {min(i + BATCH_SIZE, len(symbols))}/{len(symbols)} processed")
    return results


def _filter_and_rank(
    candidates: list[dict],
    profile: dict,
    min_rr_override: Optional[float],
) -> list[dict]:
    """Apply risk-profile filters and rank by composite power score."""
    min_rr       = min_rr_override if min_rr_override is not None else profile["min_rr"]
    allowed_sigs = profile["allowed_signals"]
    min_conf     = profile["min_confidence"]

    qualified = []
    for c in candidates:
        if c["signal"] not in allowed_sigs:
            continue
        if c["confidence"] < min_conf:
            continue
        rr = c.get("rr_ratio")
        if rr is not None and rr < min_rr:
            continue
        # Power score: drives allocation weight
        c["power_score"] = (
            c["score"] *
            (c["confidence"] / 100.0) *
            (max(rr, 0.1) if rr else 1.0)
        )
        qualified.append(c)

    qualified.sort(key=lambda x: -x["power_score"])
    return qualified


def _allocate_capital(
    ranked: list[dict],
    total_amount: float,
    max_stocks: int,
    profile: dict,
) -> list[dict]:
    """
    Distribute capital across top-N stocks using score-weighted proportional allocation.
    Enforces per-position caps and SL risk cap.
    """
    top = ranked[:max_stocks]
    if not top:
        return []

    total_power = sum(c["power_score"] for c in top)
    max_pct     = profile["max_pct_per_stock"]

    allocations = []
    for stock in top:
        # Proportional weight, capped at max_pct_per_stock
        raw_weight   = stock["power_score"] / total_power
        capped_weight = min(raw_weight, max_pct)
        raw_allocation = total_amount * capped_weight

        if raw_allocation < MIN_ALLOCATION:
            continue  # skip if too small

        price     = stock["price"]
        stop_loss = stock.get("stop_loss")
        target    = stock.get("target_base")

        # Calculate SL risk per share
        if stop_loss and stop_loss > 0 and stop_loss < price:
            sl_risk_per_share = price - stop_loss
        else:
            sl_risk_per_share = price * 0.05  # fallback: assume 5% SL

        # Maximum quantity allowed by 3% portfolio risk cap
        max_risk_amount = total_amount * MAX_SL_RISK_PCT
        max_qty_by_risk = int(max_risk_amount / sl_risk_per_share) if sl_risk_per_share > 0 else 9999

        # Quantity from allocation budget
        qty_from_budget = int(raw_allocation / price)
        qty = min(qty_from_budget, max_qty_by_risk)
        qty = max(qty, 1)  # at least 1 share

        if qty < 1:
            continue

        invested      = round(qty * price, 2)
        sl_amount     = round(qty * sl_risk_per_share, 2)
        target_amount = round(qty * (target - price), 2) if target and target > price else None
        gain_pct      = round(((target - price) / price) * 100, 2) if target and target > price else None
        rr            = stock.get("rr_ratio")

        allocations.append({
            "symbol":       stock["symbol"],
            "company_name": stock["company_name"],
            "qty":          qty,
            "price":        round(price, 2),
            "invested":     invested,
            "stop_loss":    round(stop_loss, 2) if stop_loss else None,
            "sl_risk":      sl_amount,
            "target_base":  round(target, 2) if target else None,
            "gain_amount":  target_amount,
            "gain_pct":     gain_pct,
            "rr_ratio":     round(rr, 2) if rr else None,
            "score":        round(stock["score"], 1),
            "confidence":   round(stock["confidence"], 1),
            "signal":       stock["signal"],
            "components":   stock["components"],
        })

    return allocations


async def run_optimizer(
    amount: float,
    universe: str = "nifty50",
    symbols: Optional[list[str]] = None,
    risk_profile: str = "moderate",
    max_stocks: int = 5,
    min_rr: Optional[float] = None,
    watchlist_symbols: Optional[list[str]] = None,
) -> dict:
    """
    Main optimizer entry point.
    Returns a full allocation plan dict.
    """
    profile = RISK_PROFILES.get(risk_profile, RISK_PROFILES["moderate"])
    cache   = get_cache()

    # Resolve symbol universe
    if universe == "nifty50":
        scan_symbols = NIFTY50_SYMBOLS
    elif universe == "watchlist" and watchlist_symbols:
        scan_symbols = watchlist_symbols
    elif universe == "custom" and symbols:
        scan_symbols = [s.upper() for s in symbols]
    else:
        scan_symbols = NIFTY50_SYMBOLS

    logger.info(f"🔎 Optimizer: scanning {len(scan_symbols)} stocks | profile={risk_profile} | amount=₹{amount:,.0f}")

    # Scan universe
    candidates = await _scan_universe(scan_symbols, cache)

    # Filter + rank
    ranked = _filter_and_rank(candidates, profile, min_rr)

    if len(ranked) < 2:
        return {
            "status":            "insufficient_signals",
            "message":           f"Only {len(ranked)} qualifying stock(s) found. Try Aggressive profile or a broader universe.",
            "total_investment":  amount,
            "deployed":          0,
            "remaining_cash":    amount,
            "expected_gain":     0,
            "expected_gain_pct": 0,
            "max_portfolio_risk":    0,
            "max_portfolio_risk_pct": 0,
            "allocations":       [],
            "scanned":           len(candidates),
            "qualified":         len(ranked),
        }

    # Allocate capital
    allocations = _allocate_capital(ranked, amount, max_stocks, profile)

    # Portfolio summary
    deployed         = sum(a["invested"] for a in allocations)
    remaining_cash   = round(amount - deployed, 2)
    expected_gain    = sum(a["gain_amount"] for a in allocations if a["gain_amount"])
    max_risk         = sum(a["sl_risk"] for a in allocations)
    expected_gain_pct = round((expected_gain / amount) * 100, 2) if amount > 0 else 0
    max_risk_pct      = round((max_risk / amount) * 100, 2) if amount > 0 else 0

    return {
        "status":                "ok",
        "total_investment":      amount,
        "deployed":              round(deployed, 2),
        "remaining_cash":        remaining_cash,
        "expected_gain":         round(expected_gain, 2),
        "expected_gain_pct":     expected_gain_pct,
        "max_portfolio_risk":    round(max_risk, 2),
        "max_portfolio_risk_pct": max_risk_pct,
        "risk_profile":          risk_profile,
        "universe":              universe,
        "scanned":               len(candidates),
        "qualified":             len(ranked),
        "allocations":           allocations,
    }
