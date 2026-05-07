"""store.py — Save output to timestamped JSON + latest.json."""
import json
from datetime import datetime
from pathlib import Path


def save(output: dict, output_dir: Path) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    label = datetime.now().strftime("%Y-%m-%d_%H-%M")
    path   = output_dir / f"seo_{label}.json"
    latest = output_dir / "latest.json"
    for p in (path, latest):
        p.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  ✅ JSON  → {path}")
    print(f"  ✅ Latest → {latest}")
    return str(path)