#!/usr/bin/env python3
"""
edgar_debug.py — Standalone diagnostic for the EDGAR daily-index fetcher.

Run locally:
    python edgar_debug.py

Or via GitHub Actions: .github/workflows/edgar_debug.yml (manual trigger)

Tests each stage of the pipeline independently:
1. Daily index file download and parsing
2. SIC code lookup via submissions API
3. Filing text extraction
4. Full end-to-end fetch
"""

import json
import logging
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

# Allow running standalone without package install
sys.path.insert(0, ".")

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("edgar_debug")

HEADERS = {
    "User-Agent": "BioPharmaDigest nick.paul.taylor@gmail.com",
    "Accept-Encoding": "gzip, deflate",
}

PHARMA_SIC_CODES = ["2830", "2833", "2834", "2835", "2836", "8731"]


def test_daily_index():
    """Test 1: Can we download and parse daily index files?"""
    logger.info("=" * 60)
    logger.info("TEST 1: Daily index file download")
    logger.info("=" * 60)

    # Try today and the last few business days
    today = datetime.now(timezone.utc).date()
    for offset in range(5):
        d = today - timedelta(days=offset)
        if d.weekday() >= 5:
            continue
        quarter = (d.month - 1) // 3 + 1
        date_str = d.strftime("%Y%m%d")
        url = (
            f"https://www.sec.gov/Archives/edgar/daily-index/"
            f"{d.year}/QTR{quarter}/company.{date_str}.idx"
        )
        logger.info(f"Trying {url}")
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            logger.info(f"  Status: {resp.status_code}")
            if resp.status_code == 200:
                lines = resp.text.splitlines()
                logger.info(f"  Lines: {len(lines)}")
                # Count 8-Ks
                eight_k = [l for l in lines if "|8-K" in l]
                logger.info(f"  8-K entries: {len(eight_k)}")
                if eight_k:
                    logger.info(f"  Sample: {eight_k[0][:120]}")
                return d, resp.text
        except Exception as exc:
            logger.warning(f"  Error: {exc}")
        time.sleep(0.3)

    logger.error("Could not fetch any daily index file")
    return None, None


def test_sic_lookup(cik: str):
    """Test 2: Can we look up SIC codes via submissions API?"""
    logger.info("=" * 60)
    logger.info(f"TEST 2: SIC lookup for CIK {cik}")
    logger.info("=" * 60)

    cik_padded = cik.lstrip("0").zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    logger.info(f"URL: {url}")

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        logger.info(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            sic = data.get("sic", "N/A")
            name = data.get("name", "N/A")
            sic_desc = data.get("sicDescription", "N/A")
            logger.info(f"Company: {name}")
            logger.info(f"SIC: {sic} ({sic_desc})")
            logger.info(f"Is pharma: {sic in PHARMA_SIC_CODES}")
            return sic
    except Exception as exc:
        logger.warning(f"Error: {exc}")

    return None


def test_filing_text(cik: str, accession_nodash: str):
    """Test 3: Can we fetch filing text?"""
    logger.info("=" * 60)
    logger.info(f"TEST 3: Filing text for CIK {cik}, accession {accession_nodash}")
    logger.info("=" * 60)

    index_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/index.json"
    logger.info(f"Index JSON: {index_url}")

    try:
        resp = requests.get(index_url, headers=HEADERS, timeout=15)
        logger.info(f"Status: {resp.status_code}")
        if resp.status_code != 200:
            return
        data = resp.json()
        directory = data.get("directory", {})
        items = directory.get("item", [])
        logger.info(f"Files in filing: {len(items)}")
        for item in items:
            logger.info(f"  {item.get('name', '?')} ({item.get('size', '?')} bytes)")

        # Find primary doc
        for item in items:
            name = item.get("name", "")
            if "-index" in name or name.endswith((".xml", ".xsd")):
                continue
            if name.endswith((".htm", ".html", ".txt")):
                parent = directory.get("name", "")
                doc_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{parent}/{name}"
                logger.info(f"Primary doc: {doc_url}")
                time.sleep(0.3)
                doc_resp = requests.get(doc_url, headers=HEADERS, timeout=15)
                logger.info(f"Doc status: {doc_resp.status_code}")
                if doc_resp.status_code == 200:
                    import re
                    from html.parser import HTMLParser

                    class Stripper(HTMLParser):
                        def __init__(self):
                            super().__init__()
                            self.result = []
                        def handle_data(self, data):
                            self.result.append(data)

                    s = Stripper()
                    s.feed(doc_resp.text[:50000])
                    text = re.sub(r"\s+", " ", " ".join(s.result)).strip()
                    logger.info(f"Text length: {len(text)} chars")
                    logger.info(f"First 500 chars: {text[:500]}")
                break
    except Exception as exc:
        logger.warning(f"Error: {exc}")


def test_full_fetch():
    """Test 4: Full end-to-end fetch."""
    logger.info("=" * 60)
    logger.info("TEST 4: Full fetch_edgar_filings()")
    logger.info("=" * 60)

    try:
        from fetchers.edgar import fetch_edgar_filings
        articles = fetch_edgar_filings()
        logger.info(f"Returned {len(articles)} articles")
        for i, a in enumerate(articles[:10]):
            logger.info(f"  [{i+1}] {a['title']}")
            logger.info(f"       URL: {a['url']}")
            logger.info(f"       Date: {a.get('published_dt', 'N/A')}")
            summary_preview = (a.get("summary", "")[:200] + "...") if len(a.get("summary", "")) > 200 else a.get("summary", "")
            logger.info(f"       Summary: {summary_preview}")
    except Exception as exc:
        logger.error(f"Full fetch failed: {exc}", exc_info=True)


def main():
    import re

    logger.info("EDGAR Debug Script — Daily Index Approach")
    logger.info(f"Time: {datetime.now(timezone.utc).isoformat()}")
    logger.info(f"Pharma SIC codes: {PHARMA_SIC_CODES}")

    # Test 1: Daily index
    date, index_text = test_daily_index()

    if index_text:
        # Extract a sample CIK from an 8-K entry for further tests
        sample_cik = None
        sample_accession = None
        for line in index_text.splitlines():
            if "|8-K|" in line:
                parts = line.split("|")
                if len(parts) >= 5:
                    sample_cik = parts[2].strip().lstrip("0") or "0"
                    match = re.search(r"(\d{10}-\d{2}-\d{6})", parts[4])
                    if match:
                        sample_accession = match.group(1).replace("-", "")
                    break

        time.sleep(0.5)

        # Test 2: SIC lookup
        if sample_cik:
            test_sic_lookup(sample_cik)
            time.sleep(0.5)

            # Also test a known pharma company (Pfizer CIK = 78003)
            logger.info("")
            test_sic_lookup("78003")
            time.sleep(0.5)

        # Test 3: Filing text
        if sample_cik and sample_accession:
            test_filing_text(sample_cik, sample_accession)
            time.sleep(0.5)

    # Test 4: Full fetch
    logger.info("")
    test_full_fetch()

    logger.info("")
    logger.info("=" * 60)
    logger.info("EDGAR debug complete")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
