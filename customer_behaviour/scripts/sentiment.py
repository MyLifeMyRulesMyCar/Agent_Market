"""
scripts/sentiment.py — STEP 7: Sentiment analysis on all items.

Three-class classification:
  - Positive: showcase, success, working well
  - Negative: problem posts, frustration, failure
  - Neutral:  questions, discussions, news

Logic:
  1. Count positive and negative word hits
  2. Classify based on which wins
  3. Weight by importance score for aggregate stats

Output:
  {
    "positive": int,   # count of positive items
    "negative": int,
    "neutral":  int,
    "positive_pct": float,
    "negative_pct": float,
    "neutral_pct":  float,
    "weighted_positive": float,  # importance-weighted
    "weighted_negative": float,
    "weighted_neutral":  float,
  }
"""

import yaml
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "config" / "config.yaml"

# Fallback word lists
_DEFAULT_POSITIVE = [
    "working", "works", "love", "great", "awesome", "excellent",
    "perfect", "amazing", "success", "solved", "fixed", "happy",
    "thanks", "finally", "impressed", "recommend", "good",
    "stable", "fast", "easy", "smooth",
]
_DEFAULT_NEGATIVE = [
    "issue", "problem", "fail", "error", "broken", "crash",
    "stuck", "frustrated", "annoying", "terrible", "bad",
    "worst", "disappointing", "useless", "slow", "unreliable",
    "not working", "hate", "never", "garbage", "awful",
]


def load_sentiment_words():
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            sentiment_cfg = cfg.get("sentiment", {})
            pos = [w.lower() for w in sentiment_cfg.get("positive_words", _DEFAULT_POSITIVE)]
            neg = [w.lower() for w in sentiment_cfg.get("negative_words", _DEFAULT_NEGATIVE)]
            return pos, neg
        except Exception:
            pass
    return _DEFAULT_POSITIVE, _DEFAULT_NEGATIVE


def classify_item(text: str, positive_words: list, negative_words: list) -> str:
    """Classify a single item as positive, negative, or neutral."""
    pos_hits = sum(1 for w in positive_words if w in text)
    neg_hits = sum(1 for w in negative_words if w in text)

    if pos_hits == 0 and neg_hits == 0:
        return "neutral"
    if pos_hits > neg_hits:
        return "positive"
    if neg_hits > pos_hits:
        return "negative"
    # Tie → negative (problems are usually more specific)
    return "negative"


def analyse_sentiment(items: list[dict]) -> dict:
    """
    Classify all items and return aggregate sentiment counts + percentages.
    """
    positive_words, negative_words = load_sentiment_words()

    counts = {"positive": 0, "negative": 0, "neutral": 0}
    weighted = {"positive": 0.0, "negative": 0.0, "neutral": 0.0}

    for item in items:
        text = item.get("text_clean", "")
        label = classify_item(text, positive_words, negative_words)
        counts[label] += 1
        weighted[label] += item.get("importance", 1.0)

    total = sum(counts.values()) or 1
    total_w = sum(weighted.values()) or 1.0

    return {
        "positive": counts["positive"],
        "negative": counts["negative"],
        "neutral":  counts["neutral"],
        "positive_pct": round(counts["positive"] / total * 100, 1),
        "negative_pct": round(counts["negative"] / total * 100, 1),
        "neutral_pct":  round(counts["neutral"]  / total * 100, 1),
        "weighted_positive": round(weighted["positive"] / total_w * 100, 1),
        "weighted_negative": round(weighted["negative"] / total_w * 100, 1),
        "weighted_neutral":  round(weighted["neutral"]  / total_w * 100, 1),
    }