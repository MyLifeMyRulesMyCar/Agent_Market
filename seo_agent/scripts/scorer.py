"""
scorer.py — Score each keyword using multi-source signals.
"""
from collections import defaultdict
import yaml
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "config" / "config.yaml"


def load_weights() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg.get("scoring", {
        "weight_trends": 3.0,
        "weight_reddit": 2.0,
        "weight_rss":    1.5,
        "weight_tavily": 1.0,
    })


def _calculate_confidence(
    trends_avg: float,
    reddit_count: int,
    rss_count: int,
    tavily_count: int,
) -> float:
    """
    Confidence = weighted combination of:
      - source diversity (0.3)
      - volume normalized   (0.4)
      - data quality        (0.3)
    """
    # Source diversity: how many of the 4 possible sources have data?
    active_sources = sum([
        1 if trends_avg > 0 else 0,
        1 if reddit_count > 0 else 0,
        1 if rss_count > 0 else 0,
        1 if tavily_count > 0 else 0,
    ])
    source_diversity = active_sources / 4.0

    # Volume: total mentions across all sources (cap at 50 for normalization)
    total_mentions = (1 if trends_avg > 0 else 0) + reddit_count + rss_count + tavily_count
    volume_normalized = min(total_mentions / 50.0, 1.0)

    # Quality: Google Trends data is high quality; scale 0-100 → 0-1
    quality_weight = trends_avg / 100.0

    confidence = min(1.0,
        (source_diversity * 0.3)
        + (volume_normalized * 0.4)
        + (quality_weight * 0.3)
    )
    return round(confidence, 3)


def score(
    classified: list[dict],
    processed_items: list[dict],
    trends_data: list[dict],
) -> list[dict]:
    weights = load_weights()

    # Build mention counts per source
    reddit_counts:  dict[str, int]   = defaultdict(int)
    rss_counts:     dict[str, int]   = defaultdict(int)
    tavily_counts:  dict[str, int]   = defaultdict(int)
    reddit_scores:  dict[str, float] = defaultdict(float)

    for item in processed_items:
        src = item.get("source_type", "")
        for kw in item.get("keywords", []):
            if src == "reddit":
                reddit_counts[kw] += 1
                reddit_scores[kw] += item.get("score", 0)
            elif src == "rss":
                rss_counts[kw] += 1
            elif src == "tavily":
                tavily_counts[kw] += 1

    # Build trends avg lookup
    trends_avg: dict[str, float] = {}
    for t in trends_data:
        kw = t.get("keyword", "").lower()
        trends_avg[kw] = t.get("avg", 0)

    # Score each keyword
    results = []
    for item in classified:
        kw = item["keyword"]
        t_avg = trends_avg.get(kw, 0)
        r_cnt = reddit_counts.get(kw, 0)
        s_cnt = rss_counts.get(kw, 0)
        v_cnt = tavily_counts.get(kw, 0)

        composite = (
            t_avg  * weights.get("weight_trends", 3.0) / 100   # normalise 0-100 → 0-3
            + r_cnt  * weights.get("weight_reddit", 2.0)
            + s_cnt  * weights.get("weight_rss",    1.5)
            + v_cnt  * weights.get("weight_tavily",  1.0)
        )

        confidence = _calculate_confidence(t_avg, r_cnt, s_cnt, v_cnt)

        results.append({
            **item,
            "score":          round(composite, 2),
            "confidence":     confidence,
            "trends_avg":     t_avg,
            "reddit_count":   r_cnt,
            "rss_count":      s_cnt,
            "tavily_count":   v_cnt,
            "reddit_score":   round(reddit_scores.get(kw, 0), 1),
            "source_counts": {
                "trends": 1 if t_avg > 0 else 0,
                "reddit": r_cnt,
                "rss":    s_cnt,
                "tavily": v_cnt,
            },
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results