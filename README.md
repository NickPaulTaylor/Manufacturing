# Biopharma Manufacturing Digest

Automated daily digest of pharmaceutical and biopharmaceutical manufacturing news,
delivered to your inbox every morning via GitHub Actions.

## What it monitors

| Source | Type |
|--------|------|
| GlobeNewswire (Pharma & Biotech) | Newswire |
| BusinessWire (Pharma & Biotech) | Newswire |
| FDA Press Announcements | Regulatory |
| FDA Warning Letters | Regulatory |
| FDA Drug Shortages | Regulatory |
| SEC EDGAR 8-K filings (SIC 2830–2836) | Regulatory/Financial |
| BioPharma Dive | Trade |
| Contract Pharma | Trade |
| Pharmaceutical Technology | Trade |
| Fierce Pharma | Trade |
| Endpoints News | Broad |
| STAT News (Pharma + Biotech) | Broad |

## Pipeline

```
Sources → RSS/EDGAR fetch → Keyword filter → Dedup (state) → Gemini LLM scoring → Email + commit
```

## Setup

### 1. Fork / clone this repo

### 2. Add GitHub Actions secrets

Go to **Settings → Secrets and variables → Actions** and add:

| Secret | Value |
|--------|-------|
| `GEMINI_API_KEY` | Your Google AI Studio API key (free tier) |
| `GMAIL_USER` | The Gmail address you'll send from |
| `GMAIL_APP_PASSWORD` | A [Gmail App Password](https://myaccount.google.com/apppasswords) |

> **Gmail App Password**: Go to your Google Account → Security → 2-Step Verification → App passwords.
> Generate a password for "Mail" on "Other (custom name)". Use that 16-character password here.

### 3. Update config.py

Edit `EMAIL_SENDER` in `config.py` to match your `GMAIL_USER`.

### 4. Enable write permissions for Actions

Go to **Settings → Actions → General → Workflow permissions** and select
**Read and write permissions**.

### 5. Run manually to test

Go to **Actions → Daily Biopharma Manufacturing Digest → Run workflow**.

## Running locally

```bash
pip install -r requirements.txt
export GEMINI_API_KEY=your_key
export GMAIL_USER=you@gmail.com
export GMAIL_APP_PASSWORD=your_app_password
python main.py
```

## Outputs

- `digests/digest_YYYY-MM-DD.md` — Human-readable digest committed to the repo
- `digests/digest_YYYY-MM-DD.csv` — Archive CSV for searching/analysis
- `state/seen_urls.json` — Deduplication state (committed after each run)
- Email to configured recipient

## Customisation

- **Keywords**: Edit `KEYWORDS` in `config.py`
- **Score threshold**: Edit `GEMINI_MIN_SCORE` (default: 3 out of 5)
- **Sources**: Add/remove entries in `RSS_SOURCES`
- **Recipient**: Edit `EMAIL_RECIPIENT` in `config.py`
