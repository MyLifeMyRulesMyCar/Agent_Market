"""
runner.py — Orchestrates all markets using TrendsFetcher.
"""

import os
import json
import yaml
from datetime import datetime
from pathlib import Path
from scripts.fetch_trends import TrendsFetcher
from scripts.parser import build_market_summary

CONFIG_PATH = os.path.join(os.getcwd(), "config", "config.yaml")


def load_config():
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(
            f"Config not found at: {CONFIG_PATH}\n"
            f"Run from the Serpi_feeder/ directory:\n"
            f"  cd Serpi_feeder && python main.py"
        )
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run(profile_name: str = "standard", time_range_override: str = None, force_refresh: bool = False):
    config = load_config()
    settings = config.get("settings", {})
    markets = config.get("markets", {})
    profiles = config.get("profiles", {})

    # Load profile
    profile = profiles.get(profile_name, profiles.get("standard", {}))
    layers_to_run = profile.get("layers_to_run", ["core"])
    fetch_related = profile.get("fetch_related_queries", False)

    geo = settings.get("geo", "LK")
    time_range = time_range_override or settings.get("time_range", "today 12-m")
    data_dir = Path(os.getcwd()) / settings.get("data_dir", "data")
    monthly_limit = settings.get("monthly_credit_limit", 250)
    rate_delay = settings.get("rate_limit_delay", 2.0)
    force = force_refresh or settings.get("force_refresh", False)

    api_key = os.getenv("SERPAPI_KEY", "")
    if not api_key:
        raise ValueError("SERPAPI_KEY not set in .env file")

    fetcher = TrendsFetcher(api_key, data_dir, monthly_limit, rate_delay)

    now = datetime.now()
    print(f"\n📈 Serpi Trends Runner — {now.strftime('%Y-%m-%d %H:%M')}")
    print(f"   Profile: {profile_name} | Layers: {layers_to_run} | Range: {time_range} | Geo: {geo}")

    # Estimate credits before starting
    est = fetcher.estimate_credits(markets, layers_to_run, fetch_related)
    print(f"   Estimated credits: ~{est} | Available: {fetcher.tracker.remaining()}")
    if est > fetcher.tracker.remaining():
        print(f"   ⚠️  Warning: may not have enough credits for full run!")
    print("=" * 55)

    all_summaries = {}

    for market_key, market_cfg in markets.items():
        label = market_cfg.get("label", market_key)
        market_geo = market_cfg.get("geo", geo)

        print(f"\n🏷️  Market: {label}")

        # Override geo per market
        market_cfg_with_geo = {**market_cfg, "geo": market_geo}

        layer_results = fetcher.fetch_market_layers(
            market_key=market_key,
            market_cfg=market_cfg_with_geo,
            layers_to_run=layers_to_run,
            date_param=time_range,
            fetch_related=fetch_related,
            force_refresh=force,
        )

        summary = build_market_summary(market_key, market_cfg, layer_results)
        all_summaries[market_key] = summary

        # Print ranking for this market
        print(f"\n  📊 {label} — Keyword Ranking:")
        arrows = {"rising": "↑", "falling": "↓", "flat": "→"}
        for r in summary.get("ranking", []):
            a = arrows.get(r.get("trend", ""), "?")
            print(f"    {a} {r['keyword']:<32} avg={r.get('avg','?'):>5}  "
                  f"latest={r.get('latest','?'):>3}  peak={r.get('peak_date','?')}")

    # Save consolidated output
    output_dir = Path(os.getcwd()) / "output"
    output_dir.mkdir(exist_ok=True)
    run_label = now.strftime("%Y-%m-%d_%H-%M")

    output = {
        "run_date": now.isoformat(),
        "profile": profile_name,
        "time_range": time_range,
        "geo": geo,
        "markets": all_summaries,
    }

    path = output_dir / f"trends_{run_label}.json"
    latest = output_dir / "latest.json"

    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    with open(latest, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Saved → {path}")
    print(f"   Also updated → {latest}")

    fetcher.tracker.status()
    return str(path), output