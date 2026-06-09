"""
main.py — Competitor Intelligence Agent

Full pipeline:
  Step 0: Load YAML config
  Step 1: Query Vector DB per competitor
  Step 2: Extract structured product info
  Step 3: Integrate RSS feed updates
  Step 4: Build feature comparison matrix
  Step 5: Detect strengths and weaknesses
  Step 6: Analyse pricing positioning
  Step 7: AI strategic analysis (Groq)
  Step 8: Store timestamped output

Usage:
    python main.py                      # full run with AI
    python main.py --no-ai              # skip Groq, faster
    python main.py --no-vector          # skip vector DB lookup
    python main.py --competitor "Raspberry Pi 5"  # single competitor
    python main.py --output json        # output format: json | both
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

from scripts.config_loader   import load_config
from scripts.vector_retriever import query_vector_db
from scripts.info_extractor  import extract_product_info
from scripts.rss_integrator  import fetch_competitor_rss
from scripts.feature_matrix  import build_feature_matrix
from scripts.strength_detector import detect_strengths_weaknesses
from scripts.pricing_analyzer import analyze_pricing
from scripts.ai_analyst      import run_ai_analysis
from scripts.store           import save_output

# competitor_analysis/ lives inside Marketing_agents/
# so __file__.parent       = Marketing_agents/competitor_analysis/
#    __file__.parent.parent = Marketing_agents/   ← the project root
PROJECT_ROOT = Path(__file__).parent.parent


def run(
    no_ai: bool = False,
    no_vector: bool = False,
    competitor_filter: str = None,
    output_format: str = "json",
):
    now = datetime.now()
    print(f"\n🕵️  Competitor Intelligence Agent — {now.strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # ── Step 0: Load config ───────────────────────────────────
    print("\n[Step 0] Loading configuration...")
    config = load_config(Path(__file__).parent / "config" / "competitors.yaml")

    my_products   = config["my_products"]
    competitors   = config["competitors"]
    settings      = config.get("settings", {})

    # Optional: filter to one competitor
    if competitor_filter:
        competitors = [c for c in competitors if competitor_filter.lower() in c["name"].lower()]
        if not competitors:
            print(f"  ⚠  No competitor matched '{competitor_filter}'")
            return
        print(f"  Filtered to: {[c['name'] for c in competitors]}")

    print(f"  My products  : {len(my_products)}")
    print(f"  Competitors  : {len(competitors)}")

    # ── Step 1 & 2: Vector DB query + info extraction ─────────
    competitor_profiles = {}

    for comp in competitors:
        name = comp["name"]
        print(f"\n[Step 1-2] Processing: {name}")

        profile = {
            "name":           name,
            "category":       comp.get("category", "sbc"),
            "known_price_usd": comp.get("known_price_usd"),
            "known_features": comp.get("known_features", []),
            "vector_docs":    [],
            "extracted_info": {},
        }

        if not no_vector:
            query = comp.get("vector_query", f"{name} specifications")
            top_k = settings.get("vector_top_k", 5)
            min_score = settings.get("vector_min_score", 0.3)
            docs = query_vector_db(PROJECT_ROOT, query, top_k=top_k, min_score=min_score)
            profile["vector_docs"] = docs
            print(f"  Vector results: {len(docs)}")
        else:
            print(f"  Vector DB skipped (--no-vector)")

        extracted = extract_product_info(
            competitor_name=name,
            known_features=comp.get("known_features", []),
            vector_docs=profile["vector_docs"],
            known_price=comp.get("known_price_usd"),
        )
        profile["extracted_info"] = extracted
        competitor_profiles[name] = profile

    # ── Step 3: RSS integration ───────────────────────────────
    print(f"\n[Step 3] Reading articles from RSS Feeder DB...")
    rss_data = fetch_competitor_rss(
        project_root=PROJECT_ROOT,
        config=config,
        competitor_profiles=competitor_profiles,
        lookback_days=settings.get("rss_lookback_days", 30),
        max_articles=settings.get("rss_max_articles", 200),
    )
    print(f"  Articles fetched : {rss_data['total_articles']}")
    print(f"  Relevant matches : {rss_data['total_matches']}")

    # Inject RSS updates into profiles
    for name, articles in rss_data["by_competitor"].items():
        if name in competitor_profiles and articles:
            competitor_profiles[name]["rss_updates"] = articles
            print(f"  {name}: {len(articles)} RSS articles")

    # ── Step 4: Feature comparison matrix ────────────────────
    print(f"\n[Step 4] Building feature comparison matrix...")
    feature_matrix = build_feature_matrix(
        my_products=my_products,
        competitor_profiles=competitor_profiles,
        features_to_compare=config.get("comparison_features", []),
    )
    print(f"  Features compared: {len(feature_matrix['features'])}")
    print(f"  Products in matrix: {len(feature_matrix['products'])}")

    # ── Step 5: Strength / weakness detection ─────────────────
    print(f"\n[Step 5] Detecting strengths and weaknesses...")
    sw_analysis = detect_strengths_weaknesses(
        my_products=my_products,
        competitor_profiles=competitor_profiles,
        feature_matrix=feature_matrix,
        strength_signals=config.get("strength_signals", []),
        weakness_signals=config.get("weakness_signals", []),
    )
    for name, sw in sw_analysis.items():
        s = len(sw.get("strengths", []))
        w = len(sw.get("weaknesses", []))
        print(f"  {name:<30} strengths={s}  weaknesses={w}")

    # ── Step 6: Pricing analysis ──────────────────────────────
    print(f"\n[Step 6] Analysing pricing positioning...")
    pricing_analysis = analyze_pricing(
        my_products=my_products,
        competitor_profiles=competitor_profiles,
        pricing_config=config.get("pricing", {}),
    )
    for name, pa in pricing_analysis.items():
        tier = pa.get("tier", "?")
        price = pa.get("price_usd")
        price_display = f"${price:>4}" if isinstance(price, (int, float)) else "  $ ?"
        print(f"  {name:<30} {price_display}  [{tier}]")

    # ── Step 7: AI strategic analysis ────────────────────────
    insights = []
    if not no_ai and not settings.get("skip_ai", False):
        print(f"\n[Step 7] Running AI strategic analysis (Groq)...")
        insights = run_ai_analysis(
            my_products=my_products,
            competitor_profiles=competitor_profiles,
            sw_analysis=sw_analysis,
            pricing_analysis=pricing_analysis,
            feature_matrix=feature_matrix,
            rss_data=rss_data,
        )
        print(f"  Insights generated: {len(insights)}")
    else:
        print(f"\n[Step 7] Skipping AI analysis")

    # ── Step 8: Save output ───────────────────────────────────
    print(f"\n[Step 8] Saving output...")
    output = {
        "run_date":         now.isoformat(),
        "run_date_display": now.strftime("%Y-%m-%d %H:%M"),
        "my_products":      my_products,
        "competitors":      [
            {
                "name":         name,
                "category":     p["category"],
                "price_usd":    p.get("known_price_usd"),
                "features":     p["extracted_info"].get("features", []),
                "limitations":  p["extracted_info"].get("limitations", []),
                "rss_updates":  p.get("rss_updates", []),
            }
            for name, p in competitor_profiles.items()
        ],
        "feature_matrix":   feature_matrix,
        "sw_analysis":      sw_analysis,
        "pricing_analysis": pricing_analysis,
        "rss_summary":      rss_data,
        "insights":         insights,
    }

    out_path = save_output(
        output=output,
        output_dir=Path(__file__).parent / settings.get("output_dir", "output"),
    )
    print(f"\n✅ Done → {out_path}")

    # ── Print summary ─────────────────────────────────────────
    _print_summary(output)

    return output


def _print_summary(output: dict):
    print("\n" + "=" * 60)
    print("📊 INTELLIGENCE SUMMARY")
    print("=" * 60)

    pricing = output.get("pricing_analysis", {})
    sw = output.get("sw_analysis", {})

    print("\n[Pricing Landscape]")
    for name, pa in pricing.items():
        tier = pa.get("tier", "?")
        price = pa.get("price_usd")
        vs = pa.get("vs_my_products", "")
        bar = {"low": "[low]", "mid": "[mid]", "high": "[high]"}.get(tier, "[?]")
        price_display = f"${price:>4}" if isinstance(price, (int, float)) else "$   ?"
        print(f"  {bar} {name:<28} {price_display}  [{tier}]  {vs}")

    print("\n[Competitive Positioning] Top Threats:")
    threats = sorted(
        [(n, sw.get(n, {}).get("threat_score", 0), sw.get(n, {}).get("threat_confidence", 0)) for n in sw],
        key=lambda x: x[1], reverse=True
    )[:3]
    for name, score, conf in threats:
        print(f"  [!] {name:<30} threat score: {score:.1f}  conf: {conf:.2f}")

    insights = output.get("insights", [])
    if insights:
        for ins in insights:
            if ins.get("type") == "strategic_summary":
                print(f"\n💡 AI Summary:")
                print(f"  {ins.get('summary', '')[:300]}")
                break


def main():
    parser = argparse.ArgumentParser(description="Competitor Intelligence Agent")
    parser.add_argument("--no-ai",       action="store_true", help="Skip Groq AI step")
    parser.add_argument("--no-vector",   action="store_true", help="Skip Vector DB queries")
    parser.add_argument("--competitor",  type=str,  default=None, help="Filter to one competitor name")
    parser.add_argument("--output",      type=str,  default="json",
                        choices=["json", "both"], help="Output format")
    args = parser.parse_args()

    run(
        no_ai=args.no_ai,
        no_vector=args.no_vector,
        competitor_filter=args.competitor,
        output_format=args.output,
    )


if __name__ == "__main__":
    main()