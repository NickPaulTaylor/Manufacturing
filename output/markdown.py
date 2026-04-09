"""
output/markdown.py — Generate a formatted markdown daily digest.
"""

from datetime import datetime, timezone


CATEGORY_LABELS = {
    "regulatory": "🔴 Regulatory",
    "capacity": "🏭 Capacity & Infrastructure",
    "supply_chain": "🔗 Supply Chain",
    "MA": "💼 M&A & Deals",
    "partnership": "🤝 Partnerships",
    "quality": "✅ Quality & Compliance",
    "technology": "⚗️ Technology",
    "workforce": "👥 Workforce",
    "other": "📰 Other",
}

SCORE_LABELS = {5: "★★★★★", 4: "★★★★☆", 3: "★★★☆☆"}


def generate_markdown(articles: list[dict], run_date: datetime = None) -> str:
    """Generate a markdown digest from scored articles."""
    if run_date is None:
        run_date = datetime.now(timezone.utc)

    date_str = run_date.strftime("%A, %d %B %Y")
    lines = [
        f"# Biopharma Manufacturing Digest",
        f"## {date_str}",
        "",
        f"*{len(articles)} stories identified by automated monitoring across "
        f"{_count_sources(articles)} sources.*",
        "",
        "---",
        "",
    ]

    # Group by category
    by_category: dict[str, list[dict]] = {}
    for article in articles:
        cat = article.get("llm_category", "other")
        by_category.setdefault(cat, []).append(article)

    # Define preferred category order
    category_order = [
        "regulatory", "quality", "supply_chain", "capacity",
        "MA", "partnership", "technology", "workforce", "other"
    ]

    for cat in category_order:
        if cat not in by_category:
            continue
        cat_articles = by_category[cat]
        label = CATEGORY_LABELS.get(cat, cat.title())
        lines.append(f"## {label}")
        lines.append("")

        for a in cat_articles:
            score = a.get("llm_score", 3)
            stars = SCORE_LABELS.get(score, "★★★☆☆")
            title = a.get("title", "Untitled")
            url = a.get("url", "#")
            source = a.get("source_name", "Unknown")
            note = a.get("llm_note", "")
            pub_dt = a.get("published_dt")
            pub_str = pub_dt.strftime("%d %b %H:%M UTC") if pub_dt else ""

            lines.append(f"### [{title}]({url})")
            lines.append(f"**Source:** {source}  |  **Score:** {stars}  |  **Published:** {pub_str}")
            lines.append("")
            if note:
                lines.append(f"> {note}")
                lines.append("")

        lines.append("---")
        lines.append("")

    lines.append(
        f"*Generated {run_date.strftime('%Y-%m-%d %H:%M UTC')} by biopharma-digest*"
    )

    return "\n".join(lines)


def _count_sources(articles: list[dict]) -> int:
    return len(set(a.get("source_name", "") for a in articles))
