"""
fetch_trends.py — Core engine (adapted from google_trends_fetcher.py)
Fetches Google Trends via SerpAPI with:
  - 5-keyword batch support for TIMESERIES
  - File caching (skip if already fetched today)
  - Monthly credit tracking with warnings
  - Structured file naming: data/{market}/{layer}/{slug}__{type}__{date}.json
"""

import os
import json
import time
import math
import requests
from datetime import datetime
from pathlib import Path
from typing import Optional

BASE_URL = "https://serpapi.com/search"

# SerpAPI batch limits per data_type
BATCH_LIMITS = {
    "TIMESERIES": 5,
    "GEO_MAP": 5,
    "RELATED_TOPICS": 1,
    "RELATED_QUERIES": 1,
}

# ── Credit Tracker ──────────────────────────────────────────

class CreditTracker:
    def __init__(self, data_dir: Path, monthly_limit: int = 250):
        self.log_path = data_dir / "credit_log.json"
        self.monthly_limit = monthly_limit
        self.log = self._load()

    def _load(self):
        if self.log_path.exists():
            with open(self.log_path) as f:
                return json.load(f)
        return {"monthly_usage": {}, "calls": []}

    def _save(self):
        with open(self.log_path, "w") as f:
            json.dump(self.log, f, indent=2)

    def _month_key(self):
        return datetime.now().strftime("%Y-%m")

    def used_this_month(self) -> int:
        return self.log["monthly_usage"].get(self._month_key(), 0)

    def remaining(self) -> int:
        return max(0, self.monthly_limit - self.used_this_month())

    def can_spend(self, n: int = 1) -> bool:
        return self.remaining() >= n

    def record(self, query: str, data_type: str, cost: int = 1):
        key = self._month_key()
        self.log["monthly_usage"][key] = self.log["monthly_usage"].get(key, 0) + cost
        self.log["calls"].append({
            "timestamp": datetime.now().isoformat(),
            "query": query,
            "data_type": data_type,
            "cost": cost,
        })
        self._save()

        used = self.used_this_month()
        remaining = self.remaining()
        pct = (used / self.monthly_limit) * 100
        warn = " ⚠️ OVER 80%!" if pct > 80 else ""
        print(f"    💳 Credits: {used}/{self.monthly_limit} used ({pct:.0f}%) | {remaining} remaining{warn}")

    def status(self):
        used = self.used_this_month()
        remaining = self.remaining()
        pct = (used / self.monthly_limit) * 100
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        print(f"\n{'='*50}")
        print(f" 📊 Credit Status — {datetime.now().strftime('%B %Y')}")
        print(f"{'='*50}")
        print(f"  [{bar}] {pct:.1f}%")
        print(f"  Used: {used} / {self.monthly_limit}  |  Remaining: {remaining}")
        print(f"{'='*50}\n")


# ── File Naming ─────────────────────────────────────────────

def make_filepath(data_dir: Path, market: str, layer: str, keywords: list, data_type: str, date_param: str) -> Path:
    slug = "_".join(k.replace(" ", "-") for k in keywords)[:60]
    date_slug = date_param.replace(" ", "_")
    filename = f"{slug}__{data_type}__{date_slug}.json"
    safe = "".join(c if c.isalnum() or c in "_-." else "_" for c in filename)
    folder = data_dir / market / layer
    folder.mkdir(parents=True, exist_ok=True)
    return folder / safe


# ── Core Fetcher ────────────────────────────────────────────

class TrendsFetcher:
    def __init__(self, api_key: str, data_dir: Path, monthly_limit: int = 250, rate_delay: float = 2.0):
        self.api_key = api_key
        self.data_dir = data_dir
        self.rate_delay = rate_delay
        self.tracker = CreditTracker(data_dir, monthly_limit)

    def fetch(
        self,
        keywords: list,
        market: str,
        layer: str,
        data_type: str = "TIMESERIES",
        date_param: str = "today 12-m",
        geo: str = "LK",
        force_refresh: bool = False,
    ) -> Optional[dict]:
        # Enforce batch limit
        max_kw = BATCH_LIMITS.get(data_type, 1)
        if len(keywords) > max_kw:
            print(f"    ⚠️  {data_type} max={max_kw} keywords. Trimming {len(keywords)} → {max_kw}.")
            keywords = keywords[:max_kw]

        # Cache check
        fpath = make_filepath(self.data_dir, market, layer, keywords, data_type, date_param)
        if fpath.exists() and not force_refresh:
            print(f"    📁 Cache → {fpath.name}")
            with open(fpath) as f:
                return json.load(f)

        # Credit check
        if not self.tracker.can_spend(1):
            print(f"    🚫 CREDIT LIMIT REACHED! Skipping: {keywords}")
            return None

        # API call
        query_str = ",".join(keywords)
        params = {
            "engine": "google_trends",
            "q": query_str,
            "geo": geo,
            "data_type": data_type,
            "date": date_param,
            "hl": "en",
            "api_key": self.api_key,
        }

        print(f"    🌐 API [{data_type}] {keywords}")
        try:
            resp = requests.get(BASE_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            if "error" in data:
                print(f"    ❌ API error: {data['error']}")
                return None

            # Attach metadata
            data["_meta"] = {
                "keywords": keywords,
                "market": market,
                "layer": layer,
                "data_type": data_type,
                "date_param": date_param,
                "geo": geo,
                "fetched_at": datetime.now().isoformat(),
            }

            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            self.tracker.record(query_str, data_type)
            time.sleep(self.rate_delay)
            return data

        except requests.exceptions.RequestException as e:
            print(f"    ❌ Request failed: {e}")
            return None

    def fetch_market_layers(
        self,
        market_key: str,
        market_cfg: dict,
        layers_to_run: list,
        date_param: str,
        data_type: str = "TIMESERIES",
        fetch_related: bool = False,
        force_refresh: bool = False,
    ) -> dict:
        """Run all specified layers for a market. Returns {layer: [results]}"""
        geo = market_cfg.get("geo", "LK")
        results = {}

        for layer_name in layers_to_run:
            keywords = market_cfg.get("layers", {}).get(layer_name, [])
            if not keywords:
                print(f"    ⚠️  Layer '{layer_name}' not found in market '{market_key}'")
                continue

            print(f"\n  📦 Layer: {layer_name} — {len(keywords)} keywords → {math.ceil(len(keywords)/5)} batch(es)")

            # Split into batches of 5
            batches = [keywords[i:i+5] for i in range(0, len(keywords), 5)]
            layer_results = []

            for batch in batches:
                if not self.tracker.can_spend(1):
                    print(f"\n  🛑 Monthly credit limit reached. Stopping.")
                    break

                result = self.fetch(
                    keywords=batch,
                    market=market_key,
                    layer=layer_name,
                    data_type=data_type,
                    date_param=date_param,
                    geo=geo,
                    force_refresh=force_refresh,
                )
                if result:
                    layer_results.append(result)

            # Related queries/topics (1 keyword at a time — costs more credits)
            if fetch_related:
                for kw in keywords[:3]:  # limit to first 3 to save credits
                    if not self.tracker.can_spend(2):
                        break
                    print(f"    🔗 Related queries: {kw}")
                    self.fetch(
                        keywords=[kw], market=market_key, layer=layer_name,
                        data_type="RELATED_QUERIES", date_param=date_param,
                        geo=geo, force_refresh=force_refresh,
                    )
                    self.fetch(
                        keywords=[kw], market=market_key, layer=layer_name,
                        data_type="RELATED_TOPICS", date_param=date_param,
                        geo=geo, force_refresh=force_refresh,
                    )

            results[layer_name] = layer_results

        return results

    def estimate_credits(self, markets: dict, layers_to_run: list, fetch_related: bool = False) -> int:
        total = 0
        for mk, mc in markets.items():
            for ln in layers_to_run:
                kws = mc.get("layers", {}).get(ln, [])
                total += math.ceil(len(kws) / 5)  # TIMESERIES batches
                if fetch_related:
                    total += min(len(kws), 3) * 2  # related queries + topics
        return total