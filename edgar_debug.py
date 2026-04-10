#!/usr/bin/env python3
"""
edgar_debug.py — Standalone diagnostic for the EDGAR fetcher.

Runs the EDGAR pipeline in isolation and prints a detailed report showing
exactly what is fetched, what gets filtered at each stage, and why.

Usage:
    python edgar_debug.py                   # Uses new config (SIC + keyword filtering)
    python edgar_debug.py --raw             # Skip all filtering — show raw EFTS results
    python edgar_debug.py --no-sic          # Skip SIC filtering, still apply keywords
    python edgar_debug.py --threshold 0     # Override keyword threshold
    python edgar_debug.py --term "CDMO"     # Test a single search term
    python edgar_debug.py --hours 72        # Look back further

Requires: pip install requests
No API keys needed — uses free SEC EDGAR endpoints.
"""

import argparse
import json
import logging
import re
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

# ---------------------------------------------------------------------------
# Defaults (mirroring config.py so this script is self-contained)
# ---------------------------------------------------------------------------

PHARMA_SIC_CODES = [
    "2830", "2833", "2834", "2835", "2836", "8731",
]

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
    "FDA warning letter",
    "FDA consent decree",
]

KEYWORDS = [
    "manufacturing", "manufacture", "manufactured", "manufacturer",
    "production", "facility", "facilities", "plant",
    "GMP", "cGMP", "Good Manufacturing Practice",
    "warning letter", "Form 483", "483", "consent decree",
    "inspection", "remediation", "FDA inspection", "EMA inspection",
    "CMO", "CDMO", "contract manufacturing", "contract manufacturer",
    "outsourcing", "outsourced",
    "API", "active pharmaceutical ingredient",
    "biologics", "biologic", "biosimilar",
    "fill-finish", "fill finish", "aseptic", "sterile", "sterility",
    "lyophilization", "lyophilized", "bioreactor", "fermentation",
    "upstream", "downstream", "purification", "formulation",
    "supply chain", "drug shortage", "shortage", "supply disruption",
    "inventory", "stockpile",
    "capacity", "expansion", "new facility", "build", "retrofit",
    "investment", "capital expenditure", "capex",
    "acquisition", "acquires", "acquired", "merger",
    "joint venture", "partnership", "deal", "agreement", "collaboration",
]

EFTS_URL = "https://efts.sec.gov/LATEST/search-index"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"

# Browser-like headers required for the EFTS POST endpoint.
EFTS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://efts.sec.gov",
    "Referer": "https://efts.sec.gov/LATEST/search-index",
}

# Simple headers for data.sec.gov (SEC asks for descriptive User-Agent).
SUBMISSIONS_HEADERS = {
    "User-Agent": "BioPharmaDigest nick.paul.taylor@gmail.com",
    "Accept-Encoding": "gzip, deflate",
}

_PHARMA_SIC_PREFIXES = tuple(code[:4] for code in PHARMA_SIC_CODES)
_KW_PATTERNS = [
    re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)
    for kw in KEYWORDS
]

# ---------------------------------------------------------------------------
# EFTS + SIC helpers
# ---------------------------------------------------------------------------

_sic_cache: dict[str, Optional[str]] = {}
_sic_name_cache: dict[str, str] = {}
_company_name_cache: dict[str, str] = {}


def search_efts(query_term: str, date_from: str, date_to: str) -> list[dict]:
    """Query EFTS using POST with JSON body (required by SEC API)."""
    payload = {
        "q": f'"{query_term}"',
        "forms": "8-K",
        "dateRange": "custom",
        "startdt": date_from,
        "enddt": date_to,
    }
    try:
        resp = requests.post(EFTS_URL, json=payload, headers=EFTS_HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        total_info = data.get("hits", {}).get("total", {})
        total_val = total_info.get("value", "?")
        total_rel = total_info.get("relation", "")
        hits = data.get("hits", {}).get("hits", [])
        if total_rel == "gte":
            print(f"    (API reports ≥{total_val} total matches, returning first {len(hits)})")
        return hits
    except Exception as exc:
        print(f"  ⚠ EFTS query failed: {exc}")
        return []


def extract_accession(hit: dict) -> str:
    """EFTS _id is 'accession:filename' — return just the accession part."""
    raw_id = hit.get("_id", "")
    return raw_id.split(":")[0] if ":" in raw_id else raw_id


def extract_cik(hit: dict) -> Optional[str]:
    """Pull CIK from the _source dict."""
    source = hit.get("_source", {})
    ciks = source.get("ciks", [])
    if ciks:
        return str(ciks[0]).lstrip("0") or None
    return None


def extract_entity(hit: dict) -> str:
    """Pull company name from _source."""
    source = hit.get("_source", {})
    return (
        source.get("entity_name")
        or (source.get("display_names") or [None])[0]
        or "Unknown"
    )


def lookup_sic(cik: str) -> tuple[Optional[str], str, str]:
    """Returns (sic_code, sic_description, company_name)."""
    if cik in _sic_cache:
        return _sic_cache[cik], _sic_name_cache.get(cik, ""), _company_name_cache.get(cik, "")

    padded = cik.zfill(10)
    url = SUBMISSIONS_URL.format(cik=padded)
    try:
        resp = requests.get(url, headers=SUBMISSIONS_HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        sic = data.get("sic", "")
        sic_desc = data.get("sicDescription", "")
        name = data.get("name", "")
        _sic_cache[cik] = sic or None
        _sic_name_cache[cik] = sic_desc
        _company_name_cache[cik] = name
        time.sleep(0.12)
        return _sic_cache[cik], sic_desc, name
    except Exception as exc:
        _sic_cache[cik] = None
        _sic_name_cache[cik] = ""
        _company_name_cache[cik] = ""
        return None, "", ""


def get_snippets(hit: dict) -> str:
    highlights = hit.get("highlight", {})
    snippets = []
    for field_hits in highlights.values():
        for fragment in (field_hits or []):
            clean = re.sub(r"</?[^>]+>", "", fragment).strip()
            if clean and clean not in snippets:
                snippets.append(clean)
    return " … ".join(snippets[:6])[:1500]


def count_keywords(text: str) -> tuple[int, list[str]]:
    matched = []
    for i, pat in enumerate(_KW_PATTERNS):
        if pat.search(text):
            matched.append(KEYWORDS[i])
    return len(matched), matched


# ---------------------------------------------------------------------------
# Main diagnostic
# ---------------------------------------------------------------------------

def run_diagnostic(args):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=args.hours)
    date_str = cutoff.strftime("%Y-%m-%d")
    end_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    terms = [args.term] if args.term else EDGAR_SEARCH_TERMS

    print("=" * 78)
    print("EDGAR FETCHER DIAGNOSTIC")
    print("=" * 78)
    print(f"Lookback:       {args.hours} hours (since {date_str})")
    print(f"Search terms:   {len(terms)}")
    print(f"SIC filtering:  {'OFF' if args.no_sic or args.raw else 'ON'}")
    kw_threshold = args.threshold if args.threshold is not None else 2
    print(f"Keyword threshold: {kw_threshold}{'  (disabled)' if args.raw else ''}")
    print(f"Pharma SICs:    {', '.join(PHARMA_SIC_CODES)}")
    print(f"HTTP method:    POST (JSON body)")
    print()

    # ── Stage 1: Raw EFTS fetch ──────────────────────────────────────────
    all_hits: list[dict] = []
    hits_by_term: dict[str, int] = {}
    seen_accessions: set[str] = set()

    print("─── STAGE 1: EFTS Search ───")
    for term in terms:
        raw_hits = search_efts(term, date_str, end_str)
        new_count = 0
        for hit in raw_hits:
            acc = extract_accession(hit)
            if acc and acc not in seen_accessions:
                seen_accessions.add(acc)
                hit["_matched_term"] = term
                all_hits.append(hit)
                new_count += 1
        hits_by_term[term] = new_count
        total_raw = len(raw_hits)
        print(f'  "{term}": {total_raw} raw hits, {new_count} new unique')
        time.sleep(0.5)

    print(f"\n  Total unique filings from EFTS: {len(all_hits)}")

    # Show date distribution of results
    date_counter: Counter = Counter()
    for hit in all_hits:
        fd = hit.get("_source", {}).get("file_date", "")
        date_counter[fd[:7] if fd else "NONE"] += 1
    if date_counter:
        print(f"\n  Filing date distribution:")
        for d, c in sorted(date_counter.items()):
            print(f"    {d}: {c}")
    print()

    if not all_hits:
        print("No results. Nothing to diagnose.")
        return

    # Show a sample raw hit for debugging
    print("  Sample raw hit structure:")
    sample = all_hits[0]
    sample_source = sample.get("_source", {})
    print(f"    _id:            {sample.get('_id', 'MISSING')}")
    print(f"    _source keys:   {sorted(sample_source.keys())}")
    print(f"    entity_name:    {sample_source.get('entity_name', 'MISSING')}")
    print(f"    display_names:  {sample_source.get('display_names', 'MISSING')}")
    print(f"    ciks:           {sample_source.get('ciks', 'MISSING')}")
    print(f"    file_date:      {sample_source.get('file_date', 'MISSING')}")
    print(f"    file_type:      {sample_source.get('file_type', 'MISSING')}")
    print(f"    highlight keys: {sorted(sample.get('highlight', {}).keys())}")
    snippet = get_snippets(sample)
    if snippet:
        print(f"    snippet:        {snippet[:200]}...")
    print()

    # ── Stage 2: SIC lookup + filter ─────────────────────────────────────
    print("─── STAGE 2: SIC Code Filtering ───")

    sic_pass: list[dict] = []
    sic_fail: list[dict] = []
    sic_counter: Counter = Counter()
    no_cik_count = 0

    unique_ciks = set()
    for h in all_hits:
        c = extract_cik(h)
        if c:
            unique_ciks.add(c)

    print(f"  Unique CIKs to look up: {len(unique_ciks)}")

    if not args.raw and not args.no_sic:
        # Pre-fetch all SICs
        for i, cik in enumerate(unique_ciks):
            lookup_sic(cik)
            if (i + 1) % 25 == 0:
                print(f"    ... looked up {i+1}/{len(unique_ciks)} CIKs")

        for hit in all_hits:
            cik = extract_cik(hit)
            if not cik:
                no_cik_count += 1
                sic_fail.append(hit)
                continue

            sic, sic_desc, comp_name = (
                _sic_cache.get(cik),
                _sic_name_cache.get(cik, ""),
                _company_name_cache.get(cik, ""),
            )
            hit["_sic"] = sic
            hit["_sic_desc"] = sic_desc
            hit["_company"] = comp_name or extract_entity(hit)
            label = f"{sic} ({sic_desc})" if sic else "UNKNOWN"
            sic_counter[label] += 1

            if sic and sic.startswith(_PHARMA_SIC_PREFIXES):
                sic_pass.append(hit)
            else:
                sic_fail.append(hit)

        if no_cik_count:
            print(f"\n  Hits with no CIK (dropped): {no_cik_count}")
        print(f"\n  SIC distribution (top 20):")
        for sic_label, count in sic_counter.most_common(20):
            is_pharma = any(sic_label.startswith(p) for p in _PHARMA_SIC_PREFIXES)
            marker = " ✓ PHARMA" if is_pharma else ""
            print(f"    {count:4d}  {sic_label}{marker}")

        print(f"\n  Passed SIC filter: {len(sic_pass)}")
        print(f"  Rejected by SIC:  {len(sic_fail)}")
    else:
        sic_pass = all_hits
        for hit in all_hits:
            hit["_sic"] = "N/A"
            hit["_sic_desc"] = "skipped"
            hit["_company"] = extract_entity(hit)
        print("  (SIC filtering disabled)")

    print()

    # ── Stage 3: Keyword filter ──────────────────────────────────────────
    print("─── STAGE 3: Keyword Filtering ───")

    kw_pass: list[dict] = []
    kw_fail: list[dict] = []

    if not args.raw:
        for hit in sic_pass:
            entity = hit.get("_company", extract_entity(hit))
            file_date = hit.get("_source", {}).get("file_date", "")
            sic = hit.get("_sic", "")
            snippets = get_snippets(hit)
            text = (
                f"SEC 8-K Filing: {entity} "
                f"8-K filing by {entity} (SIC {sic}) on {file_date}. "
                f"Excerpts: {snippets}"
            )
            count, matched = count_keywords(text)
            hit["_kw_count"] = count
            hit["_kw_matched"] = matched

            if count >= kw_threshold:
                kw_pass.append(hit)
            else:
                kw_fail.append(hit)

        print(f"  Passed keyword filter (>= {kw_threshold}): {len(kw_pass)}")
        print(f"  Rejected by keywords:  {len(kw_fail)}")

        if kw_fail:
            print(f"\n  Sample keyword rejections (up to 10):")
            for hit in kw_fail[:10]:
                entity = hit.get("_company", "?")
                print(f"    • {entity} — {hit.get('_kw_count', 0)} kw: {hit.get('_kw_matched', [])}")
                snip = get_snippets(hit)[:120]
                if snip:
                    print(f"      snippet: {snip}…")
    else:
        kw_pass = sic_pass
        print("  (keyword filtering disabled)")

    print()

    # ── Stage 4: Final survivors ─────────────────────────────────────────
    print("─── STAGE 4: Survivors (would go to LLM) ───")
    print(f"  Total: {len(kw_pass)} filings\n")

    for i, hit in enumerate(kw_pass):
        entity = hit.get("_company", extract_entity(hit))
        file_date = hit.get("_source", {}).get("file_date", "?")
        accession = extract_accession(hit)
        sic = hit.get("_sic", "?")
        sic_desc = hit.get("_sic_desc", "")
        kw_count = hit.get("_kw_count", "?")
        kw_matched = hit.get("_kw_matched", [])
        term = hit.get("_matched_term", "?")
        snippets = get_snippets(hit)

        print(f"  [{i+1}] {entity}")
        print(f"      Filed: {file_date}  |  SIC: {sic} ({sic_desc})")
        print(f"      Accession: {accession}")
        print(f"      Matched term: \"{term}\"")
        print(f"      Keyword matches: {kw_count} — {kw_matched}")
        if snippets:
            display = snippets[:300]
            if len(snippets) > 300:
                display += "…"
            print(f"      Snippets: {display}")
        print()

    # ── Summary ──────────────────────────────────────────────────────────
    print("=" * 78)
    print("SUMMARY")
    print("=" * 78)
    print(f"  EFTS raw unique hits:    {len(all_hits):>5}")
    if not args.raw and not args.no_sic:
        print(f"  After SIC filter:        {len(sic_pass):>5}  (−{len(sic_fail)})")
    if not args.raw:
        print(f"  After keyword filter:    {len(kw_pass):>5}  (−{len(kw_fail)})")
    print(f"  → Would send to LLM:     {len(kw_pass):>5}")
    batches = (len(kw_pass) + 19) // 20
    est_time = batches * 10
    print(f"  → Gemini batches:        {batches:>5}  (~{est_time}s at 10s/batch)")
    print()

    # ── Optional: dump full data to JSON ─────────────────────────────────
    if args.json:
        output = []
        for hit in kw_pass:
            source = hit.get("_source", {})
            output.append({
                "accession": extract_accession(hit),
                "entity": hit.get("_company", extract_entity(hit)),
                "file_date": source.get("file_date"),
                "sic": hit.get("_sic"),
                "sic_desc": hit.get("_sic_desc"),
                "matched_term": hit.get("_matched_term"),
                "kw_count": hit.get("_kw_count"),
                "kw_matched": hit.get("_kw_matched"),
                "snippets": get_snippets(hit),
            })
        with open(args.json, "w") as f:
            json.dump(output, f, indent=2)
        print(f"Full results written to {args.json}")


def main():
    parser = argparse.ArgumentParser(description="EDGAR fetcher diagnostic")
    parser.add_argument("--hours", type=int, default=26, help="Lookback hours (default: 26)")
    parser.add_argument("--term", type=str, default=None, help="Test a single search term")
    parser.add_argument("--raw", action="store_true", help="Skip all filtering — show raw EFTS results")
    parser.add_argument("--no-sic", action="store_true", help="Skip SIC filtering only")
    parser.add_argument("--threshold", type=int, default=None, help="Override keyword threshold")
    parser.add_argument("--json", type=str, default=None, help="Write survivors to JSON file")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show debug logging")

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)

    run_diagnostic(args)


if __name__ == "__main__":
    main()
