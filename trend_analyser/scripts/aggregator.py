"""
scripts/aggregator.py — Aggregate keyword frequency across all sources.

Combines:
  - Keyword hit counts from preprocessed text items (RSS, Tavily, Reddit)
  - Google Trends average interest values
  - Source-type weights (Trends > RSS > Tavily > Reddit)

Returns a dict of keyword → aggregated stats.
"""

from collections import defaultdict

# How much each source type counts
SOURCE_WEIGHTS = {
    "trends": 3.0,   # Google Trends = strongest signal (hard search data)
    "rss":    2.0,   # Tech news = strong signal
    "tavily": 1.5,   # Research results = moderate
    "reddit": 1.0,   # Community chatter = weakest (noisy)
}


def aggregate_keywords(processed_items: list[dict]) -> dict[str, dict]:
    """
    Returns:
      {
        "raspberry pi": {
          "total_score":   float,
          "mention_count": int,
          "source_counts": {"rss": 3, "reddit": 1, ...},
          "source_score":  float,  # weighted by source type
        },
        ...
      }
    """
    keyword_stats: dict[str, dict] = defaultdict(lambda: {
        "total_score":   0.0,
        "mention_count": 0,
        "source_counts": defaultdict(int),
        "source_score":  0.0,
    })

    for item in processed_items:
        source  = item.get("source_type", "rss")
        weight  = SOURCE_WEIGHTS.get(source, 1.0)
        score   = item.get("score", 0)

        for kw in item.get("keywords", []):
            stats = keyword_stats[kw]
            stats["mention_count"]       += 1
            stats["source_counts"][source] += 1
            stats["total_score"]         += score
            stats["source_score"]        += weight

    # Convert defaultdicts to plain dicts
    result = {}
    for kw, stats in keyword_stats.items():
        result[kw] = {
            "total_score":   round(stats["total_score"], 2),
            "mention_count": stats["mention_count"],
            "source_counts": dict(stats["source_counts"]),
            "source_score":  round(stats["source_score"], 2),
        }

    return result


def merge_with_trends(keyword_counts: dict, trends_data: list[dict]) -> dict:
    """
    Adds Google Trends avg + latest values to keyword_counts in-place.
    Trends entries that don't exist in keyword_counts yet are added.
    """
    for series in trends_data:
        kw  = series.get("keyword", "").lower().strip()
        avg = series.get("avg", 0)
        if not kw:
            continue

        # Latest non-partial value
        latest = 0
        for point in reversed(series.get("timeline", [])):
            if not point.get("is_partial"):
                latest = point.get("value", 0)
                break

        if kw not in keyword_counts:
            keyword_counts[kw] = {
                "total_score":   0.0,
                "mention_count": 0,
                "source_counts": {},
                "source_score":  0.0,
            }

        keyword_counts[kw]["trends_avg"]    = avg
        keyword_counts[kw]["trends_latest"] = latest
        keyword_counts[kw]["source_counts"]["trends"] = keyword_counts[kw]["source_counts"].get("trends", 0) + 1
        keyword_counts[kw]["source_score"] += avg * SOURCE_WEIGHTS["trends"] / 100.0

    return keyword_counts