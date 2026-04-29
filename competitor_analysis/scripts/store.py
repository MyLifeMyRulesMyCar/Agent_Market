"""
scripts/store.py — Save competitor intelligence output with timestamps.

Saves:
  output/YYYY-MM-DD_HH-MM_competitor_intel.json  — timestamped run
  output/latest.json                              — always the latest run
"""

import json
from datetime import datetime
from pathlib import Path


def save_output(output: dict, output_dir: Path) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)

    run_label = datetime.now().strftime("%Y-%m-%d_%H-%M")
    timestamped = output_dir / f"{run_label}_competitor_intel.json"
    latest      = output_dir / "latest.json"

    _write_json(output, timestamped)
    _write_json(output, latest)

    print(f"  ✅ JSON  → {timestamped}")
    print(f"  ✅ Latest → {latest}")

    return str(timestamped)


def _write_json(data: dict, path: Path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_latest(output_dir: Path) -> dict:
    """Load the most recent run."""
    p = output_dir / "latest.json"
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)