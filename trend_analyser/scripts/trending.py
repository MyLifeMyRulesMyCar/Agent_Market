"""
scripts/trending.py — Detect trending keywords.

A keyword is "trending" if it has:
  - High frequency (mention count across sources)
  - High combined score (weighted source score + total article score)
  - Recency (mentioned recently, not just historically)

Returns a ranked list of trending keyword objects.
"""

from datetime import datetime, timedelta
from collections import defaultdict
from scripts.aggregator import merge_with_trends


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

    results = []
    for kw, stats in keyword_counts.items():
        mention_count  = stats.get("mention_count", 0)
        source_score   = stats.get("source_score", 0.0)
        total_score    = stats.get("total_score", 0.0)
        trends_avg     = stats.get("trends_avg", 0)
        recency        = recent_hits.get(kw, 0)
        source_count   = len(stats.get("source_counts", {}))

        # Composite score formula:
        #   source_score (weighted by source quality)
        #   + mention_count * 1.5
        #   + trends_avg * 0.5 (normalised 0-100 → smaller addend)
        #   + recency * 2.0 (recent items worth more)
        composite = (
            source_score * 3.0
            + mention_count * 1.5
            + trends_avg * 0.5
            + recency * 2.0
        )

        results.append({
            "keyword":       kw,
            "score":         round(composite, 2),
            "mention_count": mention_count,
            "source_count":  source_count,
            "source_counts": stats.get("source_counts", {}),
            "trends_avg":    trends_avg,
            "trends_latest": stats.get("trends_latest", 0),
            "recency_score": recency,
        })

    # Sort by composite score
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_n]