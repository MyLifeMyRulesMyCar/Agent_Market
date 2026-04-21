"""
main.py — Reddit Watcher: fetch hot/top posts from subreddits and export to Excel.

Usage:
    python main.py                  # use config defaults
    python main.py --sort top       # override sort type
    python main.py --sort top --time week
    python main.py --limit 100      # override post limit
    python main.py --subreddits OrangePI esp32   # override subreddits

Setup:
    1. pip install -r requirements.txt
    2. Create a Reddit app at https://www.reddit.com/prefs/apps (script type)
    3. Fill in .env with your credentials
    4. python main.py
"""

import sys
import os
import json
import yaml
import argparse
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(__file__))

CONFIG_PATH = os.path.join(os.getcwd(), "config", "config.yaml")


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="Reddit Watcher — fetch subreddit posts to Excel")
    parser.add_argument("--sort",       type=str, default=None, choices=["hot", "top", "new", "rising"])
    parser.add_argument("--time",       type=str, default=None, choices=["hour", "day", "week", "month", "year", "all"],
                        help="Time filter for --sort top")
    parser.add_argument("--limit",      type=int, default=None, help="Posts per subreddit")
    parser.add_argument("--subreddits", type=str, nargs="+", default=None, help="Override subreddit list")
    args = parser.parse_args()

    config = load_config()

    # Apply CLI overrides
    if args.sort:
        config["reddit"]["fetch"]["sort"] = args.sort
    if args.time:
        config["reddit"]["fetch"]["time_filter"] = args.time
    if args.limit:
        config["reddit"]["fetch"]["limit"] = args.limit
    if args.subreddits:
        config["reddit"]["subreddits"] = args.subreddits

    now = datetime.now()
    sort = config["reddit"]["fetch"]["sort"]
    subs = config["reddit"]["subreddits"]

    print(f"\n🔴 Reddit Watcher — {now.strftime('%Y-%m-%d %H:%M')}")
    print(f"   Sort: {sort} | Subreddits: {', '.join(subs)}")
    print("=" * 55)

    # Fetch
    from scripts.fetch_reddit import fetch_all
    print("\n[1/3] Fetching posts...")
    posts = fetch_all(config)
    print(f"\n   Total posts fetched: {len(posts)}")

    if not posts:
        print("\n⚠  No posts fetched. Check your credentials and subreddit names.")
        return

    # Save JSON backup
    output_cfg = config.get("output", {})
    if output_cfg.get("save_json", True):
        json_path = os.path.join(os.getcwd(), output_cfg.get("json_file", "output/reddit_raw.json"))
        os.makedirs(os.path.dirname(json_path), exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(posts, f, indent=2, ensure_ascii=False)
        print(f"\n[2/3] JSON backup → {json_path}")
    else:
        print("\n[2/3] Skipping JSON backup")

    # Export to Excel
    print("\n[3/3] Exporting to Excel...")
    from scripts.export_excel import export_to_excel

    excel_path = os.path.join(os.getcwd(), output_cfg.get("file", "output/reddit_trends.xlsx"))
    export_to_excel(posts, excel_path)

    # Summary
    print(f"\n{'='*55}")
    print(f"✅ Done!")
    print(f"   Posts fetched : {len(posts)}")
    print(f"   Subreddits    : {len(subs)}")
    print(f"   Excel output  : {excel_path}")

    # Top 5 posts preview
    top5 = sorted(posts, key=lambda p: p.get("score", 0), reverse=True)[:5]
    print(f"\n🏆 Top 5 posts across all subreddits:")
    for i, p in enumerate(top5, 1):
        print(f"  {i}. [{p['score']} pts] r/{p['subreddit']} — {p['title'][:70]}")


if __name__ == "__main__":
    main()