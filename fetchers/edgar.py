"""
fetchers/edgar.py — Fetch recent pharma/biotech 8-K filings from SEC EDGAR.

Uses the EDGAR full-text search API (EFTS) with plain keyword queries.
The sics: filter syntax does not work in EFTS — instead we search for
manufacturing-specific terms and let the keyword filter handle relevance.

Docs: https://efts.sec.gov/LATEST/search-index (no API key required)
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

from config import EDGAR_LOOKBACK_HOURS

logger = logging.getLogger(__name__)

EFTS_URL = "https://efts.sec.gov/LATEST/search-index"

HEADERS = {
    # SEC requires a descriptive User-Agent with contact info
    "User-Agent": "BioPharmaDigest nick.paul.taylor@gmail.com",
    "Accept-Encoding": "gzip, deflate",
}

# Targeted manufacturing terms to search for in 8-K text
EDGAR_SEARCH_TERMS = [
    "pharmaceutical manufacturing",
    "biologics manufacturing",
    "CDMO",
    "CMO agreement",
    "manufacturing facility",
    "drug shortage",
    "consent decree",
    "warning letter",
    "cGMP",
    "fill-finish",
    "aseptic manufacturing",
]


def fetch_edgar_filings() -> list[dict]:
    """
    Fetch recent 8-K filings mentioning manufacturing terms.
    Returns normalised article dicts.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=EDGAR_LOOKBACK_HOURS)
    date_str = cutoff.strftime("%Y-%m-%d")

    articles = []
    seen_accessions = set()

    for term in EDGAR_SEARCH_TERMS:
        results = _search_efts(term, date_str)
        for hit in results:
            accession = hit.get("_id", "")
            if not accession or accession in seen_accessions:
                continue
            seen_accessions.add(accession)

            article = _hit_to_article(hit)
            if article:
                articles.append(article)

        time.sleep(0.5)  # Polite delay between EDGAR requests

    logger.info(f"Fetched {len(articles)} EDGAR 8-K filings")
    return articles


def _search_efts(query_term: str, date_from: str) -> list[dict]:
    """Query the EDGAR EFTS search API."""
    params = {
        "q": f'"{query_term}"',
        "forms": "8-K",
        "dateRange": "custom",
        "startdt": date_from,
    }

    try:
        resp = requests.get(EFTS_URL, params=params, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        hits = data.get("hits", {}).get("hits", [])
        return hits
    except Exception as exc:
        logger.warning(f"EDGAR search failed for '{query_term}': {exc}")
        return []


def _hit_to_article(hit: dict) -> Optional[dict]:
    """Convert an EFTS search hit to a normalised article dict."""
    source = hit.get("_source", {})
    entity = source.get("entity_name", "Unknown Company")
    file_date = source.get("file_date", "")
    accession = hit.get("_id", "")  # Format: 0001234567-26-000001

    if not accession:
        return None

    # Build the EDGAR filing viewer URL
    accession_nodash = accession.replace("-", "")
    # Extract CIK from the accession number (first 10 digits)
    cik = accession_nodash[:10].lstrip("0")
    filing_url = (
        f"https://www.sec.gov/Archives/edgar/data/{cik}/"
        f"{accession_nodash}/{accession}-index.htm"
    )

    published_dt = None
    if file_date:
        try:
            published_dt = datetime.strptime(file_date, "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
        except Exception:
            pass

    # Extract highlight snippets if available
    highlights = hit.get("highlight", {})
    snippet = ""
    for field_hits in highlights.values():
        if field_hits:
            snippet = field_hits[0][:300]
            break

    return {
        "url": filing_url,
        "title": f"SEC 8-K Filing: {entity}",
        "summary": f"8-K filing by {entity} on {file_date}. {snippet}",
        "published_dt": published_dt,
        "source_name": "SEC EDGAR (8-K)",
        "source_type": "regulatory",
    }
