"""
ATBot — Market Data Fetcher
Fetches OHLCV data from Yahoo Finance for NSE/BSE stocks
Handles caching, market hours, circuit breakers and holidays
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, date, timedelta
from typing import Optional
import logging
import pytz

from backend.config import settings, IST, INDEX_TICKERS, GLOBAL_CUES

logger = logging.getLogger(__name__)


# ── Market Hours Helpers ──────────────────────────────────────────────────

def is_market_open() -> bool:
    """Check if NSE is currently open for trading."""
    now = datetime.now(IST)
    # Skip weekends
    if now.weekday() >= 5:
        return False
    market_open = now.replace(
        hour=settings.market_open_hour,
        minute=settings.market_open_minute,
        second=0, microsecond=0
    )
    market_close = now.replace(
        hour=settings.market_close_hour,
        minute=settings.market_close_minute,
        second=0, microsecond=0
    )
    return market_open <= now <= market_close


def get_trading_days_back(n: int) -> date:
    """Return the date n trading days ago (skips weekends)."""
    d = date.today()
    count = 0
    while count < n:
        d -= timedelta(days=1)
        if d.weekday() < 5:  # Mon–Fri
            count += 1
    return d


# ── OHLCV Fetcher ─────────────────────────────────────────────────────────

def fetch_ohlcv(
    symbol: str,
    interval: str = "1d",
    period: str = "6mo"
) -> Optional[pd.DataFrame]:
    """
    Fetch OHLCV data for a symbol from Yahoo Finance.

    Args:
        symbol: NSE ticker e.g. "RELIANCE.NS" or "TCS.NS"
        interval: "1d", "1h", "15m", "5m"
        period: "1mo", "3mo", "6mo", "1y", "2y"

    Returns:
        DataFrame with columns: Open, High, Low, Close, Volume
        or None if fetch fails.
    """
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval, auto_adjust=True)

        if df.empty:
            logger.warning(f"No data returned for {symbol}")
            return None

        # Clean up columns
        df = df[["Open", "High", "Low", "Close", "Volume"]]
        df.index = pd.to_datetime(df.index)

        # Convert index to IST for NSE stocks
        if df.index.tz is not None:
            df.index = df.index.tz_convert(IST)
        else:
            df.index = df.index.tz_localize(IST)

        # Drop rows with all-zero OHLCV (bad data)
        df = df[(df["Close"] > 0) & (df["Volume"] > 0)]

        logger.info(f"✅ Fetched {len(df)} bars for {symbol} [{interval}]")
        return df

    except Exception as e:
        logger.error(f"❌ Failed to fetch OHLCV for {symbol}: {e}")
        return None


def fetch_multiple_ohlcv(
    symbols: list[str],
    interval: str = "1d",
    period: str = "6mo"
) -> dict[str, pd.DataFrame]:
    """
    Batch fetch OHLCV for multiple symbols efficiently.
    Uses yfinance's bulk download for speed.
    """
    results = {}
    try:
        raw = yf.download(
            tickers=symbols,
            period=period,
            interval=interval,
            auto_adjust=True,
            progress=False,
            group_by="ticker"
        )

        for symbol in symbols:
            try:
                if len(symbols) == 1:
                    df = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
                else:
                    df = raw[symbol][["Open", "High", "Low", "Close", "Volume"]].copy()

                df = df.dropna()
                df = df[(df["Close"] > 0)]
                if not df.empty:
                    results[symbol] = df
            except Exception as e:
                logger.warning(f"Could not extract data for {symbol}: {e}")

    except Exception as e:
        logger.error(f"Batch download failed: {e}")
        # Fallback: fetch individually
        for symbol in symbols:
            df = fetch_ohlcv(symbol, interval, period)
            if df is not None:
                results[symbol] = df

    return results


# ── Circuit Breaker Detection ─────────────────────────────────────────────

def detect_circuit_breaker(df: pd.DataFrame) -> Optional[str]:
    """
    Detect if the latest candle hit a circuit breaker.
    NSE limits: 5%, 10%, 20% from previous close.

    Returns: "UPPER_5", "UPPER_10", "UPPER_20",
             "LOWER_5", "LOWER_10", "LOWER_20", or None
    """
    if len(df) < 2:
        return None

    prev_close = df["Close"].iloc[-2]
    curr_close = df["Close"].iloc[-1]
    pct_change = ((curr_close - prev_close) / prev_close) * 100

    if pct_change >= 20:
        return "UPPER_20"
    elif pct_change >= 10:
        return "UPPER_10"
    elif pct_change >= 5:
        return "UPPER_5"
    elif pct_change <= -20:
        return "LOWER_20"
    elif pct_change <= -10:
        return "LOWER_10"
    elif pct_change <= -5:
        return "LOWER_5"
    return None


# ── Index & Global Cues ───────────────────────────────────────────────────

def fetch_index_data() -> dict:
    """Fetch Nifty 50, Sensex, India VIX current levels."""
    result = {}
    for name, ticker in INDEX_TICKERS.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="25d", interval="1d")
            if not hist.empty:
                latest = hist.iloc[-1]
                prev = hist.iloc[-2] if len(hist) > 1 else latest
                pct_change = ((latest["Close"] - prev["Close"]) / prev["Close"]) * 100
                # 20-day trailing change for regime detection
                base = hist.iloc[0] if len(hist) >= 20 else prev
                pct_change_20d = ((latest["Close"] - base["Close"]) / base["Close"]) * 100
                result[name] = {
                    "price": round(latest["Close"], 2),
                    "change_pct": round(pct_change, 2),
                    "change_pct_20d": round(pct_change_20d, 2),
                    "high": round(latest["High"], 2),
                    "low": round(latest["Low"], 2),
                }
        except Exception as e:
            logger.warning(f"Could not fetch index {name}: {e}")
    return result


def fetch_global_cues() -> dict:
    """Fetch global market cues for morning briefing."""
    result = {}
    for name, ticker in GLOBAL_CUES.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="2d", interval="1d")
            if not hist.empty:
                latest = hist.iloc[-1]
                prev = hist.iloc[-2] if len(hist) > 1 else latest
                pct_change = ((latest["Close"] - prev["Close"]) / prev["Close"]) * 100
                result[name] = {
                    "price": round(latest["Close"], 2),
                    "change_pct": round(pct_change, 2),
                }
        except Exception as e:
            logger.warning(f"Could not fetch global cue {name}: {e}")
    return result


# ── Quick Quote ───────────────────────────────────────────────────────────

def get_current_price(symbol: str) -> Optional[float]:
    """Get the latest closing price for a symbol."""
    try:
        t = yf.Ticker(symbol)
        hist = t.history(period="1d", interval="1m")
        if not hist.empty:
            return round(hist["Close"].iloc[-1], 2)
    except Exception as e:
        logger.error(f"Could not get price for {symbol}: {e}")
    return None


def get_52w_high_low(symbol: str) -> dict:
    """Get 52-week high and low for a symbol."""
    try:
        df = fetch_ohlcv(symbol, interval="1d", period="1y")
        if df is not None and not df.empty:
            return {
                "high_52w": round(df["High"].max(), 2),
                "low_52w": round(df["Low"].min(), 2),
                "current": round(df["Close"].iloc[-1], 2),
            }
    except Exception as e:
        logger.error(f"52W H/L failed for {symbol}: {e}")
    return {}
