"""
fetchers/edgar.py — Fetch recent 8-K filings from SEC EDGAR for pharma/biotech companies.

Uses the EDGAR Full-Text Search API (EFTS), which is free and requires no API key.
Docs: https://efts.sec.gov/LATEST/search-index?q=%22manufacturing%22&dateRange=custom
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

from config import PHARMA_SIC_CODES, EDGAR_LOOKBACK_HOURS, KEYWORDS

logger = logging.getLogger(__name__)

EFTS_BASE = "https://efts.sec.gov/LATEST/search-index"
EDGAR_BASE = "https://www.sec.gov"

HEADERS = {
    "User-Agent": (
        "BioPharmaDigestBot/1.0 nick.paul.taylor@gmail.com"
    )
}

# Manufacturing-focused keywords to filter 8-Ks at the EDGAR API level
# (passed as the EFTS full-text query)
EDGAR_SEARCH_TERMS = [
    "manufacturing",
    "CDMO",
    "CMO",
    "fill-finish",
    "bioreactor",
    "drug shortage",
    "warning letter",
    "consent decree",
    "cGMP",
]


def fetch_edgar_filings() -> list[dict]:
    """
    Fetch recent 8-K filings from pharma/biotech SIC codes that mention
    manufacturing-related terms. Returns normalised article dicts.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=EDGAR_LOOKBACK_HOURS)
    date_str = cutoff.strftime("%Y-%m-%d")

    articles = []
    seen_accessions = set()

    for term in EDGAR_SEARCH_TERMS:
        results = _search_efts(term, date_str)
        for hit in results:
            accession = hit.get("_id", "")
            if accession in seen_accessions:
                continue
            seen_accessions.add(accession)

            article = _hit_to_article(hit)
            if article:
                articles.append(article)

    logger.info(f"Fetched {len(articles)} EDGAR 8-K filings")
    return articles


def _search_efts(query_term: str, date_from: str) -> list[dict]:
    """Query the EDGAR full-text search API."""
    params = {
        "q": f'"{query_term}"',
        "dateRange": "custom",
        "startdt": date_from,
        "forms": "8-K",
        "hits.hits._source": "period_of_report,file_date,entity_name,file_num,period_of_report,form_type,period_of_report",
        "hits.hits.total.value": 1,
    }

    # Filter by pharma/biotech SIC codes via category parameter
    sic_filter = " OR ".join(f'sics:"{sic}"' for sic in PHARMA_SIC_CODES)
    params["q"] = f'"{query_term}" AND ({sic_filter})'

    try:
        resp = requests.get(
            "https://efts.sec.gov/LATEST/search-index",
            params={
                "q": params["q"],
                "dateRange": "custom",
                "startdt": date_from,
                "forms": "8-K",
            },
            headers=HEADERS,
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("hits", {}).get("hits", [])
    except Exception as exc:
        logger.warning(f"EDGAR search failed for '{query_term}': {exc}")
        return []


def _hit_to_article(hit: dict) -> Optional[dict]:
    """Convert an EFTS search hit into a normalised article dict."""
    source = hit.get("_source", {})
    entity = source.get("entity_name", "Unknown Company")
    file_date = source.get("file_date", "")
    accession_no = hit.get("_id", "").replace("-", "")

    if not accession_no:
        return None

    # Build the EDGAR filing URL
    cik = source.get("file_num", "").replace("-", "")
    filing_url = (
        f"https://www.sec.gov/cgi-bin/browse-edgar"
        f"?action=getcompany&filenum={source.get('file_num', '')}"
        f"&type=8-K&dateb=&owner=include&count=10"
    )

    # Prefer the direct filing index URL if we have accession info
    accession_formatted = hit.get("_id", "")
    if accession_formatted:
        filing_url = f"https://www.sec.gov/Archives/edgar/data/{accession_no[:10]}/{accession_formatted.replace('-', '')}/{accession_formatted}-index.htm"

    # Use the search result URL as a reliable fallback
    filing_url = f"https://efts.sec.gov/LATEST/search-index?q=%22{accession_formatted}%22&forms=8-K"

    published_dt = None
    if file_date:
        try:
            published_dt = datetime.strptime(file_date, "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
        except Exception:
            pass

    title = f"SEC 8-K: {entity}"
    summary = source.get("period_of_report", "")

    return {
        "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={entity}&type=8-K&dateb=&owner=include&count=5&search_text=",
        "title": title,
        "summary": f"8-K filing by {entity} filed {file_date}. {summary}",
        "published_dt": published_dt,
        "source_name": "SEC EDGAR (8-K)",
        "source_type": "regulatory",
    }
