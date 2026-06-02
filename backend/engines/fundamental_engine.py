"""
ATBot — Fundamental Analysis Engine
Scores the fundamental metrics fetched from yfinance/FMP
from 0 to 100.
"""

import logging

logger = logging.getLogger(__name__)

def analyze_fundamental(data: dict) -> dict:
    """
    Calculate fundamental score (0-100) based on India-adjusted criteria.
    Requires dictionary from data.fundamentals.fetch_fundamentals_yfinance.
    """
    if not data:
        return {"score": 50, "flags": ["No fundamental data available"]}

    score = 50.0
    flags = []

    # 1. P/E Ratio (15%) - Assuming Indian market median is around 25
    pe = data.get("pe_ratio")
    if pe is not None:
        if pe < 0:
            score -= 15  # Negative earnings
            flags.append("Negative Earnings (P/E < 0)")
        elif pe < 15:
            score += 15
            flags.append("Value stock (Low P/E)")
        elif pe < 25:
            score += 5
        elif pe > 40:
            score -= 10
            flags.append("Expensive valuation (P/E > 40)")
            
    # 2. EPS Growth YoY (20%)
    eps_growth = data.get("eps_growth_yoy")
    if eps_growth is not None:
        if eps_growth > 20:
            score += 20
            flags.append("Strong EPS Growth (>20%)")
        elif eps_growth > 10:
            score += 10
        elif eps_growth < 0:
            score -= 15
            flags.append("Negative EPS Growth")
            
    # 3. Revenue Growth (15%)
    rev_growth = data.get("revenue_growth_yoy")
    if rev_growth is not None:
        if rev_growth > 15:
            score += 15
            flags.append("Strong Revenue Growth (>15%)")
        elif rev_growth > 8:
            score += 5
        elif rev_growth < 0:
            score -= 10
            flags.append("Negative Revenue Growth")

    # 4. Debt / Equity (15%)
    de_ratio = data.get("debt_to_equity")
    if de_ratio is not None:
        if de_ratio < 0.5:
            score += 15
            flags.append("Low Debt (D/E < 0.5)")
        elif de_ratio < 1.0:
            score += 5
        elif de_ratio > 2.0:
            score -= 15
            flags.append("⚠️ High Debt Risk (D/E > 2.0)")

    # 5. ROE - Return on Equity (15%)
    roe = data.get("roe")
    if roe is not None:
        if roe > 20:
            score += 15
            flags.append("High Capital Efficiency (ROE > 20%)")
        elif roe > 15:
            score += 5
        elif roe < 8:
            score -= 10
            flags.append("Low ROE (< 8%)")

    # 6. Promoter Holding (10%)
    insider = data.get("insider_holding")
    if insider is not None:
        if insider > 50:
            score += 10
            flags.append("Strong Promoter Backing (>50%)")
        elif insider < 20:
            score -= 5
            flags.append("Low Promoter Holding (<20%)")

    # 7. Profit Margin (10%)
    margin = data.get("profit_margin")
    if margin is not None:
        if margin > 15:
            score += 10
            flags.append("High Profit Margin (>15%)")
        elif margin < 5:
            score -= 5
            flags.append("Low Profit Margin (<5%)")

    score = max(0.0, min(100.0, score))

    return {
        "score": round(score, 2),
        "flags": flags
    }
