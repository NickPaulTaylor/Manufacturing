"""
pipeline/llm.py — Batch LLM scoring via Google Gemini.

Sends articles in batches to Gemini with a journalist persona prompt.
Returns each article with a relevance score (1-5), category tag, and
editorial note. Articles below GEMINI_MIN_SCORE are filtered out.
"""

import json
import logging
import os
import time

import requests

from config import (
    GEMINI_MODEL,
    GEMINI_API_BASE,
    GEMINI_BATCH_SIZE,
    GEMINI_DELAY_SECONDS,
    GEMINI_MIN_SCORE,
    GEMINI_RPM_LIMIT,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a senior journalist and editor at a biopharma trade publication 
specialising in pharmaceutical and biopharmaceutical manufacturing, supply chain, and 
regulatory compliance. Your job is to assess incoming news items and decide which are 
worth covering.

You will receive a JSON array of news items. For each item, return a JSON array with 
the same number of objects, each containing:
  - "index": the item's index (integer, 0-based)
  - "score": relevance score from 1 to 5 where:
      5 = Must cover: major regulatory action, significant capacity/M&A news, supply crisis
      4 = Strong story: notable facility news, CDMO deal, warning letter, expansion
      3 = Worth monitoring: industry trend, minor facility update, relevant partnership
      2 = Marginal: tangentially related, likely clinical/commercial not manufacturing
      1 = Not relevant: no manufacturing angle
  - "category": one of ["regulatory", "capacity", "supply_chain", "MA", "partnership", 
                         "quality", "technology", "workforce", "other"]
  - "note": one sentence (max 25 words) on why this is or isn't newsworthy from a 
            manufacturing perspective

Return ONLY a valid JSON array. No preamble, no markdown, no backticks."""


def score_articles(articles: list[dict]) -> list[dict]:
    """
    Score all articles using Gemini in batches.
    Returns only articles scoring >= GEMINI_MIN_SCORE, with score/category/note added.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY environment variable not set")

    scored = []
    batches = _chunk(articles, GEMINI_BATCH_SIZE)
    request_count = 0
    batch_start_time = time.monotonic()

    for batch_num, batch in enumerate(batches):
        # Rate limit: stay below GEMINI_RPM_LIMIT requests per minute
        if request_count >= GEMINI_RPM_LIMIT:
            elapsed = time.monotonic() - batch_start_time
            sleep_for = max(0, 61 - elapsed)
            logger.info(f"Rate limit pause: sleeping {sleep_for:.1f}s")
            time.sleep(sleep_for)
            request_count = 0
            batch_start_time = time.monotonic()

        logger.info(f"Scoring batch {batch_num + 1}/{len(batches)} ({len(batch)} articles)")

        results = _score_batch(batch, api_key)

        for result in results:
            idx = result.get("index")
            score = result.get("score", 0)
            if idx is None or idx >= len(batch):
                continue
            article = batch[idx].copy()
            article["llm_score"] = score
            article["llm_category"] = result.get("category", "other")
            article["llm_note"] = result.get("note", "")
            if score >= GEMINI_MIN_SCORE:
                scored.append(article)

        request_count += 1
        time.sleep(GEMINI_DELAY_SECONDS)

    # Sort by score descending
    scored.sort(key=lambda a: a["llm_score"], reverse=True)
    logger.info(f"LLM scoring: {len(scored)} articles passed the score threshold")
    return scored


def _score_batch(batch: list[dict], api_key: str) -> list[dict]:
    """Send one batch to Gemini and parse the JSON response."""
    items = [
        {
            "index": i,
            "title": a.get("title", ""),
            "summary": a.get("summary", "")[:500],  # Truncate to save tokens
            "source": a.get("source_name", ""),
        }
        for i, a in enumerate(batch)
    ]

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": (
                            f"{SYSTEM_PROMPT}\n\n"
                            f"News items to assess:\n{json.dumps(items, indent=2)}"
                        )
                    }
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.1,  # Low temp for consistent scoring
            "maxOutputTokens": 2048,
        },
    }

    url = f"{GEMINI_API_BASE}/{GEMINI_MODEL}:generateContent?key={api_key}"

    try:
        resp = requests.post(url, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        # Strip any accidental markdown fences
        text = text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        return json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning(f"Gemini returned unparseable JSON: {exc}. Raw: {text[:300]}")
        return []
    except Exception as exc:
        logger.warning(f"Gemini API call failed: {exc}")
        return []


def _chunk(lst: list, size: int) -> list[list]:
    return [lst[i : i + size] for i in range(0, len(lst), size)]
