"""
ATBot — Central Configuration
Loads all settings from environment variables / .env file
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List
from functools import lru_cache
import pytz


class Settings(BaseSettings):
    # ── App ──────────────────────────────────────────────────────────────
    app_name: str = "ATBot"
    app_version: str = "1.0.0"
    app_env: str = Field(default="development", env="APP_ENV")
    app_secret_key: str = Field(default="dev-secret-key", env="APP_SECRET_KEY")
    debug: bool = Field(default=True)

    # ── Database ─────────────────────────────────────────────────────────
    database_url: str = Field(
        default="sqlite+aiosqlite:///./atbot.db",
        env="DATABASE_URL"
    )

    # ── API Keys ─────────────────────────────────────────────────────────
    finnhub_api_key: str = Field(default="", env="FINNHUB_API_KEY")
    newsapi_key: str = Field(default="", env="NEWSAPI_KEY")
    fmp_api_key: str = Field(default="", env="FMP_API_KEY")

    # ── Email Alerts ─────────────────────────────────────────────────────
    alert_email_from: str = Field(default="", env="ALERT_EMAIL_FROM")
    alert_email_to: str = Field(default="", env="ALERT_EMAIL_TO")
    smtp_host: str = Field(default="smtp.gmail.com", env="SMTP_HOST")
    smtp_port: int = Field(default=587, env="SMTP_PORT")
    smtp_user: str = Field(default="", env="SMTP_USER")
    smtp_password: str = Field(default="", env="SMTP_PASSWORD")

    # ── Scoring Weights ──────────────────────────────────────────────────
    weight_technical: float = Field(default=0.45, env="WEIGHT_TECHNICAL")
    weight_fundamental: float = Field(default=0.30, env="WEIGHT_FUNDAMENTAL")
    weight_sentiment: float = Field(default=0.25, env="WEIGHT_SENTIMENT")

    # ── Scheduler Intervals ──────────────────────────────────────────────
    market_data_interval_minutes: int = Field(default=5, env="MARKET_DATA_INTERVAL_MINUTES")
    news_refresh_interval_minutes: int = Field(default=10, env="NEWS_REFRESH_INTERVAL_MINUTES")
    fundamentals_refresh_hour: int = Field(default=18, env="FUNDAMENTALS_REFRESH_HOUR")
    morning_briefing_hour: int = Field(default=8, env="MORNING_BRIEFING_HOUR")
    morning_briefing_minute: int = Field(default=45, env="MORNING_BRIEFING_MINUTE")

    # ── Market Hours (IST) ───────────────────────────────────────────────
    market_open_hour: int = Field(default=9, env="MARKET_OPEN_HOUR")
    market_open_minute: int = Field(default=15, env="MARKET_OPEN_MINUTE")
    market_close_hour: int = Field(default=15, env="MARKET_CLOSE_HOUR")
    market_close_minute: int = Field(default=30, env="MARKET_CLOSE_MINUTE")
    market_timezone: str = Field(default="Asia/Kolkata", env="MARKET_TIMEZONE")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

# ── Timezone shortcut ────────────────────────────────────────────────────
IST = pytz.timezone(settings.market_timezone)

# ── NSE symbol lists — canonical source is backend/data/nse_universe.py ──────
# Re-exported here for backward compatibility with existing imports.
from backend.data.nse_universe import NIFTY50 as NIFTY50_SYMBOLS, NIFTY200, get_universe  # noqa: F401

# ── Index tickers (yfinance) ─────────────────────────────────────────────
INDEX_TICKERS = {
    "NIFTY50": "^NSEI",
    "SENSEX": "^BSESN",
    "NIFTYMIDCAP": "^NSEMDCP50",
    "INDIA_VIX": "^INDIAVIX",
    # GIFT Nifty (formerly SGX Nifty) — not yet available on yfinance (^SGXNIFTY delisted)
}

# ── Global cue tickers (for morning briefing) ────────────────────────────
GLOBAL_CUES = {
    "DOW_JONES": "^DJI",
    "NASDAQ": "^IXIC",
    "CRUDE_OIL": "CL=F",
    "GOLD": "GC=F",
    "USD_INR": "INR=X",
}

# ── Signal thresholds ─────────────────────────────────────────────────────
SIGNAL_THRESHOLDS = {
    "STRONG_BUY": 75,
    "BUY": 60,
    "HOLD": 45,
    "SELL": 30,
    # Below 30 → STRONG SELL
}

# ── RSS News Feeds ────────────────────────────────────────────────────────
NEWS_RSS_FEEDS = {
    "economic_times_markets": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "economic_times_stocks": "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
    "moneycontrol_news": "https://www.moneycontrol.com/rss/latestnews.xml",
    "livemint_markets": "https://www.livemint.com/rss/markets",
    "business_standard": "https://www.business-standard.com/rss/markets-106.rss",
}
