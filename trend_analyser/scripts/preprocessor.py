"""
scripts/preprocessor.py — Clean text and extract keywords from all source items.

For each item (RSS, Tavily, Reddit):
  - Strip HTML / whitespace
  - Lowercase + normalise
  - Extract keyword mentions from a master keyword list
  - Assign a base relevance score

Returns a flat list of normalised items ready for aggregation.
"""

import re
from bs4 import BeautifulSoup
from pathlib import Path
import yaml

KEYWORD_LIST_PATH = Path(__file__).parent.parent.parent / "RSS_Feeder" / "config" / "interests.yml"

# Fallback keyword list if interests.yml is unavailable
FALLBACK_KEYWORDS = [
    "raspberry pi", "orange pi", "radxa", "esp32", "arduino",
    "rockchip", "nvidia", "riscv", "risc-v", "single board computer",
    "sbc", "microcontroller", "fpga", "embedded linux",
    "solar panel", "solar inverter", "solar battery", "off grid solar",
    "home assistant", "home automation", "smart home", "zigbee",
    "matter protocol", "esphome", "tasmota", "mqtt",
]


def load_keywords() -> list[str]:
    if KEYWORD_LIST_PATH.exists():
        try:
            with open(KEYWORD_LIST_PATH) as f:
                cfg = yaml.safe_load(f)
            return [k.lower().strip() for k in cfg.get("interests", [])]
        except Exception:
            pass
    return FALLBACK_KEYWORDS


def clean_html(text: str) -> str:
    if not text:
        return ""
    try:
        soup = BeautifulSoup(text, "html.parser")
        return soup.get_text(separator=" ")
    except Exception:
        return text


def normalise_text(text: str) -> str:
    text = clean_html(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_keyword_hits(text: str, keywords: list[str]) -> list[str]:
    text_lower = text.lower()
    return [kw for kw in keywords if kw in text_lower]


def score_item(keyword_hits: list[str], base_score: int = 0) -> float:
    """
    Combined relevance score:
      - base_score: from the original data (RSS score, Reddit upvotes, Tavily score)
      - keyword hit count: number of matched keywords
    """
    kw_score = len(keyword_hits) * 2
    return float(base_score) + kw_score


# ── Per-source preprocessors ──────────────────────────────────

def preprocess_rss(items: list[dict], keywords: list[str]) -> list[dict]:
    out = []
    for item in items:
        text = f"{item.get('title','')} {item.get('summary','')}"
        text = normalise_text(text)
        hits = extract_keyword_hits(text, keywords)
        # Merge with existing matched_keywords from RSS feeder
        all_hits = list(set(hits + item.get("matched_keywords", [])))
        out.append({
            "source_type": "rss",
            "text":        text,
            "title":       normalise_text(item.get("title", "")),
            "link":        item.get("link", ""),
            "date":        item.get("fetched_date", ""),
            "keywords":    all_hits,
            "score":       score_item(all_hits, item.get("score", 0)),
            "raw":         item,
        })
    return out


def preprocess_tavily(items: list[dict], keywords: list[str]) -> list[dict]:
    out = []
    for item in items:
        text = f"{item.get('title','')} {item.get('content','')}"
        text = normalise_text(text)
        hits = extract_keyword_hits(text, keywords)
        # Also include the query subject as a keyword signal
        subject_kw = item.get("subject", "").lower().strip()
        if subject_kw and subject_kw not in hits:
            hits.append(subject_kw)
        out.append({
            "source_type": "tavily",
            "text":        text,
            "title":       normalise_text(item.get("title", "")),
            "link":        item.get("url", ""),
            "date":        "",
            "keywords":    hits,
            "score":       score_item(hits, item.get("score", 0)),
            "raw":         item,
        })
    return out


def preprocess_reddit(items: list[dict], keywords: list[str]) -> list[dict]:
    out = []
    for item in items:
        comments_text = " ".join(
            c.get("body", "") for c in item.get("top_comments", [])
        )
        text = f"{item.get('title','')} {item.get('selftext','')} {comments_text}"
        text = normalise_text(text)
        hits = extract_keyword_hits(text, keywords)
        # Subreddit name itself is a signal
        sub = item.get("subreddit", "").lower()
        if sub and sub not in hits:
            hits.append(sub)
        out.append({
            "source_type": "reddit",
            "text":        text,
            "title":       normalise_text(item.get("title", "")),
            "link":        item.get("permalink", ""),
            "date":        item.get("created_utc", "")[:10] if item.get("created_utc") else "",
            "keywords":    hits,
            "score":       score_item(hits, min(item.get("score", 0), 500)),  # cap reddit scores
            "raw":         item,
        })
    return out


# ── Master preprocessor ───────────────────────────────────────

def preprocess(raw_data: dict) -> list[dict]:
    keywords = load_keywords()
    print(f"   Using {len(keywords)} keywords for matching")

    all_items = []
    all_items += preprocess_rss(raw_data.get("rss", []), keywords)
    all_items += preprocess_tavily(raw_data.get("tavily", []), keywords)
    all_items += preprocess_reddit(raw_data.get("reddit", []), keywords)

    # Filter out items with no keyword hits
    relevant = [i for i in all_items if i["keywords"]]
    print(f"   Items with keyword matches: {len(relevant)} / {len(all_items)}")

    return relevant