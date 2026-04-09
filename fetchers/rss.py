"""
fetchers/rss.py — Fetch and parse RSS/Atom feeds
"""

import logging
import time
from datetime import datetime, timezone
from typing import Optional

import feedparser
import requests

logger = logging.getLogger(__name__)

# Browser-like headers prevent 400/403 rejections from sites that block bots
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}


def fetch_feed(source: dict) -> list[dict]:
    """
    Fetch a single RSS/Atom feed and return a normalised list of articles.
    Each article dict has: url, title, summary, published_dt, source_name, source_type.
    """
    url = source["url"]
    name = source["name"]

    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
    except Exception as exc:
        logger.warning(f"Failed to fetch {name}: {exc}")
        return []

    articles = []
    for entry in feed.entries:
        article_url = entry.get("link", "")
        if not article_url:
            continue

        title = entry.get("title", "").strip()
        summary = _extract_summary(entry)
        published_dt = _parse_date(entry)

        articles.append(
            {
                "url": article_url,
                "title": title,
                "summary": summary,
                "published_dt": published_dt,
                "source_name": name,
                "source_type": source["type"],
            }
        )

    logger.info(f"Fetched {len(articles)} articles from {name}")
    return articles


def fetch_all_feeds(sources: list[dict], delay: float = 0.5) -> list[dict]:
    """Fetch all configured RSS sources with a short polite delay between each."""
    all_articles = []
    for source in sources:
        articles = fetch_feed(source)
        all_articles.extend(articles)
        time.sleep(delay)
    return all_articles


# --- Helpers -----------------------------------------------------------------

def _extract_summary(entry) -> str:
    """Pull the best available summary text from a feed entry."""
    # Prefer content over summary (content is usually fuller)
    if hasattr(entry, "content") and entry.content:
        return entry.content[0].get("value", "")[:2000]
    summary = entry.get("summary", "") or entry.get("description", "")
    return summary[:2000]


def _parse_date(entry) -> Optional[datetime]:
    """Parse publish date from feed entry into a timezone-aware datetime."""
    for field in ("published_parsed", "updated_parsed", "created_parsed"):
        t = entry.get(field)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except Exception:
                continue
    return None
