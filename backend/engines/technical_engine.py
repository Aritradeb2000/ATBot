"""
ATBot — Technical Analysis Engine
Calculates technical indicators using pandas-ta and scores the stock
from 0 to 100 based on momentum, trend, and volume.
"""

import warnings
import pandas as pd
# pandas-ta prints "TA-Lib not available" to stderr on import — suppress it.
# ATBot uses pandas-ta's built-in pure-Python indicators; TA-Lib is optional and not needed.
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message=".*TA.Lib.*", category=UserWarning)
    warnings.filterwarnings("ignore", message=".*talib.*", category=UserWarning)
    import pandas_ta as ta
import logging

logger = logging.getLogger(__name__)

# Pattern scoring configuration
BULLISH_PATTERNS = ["CDL_ENGULFING", "CDL_MORNINGSTAR", "CDL_HAMMER", "CDL_PIERCING"]
BEARISH_PATTERNS = ["CDL_ENGULFING", "CDL_EVENINGSTAR", "CDL_SHOOTINGSTAR", "CDL_DARKCLOUDCOVER"]


def analyze_technical(df: pd.DataFrame) -> dict:
    """
    Perform technical analysis on an OHLCV DataFrame.
    Returns a dictionary with indicators and a technical score (0-100).
    """
    if df is None or len(df) < 50:
        logger.warning("Not enough data for technical analysis (need at least 50 periods).")
        return {"score": 0, "signals": ["Not enough data"]}

    try:
        # Calculate indicators
        # 1. RSI (Relative Strength Index)
        df["RSI_14"] = ta.rsi(df["Close"], length=14)
        
        # 2. MACD (Moving Average Convergence Divergence)
        macd = ta.macd(df["Close"], fast=12, slow=26, signal=9)
        df["MACD"] = macd["MACD_12_26_9"]
        df["MACD_signal"] = macd["MACDs_12_26_9"]
        df["MACD_hist"] = macd["MACDh_12_26_9"]
        
        # 3. EMAs
        df["EMA_9"] = ta.ema(df["Close"], length=9)
        df["EMA_21"] = ta.ema(df["Close"], length=21)
        df["EMA_50"] = ta.ema(df["Close"], length=50)
        df["EMA_200"] = ta.ema(df["Close"], length=200)
        
        # 4. Bollinger Bands
        bbands = ta.bbands(df["Close"], length=20, std=2)
        if bbands is not None and not bbands.empty:
            df["BB_lower"] = bbands.iloc[:, 0]
            df["BB_mid"] = bbands.iloc[:, 1]
            df["BB_upper"] = bbands.iloc[:, 2]
            df["BB_pct"] = bbands.iloc[:, 4]
        else:
            df["BB_lower"] = None
            df["BB_mid"] = None
            df["BB_upper"] = None
            df["BB_pct"] = None
        
        # 5. ATR (Average True Range)
        df["ATR_14"] = ta.atr(df["High"], df["Low"], df["Close"], length=14)
        
        # 6. Volume Average
        df["Volume_20SMA"] = ta.sma(df["Volume"], length=20)
        
        # 7. Supertrend (length=10, multiplier=3)
        st = ta.supertrend(df["High"], df["Low"], df["Close"], length=10, multiplier=3)
        if st is not None and not st.empty:
            df["Supertrend"] = st.iloc[:, 0]
            df["Supertrend_dir"] = st.iloc[:, 1]
        else:
            df["Supertrend"] = None
            df["Supertrend_dir"] = None

        # Run Candlestick patterns — requires TA-Lib (C extension, optional).
        # Suppress the "TA-Lib not available" warning; patterns contribute a small
        # bonus/penalty only — the engine scores correctly without them.
        cdl = None
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message=".*TA.Lib.*")
                warnings.filterwarnings("ignore", message=".*talib.*")
                warnings.filterwarnings("ignore", category=UserWarning)
                cdl = df.ta.cdl_pattern(name="all")
        except Exception:
            pass  # TA-Lib not installed — skip candlestick patterns silently
        if cdl is not None and not cdl.empty:
            df = pd.concat([df, cdl], axis=1)

        # Get latest data
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        score = 50.0  # Base neutral score
        signals = []
        
        # ── RSI Scoring (15% weight)
        rsi = latest["RSI_14"]
        if pd.notna(rsi):
            if rsi < 30:
                score += 10
                signals.append("RSI Oversold (<30)")
            elif 30 <= rsi <= 45:
                score += 5
            elif 55 <= rsi <= 70:
                score += 10
                signals.append("RSI Bullish Momentum")
            elif rsi > 70:
                score -= 10
                signals.append("RSI Overbought (>70)")
                
        # ── MACD Scoring (15% weight)
        macd_val = latest["MACD"]
        macd_sig = latest["MACD_signal"]
        macd_hist = latest["MACD_hist"]
        if pd.notna(macd_val) and pd.notna(macd_sig):
            if macd_val > macd_sig and macd_hist > 0:
                score += 15
                signals.append("MACD Bullish Crossover")
            elif macd_val > macd_sig:
                score += 5
            elif macd_val < macd_sig and macd_hist < 0:
                score -= 15
                signals.append("MACD Bearish Crossover")
                
        # ── EMA Scoring (20% weight)
        close_px = latest["Close"]
        if latest.get("EMA_200") is not None and pd.notna(latest["EMA_200"]):
            if close_px > latest["EMA_200"]:
                score += 5
                signals.append("Price > 200 EMA")
            else:
                score -= 5
                signals.append("Price < 200 EMA")
                
        if latest.get("EMA_21") is not None and pd.notna(latest["EMA_21"]) and latest.get("EMA_50") is not None and pd.notna(latest["EMA_50"]):
            if latest["EMA_21"] > latest["EMA_50"]:
                score += 10
                signals.append("Short EMA > Long EMA")
            elif latest["EMA_21"] < latest["EMA_50"]:
                score -= 10
                signals.append("Short EMA < Long EMA")
                
        # Golden Cross check
        if (
            prev.get("EMA_50") is not None and pd.notna(prev["EMA_50"]) and
            prev.get("EMA_200") is not None and pd.notna(prev["EMA_200"]) and
            latest.get("EMA_50") is not None and pd.notna(latest["EMA_50"]) and
            latest.get("EMA_200") is not None and pd.notna(latest["EMA_200"])
        ):
            if prev["EMA_50"] <= prev["EMA_200"] and latest["EMA_50"] > latest["EMA_200"]:
                score += 15
                signals.append("🔥 Golden Cross (50>200 EMA)")
            
        # ── Bollinger Bands (10% weight)
        if pd.notna(latest["BB_lower"]):
            if close_px <= latest["BB_lower"]:
                score += 10
                signals.append("Price at Lower Bollinger Band")
            elif close_px >= latest["BB_upper"]:
                score -= 10
                signals.append("Price at Upper Bollinger Band")
                
        # ── Volume Spike (10% weight)
        vol = latest["Volume"]
        vol_avg = latest["Volume_20SMA"]
        if pd.notna(vol_avg) and vol_avg > 0:
            if vol > (2 * vol_avg) and close_px > prev["Close"]:
                score += 10
                signals.append("Bullish Volume Spike (>2x)")
            elif vol > (2 * vol_avg) and close_px < prev["Close"]:
                score -= 10
                signals.append("Bearish Volume Spike (>2x)")
                
        # ── Supertrend (10% weight)
        if pd.notna(latest.get("Supertrend_dir")):
            if latest["Supertrend_dir"] == 1:
                score += 10
                signals.append("Supertrend Bullish")
            else:
                score -= 10
                signals.append("Supertrend Bearish")
                
        # ── Candlestick Patterns (10% weight)
        active_patterns = []
        if cdl is not None:
            # We look at the latest row for active patterns
            for pat in BULLISH_PATTERNS:
                if pat in latest and latest[pat] > 0:
                    score += 5
                    active_patterns.append(pat.replace("CDL_", ""))
            for pat in BEARISH_PATTERNS:
                # Some pandas-ta patterns return -100 for bearish, or >0. We check non-zero
                if pat in latest and latest[pat] != 0:
                    # Engulfing could be bearish if negative
                    if pat == "CDL_ENGULFING" and latest[pat] > 0:
                        continue # Already handled in bullish
                    score -= 5
                    active_patterns.append(pat.replace("CDL_", "") + " (Bearish)")

        if active_patterns:
            signals.append(f"Patterns: {', '.join(active_patterns)}")

        # Normalize score between 0 and 100
        score = max(0.0, min(100.0, score))

        return {
            "score": round(score, 2),
            "signals": signals,
            "rsi": round(rsi, 2) if pd.notna(rsi) else None,
            "macd": round(macd_val, 2) if pd.notna(macd_val) else None,
            "atr": round(latest["ATR_14"], 2) if pd.notna(latest["ATR_14"]) else None,
            "close": round(close_px, 2),
            "prev_close": round(float(prev["Close"]), 2),
            "change": round(close_px - float(prev["Close"]), 2),
            "change_pct": round(((close_px - float(prev["Close"])) / float(prev["Close"])) * 100, 2),
            "supertrend_dir": latest.get("Supertrend_dir", 0),
        }

    except Exception as e:
        logger.error(f"Technical analysis failed: {e}")
        return {"score": 50, "signals": [f"Error: {str(e)}"]}
