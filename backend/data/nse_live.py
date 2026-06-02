"""
ATBot — NSE Live Data Fetcher
Fetches live quotes, FII/DII flow, and market breadth from NSE
Uses nsepython for live NSE data
"""

import requests
import pandas as pd
from datetime import datetime, date
from typing import Optional
import logging

from backend.config import IST

logger = logging.getLogger(__name__)

# NSE base URL for direct API calls (fallback when nsepython fails)
NSE_BASE = "https://www.nseindia.com"
NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


# ── NSE Session (handles cookies) ────────────────────────────────────────

class NSESession:
    """Maintains a persistent session with NSE to handle cookie auth."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(NSE_HEADERS)
        self._init_session()

    def _init_session(self):
        """Visit NSE homepage to get session cookies."""
        try:
            self.session.get(NSE_BASE, timeout=10)
        except Exception as e:
            logger.warning(f"NSE session init failed: {e}")

    def get(self, url: str, params: dict = None) -> Optional[dict]:
        """Make a GET request to NSE API."""
        try:
            resp = self.session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            if resp.status_code == 401:
                # Session expired — reinit
                logger.info("NSE session expired, reinitializing...")
                self._init_session()
            logger.error(f"NSE API error: {e}")
        except Exception as e:
            logger.error(f"NSE request failed: {e}")
        return None


# Singleton session
_nse_session = NSESession()


# ── Live Quote ────────────────────────────────────────────────────────────

def get_live_quote(symbol: str) -> Optional[dict]:
    """
    Get live quote for an NSE symbol.
    symbol: plain NSE symbol e.g. "RELIANCE" (no .NS suffix)

    Returns dict with: lastPrice, change, pChange, open, high, low,
                       previousClose, volume, deliveryVolume, deliveryPct
    """
    try:
        url = f"{NSE_BASE}/api/quote-equity"
        data = _nse_session.get(url, params={"symbol": symbol.upper()})

        if not data:
            return None

        price_info = data.get("priceInfo", {})
        trade_info = data.get("tradeInfo", {})

        return {
            "symbol": symbol.upper(),
            "last_price": price_info.get("lastPrice"),
            "open": price_info.get("open"),
            "high": price_info.get("intraDayHighLow", {}).get("max"),
            "low": price_info.get("intraDayHighLow", {}).get("min"),
            "prev_close": price_info.get("previousClose"),
            "change": price_info.get("change"),
            "change_pct": price_info.get("pChange"),
            "volume": trade_info.get("totalTradedVolume"),
            "total_traded_value": trade_info.get("totalTradedValue"),
            "52w_high": price_info.get("weekHighLow", {}).get("max"),
            "52w_low": price_info.get("weekHighLow", {}).get("min"),
            "timestamp": datetime.now(IST).isoformat(),
        }

    except Exception as e:
        logger.error(f"Live quote failed for {symbol}: {e}")
        return None


def get_delivery_data(symbol: str) -> Optional[dict]:
    """
    Get delivery volume percentage for a symbol.
    High delivery % (>50%) = strong conviction buying signal.
    """
    try:
        url = f"{NSE_BASE}/api/quote-equity"
        data = _nse_session.get(url, params={"symbol": symbol.upper(), "section": "trade_info"})

        if not data:
            return None

        trade_info = data.get("marketDeptOrderBook", {}).get("tradeInfo", {})
        return {
            "symbol": symbol.upper(),
            "delivery_quantity": trade_info.get("deliveryQuantity"),
            "delivery_pct": trade_info.get("deliveryToTradedQuantity"),
        }
    except Exception as e:
        logger.error(f"Delivery data failed for {symbol}: {e}")
        return None


# ── Market Breadth ────────────────────────────────────────────────────────

def get_market_breadth() -> Optional[dict]:
    """
    Get NSE market breadth: advances, declines, unchanged.
    A key market health indicator.
    """
    try:
        url = f"{NSE_BASE}/api/market-status"
        data = _nse_session.get(url)

        if not data:
            return None

        # Also fetch advance/decline from equity market
        url2 = f"{NSE_BASE}/api/allIndices"
        indices_data = _nse_session.get(url2)

        breadth = {
            "timestamp": datetime.now(IST).isoformat(),
            "market_status": data.get("marketState", [{}])[0].get("marketStatus", "Unknown"),
        }

        if indices_data:
            for item in indices_data.get("data", []):
                if item.get("index") == "NIFTY 50":
                    breadth["nifty_advances"] = item.get("advances", 0)
                    breadth["nifty_declines"] = item.get("declines", 0)
                    breadth["nifty_unchanged"] = item.get("unchanged", 0)
                    break

        return breadth

    except Exception as e:
        logger.error(f"Market breadth failed: {e}")
        return None


# ── FII / DII Flow ────────────────────────────────────────────────────────

def get_fii_dii_data() -> Optional[dict]:
    """
    Fetch FII and DII provisional trading data from NSE.
    Published daily after market close (~5:30–6 PM IST).

    Returns net buy/sell figures in ₹ crores.
    """
    try:
        url = f"{NSE_BASE}/api/fiidiiTradeReact"
        data = _nse_session.get(url)

        if not data or not isinstance(data, list):
            return None

        # Latest entry is today's data
        latest = data[0] if data else {}

        fii_buy = _parse_crore(latest.get("fiiBuy", "0"))
        fii_sell = _parse_crore(latest.get("fiiSell", "0"))
        dii_buy = _parse_crore(latest.get("diiBuy", "0"))
        dii_sell = _parse_crore(latest.get("diiSell", "0"))

        return {
            "date": latest.get("date", date.today().strftime("%d-%b-%Y")),
            "fii_buy": fii_buy,
            "fii_sell": fii_sell,
            "fii_net": round(fii_buy - fii_sell, 2),
            "dii_buy": dii_buy,
            "dii_sell": dii_sell,
            "dii_net": round(dii_buy - dii_sell, 2),
            "fii_sentiment": "BULLISH" if fii_buy > fii_sell else "BEARISH",
            "dii_sentiment": "BULLISH" if dii_buy > dii_sell else "BEARISH",
        }

    except Exception as e:
        logger.error(f"FII/DII data fetch failed: {e}")
        return None


def get_fii_dii_history(days: int = 30) -> list[dict]:
    """Get FII/DII data for last N days."""
    try:
        url = f"{NSE_BASE}/api/fiidiiTradeReact"
        data = _nse_session.get(url)

        if not data or not isinstance(data, list):
            return []

        result = []
        for entry in data[:days]:
            fii_buy = _parse_crore(entry.get("fiiBuy", "0"))
            fii_sell = _parse_crore(entry.get("fiiSell", "0"))
            dii_buy = _parse_crore(entry.get("diiBuy", "0"))
            dii_sell = _parse_crore(entry.get("diiSell", "0"))

            result.append({
                "date": entry.get("date"),
                "fii_net": round(fii_buy - fii_sell, 2),
                "dii_net": round(dii_buy - dii_sell, 2),
            })

        return result

    except Exception as e:
        logger.error(f"FII/DII history failed: {e}")
        return []


# ── India VIX ─────────────────────────────────────────────────────────────

def get_india_vix() -> Optional[dict]:
    """
    Get India VIX current level and risk assessment.
    VIX < 15: Low volatility (good for trades)
    VIX 15–20: Moderate (caution)
    VIX > 20: High (avoid new positions)
    """
    try:
        import yfinance as yf
        vix = yf.Ticker("^INDIAVIX")
        hist = vix.history(period="5d", interval="1d")

        if hist.empty:
            return None

        current = round(hist["Close"].iloc[-1], 2)
        prev = round(hist["Close"].iloc[-2], 2) if len(hist) > 1 else current
        change = round(current - prev, 2)

        if current < 15:
            risk_label = "LOW"
            risk_comment = f"VIX at {current} — Low volatility. Favorable conditions for swing trades."
        elif current < 20:
            risk_label = "MODERATE"
            risk_comment = f"VIX at {current} — Moderate volatility. Trade with caution, use tighter stops."
        else:
            risk_label = "HIGH"
            risk_comment = f"VIX at {current} — High volatility. Avoid new positions, protect existing ones."

        return {
            "vix": current,
            "prev_vix": prev,
            "change": change,
            "risk_label": risk_label,
            "risk_comment": risk_comment,
        }

    except Exception as e:
        logger.error(f"India VIX fetch failed: {e}")
        return None


# ── Utilities ─────────────────────────────────────────────────────────────

def _parse_crore(value: str) -> float:
    """Parse NSE's crore value string to float."""
    try:
        return float(str(value).replace(",", "").strip())
    except (ValueError, AttributeError):
        return 0.0


def nse_to_yfinance(symbol: str) -> str:
    """Convert plain NSE symbol to yfinance format. e.g. RELIANCE → RELIANCE.NS"""
    if not symbol.endswith((".NS", ".BO")):
        return f"{symbol}.NS"
    return symbol


def yfinance_to_nse(symbol: str) -> str:
    """Convert yfinance symbol to plain NSE symbol. e.g. RELIANCE.NS → RELIANCE"""
    return symbol.replace(".NS", "").replace(".BO", "")
