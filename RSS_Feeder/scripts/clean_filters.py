import re
import os
import yaml
from bs4 import BeautifulSoup

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "../config/interests.yml")

def load_keywords():
    with open(CONFIG_PATH, "r") as f:
        config = yaml.safe_load(f)
    return [kw.lower() for kw in config.get("interests", [])]

def clean_html(text):
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
    return soup.get_text(separator=" ")

def score_relevance(text, keywords):
    """Score how relevant an article is — counts keyword hits."""
    text = text.lower()
    score = 0
    matched = []
    for kw in keywords:
        if kw in text:
            score += 1
            matched.append(kw)
    return score, matched

def clean_and_filter(entries):
    keywords = load_keywords()
    cleaned = []

    for e in entries:
        title = clean_html(e.get("title", ""))
        summary = clean_html(e.get("summary", ""))
        full_text = f"{title} {summary}"

        score, matched = score_relevance(full_text, keywords)

        if score > 0:
            cleaned.append({
                "title": title.strip(),
                "summary": summary.strip(),
                "link": e.get("link", ""),
                "published": e.get("published", ""),
                "score": score,
                "matched_keywords": matched
            })

    print(f"Filtered to {len(cleaned)} relevant articles")
    return cleaned