"""
main.py — Content Writer Agent

Reads intelligence from existing agents, then calls Groq to write
SEO-targeted blog article drafts with [PLACEHOLDER] tokens.

Pipeline:
  1. Load SEO keywords, pain points, use cases, product capabilities
  2. Build article contexts (one per keyword)
  3. Filter out recently-written topics (deduplication)
  4. For each context: build prompt -> call Groq -> quality check
  5. Save drafts as .md files + batch metadata JSON
  6. Record topics in history to avoid duplicates next run

Usage:
    python main.py                      # write 3 articles (config default)
    python main.py --count 5            # write 5 articles
    python main.py --keyword "zigbee"   # write one article for a specific keyword
    python main.py --dry-run            # show what would be written, no API calls
    python main.py --list-keywords      # show available keywords from SEO agent
    python main.py --force              # bypass topic deduplication
"""

import argparse
import yaml
from datetime import datetime
from pathlib import Path

from scripts.loader       import load_all, build_article_context
from scripts.prompt_builder import build_prompt
from scripts.writer       import generate_article, clean_content
from scripts.store        import save_draft, save_batch, print_draft_preview
from scripts.tracker      import (
    load_history,
    filter_contexts,
    record_topic,
    get_recent_topics,
)

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
):
    now = datetime.now()
    print(f"\n[Content Writer Agent] {now.strftime('%Y-%m-%d %H:%M')}")
    print("=" * 58)

    config = load_config()

    if count:
        config["generation"]["articles_per_run"] = count

    # ── 1. Load all intelligence data ─────────────────────────
    print("\n[1/5] Loading intelligence data...")
    data = load_all(PROJECT_ROOT)

    seo_count  = len(data.get("seo", {}).get("top_keywords", []))
    pain_count = len(data.get("behaviour", {}).get("pain_points", []))
    prod_count = len(data.get("products", []))

    if seo_count == 0:
        print("\n⚠  No SEO data found. Run seo_agent/main.py first.")
        return

    print(f"\n   SEO keywords    : {seo_count}")
    print(f"   Pain clusters   : {pain_count}")
    print(f"   Products loaded : {prod_count}")

    # ── 2. Build article contexts ──────────────────────────────
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
    for ctx in contexts:
        print(f"     [{ctx['index']}] {ctx['keyword']} ({ctx['intent']}) -> {ctx['title'][:55]}...")

    # ── 3. Topic deduplication ─────────────────────────────────
    output_dir = Path(__file__).parent / config["output"]["output_dir"]
    drafts_dir = Path(__file__).parent / config["output"]["drafts_dir"]
    date_str   = now.strftime("%Y-%m-%d")

    topics_cfg = config.get("topics", {})
    min_days   = topics_cfg.get("min_days_between_topics", 14)

    if not force and not keyword_filter:
        print(f"\n[3/5] Checking topic history (min {min_days} days between repeats)...")
        history = load_history(output_dir)
        recent = get_recent_topics(output_dir, days=min_days)
        print(f"   Recent topics on record: {len(recent)}")

        contexts = filter_contexts(contexts, history, min_days)
        if not contexts:
            print("\n[!] All candidate topics were recently written.")
            print(f"   Run with --force to override, or wait {min_days} days.")
            return
        print(f"   Fresh topics to write: {len(contexts)}")
    else:
        print("\n[3/5] Skipping deduplication (force mode or keyword filter)")

    if dry_run:
        print("\n[DRY RUN] prompts shown, no API calls made\n")
        for ctx in contexts:
            system, user = build_prompt(ctx, config)
            print(f"\n{'='*58}")
            print(f"ARTICLE {ctx['index']}: {ctx['keyword']}")
            print(f"{'='*58}")
            print(f"TITLE: {ctx['title']}")
            print(f"PAIN:  {ctx.get('pain_point', {}).get('label', '')}")
            print(f"\n--- PROMPT PREVIEW (first 800 chars) ---")
            print(user[:800])
            print("...")
        return

    # ── 4. Generate articles ───────────────────────────────────
    print("\n[4/5] Generating articles with Groq...")

    all_metadata = []
    total_tokens = 0

    for ctx in contexts:
        print(f"\n  [WRITE] Article {ctx['index']}/{len(contexts)}: {ctx['keyword']}")

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
            all_metadata.append(metadata)
            print_draft_preview(content, metadata)

            # Record topic in history
            record_topic(ctx, metadata, output_dir)

        except Exception as e:
            print(f"\n  [FAIL] Article {ctx['index']} failed: {e}")
            all_metadata.append({
                "keyword": ctx.get("keyword", ""),
                "status": "failed",
                "error": str(e),
            })

    # ── 5. Save batch metadata ─────────────────────────────────
    print(f"\n[5/5] Saving batch metadata...")
    batch_path = save_batch(all_metadata, output_dir, now.isoformat())

    # Summary
    successful = [a for a in all_metadata if a.get("status") != "failed"]
    total_words = sum(a.get("word_count", 0) for a in successful)

    print(f"\n{'='*58}")
    print(f"[DONE] Content Writer complete")
    print(f"   Articles written : {len(successful)} / {len(contexts)}")
    print(f"   Total words      : {total_words}")
    print(f"   Total tokens     : {total_tokens}")
    print(f"   Drafts folder    : {drafts_dir}")
    print(f"   Batch metadata   : {batch_path}")

    # Flag any quality issues
    flagged = [a for a in successful if a.get("quality_flags")]
    if flagged:
        print(f"\n[!] {len(flagged)} article(s) have quality flags -- review before publishing:")
        for a in flagged:
            print(f"   • {a['filename']}")
            for flag in a["quality_flags"]:
                print(f"     - {flag}")

    # Show recent topic count
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
    parser.add_argument("--count",    type=int,  default=None,
                        help="Number of articles to write (overrides config)")
    parser.add_argument("--keyword",  type=str,  default=None,
                        help="Write article for a specific keyword (partial match)")
    parser.add_argument("--dry-run",  action="store_true",
                        help="Show prompts without calling Groq")
    parser.add_argument("--list-keywords", action="store_true",
                        help="Show available keywords from SEO agent and exit")
    parser.add_argument("--force",    action="store_true",
                        help="Bypass topic deduplication and write even if recently done")
    args = parser.parse_args()

    if args.list_keywords:
        list_keywords()
        return

    run(
        count          = args.count,
        keyword_filter = args.keyword,
        dry_run        = args.dry_run,
        force          = args.force,
    )


if __name__ == "__main__":
    main()
