"""
scripts/bias_engine.py — Translate PerformanceSignals into concrete generation
directives that shape what the content writer produces.

This is the "bridge" between historical performance data and future content decisions.

Key decisions made here:
  1. Platform weight → how many articles/posts to bias toward each platform
  2. Format preference → which content types to request more of
  3. Topic angle → whether to frame content for top-performing platform norms
  4. Article count allocation → if generating 3 articles, which 3 use cases to pick

It does NOT call any APIs — it only reads signals and returns directives.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import math

from content_writer.scripts.performance_reader import PerformanceSignals


# ── Directive dataclass ────────────────────────────────────────

@dataclass
class GenerationDirectives:
    """
    A structured set of instructions that main.py passes through to the
    prompt builder and article context builder.
    """

    # ── Platform instructions ──────────────────────────────────
    # Ordered list of platforms to focus on (best-performing first)
    primary_platforms: list[str] = field(default_factory=list)

    # Platforms to explicitly skip or minimise this run
    deprioritised_platforms: list[str] = field(default_factory=list)

    # Numeric bias per platform (1.0 = neutral, >1.0 = lean toward, <1.0 = lean away)
    platform_bias: dict[str, float] = field(default_factory=dict)

    # ── Format instructions ────────────────────────────────────
    # Best-performing content types to prefer
    preferred_formats: list[str] = field(default_factory=list)

    # ── Article count guidance ─────────────────────────────────
    # Suggested number of articles targeting the best-performing platform's audience
    suggested_primary_count: int = 2
    suggested_secondary_count: int = 1

    # ── Tone / framing guidance ────────────────────────────────
    # If YouTube tutorials dominate, we want step-by-step practical framing
    # If LinkedIn posts win, we want professional insight framing
    recommended_framing: str = ""
    recommended_intent: str = "info"  # info | comparison | buying | problem

    # ── Prompt injection ───────────────────────────────────────
    # Full text block to inject into the Groq prompt
    performance_context_block: str = ""

    # Short one-liner for logging
    summary: str = "No performance data — using balanced defaults."

    # Whether performance data was available at all
    data_driven: bool = False


# ── Platform framing templates ─────────────────────────────────

PLATFORM_FRAMING = {
    "youtube":   (
        "step-by-step tutorial style — use numbered steps, practical commands, "
        "and a clear outcome the viewer achieves by the end"
    ),
    "linkedin":  (
        "professional insight style — lead with a data point or observation, "
        "not a product pitch; target engineers and decision-makers"
    ),
    "blog":      (
        "comprehensive how-to guide — use H2 sections, include code examples, "
        "target someone Googling this problem for the first time"
    ),
    "facebook":  (
        "community post style — conversational, ask a question, invite comments, "
        "feel like a maker sharing something cool they built"
    ),
    "x":         (
        "thread-style with punchy hook — first tweet is the hook, "
        "each subsequent tweet adds one insight, end with a CTA"
    ),
}

FORMAT_INTENTS = {
    "tutorial":     "info",
    "how-to":       "info",
    "comparison":   "comparison",
    "tip":          "info",
    "demo":         "info",
    "announcement": "info",
    "community":    "info",
    "news":         "info",
    "review":       "comparison",
    "buying-guide": "buying",
    "troubleshoot": "problem",
}

# How many articles to bump up if a platform is clearly dominant
DOMINANCE_THRESHOLD = 1.5  # platform score > 1.5x the next one = dominant


# ── Main bias function ─────────────────────────────────────────

def compute_directives(
    signals: PerformanceSignals,
    requested_article_count: int = 3,
) -> GenerationDirectives:
    """
    Given PerformanceSignals, return GenerationDirectives.

    Args:
        signals:                 Output from performance_reader.read_performance()
        requested_article_count: How many articles the content writer will generate

    Returns:
        GenerationDirectives with concrete instructions
    """
    directives = GenerationDirectives()
    directives.performance_context_block = signals.summary_for_prompt()

    if not signals.has_data or not signals.platform_scores:
        directives.summary = (
            "No tracker data available — using balanced platform defaults. "
            "Log published posts in the Social Generator to enable performance biasing."
        )
        directives.primary_platforms = ["blog", "linkedin", "youtube", "x", "facebook"]
        directives.platform_bias     = {p: 1.0 for p in directives.primary_platforms}
        directives.preferred_formats = ["tutorial", "comparison", "tip"]
        directives.recommended_framing = PLATFORM_FRAMING["blog"]
        directives.recommended_intent  = "info"
        return directives

    directives.data_driven = True

    # ── Platform ordering and bias ─────────────────────────────
    # Use signals.recommended_platform_order if populated, else derive from scores
    if signals.recommended_platform_order:
        directives.primary_platforms = signals.recommended_platform_order.copy()
    else:
        directives.primary_platforms = sorted(
            signals.platform_scores, key=signals.platform_scores.get, reverse=True
        )

    # Fill in any missing platforms (no data → neutral)
    all_platforms = ["linkedin", "x", "facebook", "youtube", "blog"]
    for p in all_platforms:
        if p not in directives.primary_platforms:
            directives.primary_platforms.append(p)

    # Bias = multiplier from signals (default 1.0)
    directives.platform_bias = {
        p: signals.format_bias.get(p, 1.0)
        for p in all_platforms
    }

    # Deprioritise the worst performer if it's significantly below average
    if signals.worst_platform:
        worst_score = signals.platform_scores.get(signals.worst_platform, 0)
        avg_score   = (
            sum(signals.platform_scores.values()) / len(signals.platform_scores)
            if signals.platform_scores else 1
        )
        if worst_score < avg_score * 0.5:
            directives.deprioritised_platforms.append(signals.worst_platform)

    # ── Format preferences ─────────────────────────────────────
    if signals.recommended_types:
        directives.preferred_formats = signals.recommended_types[:3]
    elif signals.best_content_type:
        directives.preferred_formats = [signals.best_content_type]
    else:
        directives.preferred_formats = ["tutorial", "comparison", "tip"]

    # ── Recommended framing ────────────────────────────────────
    top_platform = directives.primary_platforms[0] if directives.primary_platforms else "blog"
    directives.recommended_framing = PLATFORM_FRAMING.get(
        top_platform, PLATFORM_FRAMING["blog"]
    )

    # ── Intent recommendation ──────────────────────────────────
    best_format = directives.preferred_formats[0] if directives.preferred_formats else "tutorial"
    directives.recommended_intent = FORMAT_INTENTS.get(best_format, "info")

    # ── Article count allocation ───────────────────────────────
    # If one platform is clearly dominant, allocate more articles to it
    if len(signals.platform_scores) >= 2:
        sorted_scores = sorted(signals.platform_scores.values(), reverse=True)
        top, second   = sorted_scores[0], sorted_scores[1]
        if second > 0 and top / second >= DOMINANCE_THRESHOLD:
            directives.suggested_primary_count   = max(2, math.ceil(requested_article_count * 0.67))
            directives.suggested_secondary_count = requested_article_count - directives.suggested_primary_count
        else:
            directives.suggested_primary_count   = math.ceil(requested_article_count / 2)
            directives.suggested_secondary_count = requested_article_count - directives.suggested_primary_count
    else:
        directives.suggested_primary_count   = 2
        directives.suggested_secondary_count = max(0, requested_article_count - 2)

    # ── Build human-readable summary ───────────────────────────
    top = directives.primary_platforms[0] if directives.primary_platforms else "—"
    fmt = directives.preferred_formats[0]  if directives.preferred_formats  else "—"
    bias_str = f"{directives.platform_bias.get(top, 1.0):.1f}x"

    parts = [
        f"Performance-driven run: leading with {top.upper()} content ({bias_str} bias).",
        f"Best format: {fmt}.",
    ]
    if directives.deprioritised_platforms:
        parts.append(
            f"Deprioritising: {', '.join(directives.deprioritised_platforms).upper()}."
        )
    if signals.best_combo:
        plat, ctype = signals.best_combo.split(":", 1)
        parts.append(f"Top combo: {plat.upper()} + {ctype}.")

    directives.summary = " ".join(parts)
    return directives


# ── Context injector for article context ──────────────────────

def inject_bias_into_contexts(
    contexts: list[dict],
    directives: GenerationDirectives,
) -> list[dict]:
    """
    Enrich each article context dict with bias information
    so prompt_builder.py can use it when building the Groq prompt.

    Adds these keys to each context:
      - performance_context:  str  (full performance block for prompt)
      - preferred_platform:   str  (top platform for this article)
      - preferred_format:     str  (preferred content type)
      - recommended_framing:  str  (framing instruction)
      - recommended_intent:   str  (intent override if signals suggest it)
      - platform_bias:        dict (multipliers per platform)
      - is_performance_biased: bool
    """
    for i, ctx in enumerate(contexts):
        ctx["performance_context"]  = directives.performance_context_block
        ctx["preferred_platform"]   = (
            directives.primary_platforms[0]
            if directives.primary_platforms else "blog"
        )
        ctx["preferred_format"]     = (
            directives.preferred_formats[0]
            if directives.preferred_formats else "tutorial"
        )
        ctx["recommended_framing"]  = directives.recommended_framing
        ctx["platform_bias"]        = directives.platform_bias
        ctx["is_performance_biased"] = directives.data_driven

        # Only override intent if performance data strongly suggests a different one
        # AND the context's own intent isn't already from a high-signal keyword
        if directives.data_driven and directives.recommended_intent:
            ctx["performance_intent"] = directives.recommended_intent
        else:
            ctx["performance_intent"] = ctx.get("intent", "info")

    return contexts


# ── Quick summary for logging ──────────────────────────────────

def format_bias_report(signals: PerformanceSignals, directives: GenerationDirectives) -> str:
    """
    Returns a formatted string suitable for printing in main.py's output.
    """
    lines = [
        "\n[Performance Feedback Loop]",
        f"  Data driven   : {'YES' if directives.data_driven else 'NO (no tracker data)'}",
        f"  Posts analysed: {signals.total_posts}",
    ]
    if directives.data_driven:
        lines += [
            f"  Best platform : {signals.best_platform or '—'}",
            f"  Best format   : {signals.best_content_type or '—'}",
            f"  Best combo    : {signals.best_combo or '—'}",
            "",
            "  Platform bias multipliers:",
        ]
        for plat in ["youtube", "linkedin", "blog", "facebook", "x"]:
            bias = directives.platform_bias.get(plat, 1.0)
            bar  = "█" * int(bias * 5) + "░" * max(0, 10 - int(bias * 5))
            lines.append(f"    {plat:<12} [{bar}] {bias:.2f}x")
        if signals.insights:
            lines.append("\n  Key insights:")
            for ins in signals.insights[:3]:
                lines.append(f"    • {ins}")
        if signals.warnings:
            lines.append("\n  Warnings:")
            for w in signals.warnings:
                lines.append(f"    ⚠ {w}")
    lines.append(f"\n  Decision: {directives.summary}")
    return "\n".join(lines)