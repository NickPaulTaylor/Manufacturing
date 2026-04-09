"""
pipeline/llm.py — Batch LLM scoring via Google Gemini (google-genai SDK).

Uses the same SDK and model as the working monitor script to avoid 429 errors.
"""

import json
import logging
import os
import time

from google import genai

from config import (
    GEMINI_MODEL,
    GEMINI_BATCH_SIZE,
    GEMINI_DELAY_SECONDS,
    GEMINI_MIN_SCORE,
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

    client = genai.Client(api_key=api_key)
    scored = []
    batches = _chunk(articles, GEMINI_BATCH_SIZE)

    for batch_num, batch in enumerate(batches):
        logger.info(f"Scoring batch {batch_num + 1}/{len(batches)} ({len(batch)} articles)")
        results = _score_batch(batch, client)

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

        time.sleep(GEMINI_DELAY_SECONDS)

    scored.sort(key=lambda a: a["llm_score"], reverse=True)
    logger.info(f"LLM scoring: {len(scored)} articles passed the score threshold")
    return scored


def _score_batch(batch: list[dict], client) -> list[dict]:
    """Send one batch to Gemini via the SDK with exponential backoff on failure."""
    items = [
        {
            "index": i,
            "title": a.get("title", ""),
            "summary": a.get("summary", "")[:500],
            "source": a.get("source_name", ""),
        }
        for i, a in enumerate(batch)
    ]

    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"News items to assess:\n{json.dumps(items, indent=2)}"
    )

    max_retries = 4
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
            )
            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1]
            if text.endswith("```"):
                text = text.rsplit("\n", 1)[0]
            return json.loads(text.strip())

        except json.JSONDecodeError as exc:
            logger.warning(f"Gemini returned unparseable JSON: {exc}")
            return []
        except Exception as exc:
            wait = 15 * (2 ** attempt)
            if attempt < max_retries - 1:
                logger.warning(f"Gemini error (attempt {attempt+1}/{max_retries}): {exc}. Retrying in {wait}s...")
                time.sleep(wait)
            else:
                logger.warning(f"Gemini batch failed after {max_retries} attempts: {exc}")
                return []

    return []


def _chunk(lst: list, size: int) -> list[list]:
    return [lst[i: i + size] for i in range(0, len(lst), size)]
