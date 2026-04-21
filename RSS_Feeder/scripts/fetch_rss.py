import feedparser
import yaml
from datetime import datetime
import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "../config/interests.yml")

def load_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)

def fetch_all():
    config = load_config()
    feeds = config.get("feeds", [])
    all_entries = []

    for url in feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                all_entries.append({
                    "title": entry.get("title", ""),
                    "link": entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "summary": entry.get("summary", "")
                })
            print(f"  ✓ {url} — {len(feed.entries)} entries")
        except Exception as e:
            print(f"  ✗ Failed to fetch {url}: {e}")

    # Save raw data
    today = datetime.now().strftime("%Y-%m-%d")
    os.makedirs("data/raw", exist_ok=True)
    with open(f"data/raw/rss_{today}.json", "w") as f:
        json.dump(all_entries, f, indent=2)

    print(f"Fetched {len(all_entries)} total entries from {len(feeds)} feeds")
    return all_entries