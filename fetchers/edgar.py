"""
fetchers/edgar.py — Fetch recent pharma/biotech 8-K filings from SEC EDGAR.

Uses the EDGAR full-text search API (EFTS) with targeted keyword queries,
then post-filters by SIC code using the SEC submissions API to ensure
only pharmaceutical/biotech filers are included.

Docs:
  EFTS:        https://efts.sec.gov/LATEST/search-index (no API key required)
  Submissions: https://data.sec.gov/submissions/ (no API key required)
"""

import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

from config import EDGAR_LOOKBACK_HOURS, PHARMA_SIC_CODES

logger = logging.getLogger(__name__)

EFTS_URL = "https://efts.sec.gov/LATEST/search-index"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"

HEADERS = {
    # SEC requires a descriptive User-Agent with contact info
    "User-Agent": "BioPharmaDigest nick.paul.taylor@gmail.com",
    "Accept-Encoding": "gzip, deflate",
}

# ---------------------------------------------------------------------------
# Search terms — kept narrow to avoid matching boilerplate legal language in
# non-pharma 8-Ks.  Broad terms like "warning letter", "consent decree", and
# "cGMP" were removed because they appear as standard risk-factor language in
# filings from every industry.  SIC post-filtering (below) further ensures
# only pharma/biotech filers survive.
# ---------------------------------------------------------------------------
EDGAR_SEARCH_TERMS = [
    "pharmaceutical manufacturing",
    "biologics manufacturing",
    "CDMO",
    "CMO agreement",
    "manufacturing facility",
    "drug shortage",
    "fill-finish",
    "aseptic manufacturing",
    "GMP remediation",
    "FDA warning letter" ,       # more specific than bare "warning letter"
    "FDA consent decree",        # more specific than bare "consent decree"
]

# Prefixes that identify pharma SIC codes (first 4 chars of each SIC string)
_PHARMA_SIC_PREFIXES = tuple(code[:4] for code in PHARMA_SIC_CODES)

# Cache: CIK → (sic_code_str | None).  Shared across all search terms within
# a single pipeline run so we don't re-fetch the same company repeatedly.
_sic_cache: dict[str, Optional[str]] = {}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def fetch_edgar_filings() -> list[dict]:
    """
    Fetch recent 8-K filings mentioning manufacturing terms, filtered to
    pharma/biotech filers by SIC code.  Returns normalised article dicts.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=EDGAR_LOOKBACK_HOURS)
    date_str = cutoff.strftime("%Y-%m-%d")

    articles: list[dict] = []
    seen_accessions: set[str] = set()
    _sic_cache.clear()

    for term in EDGAR_SEARCH_TERMS:
        hits = _search_efts(term, date_str)
        for hit in hits:
            accession = hit.get("_id", "")
            if not accession or accession in seen_accessions:
                continue
            seen_accessions.add(accession)

            # --- SIC post-filter ------------------------------------------
            cik = _extract_cik(hit)
            if not cik:
                continue
            sic = _lookup_sic(cik)
            if not sic or not sic.startswith(_PHARMA_SIC_PREFIXES):
                continue
            # --------------------------------------------------------------

            article = _hit_to_article(hit, sic)
            if article:
                articles.append(article)

        time.sleep(0.5)  # Polite delay between EDGAR requests

    logger.info(
        f"Fetched {len(articles)} EDGAR 8-K filings "
        f"(from {len(seen_accessions)} unique accessions, "
        f"{len(_sic_cache)} unique CIKs checked)"
    )
    return articles


# ---------------------------------------------------------------------------
# EFTS search
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# SIC lookup via SEC submissions API
# ---------------------------------------------------------------------------

def _extract_cik(hit: dict) -> Optional[str]:
    """Pull CIK from an EFTS hit.  The accession number starts with the
    zero-padded CIK (first 10 digits)."""
    accession = hit.get("_id", "")
    if len(accession) < 10:
        return None
    cik_raw = accession.split("-")[0] if "-" in accession else accession[:10]
    return cik_raw.lstrip("0") or None


def _lookup_sic(cik: str) -> Optional[str]:
    """Return the 4-digit SIC code string for a CIK, using a cache to avoid
    redundant HTTP calls.  Returns None on any failure."""
    if cik in _sic_cache:
        return _sic_cache[cik]

    padded = cik.zfill(10)
    url = SUBMISSIONS_URL.format(cik=padded)

    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        sic = data.get("sic", "")
        _sic_cache[cik] = sic or None
        time.sleep(0.12)  # Stay under 10 req/s SEC rate limit
        return _sic_cache[cik]
    except Exception as exc:
        logger.debug(f"SIC lookup failed for CIK {cik}: {exc}")
        _sic_cache[cik] = None
        return None


# ---------------------------------------------------------------------------
# Hit → article conversion
# ---------------------------------------------------------------------------

def _hit_to_article(hit: dict, sic: str) -> Optional[dict]:
    """Convert an EFTS search hit to a normalised article dict, collecting
    *all* highlight snippets to give the LLM meaningful context."""
    source = hit.get("_source", {})
    entity = source.get("entity_name", "Unknown Company")
    file_date = source.get("file_date", "")
    accession = hit.get("_id", "")

    if not accession:
        return None

    # Build the EDGAR filing viewer URL
    accession_nodash = accession.replace("-", "")
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

    # Collect ALL highlight snippets (not just the first one) and clean HTML
    # tags that EFTS wraps around matched terms.
    highlights = hit.get("highlight", {})
    snippets: list[str] = []
    for field_hits in highlights.values():
        for fragment in (field_hits or []):
            clean = re.sub(r"</?[^>]+>", "", fragment).strip()
            if clean and clean not in snippets:
                snippets.append(clean)
    snippet_text = " … ".join(snippets[:6])[:1500]  # Cap at ~1500 chars

    # Build a richer summary so the LLM has enough to judge relevance
    summary_parts = [
        f"SEC 8-K filing by {entity} (SIC {sic}) on {file_date}.",
    ]
    if snippet_text:
        summary_parts.append(f"Excerpts: {snippet_text}")

    return {
        "url": filing_url,
        "title": f"SEC 8-K Filing: {entity}",
        "summary": " ".join(summary_parts),
        "published_dt": published_dt,
        "source_name": "SEC EDGAR (8-K)",
        "source_type": "edgar",  # Distinct type → its own keyword threshold
    }
