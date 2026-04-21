"""
scripts/rising.py — Detect rising topics based on velocity (rate of change).

A topic is "rising" if its recent interest has increased significantly
compared to the prior baseline period.

Uses two approaches:
  1. Google Trends velocity: compare last N weeks vs prior N weeks
  2. Text mention velocity: compare recent item counts vs baseline window
"""

from datetime import datetime, timedelta
from collections import defaultdict


# ── Trends-based velocity ─────────────────────────────────────

def compute_trends_velocity(
    trends_data: list[dict],
    recent_weeks: int = 4,
    baseline_weeks: int = 8,
) -> list[dict]:
    """
    For each keyword in trends_data, compare average value in the
    most recent `recent_weeks` vs the `baseline_weeks` before that.

    Velocity = (recent_avg - baseline_avg) / (baseline_avg + 1) * 100
    Returns only keywords with positive velocity (rising).
    """
    rising = []

    for series in trends_data:
        kw       = series.get("keyword", "")
        timeline = series.get("timeline", [])

        # Filter out partial weeks and sort by timestamp
        complete = [p for p in timeline if not p.get("is_partial")]
        complete.sort(key=lambda p: p.get("timestamp", 0))

        if len(complete) < recent_weeks + baseline_weeks:
            continue

        recent   = complete[-(recent_weeks):]
        baseline = complete[-(recent_weeks + baseline_weeks):-(recent_weeks)]

        recent_avg   = sum(p["value"] for p in recent)   / len(recent)
        baseline_avg = sum(p["value"] for p in baseline) / len(baseline)

        velocity = (recent_avg - baseline_avg) / (baseline_avg + 1) * 100

        if velocity > 10:  # at least 10% increase to qualify
            peak_val   = max(p["value"] for p in recent)
            peak_date  = next(
                (p["date"] for p in reversed(recent) if p["value"] == peak_val), ""
            )
            rising.append({
                "keyword":      kw,
                "velocity":     round(velocity, 1),
                "recent_avg":   round(recent_avg, 1),
                "baseline_avg": round(baseline_avg, 1),
                "peak_value":   peak_val,
                "peak_date":    peak_date,
                "market":       series.get("market", ""),
                "source":       "trends",
            })

    rising.sort(key=lambda x: x["velocity"], reverse=True)
    return rising


# ── Text-mention velocity ─────────────────────────────────────

def compute_mention_velocity(
    processed_items: list[dict],
    recent_days: int = 7,
    baseline_days: int = 21,
) -> list[dict]:
    """
    Count keyword mentions in the recent window vs a baseline window.
    Flags keywords whose recent rate is significantly higher than baseline.
    """
    now      = datetime.now()
    recent_start   = now - timedelta(days=recent_days)
    baseline_start = now - timedelta(days=recent_days + baseline_days)

    recent_counts:   dict[str, int] = defaultdict(int)
    baseline_counts: dict[str, int] = defaultdict(int)

    for item in processed_items:
        date_str = item.get("date", "")
        try:
            item_date = datetime.strptime(date_str[:10], "%Y-%m-%d")
        except Exception:
            continue

        for kw in item.get("keywords", []):
            if item_date >= recent_start:
                recent_counts[kw] += 1
            elif item_date >= baseline_start:
                baseline_counts[kw] += 1

    # Normalise by window length so we compare rates, not raw counts
    recent_rate_factor   = baseline_days / recent_days  # scale recent to same window

    rising = []
    all_keywords = set(recent_counts.keys()) | set(baseline_counts.keys())

    for kw in all_keywords:
        r = recent_counts.get(kw, 0)
        b = baseline_counts.get(kw, 0)

        if r == 0:
            continue

        # Projected count if recent rate continued for baseline window
        projected = r * recent_rate_factor
        velocity  = (projected - b) / (b + 1) * 100

        if velocity > 20 and r >= 2:  # need at least 2 recent mentions
            rising.append({
                "keyword":        kw,
                "velocity":       round(velocity, 1),
                "recent_count":   r,
                "baseline_count": b,
                "source":         "text",
            })

    rising.sort(key=lambda x: x["velocity"], reverse=True)
    return rising


# ── Merge both signals ────────────────────────────────────────

def detect_rising(
    processed_items: list[dict],
    trends_data: list[dict],
    window_days: int = 7,
) -> list[dict]:
    """
    Combine trends velocity and text mention velocity.
    Deduplicate: if a keyword appears in both, merge and boost its signal.
    """
    trends_rising  = compute_trends_velocity(trends_data, recent_weeks=4)
    mention_rising = compute_mention_velocity(processed_items, recent_days=window_days)

    # Index by keyword
    merged: dict[str, dict] = {}

    for item in trends_rising:
        kw = item["keyword"]
        merged[kw] = {**item, "signals": ["trends"]}

    for item in mention_rising:
        kw = item["keyword"]
        if kw in merged:
            # Both signals agree → boost velocity
            merged[kw]["velocity"] = round(
                max(merged[kw]["velocity"], item["velocity"]) * 1.25, 1
            )
            merged[kw]["signals"].append("text")
            merged[kw]["recent_count"]   = item.get("recent_count", 0)
            merged[kw]["baseline_count"] = item.get("baseline_count", 0)
        else:
            merged[kw] = {**item, "signals": ["text"]}

    result = sorted(merged.values(), key=lambda x: x["velocity"], reverse=True)
    return result