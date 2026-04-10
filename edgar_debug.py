#!/usr/bin/env python3
"""
edgar_debug.py — Standalone diagnostic for the EDGAR daily-index fetcher.

Run locally:
    python edgar_debug.py

Or via GitHub Actions: .github/workflows/edgar_debug.yml (manual trigger)

Tests each stage independently:
1. Daily master index download + parsing (master.YYYYMMDD.idx)
2. SIC code lookup via submissions API
3. Filing text extraction
4. Full end-to-end fetch
"""

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

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


def test_master_index():
    """Test 1: Download and parse daily master index files."""
    logger.info("=" * 60)
    logger.info("TEST 1: Daily MASTER index file download + parse")
    logger.info("=" * 60)

    today = datetime.now(timezone.utc).date()

    for offset in range(5):
        d = today - timedelta(days=offset)
        if d.weekday() >= 5:
            logger.info(f"  Skipping {d} (weekend)")
            continue

        quarter = (d.month - 1) // 3 + 1
        date_str = d.strftime("%Y%m%d")

        # Try master.idx (pipe-delimited, known format)
        url = (
            f"https://www.sec.gov/Archives/edgar/daily-index/"
            f"{d.year}/QTR{quarter}/master.{date_str}.idx"
        )
        logger.info(f"Trying: {url}")

        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            logger.info(f"  Status: {resp.status_code}")
        except Exception as exc:
            logger.warning(f"  Error: {exc}")
            time.sleep(0.3)
            continue

        if resp.status_code != 200:
            time.sleep(0.3)
            continue

        text = resp.text
        lines = text.splitlines()
        logger.info(f"  Total lines: {len(lines)}")

        # Show first 15 lines to verify format
        logger.info("  --- First 15 lines ---")
        for i, line in enumerate(lines[:15]):
            logger.info(f"    [{i}] {line[:120]}")

        # Count entries by form type
        in_data = False
        form_counts = {}
        total_parsed = 0
        sample_8k = None

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("---") or stripped.startswith("CIK|"):
                in_data = True
                continue
            if not in_data or not stripped:
                continue
            parts = stripped.split("|")
            if len(parts) >= 5:
                total_parsed += 1
                ft = parts[2].strip()
                form_counts[ft] = form_counts.get(ft, 0) + 1
                if ft in ("8-K", "8-K/A") and sample_8k is None:
                    sample_8k = parts

        logger.info(f"  Parsed entries: {total_parsed}")
        logger.info(f"  8-K count: {form_counts.get('8-K', 0)}")
        logger.info(f"  8-K/A count: {form_counts.get('8-K/A', 0)}")

        # Show top form types
        top_forms = sorted(form_counts.items(), key=lambda x: -x[1])[:10]
        logger.info(f"  Top form types: {top_forms}")

        if sample_8k:
            logger.info(f"  Sample 8-K: CIK={sample_8k[0].strip()}, "
                        f"Company={sample_8k[1].strip()}, "
                        f"Date={sample_8k[3].strip()}, "
                        f"File={sample_8k[4].strip()[:80]}")

        return d, text, sample_8k

    logger.error("Could not fetch any daily master index file")
    return None, None, None


def test_company_index():
    """Test 1b: Also check company.idx format for comparison."""
    logger.info("=" * 60)
    logger.info("TEST 1b: Company index format check (for comparison)")
    logger.info("=" * 60)

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
        logger.info(f"Trying company.idx: {url}")
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            logger.info(f"  Status: {resp.status_code}")
            if resp.status_code == 200:
                lines = resp.text.splitlines()
                logger.info(f"  Total lines: {len(lines)}")
                logger.info("  --- First 15 lines (to see format) ---")
                for i, line in enumerate(lines[:15]):
                    logger.info(f"    [{i}] {line[:120]}")

                # Check if pipe-delimited
                pipe_lines = [l for l in lines if "|" in l]
                logger.info(f"  Lines containing '|': {len(pipe_lines)}")

                eight_k_pipe = [l for l in lines if "|8-K" in l]
                eight_k_space = [l for l in lines if " 8-K " in l]
                logger.info(f"  Lines matching '|8-K': {len(eight_k_pipe)}")
                logger.info(f"  Lines matching ' 8-K ': {len(eight_k_space)}")
                if eight_k_space:
                    logger.info(f"  Sample ' 8-K ' line: {eight_k_space[0][:120]}")
                return
        except Exception as exc:
            logger.warning(f"  Error: {exc}")
        time.sleep(0.3)


def test_sic_lookup(cik: str, label: str = ""):
    """Test 2: SIC code lookup via submissions API."""
    logger.info("=" * 60)
    logger.info(f"TEST 2: SIC lookup for CIK {cik} {label}")
    logger.info("=" * 60)

    cik_padded = cik.lstrip("0").zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    logger.info(f"URL: {url}")

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        logger.info(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            logger.info(f"Company: {data.get('name', 'N/A')}")
            logger.info(f"SIC: {data.get('sic', 'N/A')} ({data.get('sicDescription', 'N/A')})")
            logger.info(f"Is pharma: {data.get('sic', '') in PHARMA_SIC_CODES}")
            return data.get("sic", "")
    except Exception as exc:
        logger.warning(f"Error: {exc}")
    return None


def test_filing_text(cik: str, accession: str):
    """Test 3: Filing text extraction."""
    logger.info("=" * 60)
    logger.info(f"TEST 3: Filing text for CIK {cik}")
    logger.info("=" * 60)

    accession_nodash = accession.replace("-", "")
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
        parent = directory.get("name", "")
        logger.info(f"Files in filing: {len(items)}")
        for item in items[:10]:
            logger.info(f"  {item.get('name', '?')} ({item.get('size', '?')} bytes)")

        # Find primary doc
        for item in items:
            name = item.get("name", "")
            if "-index" in name or name.endswith((".xml", ".xsd", ".json")):
                continue
            if re.match(r"^R\d+\.htm$", name):
                continue
            if name.endswith((".htm", ".html", ".txt")):
                doc_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{parent}/{name}"
                logger.info(f"Primary doc: {doc_url}")
                time.sleep(0.3)
                doc_resp = requests.get(doc_url, headers=HEADERS, timeout=15)
                logger.info(f"Doc status: {doc_resp.status_code}")
                if doc_resp.status_code == 200:
                    from html.parser import HTMLParser

                    class Stripper(HTMLParser):
                        def __init__(self):
                            super().__init__()
                            self.result = []
                            self._skip = False
                        def handle_starttag(self, tag, attrs):
                            if tag in ("script", "style"):
                                self._skip = True
                        def handle_endtag(self, tag):
                            if tag in ("script", "style"):
                                self._skip = False
                        def handle_data(self, data):
                            if not self._skip:
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
            summary = a.get("summary", "")
            preview = (summary[:200] + "...") if len(summary) > 200 else summary
            logger.info(f"       Summary: {preview}")
        return articles
    except Exception as exc:
        logger.error(f"Full fetch failed: {exc}", exc_info=True)
        return []


def main():
    parser = argparse.ArgumentParser(description="EDGAR debug script")
    parser.add_argument("--hours", type=int, default=26, help="Lookback hours")
    parser.add_argument("--raw", action="store_true", help="Run raw diagnostic tests")
    parser.add_argument("--no-sic", action="store_true", help="Skip SIC filtering")
    parser.add_argument("--term", type=str, help="Search term (unused, kept for compat)")
    parser.add_argument("--threshold", type=int, help="Threshold (unused, kept for compat)")
    parser.add_argument("--json", type=str, help="Output JSON file path")
    args = parser.parse_args()

    logger.info("EDGAR Debug Script — Daily Master Index Approach")
    logger.info(f"Time: {datetime.now(timezone.utc).isoformat()}")
    logger.info(f"Pharma SIC codes: {PHARMA_SIC_CODES}")
    logger.info(f"Args: hours={args.hours}, raw={args.raw}")

    if args.raw:
        # Test 1: Master index
        date, index_text, sample_8k = test_master_index()
        time.sleep(0.5)

        # Test 1b: Company index format comparison
        test_company_index()
        time.sleep(0.5)

        # Test 2: SIC lookup
        if sample_8k:
            sample_cik = sample_8k[0].strip().lstrip("0") or "0"
            test_sic_lookup(sample_cik, "(from index)")
            time.sleep(0.5)

        # Known pharma: Pfizer
        test_sic_lookup("78003", "(Pfizer)")
        time.sleep(0.5)

        # Test 3: Filing text
        if sample_8k:
            sample_cik = sample_8k[0].strip().lstrip("0") or "0"
            filename = sample_8k[4].strip()
            match = re.search(r"(\d{10}-\d{2}-\d{6})", filename)
            if match:
                test_filing_text(sample_cik, match.group(1))
            time.sleep(0.5)

    # Test 4: Full fetch
    logger.info("")
    articles = test_full_fetch()

    # Write JSON output if requested
    if args.json and articles:
        output = []
        for a in articles:
            out = dict(a)
            if out.get("published_dt"):
                out["published_dt"] = out["published_dt"].isoformat()
            output.append(out)
        with open(args.json, "w") as f:
            json.dump(output, f, indent=2)
        logger.info(f"Wrote {len(output)} articles to {args.json}")

    logger.info("")
    logger.info("=" * 60)
    logger.info("EDGAR debug complete")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
