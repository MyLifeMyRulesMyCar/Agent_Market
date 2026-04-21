"""
scripts/loader.py — Load Reddit raw data from reddit_watcher output.

Tries, in order:
  1. Explicit input_path argument
  2. PROJECT_ROOT/reddit_watcher/output/reddit_raw.json
  3. Any reddit_raw.json in the project tree
"""

import json
from pathlib import Path


def load_reddit_data(
    project_root: Path,
    input_path: str = None,
    subreddit_filter: str = None,
) -> list[dict]:
    """
    Load Reddit posts from JSON file.
    Returns list of post dicts matching reddit_watcher format.
    """
    # ── Find the file ─────────────────────────────────────────
    if input_path:
        json_path = Path(input_path)
    else:
        # Auto-detect from project root
        default = project_root / "reddit_watcher" / "output" / "reddit_raw.json"
        if default.exists():
            json_path = default
        else:
            # Search anywhere in project
            candidates = list(project_root.rglob("reddit_raw.json"))
            if not candidates:
                print(f"  ⚠ Could not find reddit_raw.json under {project_root}")
                return []
            json_path = candidates[0]

    print(f"   Loading from: {json_path}")

    if not json_path.exists():
        print(f"  ⚠ File not found: {json_path}")
        return []

    if json_path.stat().st_size == 0:
        print(f"  ⚠ File is empty: {json_path}")
        return []

    try:
        with open(json_path, encoding="utf-8") as f:
            posts = json.load(f)
    except json.JSONDecodeError as e:
        print(f"  ⚠ JSON parse error: {e}")
        return []

    # ── Optional subreddit filter ─────────────────────────────
    if subreddit_filter:
        before = len(posts)
        posts = [p for p in posts if p.get("subreddit", "").lower() == subreddit_filter.lower()]
        print(f"   Filtered to r/{subreddit_filter}: {len(posts)} / {before} posts")

    return posts