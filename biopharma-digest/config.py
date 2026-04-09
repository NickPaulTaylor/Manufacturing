# =============================================================================
# config.py — Central configuration for the biopharma manufacturing digest
# =============================================================================

# --- RSS Sources -------------------------------------------------------------
RSS_SOURCES = [
    # Newswires — correct URLs confirmed working in RSS readers
    {
        "name": "BusinessWire (Pharmaceutical)",
        "url": "https://feeds.businesswire.com/BW/Pharmaceutical-rss",
        "type": "newswire",
    },
    {
        "name": "BusinessWire (Biotechnology)",
        "url": "https://feeds.businesswire.com/BW/Biotechnology-rss",
        "type": "newswire",
    },
    {
        "name": "GlobeNewswire (Pharma)",
        "url": "https://www.globenewswire.com/RssFeed/industry/4573",
        "type": "newswire",
    },
    {
        "name": "GlobeNewswire (Biotech)",
        "url": "https://www.globenewswire.com/RssFeed/industry/4577",
        "type": "newswire",
    },
    # FDA RSS feeds
    {
        "name": "FDA Press Releases",
        "url": "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/press-releases/rss.xml",
        "type": "regulatory",
    },
    {
        "name": "FDA Criminal Investigations",
        "url": "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/oci-press-releases/rss.xml",
        "type": "regulatory",
    },
    # NOTE: openFDA API (fetchers/openfda.py) supplements these with structured
    # enforcement/recall data not available via RSS.
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
    "newswire": 1,   # Google News feeds are pre-targeted but still apply one match
    "regulatory": 0, # All FDA/EDGAR items go straight to LLM
    "trade": 0,      # All trade items go straight to LLM
    "broad": 2,      # Endpoints/STAT need 2 matches given volume
}

# --- LLM Settings (Gemini) ---------------------------------------------------
GEMINI_MODEL = "gemini-3.1-flash-lite-preview"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_BATCH_SIZE = 20       # Articles per LLM call
GEMINI_RPM_LIMIT = 30        # Free tier: requests per minute
GEMINI_DELAY_SECONDS = 10    # Pause between batches to stay below free-tier rate limit
GEMINI_MIN_SCORE = 4         # Articles scoring below this are excluded (1-5 scale)

# --- Email Settings ----------------------------------------------------------
EMAIL_RECIPIENT = "nick.paul.taylor@gmail.com"
EMAIL_SENDER = "biopharma.digest@gmail.com"  # Update to your sending address
EMAIL_SUBJECT_PREFIX = "Biopharma Manufacturing Digest"

# --- State / Output ----------------------------------------------------------
STATE_FILE = "state/seen_urls.json"
DIGEST_DIR = "digests"
MAX_STATE_AGE_DAYS = 30  # Purge URLs older than this from state to keep file small
