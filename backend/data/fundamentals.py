"""
ATBot — Fundamental Data Fetcher
Fetches financial ratios and metrics from yfinance + FMP API
Covers: P/E, EPS, ROE, Debt/Equity, Promoter Holding, Revenue Growth etc.
"""

import yfinance as yf
import requests
import pandas as pd
from typing import Optional
import logging

from backend.config import settings

logger = logging.getLogger(__name__)

FMP_BASE = "https://financialmodelingprep.com/api/v3"


# ── yfinance Fundamentals ─────────────────────────────────────────────────

def fetch_fundamentals_yfinance(symbol: str) -> Optional[dict]:
    """
    Fetch fundamental data from Yahoo Finance.
    symbol: NSE format e.g. "RELIANCE.NS"

    Returns a dict with all key financial metrics.
    """
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info

        if not info or info.get("regularMarketPrice") is None:
            logger.warning(f"No fundamental data for {symbol}")
            return None

        # ── Valuation ─────────────────────────────────
        pe_ratio = info.get("trailingPE") or info.get("forwardPE")
        pb_ratio = info.get("priceToBook")
        ev_ebitda = info.get("enterpriseToEbitda")
        market_cap = info.get("marketCap")

        # ── Profitability ──────────────────────────────
        roe = _to_pct(info.get("returnOnEquity"))
        profit_margin = _to_pct(info.get("profitMargins"))
        operating_margin = _to_pct(info.get("operatingMargins"))
        gross_margin = _to_pct(info.get("grossMargins"))

        # ── Growth ────────────────────────────────────
        revenue_growth = _to_pct(info.get("revenueGrowth"))
        earnings_growth = _to_pct(info.get("earningsGrowth"))
        eps_ttm = info.get("trailingEps")
        eps_forward = info.get("forwardEps")

        # ── Balance Sheet ─────────────────────────────
        debt_to_equity = info.get("debtToEquity")
        if debt_to_equity:
            debt_to_equity = round(debt_to_equity / 100, 2)   # yfinance returns as %
        current_ratio = info.get("currentRatio")

        # ── Dividends ─────────────────────────────────
        dividend_yield = _to_pct(info.get("dividendYield"))

        # ── Holdings (India-specific, limited in yfinance) ────
        # These will be supplemented by FMP if available
        held_percent_institutions = _to_pct(info.get("heldPercentInstitutions"))
        held_percent_insiders = _to_pct(info.get("heldPercentInsiders"))

        return {
            "symbol": symbol,
            "company_name": info.get("longName", ""),
            "sector": info.get("sector", ""),
            "industry": info.get("industry", ""),
            # Valuation
            "pe_ratio": _round(pe_ratio),
            "pb_ratio": _round(pb_ratio),
            "ev_ebitda": _round(ev_ebitda),
            "market_cap": market_cap,
            # Profitability
            "roe": roe,
            "profit_margin": profit_margin,
            "operating_margin": operating_margin,
            "gross_margin": gross_margin,
            # Growth
            "revenue_growth_yoy": revenue_growth,
            "eps_growth_yoy": earnings_growth,
            "eps_ttm": _round(eps_ttm),
            "eps_forward": _round(eps_forward),
            # Balance Sheet
            "debt_to_equity": _round(debt_to_equity),
            "current_ratio": _round(current_ratio),
            # Holdings
            "fii_holding": held_percent_institutions,
            "insider_holding": held_percent_insiders,
            # Dividends
            "dividend_yield": dividend_yield,
            # Current price context
            "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "52w_high": info.get("fiftyTwoWeekHigh"),
            "52w_low": info.get("fiftyTwoWeekLow"),
        }

    except Exception as e:
        logger.error(f"yfinance fundamental fetch failed for {symbol}: {e}")
        return None


# ── FMP Fundamentals (supplemental) ──────────────────────────────────────

def fetch_fundamentals_fmp(symbol: str) -> Optional[dict]:
    """
    Fetch additional financials from Financial Modeling Prep.
    symbol: plain symbol e.g. "RELIANCE" (FMP uses plain format for NSE)
    Free tier: 250 calls/day.

    Returns quarterly growth metrics and detailed ratios.
    """
    if not settings.fmp_api_key:
        return None

    try:
        # Use NSE symbol format for FMP (e.g., RELIANCE.NS)
        fmp_symbol = symbol if "." in symbol else f"{symbol}.NS"

        # Fetch key ratios
        url = f"{FMP_BASE}/ratios/{fmp_symbol}"
        resp = requests.get(url, params={"apikey": settings.fmp_api_key, "limit": 4}, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if not data or not isinstance(data, list):
            return None

        latest = data[0]
        prev = data[1] if len(data) > 1 else {}

        # Calculate QoQ revenue growth
        rev_growth_qoq = None
        if latest.get("revenuePerShare") and prev.get("revenuePerShare"):
            rev_growth_qoq = round(
                ((latest["revenuePerShare"] - prev["revenuePerShare"]) / abs(prev["revenuePerShare"])) * 100, 2
            )

        return {
            "roce": _round(latest.get("returnOnCapitalEmployed")),
            "revenue_growth_qoq": rev_growth_qoq,
            "interest_coverage": _round(latest.get("interestCoverage")),
            "price_to_fcf": _round(latest.get("priceToFreeCashFlowsRatio")),
        }

    except Exception as e:
        logger.warning(f"FMP fetch failed for {symbol}: {e}")
        return None


# ── Sector Comparison ─────────────────────────────────────────────────────

def get_sector_pe_median(sector: str, symbols: list[str]) -> Optional[float]:
    """
    Calculate median P/E for a sector from a list of symbols.
    Used to score a stock's P/E relative to its sector peers.
    """
    pe_ratios = []
    for symbol in symbols[:20]:  # Limit to 20 to avoid too many API calls
        try:
            t = yf.Ticker(symbol)
            pe = t.info.get("trailingPE")
            if pe and 0 < pe < 200:   # Filter out absurd P/E values
                pe_ratios.append(pe)
        except Exception:
            continue

    if pe_ratios:
        return round(float(pd.Series(pe_ratios).median()), 2)
    return None


# ── Earnings Calendar ─────────────────────────────────────────────────────

def get_upcoming_earnings(symbols: list[str]) -> list[dict]:
    """
    Check upcoming earnings dates for a list of symbols.
    Returns stocks with earnings in the next 7 days.
    """
    from datetime import date, timedelta
    upcoming = []
    today = date.today()
    week_from_now = today + timedelta(days=7)

    for symbol in symbols:
        try:
            t = yf.Ticker(symbol)
            cal = t.calendar
            if cal is not None and not cal.empty:
                earnings_date = cal.get("Earnings Date")
                if earnings_date is not None:
                    if isinstance(earnings_date, (list, pd.DatetimeIndex)):
                        earnings_date = earnings_date[0]
                    earnings_date = pd.Timestamp(earnings_date).date()
                    if today <= earnings_date <= week_from_now:
                        upcoming.append({
                            "symbol": symbol,
                            "earnings_date": earnings_date.isoformat(),
                            "days_away": (earnings_date - today).days,
                        })
        except Exception:
            continue

    return sorted(upcoming, key=lambda x: x["days_away"])


# ── Utilities ─────────────────────────────────────────────────────────────

def _to_pct(value) -> Optional[float]:
    """Convert decimal to percentage (0.15 → 15.0), handle None."""
    if value is None:
        return None
    try:
        return round(float(value) * 100, 2)
    except (TypeError, ValueError):
        return None


def _round(value, decimals: int = 2) -> Optional[float]:
    """Safe round with None handling."""
    if value is None:
        return None
    try:
        return round(float(value), decimals)
    except (TypeError, ValueError):
        return None
