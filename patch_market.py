with open(r'backend\api\routes\market.py', 'r', encoding='utf-8') as f:
    text = f.read()

import re

new_route = """@router.get("/ohlcv/{symbol}")
async def get_ohlcv(
    symbol: str,
    period: str = Query(None, description="yfinance period: max, 730d, 60d, 7d"),
    interval: str = Query("1d", description="yfinance interval: 1m, 5m, 15m, 30m, 1h, 1d, 1wk"),
):
    \"\"\"
    Returns OHLCV data for a symbol formatted for lightweight-charts.
    Dynamically handles max periods for intraday intervals.
    \"\"\"
    try:
        # Map maximum allowed periods for intraday data if user specifies "max" or doesn't specify
        if not period or period == "max":
            if interval == "1m":
                period = "7d"
            elif interval in ["5m", "15m", "30m"]:
                period = "60d"
            elif interval in ["1h", "60m"]:
                period = "730d"
            else:
                period = "max"

        df = fetch_ohlcv(symbol, interval=interval, period=period)
        if df is None or df.empty:
            return []

        bars = []
        is_intraday = interval in ["1m", "5m", "15m", "30m", "1h", "60m"]
        for idx, row in df.iterrows():
            # lightweight-charts expects UNIX timestamp in seconds for intraday,
            # or 'YYYY-MM-DD' string for daily/weekly.
            if is_intraday:
                time_val = int(idx.timestamp())
            else:
                time_val = idx.strftime("%Y-%m-%d")

            bars.append({
                "time": time_val,
                "open":  round(float(row["Open"]),  2),
                "high":  round(float(row["High"]),  2),
                "low":   round(float(row["Low"]),   2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]) if "Volume" in row else 0,
            })

        return bars
    except Exception as e:
        logger.error(f"OHLCV fetch failed for {symbol}: {e}")
        return []"""

pattern = re.compile(r'@router\.get\("/ohlcv/\{symbol\}"\).*?return \[\]', re.DOTALL)
text = pattern.sub(new_route, text)

with open(r'backend\api\routes\market.py', 'w', encoding='utf-8') as f:
    f.write(text)
