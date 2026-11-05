"""
ATBot — Technical Analysis Engine
Calculates technical indicators using pandas-ta and scores the stock
from 0 to 100 based on momentum, trend, volume, and volatility.

v3 Enhancements:
1. Multi-Timeframe Alignment (MTF: Weekly + Daily via in-memory resampling).
2. Mansfield Relative Strength (RS vs Nifty 50 over 20d and 50d).
3. Institutional Delivery Conviction tiers & On-Balance Volume (OBV) trend divergence.
4. Volatility Contraction Pattern (VCP / Squeeze Breakout using BB inside Keltner Channels).
5. Vectorized native candlestick pattern recognition (0 external spam/warnings).
"""

import warnings
import logging
import numpy as np
import pandas as pd
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message=".*TA.Lib.*", category=UserWarning)
    warnings.filterwarnings("ignore", message=".*talib.*", category=UserWarning)
    import pandas_ta as ta

logger = logging.getLogger(__name__)


def detect_candlesticks_native(df: pd.DataFrame) -> dict:
    """
    Detects classic high-probability candlestick reversal patterns
    natively without TA-Lib or noisy external warning messages.
    """
    if df is None or len(df) < 3:
        return {}

    c = df["Close"]
    o = df["Open"]
    h = df["High"]
    l = df["Low"]

    curr_c, prev_c, prev2_c = float(c.iloc[-1]), float(c.iloc[-2]), float(c.iloc[-3])
    curr_o, prev_o, prev2_o = float(o.iloc[-1]), float(o.iloc[-2]), float(o.iloc[-3])
    curr_h, prev_h, prev2_h = float(h.iloc[-1]), float(h.iloc[-2]), float(h.iloc[-3])
    curr_l, prev_l, prev2_l = float(l.iloc[-1]), float(l.iloc[-2]), float(l.iloc[-3])

    curr_body = abs(curr_c - curr_o)
    curr_rng  = max(0.001, curr_h - curr_l)
    curr_uw   = curr_h - max(curr_c, curr_o)
    curr_lw   = min(curr_c, curr_o) - curr_l

    prev_body  = abs(prev_c - prev_o)
    prev2_body = abs(prev2_c - prev2_o)

    patterns = {}

    # Hammer (Bullish Reversal after downtrend)
    if curr_lw >= 1.8 * curr_body and curr_uw <= 0.3 * curr_body and curr_c > (curr_l + 0.6 * curr_rng):
        patterns["CDL_HAMMER"] = 100

    # Shooting Star (Bearish Reversal at top)
    if curr_uw >= 1.8 * curr_body and curr_lw <= 0.3 * curr_body and curr_c < (curr_l + 0.4 * curr_rng):
        patterns["CDL_SHOOTINGSTAR"] = -100

    # Bullish Engulfing
    if prev_c < prev_o and curr_c > curr_o and curr_o <= prev_c and curr_c >= prev_o:
        patterns["CDL_ENGULFING"] = 100
    # Bearish Engulfing
    elif prev_c > prev_o and curr_c < curr_o and curr_o >= prev_c and curr_c <= prev_o:
        patterns["CDL_ENGULFING"] = -100

    # Piercing Line (Bullish)
    if prev_c < prev_o and curr_c > curr_o and curr_o < prev_l and curr_c > ((prev_o + prev_c) / 2):
        patterns["CDL_PIERCING"] = 100

    # Dark Cloud Cover (Bearish)
    if prev_c > prev_o and curr_c < curr_o and curr_o > prev_h and curr_c < ((prev_o + prev_c) / 2):
        patterns["CDL_DARKCLOUDCOVER"] = -100

    # Morning Star (Bullish Reversal)
    if prev2_c < prev2_o and prev_body < (0.4 * prev2_body) and curr_c > curr_o and curr_c > ((prev2_o + prev2_c) / 2):
        patterns["CDL_MORNINGSTAR"] = 100

    # Evening Star (Bearish Reversal)
    if prev2_c > prev2_o and prev_body < (0.4 * prev2_body) and curr_c < curr_o and curr_c < ((prev2_o + prev2_c) / 2):
        patterns["CDL_EVENINGSTAR"] = -100

    return patterns


def resample_to_weekly(df: pd.DataFrame) -> pd.DataFrame:
    """
    Resamples daily OHLCV in-memory to weekly bars (ending Friday).
    Zero network calls, sub-millisecond execution.
    """
    try:
        w_df = df.copy()
        if not isinstance(w_df.index, pd.DatetimeIndex):
            w_df.index = pd.to_datetime(w_df.index)

        weekly = w_df.resample("W-FRI").agg({
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum"
        }).dropna()
        return weekly
    except Exception as e:
        logger.warning(f"Resampling to weekly failed: {e}")
        return pd.DataFrame()


def analyze_technical(df: pd.DataFrame, delivery_pct: float = None, nifty_change_20d: float = 0.0) -> dict:
    if df is None or len(df) < 50:
        logger.warning("Not enough data for technical analysis (need at least 50 periods).")
        return {"score": 0, "signals": ["Not enough data"]}

    try:
        # ── 1. Daily Core Indicators ──────────────────────────────────────────
        df["RSI_14"] = ta.rsi(df["Close"], length=14)

        macd = ta.macd(df["Close"], fast=12, slow=26, signal=9)
        if macd is not None and not macd.empty:
            df["MACD"]        = macd["MACD_12_26_9"]
            df["MACD_signal"] = macd["MACDs_12_26_9"]
            df["MACD_hist"]   = macd["MACDh_12_26_9"]
        else:
            df["MACD"] = df["MACD_signal"] = df["MACD_hist"] = None

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

        df["ATR_14"]       = ta.atr(df["High"], df["Low"], df["Close"], length=14)
        df["Volume_20SMA"] = ta.sma(df["Volume"], length=20)

        st = ta.supertrend(df["High"], df["Low"], df["Close"], length=10, multiplier=3)
        if st is not None and not st.empty:
            df["Supertrend"]     = st.iloc[:, 0]
            df["Supertrend_dir"] = st.iloc[:, 1]
        else:
            df["Supertrend"] = df["Supertrend_dir"] = None

        # ADX (Trend strength & regime routing)
        adx_df = ta.adx(df["High"], df["Low"], df["Close"], length=14)
        if adx_df is not None and not adx_df.empty:
            df["ADX_14"] = adx_df["ADX_14"]
            df["DMP_14"] = adx_df["DMP_14"]
            df["DMN_14"] = adx_df["DMN_14"]
        else:
            df["ADX_14"] = df["DMP_14"] = df["DMN_14"] = None

        # ── 2. OBV (On-Balance Volume) & Institutional Volume Trend ───────────
        df["OBV"] = ta.obv(df["Close"], df["Volume"])
        if df["OBV"] is not None and not df["OBV"].empty:
            df["OBV_EMA20"] = ta.ema(df["OBV"], length=20)
        else:
            df["OBV_EMA20"] = None

        # ── 3. Keltner Channels & Volatility Contraction Pattern (VCP) ────────
        kc = ta.kc(df["High"], df["Low"], df["Close"], length=20, scalar=1.5)
        if kc is not None and not kc.empty and bbands is not None and not bbands.empty:
            df["KC_lower"] = kc.iloc[:, 0]
            df["KC_mid"]   = kc.iloc[:, 1]
            df["KC_upper"] = kc.iloc[:, 2]
            # Squeeze is ON when Bollinger Bands contract inside Keltner Channels
            squeeze_series = (df["BB_lower"] >= df["KC_lower"]) & (df["BB_upper"] <= df["KC_upper"])
        else:
            df["KC_lower"] = df["KC_mid"] = df["KC_upper"] = None
            squeeze_series = pd.Series(False, index=df.index)

        # ── 4. Candlestick Reversal Patterns (Native Vectorized) ──────────────
        cdl_patterns = detect_candlesticks_native(df)

        latest = df.iloc[-1]
        prev   = df.iloc[-2]
        close_px = float(latest["Close"])

        # ── 5. Multi-Timeframe (MTF: Weekly) Analysis ─────────────────────────
        weekly_trend = "NEUTRAL"
        w_rsi = 50.0
        w_ema21 = None
        w_ema50 = None
        weekly_df = resample_to_weekly(df)
        if len(weekly_df) >= 20:
            weekly_df["W_EMA21"] = ta.ema(weekly_df["Close"], length=min(21, len(weekly_df)))
            weekly_df["W_EMA50"] = ta.ema(weekly_df["Close"], length=min(50, len(weekly_df)))
            weekly_df["W_RSI14"] = ta.rsi(weekly_df["Close"], length=14)
            w_latest = weekly_df.iloc[-1]
            w_close = float(w_latest["Close"])
            w_ema21 = float(w_latest["W_EMA21"]) if pd.notna(w_latest.get("W_EMA21")) else None
            w_ema50 = float(w_latest["W_EMA50"]) if pd.notna(w_latest.get("W_EMA50")) else None
            w_rsi   = float(w_latest["W_RSI14"]) if pd.notna(w_latest.get("W_RSI14")) else 50.0

            if w_ema21 is not None:
                if w_close > w_ema21 and w_rsi >= 48 and (w_ema50 is None or w_ema21 >= w_ema50 * 0.99):
                    weekly_trend = "BULLISH"
                elif w_close < w_ema21 and w_rsi <= 52 and (w_ema50 is None or w_ema21 <= w_ema50 * 1.01):
                    weekly_trend = "BEARISH"

        # ── 6. Mansfield Relative Strength vs Benchmark (Nifty 50) ────────────
        stock_change_20d = float(((close_px - df["Close"].iloc[-21]) / df["Close"].iloc[-21]) * 100) if len(df) >= 21 else 0.0
        stock_change_50d = float(((close_px - df["Close"].iloc[-51]) / df["Close"].iloc[-51]) * 100) if len(df) >= 51 else 0.0
        rs_20d = round(stock_change_20d - nifty_change_20d, 2)

        # ── 7. VCP Squeeze & Breakout State ───────────────────────────────────
        is_vcp_squeeze = bool(squeeze_series.iloc[-1])
        # Expansion breakout: previous 1-3 bars were compressed, now expanding with upward momentum
        was_squeezed_prior = bool(squeeze_series.iloc[-4:-1].any()) if len(squeeze_series) >= 4 else False
        is_vcp_breakout = False
        if was_squeezed_prior and not is_vcp_squeeze:
            kc_mid_val = latest.get("KC_mid")
            kc_up_val  = latest.get("KC_upper")
            bb_up_val  = latest.get("BB_upper")
            vol_val    = latest.get("Volume", 0)
            vol_avg    = latest.get("Volume_20SMA", 1)
            if (kc_mid_val is not None and close_px > kc_mid_val and
                bb_up_val is not None and kc_up_val is not None and bb_up_val > kc_up_val and
                vol_avg and vol_val > vol_avg):
                is_vcp_breakout = True

        # ── 8. Scoring Engine ─────────────────────────────────────────────────
        trend_score     = 50.0
        reversion_score = 50.0
        signals = []

        adx_val = latest["ADX_14"] if pd.notna(latest.get("ADX_14")) else None

        # ═══ TREND-FOLLOWING SUB-SCORE ══════════════════════════════════════
        macd_val  = latest.get("MACD")
        macd_sig  = latest.get("MACD_signal")
        macd_hist = latest.get("MACD_hist")
        if pd.notna(macd_val) and pd.notna(macd_sig):
            if macd_val > macd_sig and macd_hist > 0:
                trend_score += 15
                signals.append("MACD Bullish Crossover")
            elif macd_val > macd_sig:
                trend_score += 5
            elif macd_val < macd_sig and macd_hist < 0:
                trend_score -= 15
                signals.append("MACD Bearish Crossover")

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
                signals.append("Golden Cross (50>200 EMA)")

        if pd.notna(latest.get("Supertrend_dir")):
            if latest["Supertrend_dir"] == 1:
                trend_score += 10
                signals.append("Supertrend Bullish")
            else:
                trend_score -= 10
                signals.append("Supertrend Bearish")

        rsi = latest.get("RSI_14")
        if pd.notna(rsi):
            if 55 <= rsi <= 70:
                trend_score += 10
                signals.append("RSI Bullish Momentum (55-70)")
            elif rsi > 70:
                trend_score -= 5

        vol     = latest.get("Volume", 0)
        vol_avg = latest.get("Volume_20SMA", 0)
        if pd.notna(vol_avg) and vol_avg > 0 and vol > (2 * vol_avg):
            if close_px > prev["Close"]:
                trend_score += 10
                signals.append("Bullish Volume Spike (>2x)")
            elif close_px < prev["Close"]:
                trend_score -= 10
                signals.append("Bearish Volume Spike (>2x)")

        # Overextension & Pullback Confirmation
        if latest.get("EMA_21") is not None and pd.notna(latest["EMA_21"]) and latest["EMA_21"] > 0:
            stretch_21 = (close_px - latest["EMA_21"]) / latest["EMA_21"] * 100
            if stretch_21 >= 3.5:
                trend_score -= 10
                signals.append(f"Overextended above 21 EMA (+{stretch_21:.1f}%) — Wait for Pullback")

            is_uptrend = (
                latest.get("EMA_200") is not None and pd.notna(latest["EMA_200"]) and close_px > latest["EMA_200"] and
                latest.get("EMA_50") is not None and pd.notna(latest["EMA_50"]) and latest["EMA_50"] > latest["EMA_200"]
            )
            low_px = latest["Low"]
            dist_low_21 = (low_px - latest["EMA_21"]) / latest["EMA_21"]
            if (is_uptrend and dist_low_21 <= 0.015 and low_px >= latest["EMA_21"] * 0.97 and
                    close_px > latest["Open"] and close_px > latest["EMA_21"] and
                    pd.notna(rsi) and 42 <= rsi <= 58):
                trend_score += 15
                signals.append("Bullish 21-EMA Pullback Confirmation (Prime R:R Setup)")

        # [ENHANCEMENT 1] Weekly Multi-Timeframe Alignment
        if weekly_trend == "BULLISH":
            trend_score += 12
            signals.append("MTF Alignment: Weekly & Daily Bullish Confirmed")
        elif weekly_trend == "BEARISH":
            trend_score -= 15
            signals.append("Counter-Trend Warning: Daily Buy against Weekly Downtrend")

        # [ENHANCEMENT 2] Mansfield Relative Strength (RS vs Nifty 50)
        if rs_20d >= 6.0:
            trend_score += 8
            signals.append(f"Market Leader: Outperforming Benchmark (RS 20d: +{rs_20d:.1f}%)")
        elif rs_20d >= 2.0:
            trend_score += 4
            signals.append(f"Benchmark Outperformer (RS 20d: +{rs_20d:.1f}%)")
        elif rs_20d <= -6.0:
            trend_score -= 8
            signals.append(f"Market Laggard: Underperforming Benchmark (RS 20d: {rs_20d:.1f}%)")
        elif rs_20d <= -2.0:
            trend_score -= 4

        # [ENHANCEMENT 3] OBV Institutional Accumulation & Divergence
        obv_val     = latest.get("OBV")
        obv_ema_val = latest.get("OBV_EMA20")
        obv_slope_5d = 0.0
        if pd.notna(obv_val) and len(df["OBV"]) >= 6:
            obv_slope_5d = float(obv_val - df["OBV"].iloc[-6])

        if pd.notna(obv_val) and pd.notna(obv_ema_val):
            if obv_val > obv_ema_val and obv_slope_5d > 0:
                trend_score += 8
                signals.append("OBV Institutional Accumulation (Above 20-EMA)")
            elif close_px > df["Close"].iloc[-6] and obv_val < obv_ema_val and obv_slope_5d < 0:
                trend_score -= 8
                signals.append("Bearish Volume Divergence: Price Up but OBV Down")
            elif obv_val < obv_ema_val:
                trend_score -= 4

        # [ENHANCEMENT 4] Volatility Contraction Pattern (VCP / Squeeze Breakout)
        if is_vcp_breakout:
            trend_score += 15
            signals.append("Volatility Squeeze Expansion Breakout (VCP Fired)")
        elif is_vcp_squeeze:
            signals.append("Volatility Contraction (VCP Squeeze Active — Coiling for Breakout)")

        # [ENHANCEMENT 5] Graded Delivery Conviction
        if delivery_pct is not None:
            if delivery_pct >= 60.0:
                trend_score += 10
                signals.append(f"Institutional Delivery Conviction ({delivery_pct:.1f}%)")
            elif delivery_pct >= 45.0:
                trend_score += 5
                signals.append(f"Solid Delivery Support ({delivery_pct:.1f}%)")
            elif delivery_pct < 25.0:
                trend_score -= 8
                signals.append(f"Speculative Churn: Low Delivery ({delivery_pct:.1f}%)")

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

        if latest.get("EMA_21") is not None and pd.notna(latest["EMA_21"]) and latest["EMA_21"] > 0:
            stretch_pct = (close_px - latest["EMA_21"]) / latest["EMA_21"] * 100
            if stretch_pct <= -5:
                reversion_score += 8
                signals.append(f"Stretched below EMA21 ({stretch_pct:.1f}%)")
            elif stretch_pct >= 5:
                reversion_score -= 8
                signals.append(f"Stretched above EMA21 (+{stretch_pct:.1f}%)")

        for pat_name, pat_val in cdl_patterns.items():
            clean_name = pat_name.replace("CDL_", "")
            if pat_val > 0:
                reversion_score += 6
                signals.append(f"Bullish candlestick: {clean_name}")
            elif pat_val < 0:
                reversion_score -= 6
                signals.append(f"Bearish candlestick: {clean_name}")

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

        # Weak delivery guard: Cap speculative spikes with low institutional delivery
        if delivery_pct is not None and delivery_pct < 30.0 and primary_score > 75:
            primary_score = min(primary_score, 72.0)
            signals.append(f"Weak Delivery Score Cap ({delivery_pct:.1f}%)")

        trend_score     = max(0.0, min(100.0, trend_score))
        reversion_score = max(0.0, min(100.0, reversion_score))
        primary_score   = max(0.0, min(100.0, primary_score))

        # ── Return Feature Vector & Analysis ──────────────────────────────────
        features = {
            "technical_score": float(primary_score),
            "rsi_14": float(rsi) if pd.notna(rsi) else 50.0,
            "adx_14": float(adx_val) if adx_val is not None else 20.0,
            "dmp_14": float(latest.get("DMP_14", 20.0)) if pd.notna(latest.get("DMP_14")) else 20.0,
            "dmn_14": float(latest.get("DMN_14", 20.0)) if pd.notna(latest.get("DMN_14")) else 20.0,
            "macd": float(macd_val) if pd.notna(macd_val) else 0.0,
            "macd_signal": float(macd_sig) if pd.notna(macd_sig) else 0.0,
            "macd_hist": float(macd_hist) if pd.notna(macd_hist) else 0.0,
            "atr_pct": float((latest["ATR_14"] / close_px) * 100) if pd.notna(latest.get("ATR_14")) and close_px > 0 else 2.0,
            "bb_pct": float(latest.get("BB_pct", 0.5)) if pd.notna(latest.get("BB_pct")) else 0.5,
            "bb_width": float((latest["BB_upper"] - latest["BB_lower"]) / latest["BB_mid"]) if (pd.notna(latest.get("BB_upper")) and pd.notna(latest.get("BB_mid")) and latest["BB_mid"] > 0) else 0.05,
            "supertrend_dir": float(latest.get("Supertrend_dir", 1.0)) if pd.notna(latest.get("Supertrend_dir")) else 1.0,
            "above_200ema": 1.0 if (latest.get("EMA_200") is not None and pd.notna(latest["EMA_200"]) and close_px > latest["EMA_200"]) else 0.0,
            "dist_ema9": float((close_px - latest["EMA_9"]) / latest["EMA_9"]) if (latest.get("EMA_9") is not None and pd.notna(latest["EMA_9"])) else 0.0,
            "dist_ema21": float((close_px - latest["EMA_21"]) / latest["EMA_21"]) if (latest.get("EMA_21") is not None and pd.notna(latest["EMA_21"])) else 0.0,
            "dist_ema50": float((close_px - latest["EMA_50"]) / latest["EMA_50"]) if (latest.get("EMA_50") is not None and pd.notna(latest["EMA_50"])) else 0.0,
            "dist_ema200": float((close_px - latest["EMA_200"]) / latest["EMA_200"]) if (latest.get("EMA_200") is not None and pd.notna(latest["EMA_200"])) else 0.0,
            "ema9_ema21_spread": float((latest["EMA_9"] - latest["EMA_21"]) / latest["EMA_21"]) if (latest.get("EMA_9") is not None and latest.get("EMA_21") is not None and pd.notna(latest["EMA_9"]) and pd.notna(latest["EMA_21"])) else 0.0,
            "ema21_ema50_spread": float((latest["EMA_21"] - latest["EMA_50"]) / latest["EMA_50"]) if (latest.get("EMA_21") is not None and latest.get("EMA_50") is not None and pd.notna(latest["EMA_21"]) and pd.notna(latest["EMA_50"])) else 0.0,
            "vol_ratio": float(vol / max(1.0, vol_avg)) if (pd.notna(vol_avg) and vol_avg > 0) else 1.0,
            "is_overextended": 1.0 if (latest.get("EMA_21") is not None and pd.notna(latest["EMA_21"]) and ((close_px - latest["EMA_21"]) / latest["EMA_21"] * 100) >= 3.5) else 0.0,
            "is_pullback_setup": 1.0 if any("Pullback" in s for s in signals) else 0.0,
            "weekly_trend_val": 1.0 if weekly_trend == "BULLISH" else (-1.0 if weekly_trend == "BEARISH" else 0.0),
            "weekly_rsi": float(w_rsi),
            "rs_20d": float(rs_20d),
            "obv_above_ema": 1.0 if (pd.notna(obv_val) and pd.notna(obv_ema_val) and obv_val > obv_ema_val) else 0.0,
            "vcp_squeeze": 1.0 if is_vcp_squeeze else 0.0,
            "vcp_breakout": 1.0 if is_vcp_breakout else 0.0,
            "delivery_pct": float(delivery_pct) if delivery_pct is not None else 40.0,
        }

        return {
            "score": round(primary_score, 2),
            "features": features,
            "trend_score":     round(trend_score, 2),
            "reversion_score": round(reversion_score, 2),
            "adx":             round(adx_val, 2) if adx_val is not None else None,
            "mode":            mode,
            "signals": signals,
            "rsi": round(rsi, 2) if pd.notna(rsi) else None,
            "macd": round(macd_val, 2) if pd.notna(macd_val) else None,
            "atr": round(latest["ATR_14"], 2) if pd.notna(latest.get("ATR_14")) else None,
            "close": round(close_px, 2),
            "prev_close": round(float(prev["Close"]), 2),
            "change": round(close_px - float(prev["Close"]), 2),
            "change_pct": round(((close_px - float(prev["Close"])) / float(prev["Close"])) * 100, 2),
            "supertrend_dir": latest.get("Supertrend_dir", 0),
            # v3 Quantitative & MTF additions
            "weekly_trend": weekly_trend,
            "weekly_rsi": round(w_rsi, 2) if pd.notna(w_rsi) else None,
            "weekly_ema21": round(w_ema21, 2) if w_ema21 is not None else None,
            "weekly_ema50": round(w_ema50, 2) if w_ema50 is not None else None,
            "rs_20d": rs_20d,
            "stock_change_20d": round(stock_change_20d, 2),
            "stock_change_50d": round(stock_change_50d, 2),
            "is_vcp_squeeze": is_vcp_squeeze,
            "is_vcp_breakout": is_vcp_breakout,
            "obv_accumulating": bool(pd.notna(obv_val) and pd.notna(obv_ema_val) and obv_val > obv_ema_val and obv_slope_5d > 0),
            "delivery_pct": delivery_pct,
        }

    except Exception as e:
        logger.error(f"Technical analysis failed: {e}")
        return {"score": 50, "signals": [f"Error: {str(e)}"]}
