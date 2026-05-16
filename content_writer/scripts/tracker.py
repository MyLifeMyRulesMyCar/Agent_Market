"""
scripts/tracker.py — Topic deduplication & history tracking.

Keeps a lightweight JSON log of every keyword we've written about
so we don't generate duplicate articles on the same topic too soon.

File: content_writer/output/topics_history.json
"""

import json
from datetime import datetime, timedelta
from pathlib import Path


HISTORY_FILENAME = "topics_history.json"


def _history_path(output_dir: Path) -> Path:
    return output_dir / HISTORY_FILENAME


def load_history(output_dir: Path) -> list[dict]:
    """Load the topics history list. Returns empty list if none exists."""
    path = _history_path(output_dir)
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        return []
    except Exception as e:
        print(f"  [!] Could not load topics history: {e}")
        return []


def save_history(history: list[dict], output_dir: Path):
    """Persist the topics history list."""
    path = _history_path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def is_recently_written(keyword: str, history: list[dict], min_days: int) -> bool:
    """
    Check if a keyword was written about within the last `min_days` days.
    Matching is case-insensitive on keyword.
    """
    if min_days <= 0:
        return False

    cutoff = datetime.now() - timedelta(days=min_days)
    kw_lower = keyword.lower()

    for entry in history:
        if entry.get("keyword", "").lower() == kw_lower:
            written_at = entry.get("written_at", "")
            try:
                written_dt = datetime.fromisoformat(written_at)
                if written_dt > cutoff:
                    return True
            except Exception:
                continue
    return False


def filter_contexts(contexts: list[dict], history: list[dict], min_days: int) -> list[dict]:
    """
    Remove contexts whose keyword was recently written about.
    Prints a summary of what was skipped.
    """
    if min_days <= 0:
        return contexts

    fresh = []
    skipped = []
    for ctx in contexts:
        kw = ctx.get("keyword", "")
        if is_recently_written(kw, history, min_days):
            skipped.append(kw)
        else:
            fresh.append(ctx)

    if skipped:
        print(f"  [~] Skipped {len(skipped)} recently-written topic(s):")
        for kw in skipped:
            print(f"     • {kw}")

    return fresh


def record_topic(context: dict, metadata: dict, output_dir: Path):
    """
    Append a topic entry to history after a draft is successfully saved.
    """
    history = load_history(output_dir)

    entry = {
        "keyword":    context.get("keyword", ""),
        "title":      context.get("title", ""),
        "slug":       metadata.get("filename", "").replace(".md", ""),
        "filename":   metadata.get("filename", ""),
        "written_at": datetime.now().isoformat(),
        "intent":     context.get("intent", ""),
        "cluster":    context.get("cluster", ""),
    }

    history.append(entry)
    save_history(history, output_dir)


def get_recent_topics(output_dir: Path, days: int = 30) -> list[dict]:
    """Return topic entries written in the last N days."""
    history = load_history(output_dir)
    cutoff = datetime.now() - timedelta(days=days)
    recent = []
    for entry in history:
        try:
            written_dt = datetime.fromisoformat(entry.get("written_at", ""))
            if written_dt > cutoff:
                recent.append(entry)
        except Exception:
            continue
    return recent
