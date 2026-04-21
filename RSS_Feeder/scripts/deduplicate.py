import re
from urllib.parse import urlparse

def normalize_url(url):
    """Strip tracking params and normalize URL for comparison."""
    try:
        parsed = urlparse(url)
        # Keep only scheme + netloc + path, drop query/fragment
        return f"{parsed.netloc}{parsed.path}".rstrip("/").lower()
    except Exception:
        return url.lower()

def normalize_title(title):
    """Lowercase and strip punctuation for title comparison."""
    return re.sub(r"[^\w\s]", "", title.lower()).strip()

def remove_duplicates(entries):
    seen_urls = set()
    seen_titles = set()
    unique = []

    for e in entries:
        url_key = normalize_url(e.get("link", ""))
        title_key = normalize_title(e.get("title", ""))

        if url_key in seen_urls or title_key in seen_titles:
            continue

        seen_urls.add(url_key)
        seen_titles.add(title_key)
        unique.append(e)

    print(f"Deduplicated: {len(entries)} → {len(unique)} unique articles")
    return unique