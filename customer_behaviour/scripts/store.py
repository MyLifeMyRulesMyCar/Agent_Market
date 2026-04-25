"""
scripts/store.py — Save final customer behaviour results.

Saves:
  output/YYYY-MM-DD_HH-MM.json  — timestamped run
  output/latest.json            — always the latest run (for dashboard)
"""

import json
from datetime import datetime
from pathlib import Path


def build_references(flat_items: list[dict], detected_issues: list[dict], max_refs: int = 200) -> list[dict]:
    """
    Build the references list for the dashboard from flat items.
    Enriches each item with the pain_category it was assigned to (if any).
    Only includes items that have a link (permalink).
    Sorted by importance descending.
    """
    # Build a lookup: text_clean -> pain_category (from detected_issues)
    pain_map = {}
    for issue in detected_issues:
        key = issue.get("text_clean", "")[:120]
        if key and issue.get("pain_category"):
            pain_map[key] = issue["pain_category"]

    refs = []
    seen_links = set()

    for item in flat_items:
        link = item.get("link", "")
        if not link:
            continue

        # Deduplicate by link for posts (comments share link with parent post)
        link_key = f"{link}::{item.get('type','post')}"
        if link_key in seen_links:
            continue
        seen_links.add(link_key)

        key = item.get("text_clean", "")[:120]
        # Normalize link to full Reddit URL regardless of what reddit_watcher stored
        norm_link = link.strip()
        if norm_link.startswith('/r/') or norm_link.startswith('/u/'):
            norm_link = 'https://www.reddit.com' + norm_link
        elif norm_link.startswith('r/'):
            norm_link = 'https://www.reddit.com/' + norm_link
        # already https:// → keep as-is

        raw = item.get("raw", {})
        refs.append({
            "title":         item.get("title") or item.get("post_title") or "",
            "text":          item.get("text_raw", item.get("text", ""))[:300],
            "score":         item.get("score", 0),
            "num_comments":  item.get("num_comments", 0),
            "subreddit":     item.get("subreddit", ""),
            "type":          item.get("type", "post"),
            "date":          item.get("date", ""),
            "pain_category": pain_map.get(key),
            "link":          norm_link,
            "post_id":       raw.get("post_id", ""),
            "importance":    item.get("importance", 0),
        })

    refs.sort(key=lambda x: x["importance"], reverse=True)
    return refs[:max_refs]


def save_results(output: dict, output_dir: Path) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)

    run_label = datetime.now().strftime("%Y-%m-%d_%H-%M")
    path   = output_dir / f"customer_behaviour_{run_label}.json"
    latest = output_dir / "latest.json"

    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    with open(latest, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"  ✅ JSON  → {path}")
    print(f"  ✅ Latest → {latest}")
    return str(path)


def load_latest(output_dir: Path) -> dict:
    """Load most recent run."""
    p = output_dir / "latest.json"
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)