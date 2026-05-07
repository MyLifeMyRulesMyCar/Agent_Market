"""
expander.py — Expand short keywords into long-tail variants using templates.
"""
import yaml
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "config" / "config.yaml"


def load_templates() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg.get("intent_templates", {})


def expand(keyword: str, intent: str) -> list[str]:
    templates = load_templates()
    t_list = templates.get(intent, templates.get("info", []))
    return [t.replace("{kw}", keyword) for t in t_list]


def expand_all(classified: list[dict]) -> list[dict]:
    """
    Input:  [{"keyword": str, "intent": str}]
    Output: adds "long_tail" list to each entry
    """
    for item in classified:
        item["long_tail"] = expand(item["keyword"], item["intent"])
    return classified