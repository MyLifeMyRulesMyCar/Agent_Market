"""
scripts/trending.py — Detect trending keywords with velocity-adjusted scoring.

A keyword is "trending" if it has:
  - High frequency (mention count across sources)
  - High combined score (weighted source score + total article score)
  - Recency (mentioned recently, not just historically)
  - Positive momentum relative to its own 4-week moving average

Returns a ranked list of trending keyword objects.
"""

from datetime import datetime, timedelta
from collections import defaultdict
from scripts.aggregator import merge_with_trends


def _load_memory_helpers():
    """Lazy import so tests can import this module without the shared package on path."""
    try:
        from shared.memory import get_keyword_history
        return get_keyword_history
    except Exception:
        return None


def _moving_average_from_history(keyword: str, get_history) -> float | None:
    """Return the 4-week moving average of SEO scores for this keyword, or None."""
    if get_history is None:
        return None
    rows = get_history(keyword, lookback_weeks=4)
    if not rows:
        return None
    scores = [r.get("score", 0) or 0 for r in rows]
    return sum(scores) / len(scores) if scores else None


def detect_trending(
    keyword_counts: dict,
    processed_items: list[dict],
    trends_data: list[dict] = None,
    top_n: int = 20,
    recency_days: int = 7,
) -> list[dict]:
    """
    keyword_counts : output of aggregator.aggregate_keywords()
    processed_items: output of preprocessor.preprocess()
    trends_data    : raw trends list from loaders (optional, improves ranking)
    top_n          : how many top keywords to return
    recency_days   : items older than this get a recency penalty

    Returns list of dicts sorted by score desc:
      [{
        "keyword":      str,
        "score":        float,   # composite trending score
        "mention_count":int,
        "source_count": int,     # number of distinct sources
        "trends_avg":   float,
        "recency_score":float,
      }]
    """
    if trends_data:
        keyword_counts = merge_with_trends(keyword_counts, trends_data)

    cutoff = datetime.now() - timedelta(days=recency_days)

    # Build recency index: how many items per keyword are recent
    recent_hits: dict[str, int] = defaultdict(int)
    for item in processed_items:
        date_str = item.get("date", "")
        try:
            item_date = datetime.strptime(date_str[:10], "%Y-%m-%d")
            if item_date >= cutoff:
                for kw in item.get("keywords", []):
                    recent_hits[kw] += 1
        except Exception:
            pass

    # First pass: raw composite scores
    raw_results = []
    for kw, stats in keyword_counts.items():
        mention_count  = stats.get("mention_count", 0)
        source_score   = stats.get("source_score", 0.0)
        total_score    = stats.get("total_score", 0.0)
        trends_avg     = stats.get("trends_avg", 0)
        recency        = recent_hits.get(kw, 0)
        source_count   = len(stats.get("source_counts", {}))

        composite = (
            source_score * 3.0
            + mention_count * 1.5
            + trends_avg * 0.5
            + recency * 2.0
        )

        source_diversity = min(source_count / 4.0, 1.0)
        volume_normalized = min(mention_count / 50.0, 1.0)
        quality_weight = trends_avg / 100.0
        confidence = min(1.0,
            (source_diversity * 0.3)
            + (volume_normalized * 0.4)
            + (quality_weight * 0.3)
        )

        raw_results.append({
            "keyword":       kw,
            "score":         round(composite, 2),
            "confidence":    round(confidence, 3),
            "mention_count": mention_count,
            "source_count":  source_count,
            "source_counts": stats.get("source_counts", {}),
            "trends_avg":    trends_avg,
            "trends_latest": stats.get("trends_latest", 0),
            "recency_score": recency,
        })

    raw_results.sort(key=lambda x: x["score"], reverse=True)

    # Second pass: velocity-adjust the top 30 candidates against their own history
    get_history = _load_memory_helpers()
    candidates = raw_results[:30]
    adjusted = []
    for item in candidates:
        current_score = item["score"]
        moving_avg = _moving_average_from_history(item["keyword"], get_history)
        if moving_avg is not None and moving_avg > 0:
            velocity_factor = current_score / moving_avg
        else:
            velocity_factor = 1.0

        item["score"] = round(current_score * velocity_factor, 2)
        item["velocity_factor"] = round(velocity_factor, 3)
        adjusted.append(item)

    adjusted.sort(key=lambda x: x["score"], reverse=True)
    return adjusted[:top_n]
