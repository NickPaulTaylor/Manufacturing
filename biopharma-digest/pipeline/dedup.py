"""
pipeline/dedup.py — URL-based deduplication and persistent state management.

State is stored as a JSON file and committed back to the repo after each run,
so previously seen URLs are not re-surfaced on subsequent days.
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone

from config import STATE_FILE, MAX_STATE_AGE_DAYS

logger = logging.getLogger(__name__)


def load_state() -> dict:
    """Load the seen-URLs state file. Returns empty dict if not found."""
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning(f"Could not load state file: {exc}. Starting fresh.")
        return {}


def save_state(state: dict) -> None:
    """Persist the seen-URLs state, pruning entries older than MAX_STATE_AGE_DAYS."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_STATE_AGE_DAYS)
    pruned = {
        url: ts
        for url, ts in state.items()
        if datetime.fromisoformat(ts) > cutoff
    }

    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(pruned, f, indent=2)

    removed = len(state) - len(pruned)
    if removed:
        logger.info(f"Pruned {removed} expired URLs from state")
    logger.info(f"State saved: {len(pruned)} URLs tracked")


def deduplicate(articles: list[dict], state: dict) -> tuple[list[dict], dict]:
    """
    Remove articles whose URLs are already in state.
    Returns (new_articles, updated_state).
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    new_articles = []

    for article in articles:
        url = article["url"]
        if url in state:
            continue
        new_articles.append(article)
        state[url] = now_iso

    duplicate_count = len(articles) - len(new_articles)
    if duplicate_count:
        logger.info(f"Dedup removed {duplicate_count} already-seen articles")
    logger.info(f"{len(new_articles)} new articles after deduplication")

    return new_articles, state
