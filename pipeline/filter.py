"""
pipeline/filter.py — Keyword-based pre-filter before LLM scoring.

Reduces LLM calls by only passing articles that match minimum keyword thresholds.
"""

import logging
import re
from config import KEYWORDS, KEYWORD_THRESHOLDS

logger = logging.getLogger(__name__)

# Pre-compile all keyword patterns (case-insensitive, whole-word-ish)
_PATTERNS = [
    re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)
    for kw in KEYWORDS
]


def keyword_matches(article: dict) -> int:
    """Return the number of distinct keywords found in title + summary."""
    text = f"{article.get('title', '')} {article.get('summary', '')}"
    return sum(1 for pat in _PATTERNS if pat.search(text))


def passes_keyword_filter(article: dict) -> bool:
    """Return True if the article meets the keyword threshold for its source type."""
    source_type = article.get("source_type", "broad")
    threshold = KEYWORD_THRESHOLDS.get(source_type, 1)
    matches = keyword_matches(article)
    article["keyword_matches"] = matches  # Store for later reference
    return matches >= threshold


def filter_articles(articles: list[dict]) -> list[dict]:
    """
    Apply keyword filter to a list of articles.
    Logs how many were dropped per source type.
    """
    passed = []
    dropped_counts: dict[str, int] = {}

    for article in articles:
        if passes_keyword_filter(article):
            passed.append(article)
        else:
            src = article.get("source_type", "unknown")
            dropped_counts[src] = dropped_counts.get(src, 0) + 1

    for src_type, count in dropped_counts.items():
        logger.info(f"Keyword filter dropped {count} articles from '{src_type}' sources")

    logger.info(
        f"Keyword filter: {len(passed)} passed out of {len(articles)} total"
    )
    return passed
