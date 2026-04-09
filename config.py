# =============================================================================
# config.py — Central configuration for the biopharma manufacturing digest
# =============================================================================

# --- RSS Sources -------------------------------------------------------------
RSS_SOURCES = [
    # Newswires
    # GlobeNewswire industry feeds use /RssFeed/industrycode/NUMBER-Name format
    {
        "name": "GlobeNewswire (Pharma)",
        "url": "https://www.globenewswire.com/RssFeed/industrycode/37-Pharmaceuticals/feedTitle/GlobeNewswire%20-%20Pharmaceuticals",
        "type": "newswire",
    },
    {
        "name": "GlobeNewswire (Biotech)",
        "url": "https://www.globenewswire.com/RssFeed/industrycode/6-Biotechnology/feedTitle/GlobeNewswire%20-%20Biotechnology",
        "type": "newswire",
    },
    # BusinessWire industry RSS — correct URL format per their feed docs
    {
        "name": "BusinessWire (Pharma)",
        "url": "https://www.businesswire.com/rss/home/?rss=G7&rssid=20",
        "type": "newswire",
    },
    {
        "name": "BusinessWire (Biotech)",
        "url": "https://www.businesswire.com/rss/home/?rss=G7&rssid=21",
        "type": "newswire",
    },
    # FDA — correct paths as of 2025
    {
        "name": "FDA Press Announcements",
        "url": "https://www.fda.gov/about-fda/stay-informed/rss-feeds/press-announcements/rss.xml",
        "type": "regulatory",
    },
    {
        "name": "FDA Warning Letters",
        "url": "https://www.fda.gov/about-fda/stay-informed/rss-feeds/warning-letters/rss.xml",
        "type": "regulatory",
    },
    {
        "name": "FDA MedWatch Safety Alerts",
        "url": "https://www.fda.gov/about-fda/stay-informed/rss-feeds/medwatch-safety-alerts/rss.xml",
        "type": "regulatory",
    },
    # Trade publications — only open feeds included (403-blocked sites removed)
    {
        "name": "BioPharma Dive",
        "url": "https://www.biopharmadive.com/feeds/news/",
        "type": "trade",
    },
    {
        "name": "Fierce Pharma",
        "url": "https://www.fiercepharma.com/rss/xml",
        "type": "trade",
    },
    {
        "name": "Fierce Biotech",
        "url": "https://www.fiercebiotech.com/rss/xml",
        "type": "trade",
    },
    # GEN (Genetic Engineering & Biotechnology News) — strong manufacturing coverage
    {
        "name": "GEN (Genetic Engineering News)",
        "url": "https://www.genengnews.com/feed/",
        "type": "trade",
    },
    # BioWorld — manufacturing and supply chain coverage
    {
        "name": "BioWorld",
        "url": "https://www.bioworld.com/rss/articles",
        "type": "trade",
    },
    # Broad biopharma publications (keyword filtering applied more strictly)
    {
        "name": "Endpoints News",
        "url": "https://endpts.com/feed",
        "type": "broad",
    },
    {
        "name": "STAT News (Pharma)",
        "url": "https://www.statnews.com/category/pharma/feed/",
        "type": "broad",
    },
    {
        "name": "STAT News (Biotech)",
        "url": "https://www.statnews.com/category/biotech/feed/",
        "type": "broad",
    },
]

# --- SEC EDGAR Settings ------------------------------------------------------
# SIC codes for pharmaceutical/biotech manufacturers
PHARMA_SIC_CODES = [
    "2830",  # Industrial Chemicals and Synthetics
    "2833",  # Pharmaceutical Preparations
    "2834",  # Pharmaceutical Preparations
    "2835",  # In Vitro & In Vivo Diagnostic Substances
    "2836",  # Biological Products (No Diagnostic Substances)
    "8731",  # Commercial Physical & Biological Research
]

# 8-K item types most relevant to manufacturing
EDGAR_RELEVANT_ITEMS = [
    "1.01",  # Entry into a Material Definitive Agreement
    "2.01",  # Completion of Acquisition or Disposition of Assets
    "7.01",  # Regulation FD Disclosure (press releases)
    "8.01",  # Other Events
]

EDGAR_LOOKBACK_HOURS = 26  # Slightly more than a day to avoid missing anything

# --- Keywords ----------------------------------------------------------------
# Applied to title + summary/description text (case-insensitive)
# Broad sources (Endpoints, STAT) require a match; trade/regulatory sources
# are included by default but boosted in LLM scoring if keywords match.

KEYWORDS = [
    # Core manufacturing terms
    "manufacturing",
    "manufacture",
    "manufactured",
    "manufacturer",
    "production",
    "facility",
    "facilities",
    "plant",
    # Quality / regulatory compliance
    "GMP",
    "cGMP",
    "Good Manufacturing Practice",
    "warning letter",
    "Form 483",
    "483",
    "consent decree",
    "inspection",
    "remediation",
    "FDA inspection",
    "EMA inspection",
    # Outsourcing / contract
    "CMO",
    "CDMO",
    "contract manufacturing",
    "contract manufacturer",
    "outsourcing",
    "outsourced",
    # Drug types and processes
    "API",
    "active pharmaceutical ingredient",
    "biologics",
    "biologic",
    "biosimilar",
    "fill-finish",
    "fill finish",
    "aseptic",
    "sterile",
    "sterility",
    "lyophilization",
    "lyophilized",
    "bioreactor",
    "fermentation",
    "upstream",
    "downstream",
    "purification",
    "formulation",
    # Supply chain
    "supply chain",
    "drug shortage",
    "shortage",
    "supply disruption",
    "inventory",
    "stockpile",
    # Capacity / infrastructure
    "capacity",
    "expansion",
    "new facility",
    "build",
    "retrofit",
    "investment",
    "capital expenditure",
    "capex",
    # M&A / deals relevant to manufacturing
    "acquisition",
    "acquires",
    "acquired",
    "merger",
    "joint venture",
    "partnership",
    "deal",
    "agreement",
    "collaboration",
]

# Minimum keyword matches required by source type
KEYWORD_THRESHOLDS = {
    "newswire": 1,
    "regulatory": 0,  # All FDA items pass through to LLM
    "trade": 0,       # All trade items pass through to LLM
    "broad": 2,       # Endpoints/STAT need 2 matches given volume
}

# --- LLM Settings (Gemini) ---------------------------------------------------
GEMINI_MODEL = "gemini-2.0-flash-lite"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_BATCH_SIZE = 20       # Articles per LLM call
GEMINI_RPM_LIMIT = 30        # Free tier: requests per minute
GEMINI_DELAY_SECONDS = 10    # Pause between batches to stay below free-tier rate limit
GEMINI_MIN_SCORE = 3         # Articles scoring below this are excluded (1-5 scale)

# --- Email Settings ----------------------------------------------------------
EMAIL_RECIPIENT = "nick.paul.taylor@gmail.com"
EMAIL_SENDER = "biopharma.digest@gmail.com"  # Update to your sending address
EMAIL_SUBJECT_PREFIX = "Biopharma Manufacturing Digest"

# --- State / Output ----------------------------------------------------------
STATE_FILE = "state/seen_urls.json"
DIGEST_DIR = "digests"
MAX_STATE_AGE_DAYS = 30  # Purge URLs older than this from state to keep file small
