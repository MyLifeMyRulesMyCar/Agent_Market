"""
main.py — Daily RSS pipeline runner.

Run this daily (e.g. via cron: 0 8 * * * python /path/to/main.py)
"""

from scripts.fetch_rss import fetch_all
from scripts.clean_filters import clean_and_filter
from scripts.deduplicate import remove_duplicates
from scripts.store import init_db, save_news
from datetime import datetime

def run_pipeline():
    print(f"\n🔄 RSS Pipeline — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    print("\n[1/4] Fetching feeds...")
    raw = fetch_all()

    print("\n[2/4] Filtering by interests...")
    cleaned = clean_and_filter(raw)

    print("\n[3/4] Removing duplicates...")
    unique = remove_duplicates(cleaned)

    print("\n[4/4] Storing to database...")
    init_db()
    save_news(unique)

    print(f"\n✅ Done. {len(unique)} new articles stored.")

if __name__ == "__main__":
    run_pipeline()