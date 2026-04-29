"""
scripts/rss_integrator.py — Read competitor-relevant articles from the RSS Feeder SQLite DB.

The RSS Feeder runs daily and stores scored, deduplicated articles in:
  PROJECT_ROOT/RSS_Feeder/db/news.db

This module reads directly from that database — it does NOT re-fetch live RSS feeds.
The weekly digest (RSS_Feeder/weekly.py) already selects the top articles; we read
the full DB and do our own competitor-specific filtering on top of that.
"""

import sqlite3
import json
import re
from datetime import datetime, timedelta
from pathlib import Path


def _article_matches_competitor(text: str, keywords: list[str]) -> bool:
    """Check if article text contains any competitor keywords (case-insensitive)."""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def _load_rss_db(project_root: Path, lookback_days: int, max_articles: int) -> list[dict]:
    """
    Read articles from RSS_Feeder/db/news.db.
    Returns articles fetched within the lookback window, sorted by score descending.
    """
    db_path = project_root / "RSS_Feeder" / "db" / "news.db"

    if not db_path.exists():
        print(f"  ⚠  RSS DB not found at {db_path}")
        print(f"      Run RSS_Feeder/main.py at least once to populate it.")
        return []

    cutoff_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    try:
        conn = sqlite3.connect(str(db_path))
        c = conn.cursor()
        c.execute("""
            SELECT title, summary, link, published, score, matched_keywords, fetched_date
            FROM news
            WHERE fetched_date >= ?
            ORDER BY score DESC, fetched_date DESC
            LIMIT ?
        """, (cutoff_date, max_articles))
        rows = c.fetchall()
        conn.close()
    except Exception as e:
        print(f"  ⚠  RSS DB read failed: {e}")
        return []

    articles = []
    for row in rows:
        try:
            matched_kws = json.loads(row[5] or "[]")
        except Exception:
            matched_kws = []

        articles.append({
            "title":            row[0] or "",
            "summary":          row[1] or "",
            "link":             row[2] or "",
            "published":        row[3] or "",
            "score":            row[4] or 0,
            "matched_keywords": matched_kws,
            "fetched_date":     row[6] or "",
        })

    return articles


def fetch_competitor_rss(
    project_root: Path,
    config: dict,
    competitor_profiles: dict,
    lookback_days: int = 30,
    max_articles: int = 200,
) -> dict:
    """
    Read from RSS_Feeder/db/news.db and match articles to competitors.

    Returns:
      {
        "total_articles": int,   # total articles read from DB in the window
        "total_matches":  int,   # articles matched to at least one competitor
        "by_competitor":  {name: [article_dicts]},
        "general_updates": [article_dicts],  # SBC-relevant but not competitor-specific
        "source": "rss_feeder_db",
        "db_path": str,
      }
    """
    competitors = config.get("competitors", [])

    # Build competitor keyword map: name → [keywords]
    comp_keywords = {
        c["name"]: c.get("rss_keywords", [c["name"].lower()])
        for c in competitors
    }

    # General SBC/hardware keywords for non-competitor-specific matches
    general_keywords = [
        "single board computer", "sbc", "rk3588", "rockchip",
        "raspberry pi", "orange pi", "nvme", "embedded linux",
        "esp32", "arduino", "radxa", "pine64", "banana pi", "khadas",
    ]

    by_competitor   = {name: [] for name in comp_keywords}
    general_updates = []

    print(f"  Reading RSS DB (last {lookback_days} days, max {max_articles} articles)...")
    all_articles = _load_rss_db(project_root, lookback_days, max_articles)
    print(f"  Articles in DB window: {len(all_articles)}")

    if not all_articles:
        return {
            "total_articles":  0,
            "total_matches":   0,
            "by_competitor":   by_competitor,
            "general_updates": [],
            "source":          "rss_feeder_db",
            "db_path":         str(project_root / "RSS_Feeder" / "db" / "news.db"),
        }

    for article in all_articles:
        full_text   = f"{article['title']} {article['summary']}"
        matched_any = False

        for comp_name, keywords in comp_keywords.items():
            if _article_matches_competitor(full_text, keywords):
                by_competitor[comp_name].append(article)
                matched_any = True

        if not matched_any and _article_matches_competitor(full_text, general_keywords):
            general_updates.append(article)

    total_matches = sum(len(v) for v in by_competitor.values())

    # Log per-competitor counts
    for name, arts in by_competitor.items():
        if arts:
            print(f"  {name}: {len(arts)} articles matched")

    return {
        "total_articles":  len(all_articles),
        "total_matches":   total_matches,
        "by_competitor":   by_competitor,
        "general_updates": general_updates[:30],
        "source":          "rss_feeder_db",
        "db_path":         str(project_root / "RSS_Feeder" / "db" / "news.db"),
    }