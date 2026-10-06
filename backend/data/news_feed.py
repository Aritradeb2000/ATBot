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



# ── RSS Feed Parser ───────────────────────────────────────────────────────

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
_feed_cache = {}  # Store etag/modified per feed

def fetch_rss_feed(feed_name: str, feed_url: str) -> list[dict]:
    articles = []
    try:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml"}
        # Polite polling headers
        cache = _feed_cache.get(feed_name, {})
        if "etag" in cache: headers["If-None-Match"] = cache["etag"]
        if "modified" in cache: headers["If-Modified-Since"] = cache["modified"]

        resp = requests.get(feed_url, headers=headers, timeout=10)
        if resp.status_code == 304:
            logger.info(f"[{feed_name}] Not modified since last fetch")
            return []
            
        if resp.status_code != 200:
            logger.warning(f"[{feed_name}] Returned {resp.status_code}")
            return []
            
        # Update cache headers
        _feed_cache[feed_name] = {
            "etag": resp.headers.get("etag"),
            "modified": resp.headers.get("last-modified")
        }

        import feedparser
        feed = feedparser.parse(resp.content)
        
        # Recency window (e.g. 7 days max for market feeds)
        from datetime import datetime, timedelta, timezone
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=7)

        for entry in feed.entries:
            published_at = _parse_feed_date(entry)
            if published_at < cutoff_date:
                continue

            url = entry.get("link", "")
            url_hash = hashlib.md5(url.encode()).hexdigest()
            headline = _clean_text(entry.get("title", ""))
            
            if headline:
                articles.append({
                    "id": url_hash,
                    "headline": headline,
                    "summary": _clean_text(entry.get("summary", entry.get("description", ""))),
                    "url": url,
                    "source": feed_name,
                    "published_at": published_at,
                    "symbol": None,
                })

        logger.info(f"[{feed_name}] Fetched {len(articles)} fresh articles")

    except Exception as e:
        logger.error(f"RSS fetch failed for {feed_name}: {e}")

    return articles

def fetch_all_rss_feeds() -> list[dict]:
    all_articles = []
    seen_ids = set()
    seen_headlines = set()  # Dedup exact identical headlines across feeds

    for feed_name, feed_url in NEWS_RSS_FEEDS.items():
        articles = fetch_rss_feed(feed_name, feed_url)
        for article in articles:
            # Dedupe logic
            h_norm = article["headline"].lower()
            if article["id"] not in seen_ids and h_norm not in seen_headlines:
                seen_ids.add(article["id"])
                seen_headlines.add(h_norm)
                all_articles.append(article)
        import time
        time.sleep(1.0)   # Polite delay

    all_articles.sort(
        key=lambda x: x["published_at"] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True
    )
    logger.info(f"Total articles fetched: {len(all_articles)}")
    return all_articles

def fetch_fallback_news(symbol: str, max_articles: int = 25) -> list[dict]:
    """Fallback: fetch company-specific news via Google News RSS when primary APIs fail."""
    import feedparser
    from urllib.parse import quote_plus
    import requests
    import hashlib
    
    try:
        # Use company name rather than ticker, quoted for multi-word
        # e.g., "Reliance Industries" when:1d
        plain_symbol = symbol.replace('.NS', '').replace('.BO', '')
        # Quoting it prevents false matches.
        query = quote_plus(f'"{plain_symbol}" when:1d')
        url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
        
        headers = {"User-Agent": USER_AGENT}
        resp = requests.get(url, headers=headers, timeout=10)
        feed = feedparser.parse(resp.content)
        
        if not feed.entries:
            return []
            
        articles = []
        for entry in feed.entries:
            url_str = entry.get("link", "")
            if not url_str: continue
                
            url_hash = hashlib.md5(url_str.encode()).hexdigest()
            published_at = _parse_feed_date(entry)
            
            articles.append({
                "id": url_hash,
                "headline": _clean_text(entry.get("title", "")),
                "summary": _clean_text(entry.get("summary", entry.get("description", ""))),
                "url": url_str,
                "source": entry.get("source", {}).get("title", "Google News"),
                "published_at": published_at,
                "symbol": symbol,
            })
            
        articles.sort(key=lambda x: x["published_at"], reverse=True)
        return articles[:max_articles]
        
    except Exception as e:
        logger.error(f"Google News fallback failed for {symbol}: {e}")
        return []

def fetch_finnhub_news(symbol: str, days_back: int = 365, max_articles: int = 25) -> list[dict]:
    """
    Fetch ticker-specific news from Finnhub API.
    Looks back up to a year to ensure we find news, but caps the results 
    to `max_articles` so the AI sentiment model doesn't take 5 minutes to run.
    """
    if not settings.finnhub_api_key:
        logger.info(f"Finnhub API key missing, falling back to Google News for {symbol}")
        return fetch_fallback_news(symbol, max_articles)

    try:
        from datetime import date, timedelta
        to_date = date.today()
        from_date = to_date - timedelta(days=days_back)

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
            if not url_str: continue
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

        articles.sort(key=lambda x: x["published_at"], reverse=True)
        articles = articles[:max_articles]
        
        if not articles:
            logger.info(f"Finnhub returned 0 articles for {symbol}, falling back to Google News")
            return fetch_fallback_news(symbol, max_articles)
            
        logger.info(f"Finnhub: {len(articles)} articles for {symbol}")
        return articles

    except Exception as e:
        logger.error(f"Finnhub news fetch failed for {symbol}: {e}, falling back to Google News")
        return fetch_fallback_news(symbol, max_articles)


# -- NewsAPI ------------------------------------------------------------------
# Free tier: 100 req/day.  Use broad market queries (not per-stock) so we stay

# ── Symbol Matching ───────────────────────────────────────────────────────

import re

def match_articles_to_symbols(
    articles: list[dict],
    symbols: list[str],
    company_names: dict[str, str]
) -> list[dict]:
    """
    Match market-wide news articles to specific symbols using regex word boundaries.
    """
    for article in articles:
        text = (article["headline"] + " " + (article["summary"] or "")).lower()

        for symbol in symbols:
            plain = symbol.replace(".NS", "").replace(".BO", "").lower()
            company = company_names.get(symbol, "").lower()
            
            # Avoid false positives for short tickers (like ITC, TCS)
            # Use word boundaries  to ensure we match the whole word
            pattern_plain = r'\b' + re.escape(plain) + r'\b'
            pattern_company = r'\b' + re.escape(company) + r'\b' if company and len(company) > 3 else None
            
            if re.search(pattern_plain, text) or (pattern_company and re.search(pattern_company, text)):
                article["symbol"] = symbol
                break

    return articles

# ── Utilities ──────────────────────────────────────────────────────────

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


# -- NewsAPI ------------------------------------------------------------------
# Free tier: 100 req/day.  Use broad market queries (not per-stock) so we stay
# within the limit.  Articles are attributed to stocks by match_articles_to_symbols.

NEWSAPI_BASE = "https://newsapi.org/v2/everything"

NEWSAPI_QUERIES = [
    "NSE OR BSE OR Nifty OR Sensex",
    "India stock market OR Indian equities",
    "RBI monetary policy OR India inflation",
    "FII DII India investment",
]

def fetch_newsapi_news(max_articles: int = 50) -> list:
    """
    Fetch market-wide Indian business news from NewsAPI.
    Uses broad queries to stay within the 100 req/day free limit.
    """
    if not settings.newsapi_key:
        logger.info("NewsAPI key missing, skipping")
        return []

    import time as _time
    from datetime import date, timedelta
    from_date = (date.today() - timedelta(days=3)).isoformat()

    all_articles = []
    seen_ids = set()

    for query in NEWSAPI_QUERIES:
        try:
            resp = requests.get(
                NEWSAPI_BASE,
                params={
                    "q":        query,
                    "from":     from_date,
                    "language": "en",
                    "sortBy":   "publishedAt",
                    "pageSize": 20,
                    "apiKey":   settings.newsapi_key,
                },
                timeout=10,
            )
            resp.raise_for_status()
            for item in resp.json().get("articles", []):
                url_str = item.get("url", "")
                if not url_str:
                    continue
                uid = hashlib.md5(url_str.encode()).hexdigest()
                if uid in seen_ids:
                    continue
                seen_ids.add(uid)
                try:
                    pub = datetime.fromisoformat(
                        item.get("publishedAt", "").replace("Z", "+00:00")
                    )
                except Exception:
                    pub = datetime.now(timezone.utc)
                all_articles.append({
                    "id":           uid,
                    "headline":     _clean_text(item.get("title", "")),
                    "summary":      _clean_text(item.get("description") or item.get("content", "")),
                    "url":          url_str,
                    "source":       (item.get("source") or {}).get("name", "NewsAPI"),
                    "published_at": pub,
                    "symbol":       None,
                })
            _time.sleep(0.3)
        except Exception as e:
            logger.error(f"NewsAPI query '{query}' failed: {e}")

    all_articles.sort(key=lambda x: x["published_at"], reverse=True)
    result = all_articles[:max_articles]
    logger.info(f"NewsAPI: {len(result)} articles from {len(NEWSAPI_QUERIES)} queries")
    return result


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
