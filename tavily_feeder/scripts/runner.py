"""
runner.py — Orchestrates all Tavily searches and saves results.
"""

import os
import json
import yaml
from datetime import datetime
from scripts.query_builder import build_queries
from scripts import tavily_client as tc

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "../config/research.yml")

def load_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)

def run():
    config = load_config()
    settings = config.get("settings", {})
    max_results = settings.get("max_results", 5)
    use_research = settings.get("use_research_api", False)
    extract_sites = settings.get("extract_spy_sites", True)
    output_dir = settings.get("output_dir", "results")

    now = datetime.now()
    run_label = now.strftime("%Y-%m-%d_%H-%M")

    print(f"\n🔍 Tavily Research Runner — {now.strftime('%Y-%m-%d %H:%M')}")
    print("=" * 55)

    all_results = []

    # ── 1. Search queries (products + competitors) ──────────
    queries = build_queries(config)
    print(f"\n[1/3] Running {len(queries)} search queries...")

    for item in queries:
        q = item["query"]
        tag = f"[{item['category']}] {item['subject']}"
        print(f"  🔎 {tag}: {q[:60]}...")

        results = tc.search(q, max_results=max_results)

        entry = {
            "query": q,
            "category": item["category"],
            "subject": item["subject"],
            "results": results
        }

        if use_research:
            print(f"     🧠 Running deep research...")
            entry["research_report"] = tc.research(q)

        all_results.append(entry)

    # ── 2. Extract spy sites ─────────────────────────────────
    spy_sites = config.get("spy_sites", [])
    spy_extracts = []

    if extract_sites and spy_sites:
        print(f"\n[2/3] Extracting {len(spy_sites)} spy sites...")
        extracted = tc.extract(spy_sites)
        for item in extracted:
            spy_extracts.append({
                "url": item.get("url", ""),
                "content": item.get("raw_content", "")[:3000]  # trim for storage
            })
            print(f"  ✓ {item.get('url', '')}")
    else:
        print(f"\n[2/3] Skipping spy site extraction (disabled in config)")

    # ── 3. Save results ──────────────────────────────────────
    print(f"\n[3/3] Saving results...")

    os.makedirs(output_dir, exist_ok=True)
    output = {
        "run_date": now.isoformat(),
        "config_summary": {
            "my_products": config.get("my_products", []),
            "competitors": config.get("competitors", []),
            "spy_sites": spy_sites,
            "total_queries": len(queries)
        },
        "search_results": all_results,
        "spy_site_extracts": spy_extracts
    }

    path = os.path.join(output_dir, f"{run_label}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Done! Results saved → {path}")
    print(f"   Queries run:   {len(queries)}")
    print(f"   Sites scraped: {len(spy_extracts)}")

    # Quick summary preview
    print("\n📋 Top results preview:")
    for entry in all_results[:3]:
        print(f"\n  [{entry['category']}] {entry['subject']}")
        print(f"  Query: {entry['query']}")
        for r in entry["results"][:2]:
            print(f"    • {r.get('title', '')[:70]}")
            print(f"      {r.get('url', '')}")

    return path, output