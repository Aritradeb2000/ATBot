"""
ATBot — Technical Analysis Engine
Calculates technical indicators using pandas-ta and scores the stock
from 0 to 100 based on momentum, trend, and volume.

v2 (PATCH): Dual scoring — trend-following sub-score + mean-reversion sub-score.
ADX routes which one becomes the primary `score`. This fixes the inverted
SIDEWAYS signal without changing the downstream interface — ensemble_scorer
still reads tech_data["score"].
"""

import warnings
import pandas as pd
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message=".*TA.Lib.*", category=UserWarning)
    warnings.filterwarnings("ignore", message=".*talib.*", category=UserWarning)
    import pandas_ta as ta
import logging

logger = logging.getLogger(__name__)

BULLISH_PATTERNS = ["CDL_ENGULFING", "CDL_MORNINGSTAR", "CDL_HAMMER", "CDL_PIERCING"]
BEARISH_PATTERNS = ["CDL_ENGULFING", "CDL_EVENINGSTAR", "CDL_SHOOTINGSTAR", "CDL_DARKCLOUDCOVER"]


def analyze_technical(df: pd.DataFrame) -> dict:
    if df is None or len(df) < 50:
        logger.warning("Not enough data for technical analysis (need at least 50 periods).")
        return {"score": 0, "signals": ["Not enough data"]}

    try:
        # ── Indicators ────────────────────────────────────────────────────────
        df["RSI_14"] = ta.rsi(df["Close"], length=14)

        macd = ta.macd(df["Close"], fast=12, slow=26, signal=9)
        df["MACD"] = macd["MACD_12_26_9"]
        df["MACD_signal"] = macd["MACDs_12_26_9"]
        df["MACD_hist"] = macd["MACDh_12_26_9"]

        df["EMA_9"]   = ta.ema(df["Close"], length=9)
        df["EMA_21"]  = ta.ema(df["Close"], length=21)
        df["EMA_50"]  = ta.ema(df["Close"], length=50)
        df["EMA_200"] = ta.ema(df["Close"], length=200)

        bbands = ta.bbands(df["Close"], length=20, std=2)
        if bbands is not None and not bbands.empty:
            df["BB_lower"] = bbands.iloc[:, 0]
            df["BB_mid"]   = bbands.iloc[:, 1]
            df["BB_upper"] = bbands.iloc[:, 2]
            df["BB_pct"]   = bbands.iloc[:, 4]
        else:
            df["BB_lower"] = df["BB_mid"] = df["BB_upper"] = df["BB_pct"] = None

        df["ATR_14"] = ta.atr(df["High"], df["Low"], df["Close"], length=14)
        df["Volume_20SMA"] = ta.sma(df["Volume"], length=20)

        st = ta.supertrend(df["High"], df["Low"], df["Close"], length=10, multiplier=3)
        if st is not None and not st.empty:
            df["Supertrend"]     = st.iloc[:, 0]
            df["Supertrend_dir"] = st.iloc[:, 1]
        else:
            df["Supertrend"] = df["Supertrend_dir"] = None

        # ── PATCH: ADX (trend strength, regime-neutral) ───────────────────────
        # ADX >= 25 → trending  |  ADX < 20 → ranging  |  20-25 → ambiguous
        adx_df = ta.adx(df["High"], df["Low"], df["Close"], length=14)
        if adx_df is not None and not adx_df.empty:
            df["ADX_14"] = adx_df["ADX_14"]
            df["DMP_14"] = adx_df["DMP_14"]
            df["DMN_14"] = adx_df["DMN_14"]
        else:
            df["ADX_14"] = df["DMP_14"] = df["DMN_14"] = None

        # Candlestick patterns (TA-Lib optional)
        cdl = None
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message=".*TA.Lib.*")
                warnings.filterwarnings("ignore", message=".*talib.*")
                warnings.filterwarnings("ignore", category=UserWarning)
                cdl = df.ta.cdl_pattern(name="all")
        except Exception:
            pass
        if cdl is not None and not cdl.empty:
            df = pd.concat([df, cdl], axis=1)

        latest = df.iloc[-1]
        prev   = df.iloc[-2]

        # ── PATCH: Dual scoring — trend vs reversion ─────────────────────────
        trend_score     = 50.0
        reversion_score = 50.0
        signals = []

        adx_val = latest["ADX_14"] if pd.notna(latest["ADX_14"]) else None

        # ═══ TREND-FOLLOWING SUB-SCORE ══════════════════════════════════════
        macd_val  = latest["MACD"]
        macd_sig  = latest["MACD_signal"]
        macd_hist = latest["MACD_hist"]
        if pd.notna(macd_val) and pd.notna(macd_sig):
            if macd_val > macd_sig and macd_hist > 0:
                trend_score += 15
                signals.append("MACD Bullish Crossover")
            elif macd_val > macd_sig:
                trend_score += 5
            elif macd_val < macd_sig and macd_hist < 0:
                trend_score -= 15
                signals.append("MACD Bearish Crossover")

        close_px = latest["Close"]
        if latest.get("EMA_200") is not None and pd.notna(latest["EMA_200"]):
            if close_px > latest["EMA_200"]:
                trend_score += 5
                signals.append("Price > 200 EMA")
            else:
                trend_score -= 5
                signals.append("Price < 200 EMA")

        if (latest.get("EMA_21") is not None and pd.notna(latest["EMA_21"]) and
                latest.get("EMA_50") is not None and pd.notna(latest["EMA_50"])):
            if latest["EMA_21"] > latest["EMA_50"]:
                trend_score += 10
                signals.append("Short EMA > Long EMA")
            elif latest["EMA_21"] < latest["EMA_50"]:
                trend_score -= 10
                signals.append("Short EMA < Long EMA")

        if (prev.get("EMA_50") is not None and pd.notna(prev["EMA_50"]) and
                prev.get("EMA_200") is not None and pd.notna(prev["EMA_200"]) and
                latest.get("EMA_50") is not None and pd.notna(latest["EMA_50"]) and
                latest.get("EMA_200") is not None and pd.notna(latest["EMA_200"])):
            if prev["EMA_50"] <= prev["EMA_200"] and latest["EMA_50"] > latest["EMA_200"]:
                trend_score += 15
                signals.append("🔥 Golden Cross (50>200 EMA)")

        if pd.notna(latest.get("Supertrend_dir")):
            if latest["Supertrend_dir"] == 1:
                trend_score += 10
                signals.append("Supertrend Bullish")
            else:
                trend_score -= 10
                signals.append("Supertrend Bearish")

        rsi = latest["RSI_14"]
        if pd.notna(rsi):
            if 55 <= rsi <= 70:
                trend_score += 10
                signals.append("RSI Bullish Momentum (55-70)")
            elif rsi > 70:
                trend_score -= 5

        vol     = latest["Volume"]
        vol_avg = latest["Volume_20SMA"]
        if pd.notna(vol_avg) and vol_avg > 0 and vol > (2 * vol_avg):
            if close_px > prev["Close"]:
                trend_score += 10
                signals.append("Bullish Volume Spike (>2x)")
            elif close_px < prev["Close"]:
                trend_score -= 10
                signals.append("Bearish Volume Spike (>2x)")

        # ═══ MEAN-REVERSION SUB-SCORE ═══════════════════════════════════════
        if pd.notna(rsi):
            if rsi < 30:
                reversion_score += 15
                signals.append("RSI Oversold (<30) — reversion long")
            elif rsi < 40:
                reversion_score += 8
            elif rsi > 70:
                reversion_score -= 15
                signals.append("RSI Overbought (>70) — reversion short")
            elif rsi > 60:
                reversion_score -= 8

        if pd.notna(latest.get("BB_lower")):
            if close_px <= latest["BB_lower"]:
                reversion_score += 15
                signals.append("Price at Lower Bollinger Band — reversion long")
            elif close_px >= latest["BB_upper"]:
                reversion_score -= 15
                signals.append("Price at Upper Bollinger Band — reversion short")

        if (latest.get("EMA_21") is not None and pd.notna(latest["EMA_21"])
                and latest["EMA_21"] > 0):
            stretch_pct = (close_px - latest["EMA_21"]) / latest["EMA_21"] * 100
            if stretch_pct <= -5:
                reversion_score += 8
                signals.append(f"Stretched below EMA21 ({stretch_pct:.1f}%)")
            elif stretch_pct >= 5:
                reversion_score -= 8
                signals.append(f"Stretched above EMA21 (+{stretch_pct:.1f}%)")

        if cdl is not None:
            bull_rev = ["CDL_HAMMER", "CDL_MORNINGSTAR", "CDL_PIERCING", "CDL_ENGULFING"]
            bear_rev = ["CDL_SHOOTINGSTAR", "CDL_EVENINGSTAR", "CDL_DARKCLOUDCOVER"]
            for pat in bull_rev:
                if pat in latest and latest[pat] > 0:
                    reversion_score += 6
                    signals.append(f"Bullish reversal: {pat.replace('CDL_', '')}")
            for pat in bear_rev:
                if pat in latest and latest[pat] != 0:
                    reversion_score -= 6
                    signals.append(f"Bearish reversal: {pat.replace('CDL_', '')}")

        # ═══ ROUTING — ADX decides which sub-score is primary ═══════════════
        if adx_val is None:
            primary_score = trend_score
            mode = "TREND_DEFAULT"
        elif adx_val >= 25:
            primary_score = trend_score
            mode = "TREND"
        elif adx_val < 20:
            primary_score = reversion_score
            mode = "REVERSION"
        else:
            primary_score = 0.5 * trend_score + 0.5 * reversion_score
            mode = "MIXED"

        trend_score     = max(0.0, min(100.0, trend_score))
        reversion_score = max(0.0, min(100.0, reversion_score))
        primary_score   = max(0.0, min(100.0, primary_score))

        # ── Return ───────────────────────────────────────────────────────────
        return {
            # Backward-compatible primary score — ensemble_scorer reads this
            "score": round(primary_score, 2),

            # PATCH: dual-engine outputs for future meta-learner use
            "trend_score":     round(trend_score, 2),
            "reversion_score": round(reversion_score, 2),
            "adx":             round(adx_val, 2) if adx_val is not None else None,
            "mode":            mode,   # TREND / REVERSION / MIXED / TREND_DEFAULT

            # Existing diagnostics
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