"""
fetchers/openfda.py — Fetch enforcement actions from the openFDA API.

openFDA is explicitly designed for programmatic/automated access and works
from any IP including GitHub Actions. No API key required for low volumes.
Covers drug recalls and enforcement actions, which are high-signal for
manufacturing compliance news.

Docs: https://open.fda.gov/apis/drug/enforcement/
"""

import logging
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)

OPENFDA_BASE = "https://api.fda.gov/drug/enforcement.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; BioPharmaDigest/1.0)"
}


def fetch_fda_enforcement() -> list[dict]:
    """
    Fetch recent drug enforcement actions (recalls) from openFDA.
    Returns normalised article dicts compatible with the rest of the pipeline.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=36)
    date_str = cutoff.strftime("%Y%m%d")

    params = {
        "search": f"recall_initiation_date:[{date_str}+TO+99991231]",
        "limit": 50,
        "sort": "recall_initiation_date:desc",
    }

    try:
        resp = requests.get(OPENFDA_BASE, params=params, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
    except Exception as exc:
        logger.warning(f"openFDA enforcement fetch failed: {exc}")
        return []

    articles = []
    for r in results:
        company = r.get("recalling_firm", "Unknown firm")
        product = r.get("product_description", "")[:120]
        reason = r.get("reason_for_recall", "")[:200]
        status = r.get("status", "")
        recall_class = r.get("classification", "")  # Class I/II/III
        date_str_raw = r.get("recall_initiation_date", "")

        published_dt = None
        if date_str_raw:
            try:
                published_dt = datetime.strptime(date_str_raw, "%Y%m%d").replace(
                    tzinfo=timezone.utc
                )
            except Exception:
                pass

        # Build a readable URL to the openFDA enforcement search
        recall_number = r.get("recall_number", "")
        url = f"https://www.accessdata.fda.gov/scripts/ires/?recall_number={recall_number}"

        title = f"FDA Enforcement ({recall_class}): {company} — {product[:60]}"
        summary = (
            f"Recall by {company}. Reason: {reason}. "
            f"Status: {status}. Classification: {recall_class}."
        )

        articles.append({
            "url": url,
            "title": title,
            "summary": summary,
            "published_dt": published_dt,
            "source_name": "FDA Enforcement (openFDA)",
            "source_type": "regulatory",
        })

    logger.info(f"Fetched {len(articles)} FDA enforcement actions from openFDA")
    return articles
