"""
scripts/store.py — Save final customer behaviour results.

Saves:
  output/YYYY-MM-DD_HH-MM.json  — timestamped run
  output/latest.json            — always the latest run (for dashboard)
"""

import json
from datetime import datetime
from pathlib import Path


def save_results(output: dict, output_dir: Path) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)

    run_label = datetime.now().strftime("%Y-%m-%d_%H-%M")
    path   = output_dir / f"customer_behaviour_{run_label}.json"
    latest = output_dir / "latest.json"

    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    with open(latest, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"  ✅ JSON  → {path}")
    print(f"  ✅ Latest → {latest}")
    return str(path)


def load_latest(output_dir: Path) -> dict:
    """Load most recent run."""
    p = output_dir / "latest.json"
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)