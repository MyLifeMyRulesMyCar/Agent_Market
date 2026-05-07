"""
preprocessor.py — Clean text, extract keyword hits from all sources.
"""
import re
from bs4 import BeautifulSoup

DOMAIN_KEYWORDS = [
    "raspberry pi", "orange pi", "radxa", "esp32", "arduino",
    "rockchip", "rk3588", "nvme", "emmc", "sd card", "single board computer",
    "sbc", "home assistant", "smart home", "zigbee", "esphome", "solar panel",
    "solar inverter", "off grid", "lifepo4", "mppt", "embedded linux",
    "kubernetes", "k3s", "docker", "nas", "plex", "jellyfin",
]

STOPWORDS = {
    "the", "and", "for", "this", "with", "have", "from", "not", "are",
    "but", "can", "was", "has", "you", "your", "they", "use", "just",
    "also", "like", "than", "when", "what", "will", "would", "could",
    "there", "here", "some", "any", "all", "more", "very", "my", "we",
    "our", "so", "if", "or", "at", "in", "is", "it", "be", "to", "of",
    "a", "an", "on", "do", "how", "why", "who",
}

_SORTED_KW = sorted(DOMAIN_KEYWORDS, key=len, reverse=True)


def clean(text: str) -> str:
    if not text:
        return ""
    try:
        text = BeautifulSoup(text, "html.parser").get_text(separator=" ")
    except Exception:
        pass
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[*#~`_\[\]>|]", " ", text)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def extract_keywords(text: str) -> list[str]:
    found = []
    remaining = text
    for kw in _SORTED_KW:
        if kw in remaining:
            found.append(kw)
            remaining = remaining.replace(kw, " ")
    return list(set(found))


def preprocess(raw: dict) -> list[dict]:
    items = []

    for post in raw.get("reddit", []):
        comments = " ".join(c.get("body", "") for c in post.get("top_comments", []))
        text = clean(f"{post.get('title','')} {post.get('selftext','')} {comments}")
        kws = extract_keywords(text)
        if kws:
            items.append({
                "source_type": "reddit",
                "text": text,
                "title": post.get("title", ""),
                "keywords": kws,
                "score": min(post.get("score", 0), 500),
                "subreddit": post.get("subreddit", ""),
                "link": post.get("permalink", ""),
            })

    for art in raw.get("rss", []):
        text = clean(f"{art.get('title','')} {art.get('summary','')}")
        kws = list(set(extract_keywords(text) + art.get("matched_keywords", [])))
        if kws:
            items.append({
                "source_type": "rss",
                "text": text,
                "title": art.get("title", ""),
                "keywords": kws,
                "score": art.get("score", 0),
                "link": art.get("link", ""),
            })

    for r in raw.get("tavily", []):
        text = clean(f"{r.get('title','')} {r.get('content','')}")
        kws = extract_keywords(text)
        if kws:
            items.append({
                "source_type": "tavily",
                "text": text,
                "title": r.get("title", ""),
                "keywords": kws,
                "score": r.get("score", 0) * 10,  # normalise 0-1 → 0-10
                "link": r.get("url", ""),
            })

    return items