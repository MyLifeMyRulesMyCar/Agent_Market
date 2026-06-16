"""
orchestrator.py — Marketing Intelligence Orchestrator (v2)

Six-step reasoning chain:
  1. Signal Merger      → shared/signal_matrix.json
  2. Opportunity Scorer → shared/opportunity_ranking.json
  3. Brief Generator    → shared/content_brief_latest.json
  4. Competitor Context → shared/enriched_brief_latest.json
  5. Platform Writer    → content outputs (optional, can be skipped via --no-content)
  6. Quality Gate       → flag review (optional, can be skipped via --no-quality-gate)

Also generates backward-compatible intelligence_snapshot.json
so index.html and weekly_brief.html keep working.

Usage:
    python orchestrator.py              # full chain
    python orchestrator.py --no-content # steps 1-4 only
"""

from __future__ import annotations

import json
import os
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

# Ensure shared modules are importable
PROJECT_ROOT = Path(__file__).parent
SHARED_DIR = PROJECT_ROOT / "shared"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SHARED_DIR))

OUTPUT_FILE = SHARED_DIR / "intelligence_snapshot.json"
LOG_FILE = SHARED_DIR / "orchestrator_log.txt"


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    safe = line.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
           sys.stdout.encoding or "utf-8", errors="replace")
    print(safe)
    SHARED_DIR.mkdir(exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ── Step runners ──────────────────────────────────────────────

def run_step(name: str, module_name: str, func_name: str = "main") -> bool:
    """Import a shared module and run its main() function."""
    log(f"[STEP] {name}")
    try:
        module = __import__(module_name)
        getattr(module, func_name)()
        log(f"[OK]   {name}")
        return True
    except Exception as e:
        log(f"[FAIL] {name}: {e}")
        return False


def run_signal_merger() -> bool:
    return run_step("Signal Merger", "signal_merger")


def run_opportunity_scorer() -> bool:
    return run_step("Opportunity Scorer", "opportunity_scorer")


def run_brief_generator() -> bool:
    return run_step("Brief Generator", "brief_generator")


def run_competitor_context_injector() -> bool:
    return run_step("Competitor Context Injector", "competitor_context_injector")


def run_platform_writer() -> bool:
    return run_step("Platform Writer", "platform_writer")


def run_quality_gate() -> bool:
    return run_step("Quality Gate", "quality_gate")


# ── Backward-compatible snapshot builder ──────────────────────

def build_snapshot(signal_matrix: dict, ranking: dict, enriched_brief: dict) -> dict:
    """
    Map the new chain outputs into the old intelligence_snapshot.json schema
    so dashboards don't break.
    """
    top_3_keywords = signal_matrix.get("trending_keywords", [])[:3]
    top_3_pains = signal_matrix.get("pain_clusters", [])[:3]
    top_3_opps = ranking.get("ranking", [])[:3]

    brief = enriched_brief.get("brief", {})
    comp_ctx = enriched_brief.get("competitor_context", {})

    # Build executive summary from brief
    exec_summary_parts = []
    if brief.get("angle"):
        exec_summary_parts.append(brief["angle"])
    if brief.get("key_claim"):
        exec_summary_parts.append(brief["key_claim"])
    executive_summary = " ".join(exec_summary_parts) if exec_summary_parts else "No brief generated."

    # Competitor moves from enriched brief
    competitor_moves = []
    if comp_ctx.get("competitor_name"):
        move = {
            "competitor": comp_ctx["competitor_name"],
            "move": f"Lacks {comp_ctx.get('feature_gap', 'key capability')}",
            "impact": "high" if (comp_ctx.get("threat_score", 0) > 7) else "medium",
        }
        competitor_moves.append(move)

    # Pricing signals
    pricing_signals = []
    if comp_ctx.get("their_price"):
        pricing_signals.append(
            f"{comp_ctx['competitor_name']} priced at ${comp_ctx['their_price']} ({comp_ctx.get('their_tier', 'unknown')} tier)"
        )

    snapshot = {
        "snapshot_date": datetime.now(timezone.utc).isoformat(),
        "sources": ["customer_behaviour", "trend_analyser", "seo_agent", "competitor_analysis"],
        "executive_summary": executive_summary,
        "market_intelligence": {
            "top_trends": [
                {
                    "trend": kw.get("keyword", ""),
                    "momentum": "high" if kw.get("score", 0) > 500 else "medium" if kw.get("score", 0) > 200 else "low",
                    "confidence": kw.get("confidence", 0),
                    "insight": f"Mentioned {kw.get('mention_count', 0)} times across sources",
                }
                for kw in top_3_keywords
            ],
            "emerging_opportunities": [
                f"{o.get('keyword', '')}: {o.get('rationale', '')}" for o in top_3_opps
            ],
            "threats": [
                f"{comp_ctx.get('competitor_name', 'Competitor')} gap: {comp_ctx.get('feature_gap', 'unknown')}"
            ] if comp_ctx.get("competitor_name") else [],
        },
        "customer_insights": {
            "top_pain_points": [
                {
                    "issue": p.get("label", ""),
                    "severity": "high" if p.get("mentions", 0) > 30 else "medium" if p.get("mentions", 0) > 10 else "low",
                    "confidence": p.get("confidence", 0),
                    "evidence": p.get("example_quotes", [""])[0] if p.get("example_quotes") else "",
                }
                for p in top_3_pains
            ],
            "sentiment_summary": "See customer_behaviour agent for full sentiment analysis.",
            "unmet_needs": [o.get("pain_link", "") for o in top_3_opps if o.get("pain_link")],
        },
        "competitive_landscape": {
            "competitor_moves": competitor_moves,
            "positioning_gaps": [comp_ctx.get("feature_gap", "")] if comp_ctx.get("feature_gap") else [],
            "pricing_signals": pricing_signals,
        },
        "seo_and_content_opportunities": {
            "high_value_keywords": [
                {
                    "keyword": o.get("keyword", ""),
                    "intent": "info",  # simplified
                    "priority": "high" if o.get("final_score", 0) > 5 else "medium",
                }
                for o in top_3_opps
            ],
            "content_gaps": [
                f"{o.get('keyword', '')} + {o.get('pain_link', '')}" for o in top_3_opps
            ],
            "recommended_actions": [
                f"Write: {brief.get('title', 'content piece')}",
                f"Angle: {brief.get('angle', '')}",
                f"CTA: {brief.get('cta', '')}",
            ] if brief.get("title") else [],
        },
        "strategic_recommendations": [
            {
                "action": f"Create content targeting '{o.get('keyword', '')}'",
                "rationale": o.get("rationale", ""),
                "priority": "high" if o.get("final_score", 0) > 5 else "medium",
            }
            for o in top_3_opps
        ],
        # New metadata for observability
        "_orchestration": {
            "version": "2.0",
            "chain_steps_run": [],
            "top_opportunity": top_3_opps[0].get("keyword", "") if top_3_opps else None,
            "brief_title": brief.get("title", ""),
            "competitor_context_injected": bool(comp_ctx),
        },
    }

    return snapshot


def write_snapshot(snapshot: dict):
    SHARED_DIR.mkdir(exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    log(f"[SAVED]   {OUTPUT_FILE}")


# ── Main orchestrator ─────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Marketing Intelligence Orchestrator v2")
    parser.add_argument("--no-content", action="store_true", help="Skip platform content generation")
    parser.add_argument("--no-quality-gate", action="store_true", help="Skip quality gate")
    parser.add_argument("--step", type=str, default=None,
                        choices=["merge", "score", "brief", "enrich", "write", "gate"],
                        help="Run a single step and exit")
    args = parser.parse_args()

    log("=" * 55)
    log("Orchestrator v2 starting")
    log("=" * 55)

    steps_run = []
    failed_steps = []

    # Step 1: Signal Merger
    if args.step is None or args.step == "merge":
        if run_signal_merger():
            steps_run.append("signal_merger")
        else:
            failed_steps.append("signal_merger")
        if args.step == "merge":
            log("Single step complete.")
            return

    # Step 2: Opportunity Scorer
    if args.step is None or args.step == "score":
        if run_opportunity_scorer():
            steps_run.append("opportunity_scorer")
        else:
            failed_steps.append("opportunity_scorer")
        if args.step == "score":
            log("Single step complete.")
            return

    # Step 3: Brief Generator
    if args.step is None or args.step == "brief":
        if run_brief_generator():
            steps_run.append("brief_generator")
        else:
            failed_steps.append("brief_generator")
        if args.step == "brief":
            log("Single step complete.")
            return

    # Step 4: Competitor Context Injector
    if args.step is None or args.step == "enrich":
        if run_competitor_context_injector():
            steps_run.append("competitor_context_injector")
        else:
            failed_steps.append("competitor_context_injector")
        if args.step == "enrich":
            log("Single step complete.")
            return

    # Step 5: Platform Writer (optional)
    if not args.no_content:
        if args.step is None or args.step == "write":
            if run_platform_writer():
                steps_run.append("platform_writer")
            else:
                failed_steps.append("platform_writer")
            if args.step == "write":
                log("Single step complete.")
                return

    # Step 6: Quality Gate (optional)
    if not args.no_quality_gate and not args.no_content:
        if args.step is None or args.step == "gate":
            if run_quality_gate():
                steps_run.append("quality_gate")
            else:
                failed_steps.append("quality_gate")
            if args.step == "gate":
                log("Single step complete.")
                return

    # ── Build backward-compatible snapshot ────────────────────
    log("Building backward-compatible intelligence_snapshot...")
    try:
        with open(SHARED_DIR / "signal_matrix.json", "r", encoding="utf-8") as f:
            signal_matrix = json.load(f)
    except Exception:
        signal_matrix = {}

    try:
        with open(SHARED_DIR / "opportunity_ranking.json", "r", encoding="utf-8") as f:
            ranking = json.load(f)
    except Exception:
        ranking = {}

    try:
        with open(SHARED_DIR / "enriched_brief_latest.json", "r", encoding="utf-8") as f:
            enriched_brief = json.load(f)
    except Exception:
        enriched_brief = {}

    snapshot = build_snapshot(signal_matrix, ranking, enriched_brief)
    snapshot["_orchestration"]["chain_steps_run"] = steps_run
    snapshot["_orchestration"]["failed_steps"] = failed_steps
    write_snapshot(snapshot)

    if failed_steps:
        log(f"[WARN] Failed steps: {', '.join(failed_steps)}")

    log("=" * 55)
    log("Orchestrator v2 complete")
    log(f"Steps run: {', '.join(steps_run)}")


if __name__ == "__main__":
    main()
