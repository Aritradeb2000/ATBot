"""
ATBot — News Feed Fetcher
Fetches and stores news from RSS feeds + Finnhub API
Sources: Economic Times, Moneycontrol, LiveMint, Business Standard, Finnhub
"""

import feedparser
import requests
import hashlib
from datetime import datetime, timezone
from typing import Optional
import logging
import time

from backend.config import settings, NEWS_RSS_FEEDS, IST

logger = logging.getLogger(__name__)


# ── RSS Feed Parser ────────────────────────────────────────────────────────

def fetch_rss_feed(feed_name: str, feed_url: str) -> list[dict]:
    """
    Fetch and parse a single RSS feed.
    Returns list of news articles as dicts.
    """
    articles = []
    try:
        feed = feedparser.parse(feed_url)

        for entry in feed.entries:
            # Parse publish time
            published_at = _parse_feed_date(entry)

            # Generate URL hash as unique ID (avoids duplicates)
            url = entry.get("link", "")
            url_hash = hashlib.md5(url.encode()).hexdigest()

            article = {
                "id": url_hash,
                "headline": _clean_text(entry.get("title", "")),
                "summary": _clean_text(entry.get("summary", entry.get("description", ""))),
                "url": url,
                "source": feed_name,
                "published_at": published_at,
                "symbol": None,   # Will be matched to symbol later
            }

            if article["headline"]:
                articles.append(article)

        logger.info(f"📰 [{feed_name}] Fetched {len(articles)} articles")

    except Exception as e:
        logger.error(f"RSS fetch failed for {feed_name}: {e}")

    return articles


def fetch_all_rss_feeds() -> list[dict]:
    """
    Fetch all configured RSS feeds.
    Returns combined, deduplicated list of articles.
    """
    all_articles = []
    seen_ids = set()

    for feed_name, feed_url in NEWS_RSS_FEEDS.items():
        articles = fetch_rss_feed(feed_name, feed_url)
        for article in articles:
            if article["id"] not in seen_ids:
                seen_ids.add(article["id"])
                all_articles.append(article)
        time.sleep(0.5)   # Polite delay between feeds

    # Sort by published date (newest first)
    all_articles.sort(
        key=lambda x: x["published_at"] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True
    )

    logger.info(f"📰 Total articles fetched: {len(all_articles)}")
    return all_articles


# ── Finnhub News ──────────────────────────────────────────────────────────

def fetch_finnhub_news(symbol: str, days_back: int = 3) -> list[dict]:
    """
    Fetch ticker-specific news from Finnhub API.
    symbol: plain symbol e.g. "RELIANCE" (Finnhub uses exchange prefix)
    Free tier: 60 calls/min

    Returns list of news articles.
    """
    if not settings.finnhub_api_key:
        return []

    try:
        from datetime import date, timedelta
        to_date = date.today()
        from_date = to_date - timedelta(days=days_back)

        # Finnhub uses NSE: prefix for Indian stocks
        finnhub_symbol = f"NSE:{symbol.replace('.NS', '').replace('.BO', '')}"

        url = "https://finnhub.io/api/v1/company-news"
        resp = requests.get(url, params={
            "symbol": finnhub_symbol,
            "from": from_date.isoformat(),
            "to": to_date.isoformat(),
            "token": settings.finnhub_api_key,
        }, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        articles = []
        for item in data:
            url_str = item.get("url", "")
            url_hash = hashlib.md5(url_str.encode()).hexdigest()
            published_at = datetime.fromtimestamp(
                item.get("datetime", 0), tz=timezone.utc
            )

            articles.append({
                "id": url_hash,
                "headline": _clean_text(item.get("headline", "")),
                "summary": _clean_text(item.get("summary", "")),
                "url": url_str,
                "source": item.get("source", "Finnhub"),
                "published_at": published_at,
                "symbol": symbol,
            })

        logger.info(f"📰 Finnhub: {len(articles)} articles for {symbol}")
        return articles

    except Exception as e:
        logger.error(f"Finnhub news fetch failed for {symbol}: {e}")
        return []


# ── Symbol Matching ───────────────────────────────────────────────────────

def match_articles_to_symbols(
    articles: list[dict],
    symbols: list[str],
    company_names: dict[str, str]  # {symbol: company_name}
) -> list[dict]:
    """
    Match market-wide news articles to specific symbols by scanning
    headline + summary for ticker/company name mentions.

    company_names: e.g. {"RELIANCE.NS": "Reliance Industries"}
    """
    for article in articles:
        text = (article["headline"] + " " + (article["summary"] or "")).lower()

        for symbol in symbols:
            plain = symbol.replace(".NS", "").replace(".BO", "").lower()
            company = company_names.get(symbol, "").lower()

            if plain in text or (company and len(company) > 4 and company in text):
                article["symbol"] = symbol
                break   # Match to first found symbol

    return articles


# ── Utilities ─────────────────────────────────────────────────────────────

def _parse_feed_date(entry) -> Optional[datetime]:
    """Parse publish date from feed entry."""
    try:
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
            return datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
    except Exception:
        pass
    return datetime.now(timezone.utc)


def _clean_text(text: str) -> str:
    """Strip HTML tags and excessive whitespace from text."""
    if not text:
        return ""
    import re
    text = re.sub(r"<[^>]+>", " ", text)          # Remove HTML tags
    text = re.sub(r"&[a-z]+;", " ", text)          # Remove HTML entities
    text = re.sub(r"\s+", " ", text).strip()        # Normalize whitespace
    return text[:1000]                              # Cap at 1000 chars
