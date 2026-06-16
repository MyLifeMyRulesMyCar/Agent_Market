"""
shared/signal_merger.py — Marketing Agents Signal Merger

Reads the four analysis agent outputs and produces a structured
"signal_matrix" — a compact, normalized representation that downstream
steps can query without re-reading raw JSONs.

Inputs:
  customer_behaviour/output/latest.json
  trend_analyser/output/latest.json
  seo_agent/output/latest.json
  competitor_analysis/output/latest.json

Output:
  shared/signal_matrix.json

This module is deterministic Python — no LLM calls.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
SHARED_DIR   = PROJECT_ROOT / "shared"

AGENT_PATHS = {
    "customer_behaviour": PROJECT_ROOT / "customer_behaviour" / "output" / "latest.json",
    "trend_analyser":     PROJECT_ROOT / "trend_analyser"     / "output" / "latest.json",
    "seo_agent":          PROJECT_ROOT / "seo_agent"          / "output" / "latest.json",
    "competitor_analysis":PROJECT_ROOT / "competitor_analysis"/ "output" / "latest.json",
}

OUTPUT_PATH = SHARED_DIR / "signal_matrix.json"


# ── Helpers ───────────────────────────────────────────────────

def _log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [signal_merger] {msg}"
    safe = line.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
           sys.stdout.encoding or "utf-8", errors="replace")
    print(safe)


def _load_json(path: Path, label: str) -> dict:
    if not path.exists():
        _log(f"[MISSING] {label}: {path}")
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        _log(f"[LOADED]  {label}: {len(json.dumps(data))} chars")
        return data
    except Exception as e:
        _log(f"[ERROR]   {label}: {e}")
        return {}


def _norm_keyword(kw: str) -> str:
    """Normalize keyword for cross-agent matching."""
    return kw.lower().strip() if kw else ""


def _keyword_overlap(kws_a: list[str], kws_b: list[str]) -> set[str]:
    """Return normalized overlapping keywords between two lists."""
    set_a = {_norm_keyword(k) for k in kws_a}
    set_b = {_norm_keyword(k) for k in kws_b}
    return set_a & set_b


# ── Extractors ────────────────────────────────────────────────

def extract_trending_keywords(trend_data: dict, seo_data: dict) -> list[dict]:
    """
    Merge trending keywords from trend_analyser and seo_agent.
    When both agents mention the same keyword, merge their scores and
    take the max confidence.
    """
    trend_keywords = trend_data.get("trending_keywords", [])
    seo_keywords   = seo_data.get("top_keywords", [])

    by_kw: dict[str, dict] = {}

    for tk in trend_keywords:
        kw = _norm_keyword(tk.get("keyword", ""))
        if not kw:
            continue
        by_kw[kw] = {
            "keyword": tk.get("keyword", kw),
            "score": tk.get("score", 0),
            "confidence": tk.get("confidence", 0),
            "sources": ["trend_analyser"],
            "velocity": tk.get("trends_latest", 0),
            "mention_count": tk.get("mention_count", 0),
        }

    for sk in seo_keywords:
        kw = _norm_keyword(sk.get("keyword", ""))
        if not kw:
            continue
        if kw in by_kw:
            # Merge: take max confidence, sum mention counts, add source
            existing = by_kw[kw]
            existing["confidence"] = max(existing["confidence"], sk.get("confidence", 0))
            existing["score"] = max(existing["score"], sk.get("score", 0))
            existing["mention_count"] = existing.get("mention_count", 0) + sk.get("reddit_count", 0) + sk.get("tavily_count", 0) + sk.get("rss_count", 0)
            if "seo_agent" not in existing["sources"]:
                existing["sources"].append("seo_agent")
        else:
            by_kw[kw] = {
                "keyword": sk.get("keyword", kw),
                "score": sk.get("score", 0),
                "confidence": sk.get("confidence", 0),
                "sources": ["seo_agent"],
                "velocity": 0,
                "mention_count": sk.get("reddit_count", 0) + sk.get("tavily_count", 0) + sk.get("rss_count", 0),
            }

    # Sort by score descending
    result = sorted(by_kw.values(), key=lambda x: x["score"], reverse=True)
    return result[:50]  # cap at 50


def extract_pain_clusters(behaviour_data: dict) -> list[dict]:
    """Extract and normalize pain point clusters."""
    pain_points = behaviour_data.get("pain_points", [])
    result = []
    for pp in pain_points:
        examples = pp.get("examples", [])
        result.append({
            "label": pp.get("label", "Unknown"),
            "mentions": pp.get("mentions", 0),
            "confidence": pp.get("confidence", 0),
            "example_quotes": examples[:3] if isinstance(examples, list) else [],
            "category": pp.get("category", "other"),
            "keywords": pp.get("keywords", []),
        })
    return result


def extract_competitor_gaps(competitor_data: dict) -> list[dict]:
    """
    Extract competitor gaps from feature_matrix and sw_analysis.
    Each gap becomes: {competitor_name, missing_features[], threat_score, confidence}
    """
    fm = competitor_data.get("feature_matrix", {})
    feature_gaps = fm.get("feature_gaps", {})
    sw_analysis = competitor_data.get("sw_analysis", {})
    pricing = competitor_data.get("pricing_analysis", {})

    # Group gaps by competitor
    gaps_by_competitor: dict[str, list[str]] = defaultdict(list)
    for feature, competitors in feature_gaps.items():
        for comp_name in competitors:
            gaps_by_competitor[comp_name].append(feature)

    result = []
    for comp_name, missing in gaps_by_competitor.items():
        sw = sw_analysis.get(comp_name, {})
        threat_score = sw.get("threat_score", 5.0)
        threat_confidence = sw.get("threat_confidence", 0.5)
        price_info = pricing.get(comp_name, {})

        result.append({
            "competitor_name": comp_name,
            "missing_features": missing,
            "threat_score": threat_score,
            "confidence": threat_confidence,
            "their_price": price_info.get("price_usd"),
            "their_tier": price_info.get("tier"),
        })

    # Also include competitors with no gaps but high threat score
    for comp_name, sw in sw_analysis.items():
        if comp_name not in gaps_by_competitor and not sw.get("is_mine", False):
            price_info = pricing.get(comp_name, {})
            result.append({
                "competitor_name": comp_name,
                "missing_features": [],
                "threat_score": sw.get("threat_score", 5.0),
                "confidence": sw.get("threat_confidence", 0.5),
                "their_price": price_info.get("price_usd"),
                "their_tier": price_info.get("tier"),
            })

    # Sort by threat_score descending
    result.sort(key=lambda x: x["threat_score"], reverse=True)
    return result


def generate_opportunity_signals(
    trending_keywords: list[dict],
    pain_clusters: list[dict],
    competitor_gaps: list[dict],
    rising_topics: list[dict],
) -> list[dict]:
    """
    Cross-reference the three signal types to find content opportunities.

    An opportunity signal links:
      - a keyword (from SEO/trends)
      - a pain point (from customer behaviour)
      - a competitor gap (from competitor analysis)

    strength is computed from the underlying confidence scores.
    rationale is deterministic text.
    """
    opportunities = []

    # Build lookup for fast matching
    pain_kw_map: dict[str, list[dict]] = defaultdict(list)
    for pc in pain_clusters:
        for kw in pc.get("keywords", []):
            pain_kw_map[_norm_keyword(kw)].append(pc)

    gap_kw_map: dict[str, list[dict]] = defaultdict(list)
    for cg in competitor_gaps:
        for gap_feat in cg.get("missing_features", []):
            # Index by each word in the feature name
            for word in gap_feat.lower().split():
                if len(word) > 2:
                    gap_kw_map[word].append(cg)

    rising_kw_set = {_norm_keyword(r.get("keyword", "")) for r in rising_topics}
    rising_by_kw = {_norm_keyword(r.get("keyword", "")): r for r in rising_topics}

    for tk in trending_keywords[:30]:  # only top 30 keywords
        kw = _norm_keyword(tk["keyword"])
        if not kw:
            continue

        keyword_conf = tk.get("confidence", 0)
        keyword_score = tk.get("score", 0)
        mention_count = tk.get("mention_count", 0)

        # Find linked pain points
        linked_pains = pain_kw_map.get(kw, [])
        if not linked_pains:
            # Try partial match: any pain keyword contains trend keyword
            for pk, pvals in pain_kw_map.items():
                if kw in pk or pk in kw:
                    linked_pains.extend(pvals)
            # Deduplicate
            seen = set()
            deduped = []
            for p in linked_pains:
                lid = p.get("label", "")
                if lid not in seen:
                    seen.add(lid)
                    deduped.append(p)
            linked_pains = deduped

        # Pick the best-linked pain first (needed for gap matching)
        best_pain = linked_pains[0] if linked_pains else None

        # Find linked competitor gaps by keyword
        linked_gaps = []
        for word in kw.split():
            if len(word) > 2:
                linked_gaps.extend(gap_kw_map.get(word, []))

        # If no keyword match, try matching pain point keywords to gap features
        if not linked_gaps and best_pain:
            for pkw in best_pain.get("keywords", []):
                pkw_norm = _norm_keyword(pkw)
                if len(pkw_norm) > 2:
                    linked_gaps.extend(gap_kw_map.get(pkw_norm, []))
                # Also try partial matches
                for gap_word, gap_list in gap_kw_map.items():
                    if pkw_norm in gap_word or gap_word in pkw_norm:
                        linked_gaps.extend(gap_list)

        # If still no gap, pick the highest-threat competitor with gaps
        if not linked_gaps and competitor_gaps:
            top_gap = max(competitor_gaps, key=lambda x: x.get("threat_score", 0))
            linked_gaps = [top_gap]

        # Deduplicate
        seen = set()
        deduped_gaps = []
        for g in linked_gaps:
            cid = g.get("competitor_name", "")
            if cid not in seen:
                seen.add(cid)
                deduped_gaps.append(g)
        linked_gaps = deduped_gaps

        # If no direct links, still create an opportunity for high-confidence keywords
        if not linked_pains and keyword_conf < 0.5:
            continue

        # Pick the best-linked gap
        best_gap = linked_gaps[0] if linked_gaps else None

        pain_conf = best_pain.get("confidence", 0) if best_pain else 0
        pain_label = best_pain.get("label", "") if best_pain else ""
        pain_quote = (best_pain.get("example_quotes", [])[0] if best_pain and best_pain.get("example_quotes") else "")

        gap_conf = best_gap.get("confidence", 0) if best_gap else 0
        competitor_name = best_gap.get("competitor_name", "") if best_gap else ""
        missing_feature = best_gap.get("missing_features", [""])[0] if best_gap and best_gap.get("missing_features") else ""

        # Compute strength
        strength = (
            keyword_conf * 3.0
            + pain_conf * 2.5
            + gap_conf * 2.0
            + (1.0 if kw in rising_kw_set else 0.0)
        )
        strength = round(min(strength, 10.0), 2)

        # Build deterministic rationale
        parts = []
        if mention_count:
            parts.append(f"{mention_count} mention(s) across sources")
        if keyword_score:
            parts.append(f"SEO/trend score {keyword_score:.1f}")
        if pain_label:
            parts.append(f"linked to pain point '{pain_label}'")
        if competitor_name and missing_feature:
            parts.append(f"{competitor_name} lacks {missing_feature}")
        elif competitor_name:
            parts.append(f"{competitor_name} has identified gaps")

        rationale = "; ".join(parts) if parts else f"Keyword '{tk['keyword']}' shows activity"

        opp = {
            "type": "content_gap",
            "keyword": tk["keyword"],
            "keyword_confidence": keyword_conf,
            "pain_link": pain_label,
            "pain_confidence": pain_conf,
            "pain_example_quote": pain_quote,
            "competitor_link": competitor_name,
            "competitor_gap_confidence": gap_conf,
            "missing_feature": missing_feature,
            "strength": strength,
            "is_rising": kw in rising_kw_set,
            "velocity": rising_by_kw.get(kw, {}).get("velocity", 0) if kw in rising_by_kw else 0,
            "rationale": rationale,
        }
        opportunities.append(opp)

    # Sort by strength descending
    opportunities.sort(key=lambda x: x["strength"], reverse=True)
    return opportunities


# ── Main pipeline ─────────────────────────────────────────────

def merge_signals(agent_data: dict) -> dict:
    """
    Run the full merge pipeline.
    Returns the signal matrix dict.
    """
    behaviour  = agent_data.get("customer_behaviour", {})
    trends     = agent_data.get("trend_analyser", {})
    seo        = agent_data.get("seo_agent", {})
    competitor = agent_data.get("competitor_analysis", {})

    _log("Extracting trending keywords...")
    trending_keywords = extract_trending_keywords(trends, seo)
    _log(f"  → {len(trending_keywords)} trending keywords")

    _log("Extracting pain clusters...")
    pain_clusters = extract_pain_clusters(behaviour)
    _log(f"  → {len(pain_clusters)} pain clusters")

    _log("Extracting competitor gaps...")
    competitor_gaps = extract_competitor_gaps(competitor)
    _log(f"  → {len(competitor_gaps)} competitor gaps")

    _log("Generating opportunity signals...")
    rising_topics = trends.get("rising_topics", [])
    opportunity_signals = generate_opportunity_signals(
        trending_keywords, pain_clusters, competitor_gaps, rising_topics
    )
    _log(f"  → {len(opportunity_signals)} opportunity signals")

    matrix = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": list(AGENT_PATHS.keys()),
        "trending_keywords": trending_keywords,
        "pain_clusters": pain_clusters,
        "competitor_gaps": competitor_gaps,
        "opportunity_signals": opportunity_signals,
        "rising_topics": [
            {
                "keyword": r.get("keyword", ""),
                "velocity": r.get("velocity", 0),
                "confidence": r.get("confidence", 0),
            }
            for r in rising_topics[:10]
        ],
    }

    return matrix


def write_signal_matrix(matrix: dict, path: Path = OUTPUT_PATH):
    SHARED_DIR.mkdir(exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(matrix, f, ensure_ascii=False, indent=2)
    _log(f"[SAVED]   {path}")


def main():
    _log("=" * 55)
    _log("Signal Merger starting")
    _log("=" * 55)

    agent_data = {}
    for name, path in AGENT_PATHS.items():
        agent_data[name] = _load_json(path, name)

    missing = [name for name, data in agent_data.items() if not data]
    if missing:
        _log(f"[WARN] Missing data for: {', '.join(missing)}")
    if len(missing) == len(agent_data):
        _log("[ABORT] No agent data available.")
        sys.exit(1)

    matrix = merge_signals(agent_data)
    write_signal_matrix(matrix)

    _log("=" * 55)
    _log("Signal Merger complete")


if __name__ == "__main__":
    main()
