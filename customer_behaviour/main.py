"""
main.py — Customer Behaviour Agent

Converts Reddit noise → structured customer intelligence.

Pipeline:
  1. Load Reddit raw JSON (from reddit_watcher output)
  2. Flatten posts + comments
  3. Clean & preprocess text
  4. Extract keywords
  5. Detect pain points (rule-based)
  6. Cluster pain points into categories
  7. Detect use cases
  8. Analyse sentiment
  9. AI enhancement via Groq
  10. Save final JSON with timestamp

Usage:
    python main.py                          # use latest reddit_raw.json
    python main.py --input path/to/raw.json # specify custom input
    python main.py --no-ai                  # skip Groq step
    python main.py --subreddit OrangePI     # filter to one subreddit
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

from scripts.loader       import load_reddit_data
from scripts.flattener    import flatten_posts
from scripts.cleaner      import clean_items
from scripts.extractor    import extract_keywords
from scripts.pain_points  import detect_pain_points
from scripts.clusterer    import cluster_pain_points
from scripts.use_cases    import detect_use_cases
from scripts.sentiment    import analyse_sentiment
from scripts.ai_enhancer  import enhance_with_groq
from scripts.store        import save_results

PROJECT_ROOT = Path(__file__).parent.parent


def run(
    input_path: str = None,
    no_ai: bool = False,
    subreddit_filter: str = None,
):
    now = datetime.now()
    print(f"\n🧠 Customer Behaviour Agent — {now.strftime('%Y-%m-%d %H:%M')}")
    print("=" * 55)

    # ── 1. Load ───────────────────────────────────────────────
    print("\n[1/9] Loading Reddit data...")
    posts = load_reddit_data(PROJECT_ROOT, input_path, subreddit_filter)
    print(f"   Posts loaded: {len(posts)}")
    if not posts:
        print("   ⚠  No posts found. Check input path.")
        return

    # ── 2. Flatten ────────────────────────────────────────────
    print("\n[2/9] Flattening posts + comments...")
    flat_items = flatten_posts(posts)
    print(f"   Flat items (posts + comments): {len(flat_items)}")

    # ── 3. Clean ──────────────────────────────────────────────
    print("\n[3/9] Cleaning text...")
    cleaned = clean_items(flat_items)
    print(f"   Items after cleaning: {len(cleaned)}")

    # ── 4. Extract keywords ───────────────────────────────────
    print("\n[4/9] Extracting keywords...")
    with_keywords = extract_keywords(cleaned)
    kw_counts = {}
    for item in with_keywords:
        for kw in item.get("keywords", []):
            kw_counts[kw] = kw_counts.get(kw, 0) + 1
    print(f"   Unique keywords found: {len(kw_counts)}")
    top5 = sorted(kw_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    for kw, cnt in top5:
        print(f"     [{cnt}x] {kw}")

    # ── 5. Detect pain points ─────────────────────────────────
    print("\n[5/9] Detecting pain points...")
    detected_issues = detect_pain_points(with_keywords)
    print(f"   Raw issues detected: {len(detected_issues)}")

    # ── 6. Cluster pain points ────────────────────────────────
    print("\n[6/9] Clustering pain points...")
    pain_points = cluster_pain_points(detected_issues)
    print(f"   Pain point clusters: {len(pain_points)}")
    for pp in pain_points[:5]:
        print(f"     [{pp['mentions']}x] {pp['category']}")

    # ── 7. Detect use cases ───────────────────────────────────
    print("\n[7/9] Detecting use cases...")
    use_cases = detect_use_cases(with_keywords)
    print(f"   Use cases found: {len(use_cases)}")
    for uc in use_cases[:3]:
        print(f"     [{uc['mentions']}x] {uc['case']}")

    # ── 8. Sentiment ──────────────────────────────────────────
    print("\n[8/9] Analysing sentiment...")
    sentiment = analyse_sentiment(with_keywords)
    total = sum(sentiment.values())
    print(f"   Positive: {sentiment['positive']}  "
          f"Negative: {sentiment['negative']}  "
          f"Neutral: {sentiment['neutral']}  "
          f"(total: {total})")

    # ── 9. AI Enhancement ────────────────────────────────────
    insights = []
    if not no_ai:
        print("\n[9/9] Enhancing with Groq AI...")
        insights = enhance_with_groq(
            pain_points=pain_points,
            use_cases=use_cases,
            sentiment=sentiment,
            top_keywords=sorted(kw_counts.items(), key=lambda x: x[1], reverse=True)[:20],
        )
        print(f"   Insights generated: {len(insights)}")
    else:
        print("\n[9/9] Skipping Groq (--no-ai)")

    # ── 10. Save ──────────────────────────────────────────────
    output = {
        "timestamp":   now.strftime("%Y-%m-%d"),
        "run_at":      now.isoformat(),
        "source_posts": len(posts),
        "flat_items":  len(flat_items),
        "pain_points": pain_points,
        "use_cases":   use_cases,
        "sentiment":   sentiment,
        "top_keywords": [{"keyword": k, "count": v} for k, v in
                         sorted(kw_counts.items(), key=lambda x: x[1], reverse=True)[:30]],
        "insights":    insights,
    }

    out_path = save_results(output, Path(__file__).parent / "output")
    print(f"\n✅ Done → {out_path}")

    # Quick preview
    print("\n🔥 Top pain points:")
    for pp in pain_points[:5]:
        print(f"   [{pp['mentions']}x] {pp['category']}: {', '.join(pp['examples'][:2])}")

    if insights:
        for ins in insights[:3]:
            print(f"\n💡 {ins}")

    return output


def main():
    parser = argparse.ArgumentParser(description="Customer Behaviour Agent — Reddit → Intelligence")
    parser.add_argument("--input",      type=str, default=None,
                        help="Path to reddit_raw.json (default: auto-detect)")
    parser.add_argument("--no-ai",      action="store_true",
                        help="Skip Groq AI enhancement")
    parser.add_argument("--subreddit",  type=str, default=None,
                        help="Filter to a specific subreddit")
    args = parser.parse_args()

    run(
        input_path=args.input,
        no_ai=args.no_ai,
        subreddit_filter=args.subreddit,
    )


if __name__ == "__main__":
    main()