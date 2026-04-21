"""
weekly_digest.py — Generate a weekly top-articles JSON file.

Run this once a week (e.g. every Sunday via cron).
It reads articles collected during the past 7 days from the DB,
scores them, deduplicates, and saves the top N to:
    data/weekly/YYYY-WW.json
"""

import os
import json
import yaml
from datetime import datetime, timedelta
from scripts.store import get_articles_since
from scripts.deduplicate import remove_duplicates

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config/interests.yml")

def load_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)

def generate_weekly_digest():
    config = load_config()
    top_n = config.get("weekly_top_n", 20)

    # Get ISO week label, e.g. "2025-W03"
    now = datetime.now()
    week_label = now.strftime("%G-W%V")
    since_date = (now - timedelta(days=7)).strftime("%Y-%m-%d")

    print(f"\n📰 Generating weekly digest for {week_label}")
    print(f"   Articles since: {since_date}")

    articles = get_articles_since(since_date)
    print(f"   Found {len(articles)} articles in DB")

    # Deduplicate again in case of any cross-day duplication
    articles = remove_duplicates(articles)

    # Sort by score descending, then by date descending
    articles.sort(key=lambda a: (-a["score"], a.get("published", "") or ""))

    top_articles = articles[:top_n]

    digest = {
        "week": week_label,
        "generated_at": now.isoformat(),
        "total_candidates": len(articles),
        "top_n": top_n,
        "articles": top_articles
    }

    os.makedirs("data/weekly", exist_ok=True)
    output_path = f"data/weekly/{week_label}.json"

    with open(output_path, "w") as f:
        json.dump(digest, f, indent=2)

    print(f"\n✅ Saved top {len(top_articles)} articles → {output_path}")
    print("\nTop 5 preview:")
    for i, a in enumerate(top_articles[:5], 1):
        print(f"  {i}. [{a['score']} pts] {a['title'][:80]}")
        print(f"     {a['link']}")

    return output_path, digest

if __name__ == "__main__":
    generate_weekly_digest()