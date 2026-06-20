"""
scripts/tracker.py — Topic deduplication & history tracking.

Uses the shared memory database as the source of truth and keeps the local
JSON file as a fallback mirror for backwards compatibility.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path


try:
    from shared.memory import (
        get_saturation_score,
        get_published_this_cycle,
        record_content_published,
    )
except Exception:
    try:
        import memory
        get_saturation_score = memory.get_saturation_score
        get_published_this_cycle = memory.get_published_this_cycle
        record_content_published = memory.record_content_published
    except Exception:
        get_saturation_score = None
        get_published_this_cycle = None
        record_content_published = None


HISTORY_FILENAME = "topics_history.json"
SATURATION_SKIP_THRESHOLD = 0.5


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
    Legacy fallback: check if a keyword was written about within the last `min_days` days.
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


def _is_recently_published(keyword: str, published_rows: list[dict], min_days: int) -> bool:
    """Check shared memory for a keyword published within min_days."""
    keyword_norm = keyword.lower().strip()
    cutoff = datetime.now() - timedelta(days=min_days)
    for row in published_rows:
        if row.get("keyword", "").lower().strip() != keyword_norm:
            continue
        run_date = row.get("run_date", "")
        try:
            dt = datetime.fromisoformat(run_date.replace("Z", "+00:00"))
            if dt > cutoff:
                return True
        except Exception:
            continue
    return False


def filter_contexts(contexts: list[dict], history: list[dict], min_days: int) -> list[dict]:
    """
    Remove contexts whose keyword is saturated or was recently published.
    Falls back to the local JSON history only if shared memory is unavailable.
    """
    if min_days <= 0:
        return contexts

    memory_available = get_saturation_score is not None and get_published_this_cycle is not None
    published_rows = get_published_this_cycle(lookback_weeks=4) if memory_available else []

    fresh = []
    skipped = []
    for ctx in contexts:
        kw = ctx.get("keyword", "")

        if memory_available:
            saturation = get_saturation_score(kw)
            if saturation >= SATURATION_SKIP_THRESHOLD:
                skipped.append((kw, f"saturation={saturation:.2f}"))
                continue
            if _is_recently_published(kw, published_rows, min_days):
                skipped.append((kw, "recently published"))
                continue
        else:
            if is_recently_written(kw, history, min_days):
                skipped.append((kw, "recently written (legacy)"))
                continue

        fresh.append(ctx)

    if skipped:
        print(f"  [~] Skipped {len(skipped)} recently-written / saturated topic(s):")
        for kw, reason in skipped:
            print(f"     • {kw} ({reason})")

    return fresh


def record_topic(context: dict, metadata: dict, output_dir: Path):
    """
    Append a topic entry to local history and mirror it to shared memory.
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

    # Mirror to shared memory
    try:
        if record_content_published is not None:
            week_label = datetime.now().strftime("%G-W%V")
            record_content_published(
                week_label=week_label,
                keyword=entry["keyword"],
                title=entry["title"],
                platform="blog",
                content_type=context.get("preferred_format") or context.get("content_type") or "article",
                status="draft",
                agent="content_writer",
            )
    except Exception as e:
        print(f"  [!] Could not record topic to shared memory: {e}")


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
