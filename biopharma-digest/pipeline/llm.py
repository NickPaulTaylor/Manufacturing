"""
pipeline/llm.py — Batch LLM scoring via Google Gemini (google-genai SDK).
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

SYSTEM_PROMPT = """You are a senior editor at a trade publication covering pharmaceutical and
biopharmaceutical MANUFACTURING. Your job is to filter news strictly for manufacturing relevance.

You will receive a JSON array of news items. For each, return a JSON array with:
  - "index": integer (0-based)
  - "score": 1-5 (defined below)
  - "category": one of ["regulatory", "capacity", "supply_chain", "MA", "partnership",
                         "quality", "technology", "workforce", "other"]
  - "note": one sentence, max 20 words, stating the specific manufacturing fact — not why
            it might be relevant, the actual fact that makes it relevant.

SCORING — be strict:
  5 = Direct manufacturing news: FDA warning letter or consent decree at a pharma/biotech
      facility; plant closure or shutdown; drug shortage caused by manufacturing failure;
      new manufacturing site announced or acquired; CDMO/CMO wins or loses a major contract.
  4 = Clear manufacturing story: facility expansion or investment with named site; capacity
      announcement; GMP compliance remediation update; manufacturing partnership with named
      parties and explicit scope; supply disruption with identified manufacturing cause;
      reshoring or nearshoring of specific production lines.
  3 = Manufacturing-adjacent with explicit evidence: CDMO/CMO M&A where manufacturing
      assets are explicitly named; drug shortage where cause is unclear; tariff or trade
      policy that explicitly names manufacturing operations being affected; bioprocessing
      technology at commercial scale with a named company deploying it.
  2 = Weak or speculative link: M&A or deals where manufacturing implications are implied
      but not stated in the article; regulatory approvals with no facility or supply angle.
  1 = Not relevant — score 1 for ALL of the following, regardless of any manufacturing
      mention in the summary:
        - Medical devices and medtech (510k, PMA, CE mark)
        - Clinical trial results or drug efficacy data
        - Drug pricing, reimbursement, or commercial strategy
        - Marketing or promotional compliance
        - Executive appointments, departures, or leadership changes
        - Basic research, drug discovery, or target identification
        - AI tools for drug development or computational biology
        - Company earnings, financial results, or investor news
        - Policy debates or government negotiations without named manufacturing actions
        - Regulatory approvals (drug or device) unless the approval explicitly triggers
          a named manufacturing scale-up, site change, or capacity investment

CRITICAL RULE: If you are constructing a manufacturing angle rather than directly reporting
one that is explicitly present in the title or summary, score it 1 or 2. Do not infer.
Do not speculate. The manufacturing relevance must be stated in the article itself.

Return ONLY a valid JSON array. No preamble, no markdown, no backticks."""


def score_articles(articles: list[dict]) -> list[dict]:
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
