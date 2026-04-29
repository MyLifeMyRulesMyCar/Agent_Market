"""
scripts/config_loader.py — Load and validate the competitors YAML config.
"""

import yaml
from pathlib import Path


def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # Validate required sections
    required = ["my_products", "competitors"]
    for key in required:
        if key not in cfg:
            raise ValueError(f"Config missing required section: '{key}'")

    # Apply defaults
    cfg.setdefault("comparison_features", [
        "NVMe support", "RAM capacity (max)", "USB 3.0",
        "HDMI output", "Wi-Fi", "Bluetooth", "GPIO pins", "PCIe",
    ])
    cfg.setdefault("strength_signals", [])
    cfg.setdefault("weakness_signals", [])
    cfg.setdefault("pricing", {"low_max": 35, "mid_max": 75, "high_min": 76})
    cfg.setdefault("rss_feeds", [])
    cfg.setdefault("settings", {})

    return cfg