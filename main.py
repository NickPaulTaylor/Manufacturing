"""
main.py — Orchestrates the biopharma manufacturing digest pipeline.

Run locally:
  export GEMINI_API_KEY=your_key
  export GMAIL_USER=you@gmail.com
  export GMAIL_APP_PASSWORD=your_app_password
  python main.py

Or triggered automatically via GitHub Actions.
"""

import logging
import os
import sys
from datetime import datetime, timezone

from config import RSS_SOURCES, DIGEST_DIR, STATE_FILE
from fetchers.rss import fetch_all_feeds
from fetchers.edgar import fetch_edgar_filings
from fetchers.openfda import fetch_fda_enforcement
from pipeline.filter import filter_articles
from pipeline.dedup import load_state, save_state, deduplicate
from pipeline.llm import score_articles
from output.markdown import generate_markdown
from output.csv_writer import write_csv
from output.email_sender import send_digest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("main")


def run():
    run_start = datetime.now(timezone.utc)
    logger.info(f"=== Biopharma Digest Pipeline starting at {run_start.isoformat()} ===")

    # 1. Load state (previously seen URLs)
    state = load_state()
    logger.info(f"State loaded: {len(state)} previously seen URLs")

    # 2. Fetch all sources
    logger.info("Fetching RSS sources...")
    rss_articles = fetch_all_feeds(RSS_SOURCES)

    logger.info("Fetching SEC EDGAR filings...")
    edgar_articles = fetch_edgar_filings()

    logger.info("Fetching FDA enforcement actions...")
    fda_articles = fetch_fda_enforcement()

    all_articles = rss_articles + edgar_articles + fda_articles
    logger.info(f"Total fetched: {len(all_articles)} articles")

    # 3. Keyword filter
    filtered = filter_articles(all_articles)

    # 4. Deduplicate against seen URLs
    new_articles, updated_state = deduplicate(filtered, state)

    if not new_articles:
        logger.info("No new articles after deduplication. Sending empty digest notice.")
        _send_empty_notice(run_start)
        save_state(updated_state)
        return

    # 5. LLM scoring
    logger.info(f"Sending {len(new_articles)} articles to Gemini for scoring...")
    scored_articles = score_articles(new_articles)

    if not scored_articles:
        logger.info("No articles passed the LLM relevance threshold.")
        _send_empty_notice(run_start)
        save_state(updated_state)
        return

    logger.info(f"{len(scored_articles)} articles will appear in today's digest")

    # 6. Generate outputs
    date_slug = run_start.strftime("%Y-%m-%d")
    os.makedirs(DIGEST_DIR, exist_ok=True)

    md_path = os.path.join(DIGEST_DIR, f"digest_{date_slug}.md")
    csv_path = os.path.join(DIGEST_DIR, f"digest_{date_slug}.csv")

    markdown_content = generate_markdown(scored_articles, run_date=run_start)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(markdown_content)
    logger.info(f"Markdown digest written to {md_path}")

    write_csv(scored_articles, csv_path)
    logger.info(f"CSV written to {csv_path}")

    # 7. Send email
    send_digest(markdown_content, article_count=len(scored_articles))

    # 8. Save updated state
    save_state(updated_state)

    run_end = datetime.now(timezone.utc)
    duration = (run_end - run_start).total_seconds()
    logger.info(f"=== Pipeline complete in {duration:.1f}s ===")


def _send_empty_notice(run_date: datetime) -> None:
    """Send a brief email when no relevant stories are found."""
    from output.email_sender import send_digest
    msg = (
        f"# Biopharma Manufacturing Digest\n"
        f"## {run_date.strftime('%A, %d %B %Y')}\n\n"
        f"No new manufacturing-relevant stories were identified today across monitored sources.\n\n"
        f"*Generated {run_date.strftime('%Y-%m-%d %H:%M UTC')}*"
    )
    send_digest(msg, article_count=0)


if __name__ == "__main__":
    run()
