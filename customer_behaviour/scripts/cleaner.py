"""
scripts/cleaner.py — STEP 2: Clean and normalise text from flat items.

Removes:
  - URLs
  - Markdown formatting (**, ##, ~~, etc.)
  - Special characters and symbols
  - Excess whitespace

Lowercases everything for keyword matching.
Keeps original text in 'text_raw' for display.
"""

import re


# Patterns to strip
_URL_RE       = re.compile(r"https?://\S+|www\.\S+")
_MARKDOWN_RE  = re.compile(r"[*#~`_\[\]>|]")
_EXTRA_WS_RE  = re.compile(r"\s+")
_SYMBOLS_RE   = re.compile(r"[^\w\s\-./]")  # keep word chars, spaces, hyphens, dots, slashes


def clean_text(text: str) -> str:
    """Full cleaning pipeline for a single string."""
    if not text:
        return ""

    # Remove URLs
    text = _URL_RE.sub(" ", text)

    # Remove markdown
    text = _MARKDOWN_RE.sub(" ", text)

    # Remove non-essential symbols
    text = _SYMBOLS_RE.sub(" ", text)

    # Collapse whitespace
    text = _EXTRA_WS_RE.sub(" ", text).strip()

    # Lowercase
    text = text.lower()

    return text


def clean_items(flat_items: list[dict]) -> list[dict]:
    """
    Clean the 'text' field of each flat item.
    Stores original in 'text_raw', cleaned version in 'text_clean'.
    Skips items that are empty after cleaning.
    """
    cleaned = []
    for item in flat_items:
        raw_text = item.get("text", "")
        clean = clean_text(raw_text)

        if len(clean.strip()) < 5:
            continue  # skip near-empty items

        item["text_raw"]   = raw_text
        item["text_clean"] = clean

        cleaned.append(item)

    return cleaned