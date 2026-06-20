"""
main.py — Content Writer Agent

Reads intelligence from existing agents, then calls Groq to write
SEO-targeted blog article drafts with [PLACEHOLDER] tokens.

Pipeline:
  0. Read performance tracker → compute platform/format bias
  1. Load SEO keywords, pain points, use cases, product capabilities
  2. Build article contexts (one per keyword)
  3. Inject performance bias into each context
  4. Filter out recently-written topics (deduplication)
  5. For each context: build prompt -> call Groq -> quality check
  6. Save drafts as .md files + batch metadata JSON
  7. Record topics in history to avoid duplicates next run

Usage:
    python main.py                      # write 3 articles, performance-biased
    python main.py --count 5            # write 5 articles
    python main.py --keyword "zigbee"   # write one article for a specific keyword
    python main.py --dry-run            # show what would be written, no API calls
    python main.py --list-keywords      # show available keywords from SEO agent
    python main.py --force              # bypass topic deduplication
    python main.py --no-bias            # skip performance feedback, balanced defaults
"""

import argparse
import sys
import yaml
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.loader         import load_all, build_article_context
from scripts.prompt_builder import build_prompt
from scripts.writer         import generate_article, clean_content
from scripts.store          import save_draft, save_batch, print_draft_preview
from scripts.tracker        import (
    load_history,
    filter_contexts,
    record_topic,
    get_recent_topics,
)
from scripts.performance_reader import read_performance
from scripts.bias_engine        import compute_directives, inject_bias_into_contexts, format_bias_report

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_PATH  = Path(__file__).parent / "config" / "content.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def run(
    count: int = None,
    keyword_filter: str = None,
    dry_run: bool = False,
    force: bool = False,
    no_bias: bool = False,
):
    now = datetime.now()
    print(f"\n[Content Writer Agent] {now.strftime('%Y-%m-%d %H:%M')}")
    print("=" * 58)

    config = load_config()

    if count:
        config["generation"]["articles_per_run"] = count

    n_articles = config["generation"].get("articles_per_run", 3)

    # ── Step 0: Performance feedback loop ─────────────────────
    print("\n[0/5] Reading performance tracker data...")

    if no_bias:
        print("   Skipping performance bias (--no-bias flag set)")
        from scripts.performance_reader import PerformanceSignals
        signals = PerformanceSignals()
        from scripts.bias_engine import GenerationDirectives
        directives = GenerationDirectives()
        directives.primary_platforms    = ["blog", "linkedin", "youtube", "x", "facebook"]
        directives.platform_bias        = {p: 1.0 for p in directives.primary_platforms}
        directives.preferred_formats    = ["tutorial", "comparison", "tip"]
        directives.recommended_framing  = ""
        directives.recommended_intent   = "info"
        directives.summary              = "No bias applied (--no-bias)."
    else:
        signals    = read_performance(PROJECT_ROOT, lookback_days=90, min_posts=1)
        directives = compute_directives(signals, requested_article_count=n_articles)

    print(format_bias_report(signals, directives))

    # ── Step 1: Load all intelligence data ─────────────────────
    print("\n[1/5] Loading intelligence data...")
    data = load_all(PROJECT_ROOT)

    seo_count  = len(data.get("seo", {}).get("top_keywords", []))
    pain_count = len(data.get("behaviour", {}).get("pain_points", []))
    prod_count = len(data.get("products", []))

    if seo_count == 0:
        print("\n[!] No SEO data found. Run seo_agent/main.py first.")
        return

    print(f"\n   SEO keywords    : {seo_count}")
    print(f"   Pain clusters   : {pain_count}")
    print(f"   Products loaded : {prod_count}")

    # ── Step 2: Build article contexts ──────────────────────────
    print("\n[2/5] Building article contexts...")
    contexts = build_article_context(data, config)

    # Optional: filter to specific keyword
    if keyword_filter:
        kf_lower = keyword_filter.lower()
        contexts = [c for c in contexts if kf_lower in c.get("keyword", "").lower()]
        if not contexts:
            print(f"\n[!] No context matched keyword filter '{keyword_filter}'")
            print("   Run with --list-keywords to see available options.")
            return
        print(f"   Filtered to keyword: '{keyword_filter}'")

    print(f"   Articles to write: {len(contexts)}")

    # ── Step 3: Inject performance bias into contexts ──────────
    if directives.data_driven:
        print(f"\n[3/5] Injecting performance bias into article contexts...")
        contexts = inject_bias_into_contexts(contexts, directives)
        print(f"   Primary platform  : {directives.primary_platforms[0].upper() if directives.primary_platforms else '-'}")
        print(f"   Preferred format  : {directives.preferred_formats[0] if directives.preferred_formats else '-'}")
        print(f"   Intent            : {directives.recommended_intent}")
    else:
        print(f"\n[3/5] No performance data - using balanced defaults")
        contexts = inject_bias_into_contexts(contexts, directives)

    for ctx in contexts:
        bias_marker = "[biased]" if ctx.get("is_performance_biased") else "[default]"
        print(f"     [{ctx['index']}] [{bias_marker}] {ctx['keyword']} ({ctx['intent']}) -> {ctx['title'][:50]}...")

    # ── Step 4: Topic deduplication ─────────────────────────────
    output_dir = Path(__file__).parent / config["output"]["output_dir"]
    drafts_dir = Path(__file__).parent / config["output"]["drafts_dir"]
    date_str   = now.strftime("%Y-%m-%d")

    topics_cfg = config.get("topics", {})
    min_days   = topics_cfg.get("min_days_between_topics", 14)

    if not force and not keyword_filter:
        print(f"\n[4/5] Checking topic history (min {min_days} days between repeats)...")
        history = load_history(output_dir)
        recent  = get_recent_topics(output_dir, days=min_days)
        print(f"   Recent topics on record: {len(recent)}")

        contexts = filter_contexts(contexts, history, min_days)
        if not contexts:
            print("\n[!] All candidate topics were recently written.")
            print(f"   Run with --force to override, or wait {min_days} days.")
            return
        print(f"   Fresh topics to write: {len(contexts)}")
    else:
        print("\n[4/5] Skipping deduplication (force mode or keyword filter)")

    if dry_run:
        print("\n[DRY RUN] Prompts shown - no API calls made\n")
        for ctx in contexts:
            system, user = build_prompt(ctx, config)
            print(f"\n{'='*58}")
            print(f"ARTICLE {ctx['index']}: {ctx['keyword']}")
            print(f"  Bias: platform={ctx.get('preferred_platform','-')} | "
                  f"format={ctx.get('preferred_format','-')} | "
                  f"data-driven={ctx.get('is_performance_biased', False)}")
            print(f"  Title: {ctx['title']}")
            print(f"  Pain:  {ctx.get('pain_point', {}).get('label', '')}")
            print(f"\n--- PROMPT PREVIEW (first 800 chars) ---")
            print(user[:800])
            print("...")
        return

    # ── Step 5: Generate articles ──────────────────────────────
    print("\n[5/5] Generating articles with Groq...")

    all_metadata = []
    total_tokens = 0

    for ctx in contexts:
        bias_label = f"[{ctx.get('preferred_platform','?').upper()}+{ctx.get('preferred_format','?')}]"
        print(f"\n  [WRITE] Article {ctx['index']}/{len(contexts)}: {ctx['keyword']} {bias_label}")

        try:
            system, user = build_prompt(ctx, config)
            result = generate_article(system, user, config)

            content = clean_content(result["content"])
            total_tokens += result.get("tokens_used", 0)

            metadata = save_draft(
                content    = content,
                context    = ctx,
                result     = result,
                output_dir = output_dir,
                drafts_dir = drafts_dir,
                date_str   = date_str,
            )
            # Store performance bias metadata
            metadata["preferred_platform"]    = ctx.get("preferred_platform", "blog")
            metadata["preferred_format"]      = ctx.get("preferred_format", "tutorial")
            metadata["is_performance_biased"] = ctx.get("is_performance_biased", False)

            all_metadata.append(metadata)
            print_draft_preview(content, metadata)

            # Record topic in history
            record_topic(ctx, metadata, output_dir)

        except Exception as e:
            print(f"\n  [FAIL] Article {ctx['index']} failed: {e}")
            all_metadata.append({
                "keyword": ctx.get("keyword", ""),
                "status":  "failed",
                "error":   str(e),
            })

    # ── Save batch metadata ─────────────────────────────────────
    print(f"\n[Saving batch metadata...]")
    batch_path = save_batch(all_metadata, output_dir, now.isoformat())

    # Summary
    successful  = [a for a in all_metadata if a.get("status") != "failed"]
    total_words = sum(a.get("word_count", 0) for a in successful)

    biased_count   = sum(1 for a in successful if a.get("is_performance_biased"))
    unbiased_count = len(successful) - biased_count

    print(f"\n{'='*58}")
    print(f"[DONE] Content Writer complete")
    print(f"   Articles written   : {len(successful)} / {len(contexts)}")
    print(f"   Performance-biased : {biased_count}")
    print(f"   Default (no data)  : {unbiased_count}")
    print(f"   Total words        : {total_words}")
    print(f"   Total tokens       : {total_tokens}")
    print(f"   Drafts folder      : {drafts_dir}")
    print(f"   Batch metadata     : {batch_path}")

    if directives.data_driven:
        print(f"\n[Performance Loop] {directives.summary}")

    # Flag any quality issues
    flagged = [a for a in successful if a.get("quality_flags")]
    if flagged:
        print(f"\n[!] {len(flagged)} article(s) have quality flags - review before publishing:")
        for a in flagged:
            print(f"   - {a['filename']}")
            for flag in a["quality_flags"]:
                print(f"     - {flag}")

    recent_topics = get_recent_topics(output_dir, days=min_days)
    print(f"\n[TOPICS] Topics on record (last {min_days}d): {len(recent_topics)}")

    return all_metadata


def list_keywords():
    """Show available keywords from the SEO agent output."""
    import json
    path = PROJECT_ROOT / "seo_agent" / "output" / "latest.json"
    if not path.exists():
        print("[!] seo_agent/output/latest.json not found. Run seo_agent/main.py first.")
        return
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    kws = data.get("top_keywords", [])
    print(f"\n[SEO] Available SEO keywords ({len(kws)} total):")
    print(f"{'-'*58}")
    for i, kw in enumerate(kws[:20], 1):
        print(f"  {i:2}. [{kw.get('intent','?'):<10}] {kw['keyword']:<30} score={kw.get('score',0):.1f}")
    if len(kws) > 20:
        print(f"  ... and {len(kws)-20} more")


def main():
    parser = argparse.ArgumentParser(description="Content Writer Agent")
    parser.add_argument("--count",         type=int,  default=None,
                        help="Number of articles to write (overrides config)")
    parser.add_argument("--keyword",       type=str,  default=None,
                        help="Write article for a specific keyword (partial match)")
    parser.add_argument("--dry-run",       action="store_true",
                        help="Show prompts without calling Groq")
    parser.add_argument("--list-keywords", action="store_true",
                        help="Show available keywords from SEO agent and exit")
    parser.add_argument("--force",         action="store_true",
                        help="Bypass topic deduplication")
    parser.add_argument("--no-bias",       action="store_true",
                        help="Skip performance feedback loop, use balanced defaults")
    args = parser.parse_args()

    if args.list_keywords:
        list_keywords()
        return

    run(
        count          = args.count,
        keyword_filter = args.keyword,
        dry_run        = args.dry_run,
        force          = args.force,
        no_bias        = args.no_bias,
    )


if __name__ == "__main__":
    main()