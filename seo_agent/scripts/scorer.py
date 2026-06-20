"""
scorer.py — Score each keyword using multi-source signals and historical memory.
"""
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import yaml


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
    active_sources = sum([
        1 if trends_avg > 0 else 0,
        1 if reddit_count > 0 else 0,
        1 if rss_count > 0 else 0,
        1 if tavily_count > 0 else 0,
    ])
    source_diversity = active_sources / 4.0

    total_mentions = (1 if trends_avg > 0 else 0) + reddit_count + rss_count + tavily_count
    volume_normalized = min(total_mentions / 50.0, 1.0)

    quality_weight = trends_avg / 100.0

    confidence = min(1.0,
        (source_diversity * 0.3)
        + (volume_normalized * 0.4)
        + (quality_weight * 0.3)
    )
    return round(confidence, 3)


def _load_memory_helpers():
    """Lazy import so standalone confidence tests don't need the shared package on path."""
    try:
        from shared.memory import (
            get_published_this_cycle,
            get_saturation_score,
            get_momentum_direction,
            record_keyword_scores,
        )
        return get_published_this_cycle, get_saturation_score, get_momentum_direction, record_keyword_scores
    except Exception:
        return None, None, None, None


def _most_recent_publish_days(published_rows: list[dict], keyword: str) -> int | None:
    """Return the number of days since the most recent publish of this keyword, or None."""
    keyword_norm = keyword.lower()
    now = datetime.now()
    min_days = None
    for row in published_rows:
        if row.get("keyword", "").lower() != keyword_norm:
            continue
        run_date = row.get("run_date", "")
        try:
            dt = datetime.fromisoformat(run_date.replace("Z", "+00:00"))
            days = (now - dt).days
            if min_days is None or days < min_days:
                min_days = days
        except Exception:
            continue
    return min_days


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

    # ── Load cross-agent memory context ──────────────────────────
    get_published, get_saturation, get_momentum, record_scores = _load_memory_helpers()
    published_rows = get_published(lookback_weeks=4) if get_published else []

    # Score each keyword
    results = []
    for item in classified:
        kw = item["keyword"]
        t_avg = trends_avg.get(kw, 0)
        r_cnt = reddit_counts.get(kw, 0)
        s_cnt = rss_counts.get(kw, 0)
        v_cnt = tavily_counts.get(kw, 0)

        composite = (
            t_avg  * weights.get("weight_trends", 3.0) / 100
            + r_cnt  * weights.get("weight_reddit", 2.0)
            + s_cnt  * weights.get("weight_rss",    1.5)
            + v_cnt  * weights.get("weight_tavily",  1.0)
        )

        confidence = _calculate_confidence(t_avg, r_cnt, s_cnt, v_cnt)

        # ── Memory modifiers ─────────────────────────────────────
        multiplier = 1.0

        # Recency penalty: 30% if published in last 2 weeks, 15% if in last 4 weeks
        recent_days = _most_recent_publish_days(published_rows, kw)
        if recent_days is not None:
            if recent_days <= 14:
                multiplier *= 0.70
            elif recent_days <= 28:
                multiplier *= 0.85

        # Saturation penalty: proportional to saturation score
        if get_saturation:
            saturation = get_saturation(kw)
            multiplier *= (1.0 - saturation)

        # Momentum bonus: +15% if keyword is accelerating
        if get_momentum and get_momentum(kw) == "accelerating":
            multiplier *= 1.15

        final_score = composite * multiplier

        results.append({
            **item,
            "score":          round(final_score, 2),
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

    # ── Persist this week's scores to memory ─────────────────────
    if record_scores:
        week_label = datetime.now().strftime("%G-W%V")
        record_scores(week_label, results)

    return results
