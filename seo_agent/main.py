"""
main.py — SEO Keyword Agent

Usage:
    python main.py              # full run with AI
    python main.py --no-ai      # skip Groq, fast
    python main.py --days 14    # look back 14 days of data
"""
import argparse
from datetime import datetime
from pathlib import Path

from scripts.loaders           import load_all
from scripts.preprocessor      import preprocess
from scripts.intent_classifier import classify_all
from scripts.expander          import expand_all
from scripts.scorer            import score
from scripts.clusterer         import cluster_keywords, build_cluster_summary
from scripts.ai_enhancer       import enhance
from scripts.store             import save

PROJECT_ROOT = Path(__file__).parent.parent


def run(no_ai: bool = False, days: int = 7):
    now = datetime.now()
    print(f"\n🔍 SEO Agent — {now.strftime('%Y-%m-%d %H:%M')}")
    print("=" * 55)

    print("\n[1/7] Loading data from all sources...")
    raw = load_all(PROJECT_ROOT, since_days=days)
    print(f"   Trends batches : {len(raw['trends'])}")
    print(f"   Reddit posts   : {len(raw['reddit'])}")
    print(f"   RSS articles   : {len(raw['rss'])}")
    print(f"   Tavily results : {len(raw['tavily'])}")

    print("\n[2/7] Preprocessing...")
    items = preprocess(raw)
    print(f"   Items with keyword hits: {len(items)}")

    print("\n[3/7] Collecting unique keywords...")
    all_kws = list(set(kw for item in items for kw in item["keywords"]))
    # Also add all trend keywords
    for t in raw["trends"]:
        kw = t.get("keyword", "").lower()
        if kw and kw not in all_kws:
            all_kws.append(kw)
    print(f"   Unique keywords: {len(all_kws)}")

    print("\n[4/7] Classifying intent...")
    classified = classify_all(all_kws)

    print("\n[5/7] Expanding to long-tail...")
    expanded = expand_all(classified)

    print("\n[6/7] Scoring...")
    scored = score(expanded, items, raw["trends"])

    print("\n[6b/7] Clustering...")
    scored = cluster_keywords(scored)
    clusters = build_cluster_summary(scored)

    print("\n[7/7] AI enhancement...")
    insights = [] if no_ai else enhance(scored, clusters)

    # Build output
    output = {
        "run_date":    now.isoformat(),
        "since_days":  days,
        "total_keywords": len(scored),
        "top_keywords": scored[:30],
        "clusters":    {k: v[:5] for k, v in clusters.items()},
        "insights":    insights,
    }

    out_path = save(output, Path(__file__).parent / "output")
    print(f"\n✅ Done → {out_path}")

    print("\n🔥 Top 10 SEO keywords:")
    for kw in scored[:10]:
        lt = kw["long_tail"][0] if kw.get("long_tail") else ""
        print(f"   [{kw['intent']:<10}] {kw['keyword']:<35} "
              f"score={kw['score']:.1f}  conf={kw.get('confidence', 0):.2f}  → \"{lt}\"")

    print("\n📦 Keyword clusters:")
    for cluster, kws in list(clusters.items())[:5]:
        top = ", ".join(k["keyword"] for k in kws[:3])
        print(f"   {cluster:<14} {top}")

    return output


def main():
    p = argparse.ArgumentParser(description="SEO Keyword Agent")
    p.add_argument("--no-ai", action="store_true", help="Skip Groq step")
    p.add_argument("--days",  type=int, default=7,  help="Lookback window in days")
    args = p.parse_args()
    run(no_ai=args.no_ai, days=args.days)


if __name__ == "__main__":
    main()