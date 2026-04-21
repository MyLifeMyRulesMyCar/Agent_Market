"""
main.py — Trend Analyser Agent

Runs the full pipeline:
  1. Load data from all collector outputs
  2. Preprocess & clean
  3. Aggregate keywords across sources
  4. Detect trending keywords
  5. Detect rising topics (velocity)
  6. Detect seasonal patterns
  7. AI enhancement via Groq
  8. Store final output

Usage:
    python main.py                     # full run
    python main.py --no-ai             # skip Groq (fast, offline)
    python main.py --since 2026-04-01  # only load data from this date
    python main.py --output json       # output format: json | sqlite | both
"""

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

from scripts.loaders        import load_all_sources
from scripts.preprocessor   import preprocess
from scripts.aggregator     import aggregate_keywords
from scripts.trending       import detect_trending
from scripts.rising         import detect_rising
from scripts.seasonal       import detect_seasonal
from scripts.ai_enhancer    import enhance_with_ai
from scripts.store          import save_results
from scripts.link_collector import collect_top_links

PROJECT_ROOT = Path(__file__).parent.parent


def run(since: str = None, no_ai: bool = False, output_format: str = "both"):
    now = datetime.now()

    if since is None:
        since = (now - timedelta(days=7)).strftime("%Y-%m-%d")

    print(f"\n📊 Trend Analyser — {now.strftime('%Y-%m-%d %H:%M')}")
    print(f"   Analysing data since: {since}")
    print("=" * 55)

    # ── 1. Load ───────────────────────────────────────────────
    print("\n[1/7] Loading data from all sources...")
    raw_data = load_all_sources(PROJECT_ROOT, since_date=since)
    print(f"   RSS articles   : {len(raw_data['rss'])}")
    print(f"   Trends batches : {len(raw_data['trends'])}")
    print(f"   Tavily results : {len(raw_data['tavily'])}")
    print(f"   Reddit posts   : {len(raw_data['reddit'])}")

    # ── 2. Preprocess ─────────────────────────────────────────
    print("\n[2/7] Preprocessing...")
    processed = preprocess(raw_data)
    print(f"   Total items processed: {len(processed)}")

    # ── 3. Aggregate keywords ─────────────────────────────────
    print("\n[3/7] Aggregating keywords...")
    keyword_counts = aggregate_keywords(processed)
    print(f"   Unique keywords found: {len(keyword_counts)}")

    # ── 4. Trending keywords ──────────────────────────────────
    print("\n[4/7] Detecting trending keywords...")
    trending = detect_trending(keyword_counts, processed, top_n=20)
    print(f"   Top trending keywords: {len(trending)}")
    for kw in trending[:5]:
        print(f"     [{kw['score']:.1f}] {kw['keyword']}")

    # ── 5. Rising topics ──────────────────────────────────────
    print("\n[5/7] Detecting rising topics...")
    rising = detect_rising(processed, raw_data["trends"], window_days=7)
    print(f"   Rising topics found: {len(rising)}")
    for t in rising[:5]:
        print(f"     ↑{t['velocity']:+.0f}%  {t['keyword']}")

    # ── 6. Seasonal patterns ──────────────────────────────────
    print("\n[6/7] Analysing seasonal patterns...")
    seasonal = detect_seasonal(raw_data["trends"])
    print(f"   Seasonal signals: {len(seasonal)}")

    # ── 7. AI Enhancement ────────────────────────────────────
    insights = []
    if not no_ai:
        print("\n[7/7] Enhancing with AI (Groq)...")
        insights = enhance_with_ai(
            trending=trending,
            rising=rising,
            seasonal=seasonal,
        )
        print(f"   Insights generated: {len(insights)}")
    else:
        print("\n[7/7] Skipping AI enhancement (--no-ai)")

    # ── 8. Collect top links for dashboard ───────────────────
    print("\n[8/8] Collecting top links...")
    top_links = collect_top_links(PROJECT_ROOT, since_date=since, top_n=10)
    print(f"   RSS links    : {len(top_links.get('rss', []))}")
    print(f"   Reddit links : {len(top_links.get('reddit', []))}")
    print(f"   Tavily links : {len(top_links.get('tavily', []))}")

    # ── 9. Store ──────────────────────────────────────────────
    output = {
        "run_date":   now.isoformat(),
        "since_date": since,
        "trending_keywords": trending,
        "rising_topics":     rising,
        "seasonal_patterns": seasonal,
        "insights":          insights,
        "top_links":         top_links,
    }

    out_path = save_results(output, Path(__file__).parent / "output", output_format)
    print(f"\n✅ Done → {out_path}")

    # Quick preview
    print("\n🔥 Top 5 trending:")
    for kw in trending[:5]:
        print(f"   {kw['keyword']:<30} score={kw['score']:.1f}  sources={kw['source_count']}")

    if rising:
        print("\n📈 Top rising:")
        for t in rising[:3]:
            print(f"   {t['keyword']:<30} velocity={t['velocity']:+.0f}%")

    if insights:
        print(f"\n💡 AI summary preview:")
        print(f"   {insights[0].get('summary', '')[:200]}")

    return output


def main():
    parser = argparse.ArgumentParser(description="Trend Analyser Agent")
    parser.add_argument("--since",  type=str, default=None,
                        help="Only load data since this date (YYYY-MM-DD). Default: 7 days ago.")
    parser.add_argument("--no-ai",  action="store_true",
                        help="Skip Groq AI enhancement step")
    parser.add_argument("--output", type=str, default="both",
                        choices=["json", "sqlite", "both"],
                        help="Output format (default: both)")
    args = parser.parse_args()

    run(
        since=args.since,
        no_ai=args.no_ai,
        output_format=args.output,
    )


if __name__ == "__main__":
    main()