"""
ATBot — News Feed Fetcher
Fetches and stores news from RSS feeds + Zerodha Pulse + Finnhub API
Sources: Zerodha Pulse (pulse.zerodha.com), Economic Times, Moneycontrol,
LiveMint, Business Standard, The Hindu, NDTV Profit, Finshots, Finnhub
"""

import feedparser
import requests
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict
import logging
import time
import re
from urllib.parse import urlparse, quote_plus

from backend.config import settings, NEWS_RSS_FEEDS, IST
from backend.data.nse_universe import NIFTY50 as NIFTY50_SYMBOLS

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
_feed_cache = {}  # Store etag/modified per feed

# Common Indian Equities Aliases for High-Precision News Matching
DEFAULT_COMPANY_ALIASES = {
    "RELIANCE.NS": ["reliance", "ril", "jio"],
    "TCS.NS": ["tcs", "tata consultancy"],
    "INFY.NS": ["infosys", "infy"],
    "HDFCBANK.NS": ["hdfc bank", "hdfc"],
    "ICICIBANK.NS": ["icici bank", "icici"],
    "SBIN.NS": ["state bank of india", "state bank", "sbi"],
    "BHARTIARTL.NS": ["bharti airtel", "airtel"],
    "TATAMOTORS.NS": ["tata motors", "jlr"],
    "ITC.NS": ["itc"],
    "LT.NS": ["larsen & toubro", "larsen and toubro", "l&t", "larsen"],
    "KOTAKBANK.NS": ["kotak mahindra", "kotak bank", "kotak"],
    "AXISBANK.NS": ["axis bank", "axis"],
    "MARUTI.NS": ["maruti suzuki", "maruti"],
    "SUNPHARMA.NS": ["sun pharma", "sun pharmaceutical"],
    "TITAN.NS": ["titan company", "titan"],
    "BAJFINANCE.NS": ["bajaj finance"],
    "BAJAJFINSV.NS": ["bajaj finserv"],
    "WIPRO.NS": ["wipro"],
    "HCLTECH.NS": ["hcl tech", "hcl technologies", "hcl"],
    "NTPC.NS": ["ntpc"],
    "ONGC.NS": ["ongc", "oil and natural gas"],
    "POWERGRID.NS": ["power grid", "powergrid"],
    "ADANIENT.NS": ["adani enterprises", "adani ent"],
    "ADANIPORTS.NS": ["adani ports", "sez"],
    "COALINDIA.NS": ["coal india"],
    "TATASTEEL.NS": ["tata steel"],
    "JSWSTEEL.NS": ["jsw steel", "jsw"],
    "ASIANPAINT.NS": ["asian paints", "asian paint"],
    "HINDUNILVR.NS": ["hindustan unilever", "hul"],
    "NESTLEIND.NS": ["nestle india", "nestle"],
    "ULTRACEMCO.NS": ["ultratech cement", "ultratech"],
    "GRASIM.NS": ["grasim industries", "grasim"],
    "CIPLA.NS": ["cipla"],
    "DRREDDY.NS": ["dr reddy", "dr. reddy"],
    "EICHERMOT.NS": ["eicher motors", "royal enfield", "eicher"],
    "M&M.NS": ["mahindra & mahindra", "mahindra and mahindra", "m&m"],
    "HEROMOTOCO.NS": ["hero motocorp", "hero moto"],
    "DIVISLAB.NS": ["divi's lab", "divis lab"],
    "HINDALCO.NS": ["hindalco"],
    "BPCL.NS": ["bharat petroleum", "bpcl"],
    "APOLLOHOSP.NS": ["apollo hospitals", "apollo hospital"],
    "BRITANNIA.NS": ["britannia industries", "britannia"],
    "TECHM.NS": ["tech mahindra"],
    "INDUSINDBK.NS": ["indusind bank", "indusind"],
    "TATACONSUM.NS": ["tata consumer"],
    "BEL.NS": ["bharat electronics", "bel"],
    "SHRIRAMFIN.NS": ["shriram finance"],
}


# ── RSS Feed Parser ───────────────────────────────────────────────────────────

def fetch_rss_feed(feed_name: str, feed_url: str) -> list[dict]:
    """Fetch and parse an individual RSS/Atom feed."""
    articles = []
    try:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml"}
        cache = _feed_cache.get(feed_name, {})
        if "etag" in cache and cache["etag"]:
            headers["If-None-Match"] = cache["etag"]
        if "modified" in cache and cache["modified"]:
            headers["If-Modified-Since"] = cache["modified"]

        resp = requests.get(feed_url, headers=headers, timeout=10)
        if resp.status_code == 304:
            logger.info(f"[{feed_name}] Not modified since last fetch")
            return []

        if resp.status_code != 200:
            logger.warning(f"[{feed_name}] Returned status {resp.status_code}")
            return []

        _feed_cache[feed_name] = {
            "etag": resp.headers.get("etag"),
            "modified": resp.headers.get("last-modified")
        }

        feed = feedparser.parse(resp.content)
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=7)

        for entry in feed.entries:
            published_at = _parse_feed_date(entry)
            if published_at < cutoff_date:
                continue

            url = entry.get("link", "")
            if not url:
                continue
            url_hash = hashlib.md5(url.encode()).hexdigest()
            headline = _clean_text(entry.get("title", ""))
            summary = _clean_text(entry.get("summary", entry.get("description", "")))

            # Source attribution formatting
            if feed_name == "zerodha_pulse":
                netloc = urlparse(url).netloc.replace("www.", "").lower()
                domain_map = {
                    "economictimes.indiatimes.com": "Economic Times",
                    "thehindu.com": "The Hindu",
                    "thehindubusinessline.com": "Business Line",
                    "business-standard.com": "Business Standard",
                    "livemint.com": "LiveMint",
                    "ndtvprofit.com": "NDTV Profit",
                    "finshots.in": "Finshots",
                    "moneycontrol.com": "Moneycontrol",
                    "reuters.com": "Reuters",
                    "bloomberg.com": "Bloomberg",
                    "cnbctv18.com": "CNBC-TV18",
                }
                pub = domain_map.get(netloc)
                source_label = f"Pulse • {pub}" if pub else "Pulse by Zerodha"
            else:
                source_label = feed_name.replace("_", " ").title()

            if headline:
                articles.append({
                    "id": url_hash,
                    "headline": headline,
                    "summary": summary,
                    "url": url,
                    "source": source_label,
                    "published_at": published_at,
                    "symbol": None,
                })

        logger.info(f"[{feed_name}] Fetched {len(articles)} articles")

    except Exception as e:
        logger.error(f"RSS fetch failed for {feed_name}: {e}")

    return articles


def fetch_zerodha_pulse(symbol: Optional[str] = None, max_articles: int = 50) -> list[dict]:
    """
    Fetch latest curated Indian financial news directly from Zerodha Pulse (pulse.zerodha.com).
    Optionally filter by ticker symbol or company name.
    """
    url = "https://pulse.zerodha.com/feed.xml"
    articles = fetch_rss_feed("zerodha_pulse", url)
    if not articles:
        return []

    if symbol:
        matched_articles = []
        sym_clean = symbol.upper().replace(".NS", "").replace(".BO", "")
        aliases = DEFAULT_COMPANY_ALIASES.get(symbol.upper(), [sym_clean.lower()])
        if sym_clean.lower() not in aliases:
            aliases.append(sym_clean.lower())

        for a in articles:
            text = (a.get("headline", "") + " " + (a.get("summary", "") or "")).lower()
            # Test word boundaries
            is_match = False
            for alias in aliases:
                pattern = r'\b' + re.escape(alias) + r'\b'
                if re.search(pattern, text):
                    is_match = True
                    break
            if is_match:
                a_copy = dict(a)
                a_copy["symbol"] = symbol.upper()
                matched_articles.append(a_copy)
        return matched_articles[:max_articles]

    return articles[:max_articles]


def fetch_all_rss_feeds() -> list[dict]:
    """
    Fetch and aggregate all RSS feeds defined in NEWS_RSS_FEEDS (with Zerodha Pulse prioritized).
    De-duplicates identical articles across feeds.
    """
    all_articles = []
    seen_ids = set()
    seen_headlines = set()

    for feed_name, feed_url in NEWS_RSS_FEEDS.items():
        articles = fetch_rss_feed(feed_name, feed_url)
        for article in articles:
            h_norm = article["headline"].lower()
            if article["id"] not in seen_ids and h_norm not in seen_headlines:
                seen_ids.add(article["id"])
                seen_headlines.add(h_norm)
                all_articles.append(article)
        time.sleep(0.5)

    all_articles.sort(
        key=lambda x: x["published_at"] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True
    )
    logger.info(f"Total RSS articles fetched across feeds: {len(all_articles)}")
    return all_articles


def match_articles_to_symbols(
    articles: list[dict],
    symbols: list[str] = None,
    company_names: dict[str, str] = None
) -> list[dict]:
    """
    Match market-wide news articles to specific stock symbols by scanning
    headline + summary for ticker and company name mentions using word boundaries.
    """
    if symbols is None:
        symbols = list(DEFAULT_COMPANY_ALIASES.keys())

    for article in articles:
        if article.get("symbol"):
            continue

        text = (article["headline"] + " " + (article["summary"] or "")).lower()

        for symbol in symbols:
            plain = symbol.replace(".NS", "").replace(".BO", "").lower()
            aliases = DEFAULT_COMPANY_ALIASES.get(symbol, [plain])
            if company_names and symbol in company_names:
                c_name = company_names[symbol].lower()
                if c_name not in aliases:
                    aliases.append(c_name)

            matched = False
            for alias in aliases:
                pattern = r'\b' + re.escape(alias) + r'\b'
                if re.search(pattern, text):
                    article["symbol"] = symbol
                    matched = True
                    break

            if matched:
                break

    return articles


def fetch_fallback_news(symbol: str, max_articles: int = 25) -> list[dict]:
    """
    Fallback news pipeline:
    1. Check Zerodha Pulse for articles mentioning symbol/company.
    2. Fall back to Google News RSS to fill remaining slots.
    """
    combined = []
    seen_urls = set()

    # Step 1: Zerodha Pulse check
    try:
        pulse_news = fetch_zerodha_pulse(symbol=symbol, max_articles=max_articles)
        for a in pulse_news:
            if a["url"] not in seen_urls:
                seen_urls.add(a["url"])
                combined.append(a)
    except Exception as e:
        logger.warning(f"Zerodha Pulse check failed for {symbol}: {e}")

    if len(combined) >= max_articles:
        return combined[:max_articles]

    # Step 2: Google News search
    try:
        plain_symbol = symbol.replace(".NS", "").replace(".BO", "")
        aliases = DEFAULT_COMPANY_ALIASES.get(symbol, [plain_symbol])
        search_term = aliases[1] if len(aliases) > 1 else plain_symbol
        query = quote_plus(f'"{search_term}" when:7d')
        url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"

        headers = {"User-Agent": USER_AGENT}
        resp = requests.get(url, headers=headers, timeout=10)
        feed = feedparser.parse(resp.content)

        for entry in feed.entries:
            url_str = entry.get("link", "")
            if not url_str or url_str in seen_urls:
                continue

            seen_urls.add(url_str)
            url_hash = hashlib.md5(url_str.encode()).hexdigest()
            published_at = _parse_feed_date(entry)

            combined.append({
                "id": url_hash,
                "headline": _clean_text(entry.get("title", "")),
                "summary": _clean_text(entry.get("summary", entry.get("description", ""))),
                "url": url_str,
                "source": entry.get("source", {}).get("title", "Google News"),
                "published_at": published_at,
                "symbol": symbol,
            })

            if len(combined) >= max_articles:
                break

    except Exception as e:
        logger.warning(f"Google News fallback failed for {symbol}: {e}")

    combined.sort(key=lambda x: x["published_at"], reverse=True)
    return combined[:max_articles]


def fetch_finnhub_news(symbol: str, days_back: int = 365, max_articles: int = 25) -> list[dict]:
    """
    Fetch company-specific news.
    If Finnhub is available, queries Finnhub.
    Falls back seamlessly to Zerodha Pulse + Google News.
    """
    if not settings.finnhub_api_key:
        logger.info(f"Finnhub API key missing, fetching via Pulse & Google News for {symbol}")
        return fetch_fallback_news(symbol, max_articles)

    try:
        from datetime import date
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
            if not url_str:
                continue
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
            logger.info(f"Finnhub returned 0 articles for {symbol}, using Pulse & fallback")
            return fetch_fallback_news(symbol, max_articles)

        return articles

    except Exception as e:
        logger.warning(f"Finnhub news fetch failed for {symbol}: {e}, using Pulse & fallback")
        return fetch_fallback_news(symbol, max_articles)


# ── Utilities ─────────────────────────────────────────────────────────────────

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
    """Strip HTML tags, entities and excessive whitespace from text."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-z0-9#]+;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:1000]
