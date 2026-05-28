"""
scripts/performance_reader.py — Read the social media tracker log and compute
performance signals that the content writer uses to bias generation.

Reads: social_media_generator/data/posts_log.json
Returns: a PerformanceSignals object with actionable recommendations.

Logic:
  - Compute engagement score per post (likes + comments*2 + shares*3 + reach/10 + clicks*2)
  - Aggregate by platform → avg engagement score
  - Aggregate by content_type → avg engagement score
  - Aggregate by platform+content_type combo → best combos
  - Compute recency-weighted scores (recent posts count more)
  - Identify the top platform, top format, and any dead combos to avoid
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional


# ── Engagement scoring ─────────────────────────────────────────

def compute_engagement(metrics: dict) -> float:
    """
    Weighted engagement score from raw metrics.
    Weights based on marketing value: shares > clicks > comments > likes > reach.
    """
    return (
        metrics.get("likes", 0)        * 1.0
        + metrics.get("comments", 0)   * 2.0
        + metrics.get("shares", 0)     * 3.0
        + metrics.get("reach", 0)      * 0.1
        + metrics.get("views", 0)      * 0.05   # YouTube views (lower weight, higher volume)
        + metrics.get("clicks", 0)     * 2.0
        + metrics.get("watch_time_hours", 0) * 5.0  # YouTube watch time
        + metrics.get("page_views", 0) * 0.5
        + metrics.get("unique_visitors", 0) * 0.8
        + metrics.get("clicks_to_shop", 0) * 4.0  # highest intent signal
        + metrics.get("subscribers_gained", 0) * 10.0  # YouTube subs
    )


def recency_weight(posted_date: str, half_life_days: int = 30) -> float:
    """
    Exponential decay: a post from today = weight 1.0,
    a post from half_life_days ago = weight 0.5.
    Older posts still count but progressively less.
    """
    try:
        post_dt = datetime.strptime(posted_date[:10], "%Y-%m-%d")
        age_days = (datetime.now() - post_dt).days
        return max(0.1, 0.5 ** (age_days / half_life_days))
    except Exception:
        return 0.5  # neutral weight if date is missing


# ── Core analysis ──────────────────────────────────────────────

class PerformanceSignals:
    """
    Encapsulates all performance signals derived from tracker data.
    Consumed by bias_engine.py to shape content generation.
    """

    def __init__(self):
        self.total_posts         = 0
        self.has_data            = False

        # Platform-level signals
        self.platform_scores: dict[str, float]     = {}   # platform → avg weighted engagement
        self.platform_counts: dict[str, int]        = {}   # platform → post count
        self.platform_trend:  dict[str, str]        = {}   # platform → "rising"|"falling"|"stable"

        # Content type signals
        self.type_scores:  dict[str, float]         = {}   # content_type → avg weighted engagement
        self.type_counts:  dict[str, int]            = {}   # content_type → post count

        # Platform + type combo signals
        self.combo_scores: dict[str, float]         = {}   # "platform:type" → avg weighted engagement
        self.combo_counts: dict[str, int]            = {}   # "platform:type" → post count

        # Top performers
        self.best_platform:      Optional[str]      = None
        self.best_content_type:  Optional[str]      = None
        self.best_combo:         Optional[str]      = None  # "platform:type"
        self.worst_platform:     Optional[str]      = None

        # Relative multipliers (best platform = 1.0, others scaled)
        self.platform_multipliers: dict[str, float] = {}

        # Human-readable insights
        self.insights: list[str]                    = []
        self.warnings: list[str]                    = []

        # Raw platform bias for prompt injection
        # e.g. {"youtube": 1.8, "linkedin": 1.2, "facebook": 0.6, "x": 0.9, "blog": 1.0}
        self.format_bias: dict[str, float]          = {}

        # Suggested platform order for this week's content (best first)
        self.recommended_platform_order: list[str]  = []

        # Suggested content types that are working
        self.recommended_types: list[str]           = []

        # Minimum post count threshold before we trust a platform's data
        self.min_posts_for_signal = 2

    def summary_for_prompt(self) -> str:
        """
        Returns a compact, human-readable performance summary
        suitable for injection into the Groq prompt.
        """
        if not self.has_data:
            return "No historical performance data yet — use balanced platform distribution."

        lines = [
            "=== PERFORMANCE DATA FROM YOUR TRACKER (use this to bias your output) ===",
        ]

        if self.best_platform:
            score = self.platform_scores.get(self.best_platform, 0)
            count = self.platform_counts.get(self.best_platform, 0)
            lines.append(
                f"BEST PLATFORM: {self.best_platform.upper()} "
                f"(avg engagement {score:.1f}, {count} posts tracked)"
            )

        if self.worst_platform:
            lines.append(
                f"WEAKEST PLATFORM: {self.worst_platform.upper()} — "
                f"deprioritise this in your output"
            )

        if self.best_content_type:
            score = self.type_scores.get(self.best_content_type, 0)
            lines.append(
                f"BEST CONTENT TYPE: {self.best_content_type} "
                f"(avg engagement {score:.1f})"
            )

        if self.best_combo:
            plat, ctype = self.best_combo.split(":", 1)
            score = self.combo_scores.get(self.best_combo, 0)
            lines.append(
                f"BEST COMBO: {plat.upper()} + {ctype} "
                f"(avg engagement {score:.1f}) — prioritise this combination"
            )

        if self.recommended_platform_order:
            order = " > ".join(p.upper() for p in self.recommended_platform_order)
            lines.append(f"PLATFORM PRIORITY ORDER: {order}")

        if self.insights:
            lines.append("KEY INSIGHTS:")
            for ins in self.insights[:3]:
                lines.append(f"  • {ins}")

        if self.warnings:
            lines.append("AVOID:")
            for w in self.warnings[:2]:
                lines.append(f"  ✗ {w}")

        lines.append("=== END PERFORMANCE DATA ===")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "has_data":                    self.has_data,
            "total_posts":                 self.total_posts,
            "best_platform":               self.best_platform,
            "best_content_type":           self.best_content_type,
            "best_combo":                  self.best_combo,
            "worst_platform":              self.worst_platform,
            "platform_scores":             self.platform_scores,
            "platform_counts":             self.platform_counts,
            "platform_multipliers":        self.platform_multipliers,
            "type_scores":                 self.type_scores,
            "combo_scores":                self.combo_scores,
            "format_bias":                 self.format_bias,
            "recommended_platform_order":  self.recommended_platform_order,
            "recommended_types":           self.recommended_types,
            "insights":                    self.insights,
            "warnings":                    self.warnings,
        }


# ── Main reader ────────────────────────────────────────────────

def read_performance(
    project_root: Path,
    lookback_days: int = 90,
    min_posts: int = 1,
) -> PerformanceSignals:
    """
    Load tracker log and compute performance signals.

    Args:
        project_root:  Root of the Marketing_agents project
        lookback_days: Only consider posts from this many days ago (default 90)
        min_posts:     Minimum posts per platform to include in ranking (default 1)

    Returns:
        PerformanceSignals object (always returns one, even if no data)
    """
    signals = PerformanceSignals()
    signals.min_posts_for_signal = min_posts

    log_path = project_root / "social_media_generator" / "data" / "posts_log.json"

    if not log_path.exists():
        signals.insights.append(
            "No tracker data found yet. Log published posts in the Social Generator "
            "to enable performance-based content biasing."
        )
        return signals

    try:
        with open(log_path, encoding="utf-8") as f:
            all_posts = json.load(f)
    except Exception as e:
        signals.warnings.append(f"Could not read tracker log: {e}")
        return signals

    if not all_posts:
        return signals

    # Filter to lookback window
    cutoff = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    posts = [
        p for p in all_posts
        if p.get("posted_date", "9999") >= cutoff
    ]

    if not posts:
        # Fall back to all posts if the window is too narrow
        posts = all_posts

    signals.total_posts = len(posts)
    signals.has_data    = len(posts) > 0

    # ── Accumulate weighted scores ─────────────────────────────
    # Structure: {key: {"total_weighted_score": float, "count": int, "recent_count": int}}
    platform_agg: dict[str, dict] = defaultdict(lambda: {"total": 0.0, "count": 0, "recent": 0})
    type_agg:     dict[str, dict] = defaultdict(lambda: {"total": 0.0, "count": 0})
    combo_agg:    dict[str, dict] = defaultdict(lambda: {"total": 0.0, "count": 0})

    # For trend detection: split into two halves
    posts_sorted = sorted(posts, key=lambda p: p.get("posted_date", ""))
    mid          = max(len(posts_sorted) // 2, 1)
    first_half   = posts_sorted[:mid]
    second_half  = posts_sorted[mid:]

    first_half_plat:  dict[str, float] = defaultdict(float)
    second_half_plat: dict[str, float] = defaultdict(float)

    for i, post in enumerate(posts_sorted):
        platform     = post.get("platform", "unknown").lower().strip()
        content_type = post.get("content_type", "unknown").lower().strip()
        posted_date  = post.get("posted_date", "")
        metrics      = post.get("metrics", {})

        raw_score     = compute_engagement(metrics)
        weight        = recency_weight(posted_date)
        weighted      = raw_score * weight

        platform_agg[platform]["total"]  += weighted
        platform_agg[platform]["count"]  += 1
        type_agg[content_type]["total"]  += weighted
        type_agg[content_type]["count"]  += 1

        combo_key = f"{platform}:{content_type}"
        combo_agg[combo_key]["total"] += weighted
        combo_agg[combo_key]["count"] += 1

        # Trend split
        if i < mid:
            first_half_plat[platform] += weighted
        else:
            second_half_plat[platform] += weighted

    # ── Compute averages ───────────────────────────────────────
    for plat, agg in platform_agg.items():
        if agg["count"] > 0:
            signals.platform_scores[plat] = round(agg["total"] / agg["count"], 2)
            signals.platform_counts[plat] = agg["count"]

    for ctype, agg in type_agg.items():
        if agg["count"] > 0:
            signals.type_scores[ctype] = round(agg["total"] / agg["count"], 2)
            signals.type_counts[ctype] = agg["count"]

    for combo, agg in combo_agg.items():
        if agg["count"] > 0:
            signals.combo_scores[combo] = round(agg["total"] / agg["count"], 2)
            signals.combo_counts[combo] = agg["count"]

    # ── Identify top/bottom performers ─────────────────────────
    # Only rank platforms with enough data
    qualified_platforms = {
        p: s for p, s in signals.platform_scores.items()
        if signals.platform_counts.get(p, 0) >= min_posts
    }

    if qualified_platforms:
        sorted_plats = sorted(qualified_platforms.items(), key=lambda x: x[1], reverse=True)
        signals.best_platform  = sorted_plats[0][0]
        signals.worst_platform = sorted_plats[-1][0] if len(sorted_plats) > 1 else None
        signals.recommended_platform_order = [p for p, _ in sorted_plats]

        # Compute multipliers relative to best
        best_score = sorted_plats[0][1] or 1.0
        for plat, score in sorted_plats:
            signals.platform_multipliers[plat] = round(score / best_score, 2)

    # Compute format bias for ALL platforms (default 1.0 if no data)
    all_platforms = ["linkedin", "x", "facebook", "youtube", "blog"]
    if qualified_platforms:
        best_score = max(qualified_platforms.values()) or 1.0
        for plat in all_platforms:
            if plat in qualified_platforms:
                signals.format_bias[plat] = round(qualified_platforms[plat] / best_score, 2)
            else:
                # No data → neutral bias
                signals.format_bias[plat] = 1.0
    else:
        for plat in all_platforms:
            signals.format_bias[plat] = 1.0

    # Best content type (with at least min_posts)
    qualified_types = {
        t: s for t, s in signals.type_scores.items()
        if signals.type_counts.get(t, 0) >= min_posts
    }
    if qualified_types:
        signals.best_content_type = max(qualified_types, key=qualified_types.get)
        signals.recommended_types = sorted(qualified_types, key=qualified_types.get, reverse=True)

    # Best combo
    qualified_combos = {
        c: s for c, s in signals.combo_scores.items()
        if signals.combo_counts.get(c, 0) >= min_posts
    }
    if qualified_combos:
        signals.best_combo = max(qualified_combos, key=qualified_combos.get)

    # ── Platform trend (rising/falling/stable) ─────────────────
    for plat in platform_agg:
        f1_count = sum(1 for p in first_half  if p.get("platform","").lower() == plat)
        f2_count = sum(1 for p in second_half if p.get("platform","").lower() == plat)
        f1_score = first_half_plat.get(plat, 0)
        f2_score = second_half_plat.get(plat, 0)

        f1_avg = f1_score / f1_count if f1_count else 0
        f2_avg = f2_score / f2_count if f2_count else 0

        if f1_avg == 0:
            signals.platform_trend[plat] = "new"
        elif f2_avg > f1_avg * 1.2:
            signals.platform_trend[plat] = "rising"
        elif f2_avg < f1_avg * 0.8:
            signals.platform_trend[plat] = "falling"
        else:
            signals.platform_trend[plat] = "stable"

    # ── Generate human-readable insights ──────────────────────
    _generate_insights(signals)

    return signals


def _generate_insights(signals: PerformanceSignals):
    """Populate signals.insights and signals.warnings with readable text."""
    ps = signals.platform_scores
    pc = signals.platform_counts
    ts = signals.type_scores

    if not ps:
        signals.insights.append(
            "Not enough data yet — log more published posts to unlock performance insights."
        )
        return

    # Best platform insight
    if signals.best_platform:
        best_score = ps[signals.best_platform]
        best_count = pc[signals.best_platform]
        multiplier = signals.platform_multipliers.get(signals.best_platform, 1.0)
        signals.insights.append(
            f"{signals.best_platform.upper()} is your highest-performing platform "
            f"(avg engagement score {best_score:.1f} across {best_count} posts). "
            f"Prioritise it in this generation run."
        )

    # Worst platform warning
    if signals.worst_platform and signals.best_platform != signals.worst_platform:
        worst_score = ps[signals.worst_platform]
        best_score  = ps.get(signals.best_platform, 1)
        ratio       = (worst_score / best_score * 100) if best_score else 0
        signals.warnings.append(
            f"{signals.worst_platform.upper()} is underperforming "
            f"(only {ratio:.0f}% of your best platform's engagement). "
            f"Consider deprioritising or changing your approach there."
        )

    # Rising platform
    for plat, trend in signals.platform_trend.items():
        if trend == "rising" and plat in ps:
            signals.insights.append(
                f"{plat.upper()} engagement is trending UP in your recent posts — "
                f"good time to push more content there."
            )

    # Best content type
    if signals.best_content_type:
        score = ts.get(signals.best_content_type, 0)
        signals.insights.append(
            f"'{signals.best_content_type}' content type is your best performer "
            f"(avg engagement {score:.1f}). Lead with this format."
        )

    # Best combo
    if signals.best_combo:
        plat, ctype = signals.best_combo.split(":", 1)
        score = signals.combo_scores.get(signals.best_combo, 0)
        signals.insights.append(
            f"Your best combination is {plat.upper()} + {ctype} content "
            f"(avg engagement {score:.1f}). This combo should be your first priority."
        )

    # Untested platforms
    all_platforms = {"linkedin", "x", "facebook", "youtube", "blog"}
    tested = set(ps.keys())
    untested = all_platforms - tested
    if untested:
        signals.insights.append(
            f"You haven't logged any posts for: {', '.join(sorted(untested))}. "
            f"Try one this week to gather comparison data."
        )