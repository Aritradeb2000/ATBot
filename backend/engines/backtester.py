"""
ATBot — Historical Backtester
Simulates ATBot technical signals and ATR-based price targets & stop-losses
across historical Nifty 200 daily OHLCV data.
"""

import os
import time
import logging
import warnings
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Tuple

with warnings.catch_warnings():
    warnings.filterwarnings("ignore")
    import pandas_ta as ta

logger = logging.getLogger(__name__)

DATA_DIR = r"C:\Users\aritrad\Desktop\ATBot\nifty200_data"


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Vectorized calculation of core technical indicators on historical candles."""
    df = df.copy()
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    # 1. Trend & Moving Averages
    df["EMA_9"] = ta.ema(close, length=9)
    df["EMA_21"] = ta.ema(close, length=21)
    df["EMA_50"] = ta.ema(close, length=50)
    df["EMA_200"] = ta.ema(close, length=200)

    # 2. Momentum
    df["RSI_14"] = ta.rsi(close, length=14)
    macd = ta.macd(close, fast=12, slow=26, signal=9)
    if macd is not None and not macd.empty:
        df["MACD"] = macd["MACD_12_26_9"]
        df["MACD_signal"] = macd["MACDs_12_26_9"]
        df["MACD_hist"] = macd["MACDh_12_26_9"]
    else:
        df["MACD"] = df["MACD_signal"] = df["MACD_hist"] = 0.0

    # 3. Volatility & Bands
    df["ATR_14"] = ta.atr(high, low, close, length=14)
    bb = ta.bbands(close, length=20, std=2)
    if bb is not None and not bb.empty:
        df["BB_lower"] = bb.iloc[:, 0]
        df["BB_mid"] = bb.iloc[:, 1]
        df["BB_upper"] = bb.iloc[:, 2]
        df["BB_pct"] = bb.iloc[:, 4]
    else:
        df["BB_lower"] = df["BB_mid"] = df["BB_upper"] = df["BB_pct"] = 0.5

    # 4. Supertrend
    st = ta.supertrend(high, low, close, length=10, multiplier=3)
    if st is not None and not st.empty:
        df["Supertrend"] = st.iloc[:, 0]
        df["Supertrend_dir"] = st.iloc[:, 1]
    else:
        df["Supertrend"] = close
        df["Supertrend_dir"] = 1

    # 5. ADX
    adx_df = ta.adx(high, low, close, length=14)
    if adx_df is not None and not adx_df.empty:
        df["ADX_14"] = adx_df["ADX_14"]
    else:
        df["ADX_14"] = 20.0

    # 6. Volume
    df["Volume_20SMA"] = ta.sma(volume, length=20)
    return df


def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Evaluates ATBot's Technical scoring logic on each historical candle.
    Outputs: technical_score, signal ('BUY', 'SELL', 'HOLD')
    """
    df = df.copy()
    n = len(df)
    scores = np.full(n, 50.0)
    signals = ["HOLD"] * n

    # Vectorized scoring components
    # 1. MACD Bullish / Bearish
    macd_bull = (df["MACD"] > df["MACD_signal"]) & (df["MACD_hist"] > 0)
    macd_bear = (df["MACD"] < df["MACD_signal"]) & (df["MACD_hist"] < 0)
    scores += np.where(macd_bull, 15, np.where(macd_bear, -15, 0))

    # 2. 200 EMA Trend Alignment
    above_200 = df["Close"] > df["EMA_200"]
    scores += np.where(above_200, 5, -5)

    # 3. EMA Cross (21 > 50)
    ema_bull = df["EMA_21"] > df["EMA_50"]
    scores += np.where(ema_bull, 10, -10)

    # 4. Supertrend
    st_bull = df["Supertrend_dir"] == 1
    scores += np.where(st_bull, 10, -10)

    # 5. RSI Momentum
    rsi = df["RSI_14"]
    rsi_bull = (rsi >= 55) & (rsi <= 70)
    rsi_overbought = rsi > 70
    scores += np.where(rsi_bull, 10, np.where(rsi_overbought, -5, 0))

    # 6. Volume Spike
    vol_spike = (df["Volume_20SMA"] > 0) & (df["Volume"] > (2 * df["Volume_20SMA"]))
    vol_bull = vol_spike & (df["Close"] > df["Open"])
    vol_bear = vol_spike & (df["Close"] < df["Open"])
    scores += np.where(vol_bull, 10, np.where(vol_bear, -10, 0))

    scores = np.clip(scores, 0.0, 100.0)
    df["technical_score"] = scores

    # Generate signals based on ATBot thresholds
    # BUY >= 65, SELL <= 40, otherwise HOLD
    for i in range(n):
        s = scores[i]
        if s >= 75:
            signals[i] = "STRONG BUY"
        elif s >= 65:
            signals[i] = "BUY"
        elif s <= 30:
            signals[i] = "STRONG SELL"
        elif s <= 40:
            signals[i] = "SELL"
        else:
            signals[i] = "HOLD"

    df["signal"] = signals
    return df


def simulate_trades(
    df: pd.DataFrame,
    symbol: str,
    holding_days: int = 10,
    target_atr_mult: float = 1.5,
    stop_atr_mult: float = 1.5
) -> List[dict]:
    """
    Simulates trades for signals generated in df.
    Checks price action over the next `holding_days` to see if Target or SL was hit first.
    """
    trades = []
    n = len(df)

    # Only evaluate once warm (e.g. after index 200 for EMA200)
    for i in range(200, n - holding_days):
        sig = df["signal"].iloc[i]
        if sig not in ["BUY", "STRONG BUY", "SELL", "STRONG SELL"]:
            continue

        entry_date = df["Date"].iloc[i]
        entry_price = df["Close"].iloc[i]
        atr = df["ATR_14"].iloc[i]

        if pd.isna(atr) or atr <= 0 or entry_price <= 0:
            continue

        is_buy = "BUY" in sig
        direction = 1.0 if is_buy else -1.0

        target_price = entry_price + (direction * atr * target_atr_mult)
        stop_price = entry_price - (direction * atr * stop_atr_mult)

        # Forward simulate over holding_days
        outcome = "EXPIRED"
        exit_date = df["Date"].iloc[i + holding_days]
        exit_price = df["Close"].iloc[i + holding_days]
        exit_day = holding_days

        for d in range(1, holding_days + 1):
            bar_high = df["High"].iloc[i + d]
            bar_low = df["Low"].iloc[i + d]
            bar_date = df["Date"].iloc[i + d]

            if is_buy:
                # Check stop loss first (risk-first assumption)
                if bar_low <= stop_price:
                    outcome = "LOSS"
                    exit_price = stop_price
                    exit_date = bar_date
                    exit_day = d
                    break
                elif bar_high >= target_price:
                    outcome = "WIN"
                    exit_price = target_price
                    exit_date = bar_date
                    exit_day = d
                    break
            else: # SELL / SHORT
                if bar_high >= stop_price:
                    outcome = "LOSS"
                    exit_price = stop_price
                    exit_date = bar_date
                    exit_day = d
                    break
                elif bar_low <= target_price:
                    outcome = "WIN"
                    exit_price = target_price
                    exit_date = bar_date
                    exit_day = d
                    break

        pnl_pct = ((exit_price - entry_price) / entry_price) * 100 * direction

        trades.append({
            "symbol": symbol,
            "entry_date": entry_date,
            "exit_date": exit_date,
            "signal": sig,
            "direction": "LONG" if is_buy else "SHORT",
            "entry_price": round(entry_price, 2),
            "exit_price": round(exit_price, 2),
            "target_price": round(target_price, 2),
            "stop_price": round(stop_price, 2),
            "outcome": outcome,
            "exit_day": exit_day,
            "pnl_pct": round(pnl_pct, 2),
            "technical_score": df["technical_score"].iloc[i],
            "rsi_14": df["RSI_14"].iloc[i],
            "adx_14": df["ADX_14"].iloc[i],
            "macd_hist": df["MACD_hist"].iloc[i],
            "atr_pct": round((atr / entry_price) * 100, 2),
            "above_200ema": 1 if entry_price > df["EMA_200"].iloc[i] else 0,
            "supertrend_dir": df["Supertrend_dir"].iloc[i],
            "vol_ratio": round(df["Volume"].iloc[i] / max(1.0, df["Volume_20SMA"].iloc[i]), 2),
        })

    return trades


def run_full_backtest(
    sample_size: Optional[int] = None,
    start_year: int = 2021,
    holding_days: int = 10
) -> pd.DataFrame:
    """
    Runs backtest across the Nifty 200 CSV dataset.
    Returns DataFrame of all trades executed.
    """
    csv_files = [f for f in os.listdir(DATA_DIR) if f.endswith(".csv")]
    if sample_size:
        csv_files = csv_files[:sample_size]

    all_trades = []
    start_time = time.time()
    print(f"Starting backtest across {len(csv_files)} stocks (since year {start_year})...")

    for idx, fname in enumerate(csv_files):
        symbol = fname.replace(".csv", "")
        fpath = os.path.join(DATA_DIR, fname)
        try:
            df = pd.read_csv(fpath)
            df["Date"] = pd.to_datetime(df["Date"])
            df = df.sort_values("Date").reset_index(drop=True)

            if len(df) < 250:
                continue

            df = compute_indicators(df)
            df = generate_signals(df)

            trades = simulate_trades(df, symbol, holding_days=holding_days)
            trades = [t for t in trades if t["entry_date"] >= pd.to_datetime(f"{start_year}-01-01")]
            all_trades.extend(trades)

            if (idx + 1) % 40 == 0 or (idx + 1) == len(csv_files):
                print(f"  Processed {idx + 1}/{len(csv_files)} stocks ({len(all_trades)} trades simulated)...")

        except Exception as e:
            logger.warning(f"Error backtesting {symbol}: {e}")

    elapsed = time.time() - start_time
    print(f"Backtest completed in {elapsed:.2f}s! Total trades simulated: {len(all_trades)}")
    return pd.DataFrame(all_trades)
