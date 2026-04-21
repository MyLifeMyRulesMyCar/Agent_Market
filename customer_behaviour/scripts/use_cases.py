"""
scripts/use_cases.py — STEP 6: Detect what users are TRYING TO BUILD.

Looks for intent signals in text:
  "building", "running", "using for", "project", "setup", "deploy"

Maps discovered use cases to predefined categories from config.

Output:
  [{
    "case":       str,    # use case label
    "category":   str,    # config key
    "mentions":   int,
    "importance": float,
    "examples":   [str],  # top example snippets
    "subreddits": [str],
  }]
"""

import yaml
from pathlib import Path
from collections import defaultdict, Counter

CONFIG_PATH = Path(__file__).parent.parent / "config" / "config.yaml"

# Verbs/phrases that signal "I am building / using for X"
INTENT_SIGNALS = [
    "using",
    "building",
    "running",
    "project",
    "setup",
    "setting up",
    "deployed",
    "deploy",
    "want to",
    "trying to",
    "built",
    "made",
    "created",
    "running as",
]


def load_use_case_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        return cfg.get("use_case_triggers", {})
    return {}


def detect_use_cases(items: list[dict]) -> list[dict]:
    """
    Scan all items for use case signals and categorise them.
    """
    uc_config = load_use_case_config()
    buckets: dict[str, list[dict]] = defaultdict(list)

    for item in items:
        text = item.get("text_clean", "")
        if not text:
            continue

        # Check if item has any intent signal
        has_intent = any(signal in text for signal in INTENT_SIGNALS)
        if not has_intent:
            continue

        # Try to match a use case
        matched = False
        for uc_key, uc_cfg in uc_config.items():
            uc_kws = [k.lower() for k in uc_cfg.get("keywords", [])]
            if any(kw in text for kw in uc_kws):
                buckets[uc_key].append(item)
                matched = True

        # Catch-all for unmatched intent items
        if not matched:
            buckets["general_project"].append(item)

    # Build output
    result = []
    for uc_key, items_in_uc in buckets.items():
        label = uc_config.get(uc_key, {}).get("label", uc_key.replace("_", " ").title())
        total_importance = sum(i.get("importance", 0) for i in items_in_uc)
        subreddits = list(set(i.get("subreddit", "") for i in items_in_uc if i.get("subreddit")))

        sorted_items = sorted(items_in_uc, key=lambda x: x.get("importance", 0), reverse=True)
        examples = []
        for it in sorted_items[:5]:
            snippet = it.get("post_title") or it.get("text", "")
            snippet = snippet[:120].strip()
            if snippet and snippet not in examples:
                examples.append(snippet)

        result.append({
            "case":       label,
            "category":   uc_key,
            "mentions":   len(items_in_uc),
            "importance": round(total_importance, 1),
            "examples":   examples,
            "subreddits": subreddits,
        })

    result.sort(key=lambda x: x["mentions"], reverse=True)
    return result