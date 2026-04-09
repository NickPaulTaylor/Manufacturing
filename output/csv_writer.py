"""
output/csv_writer.py — Write scored articles to a CSV archive file.
"""

import csv
import os
from datetime import datetime, timezone


FIELDS = [
    "date",
    "title",
    "url",
    "source_name",
    "source_type",
    "llm_score",
    "llm_category",
    "llm_note",
    "keyword_matches",
    "published_dt",
]


def write_csv(articles: list[dict], filepath: str) -> None:
    """Write articles to a CSV file."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        for a in articles:
            row = dict(a)
            row["date"] = run_date
            pub_dt = row.get("published_dt")
            row["published_dt"] = pub_dt.isoformat() if pub_dt else ""
            writer.writerow(row)
