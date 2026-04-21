"""
scripts/pain_points.py — STEP 4: Detect pain points using rule-based matching.

Logic:
  - Scan each item's cleaned text for "pain trigger" phrases
    (error, problem, fail, not working, etc.)
  - If a trigger is found, record the item as a pain point
  - Attach the matched trigger + keywords as evidence
  - Weight by importance score (upvotes + comments)

Output: list of detected issue dicts:
  [{
    "text":        str,    # original item text
    "triggers":    [str],  # matched pain trigger words
    "keywords":    [str],  # tech keywords in this item
    "importance":  float,
    "type":        str,    # post or comment
    "subreddit":   str,
    "date":        str,
    "post_title":  str,
  }]
"""

import os
import yaml
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "config" / "config.yaml"


def load_pain_triggers() -> list[str]:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        return [t.lower() for t in cfg.get("pain_triggers", [])]
    # Fallback
    return [
        "issue", "problem", "fail", "not working", "error",
        "cannot", "can't", "crash", "broken", "stuck", "help",
        "frustrated", "bug", "slow", "unstable", "lockup",
    ]


def detect_pain_points(items_with_keywords: list[dict]) -> list[dict]:
    """
    Scan all items for pain trigger phrases.
    Returns a flat list of detected pain point items.
    """
    triggers = load_pain_triggers()
    detected = []

    for item in items_with_keywords:
        text = item.get("text_clean", "")
        if not text:
            continue

        matched_triggers = [t for t in triggers if t in text]

        if matched_triggers:
            detected.append({
                "text":        item.get("text_raw", item.get("text", ""))[:500],
                "text_clean":  text,
                "triggers":    matched_triggers,
                "keywords":    item.get("keywords", []),
                "importance":  item.get("importance", 0),
                "score":       item.get("score", 0),
                "type":        item.get("type", "post"),
                "subreddit":   item.get("subreddit", ""),
                "date":        item.get("date", ""),
                "post_title":  item.get("post_title", ""),
                "link":        item.get("link", ""),
            })

    # Sort by importance descending
    detected.sort(key=lambda x: x["importance"], reverse=True)
    return detected