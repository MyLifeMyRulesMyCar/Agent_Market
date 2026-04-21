"""
scripts/link_collector.py — Collect top links from RSS and Reddit for the dashboard.

Reads the raw source data and returns the highest-value links across:
  - RSS: sorted by relevance score
  - Reddit: sorted by upvote score

Call this from main.py and merge results into the output dict before saving.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime


def collect_top_links(project_root: Path, since_date: str, top_n: int = 10) -> dict:
    """
    Returns:
      {
        "rss":    [top N RSS articles with title, link, score, keywords, source, published],
        "reddit": [top N Reddit posts with title, link, score, subreddit, top_comments],
      }
    """
    rss_links    = _get_top_rss(project_root, since_date, top_n)
    reddit_links = _get_top_reddit(project_root, top_n)
    tavily_links = _get_top_tavily(project_root, since_date, top_n)

    return {
        "rss":    rss_links,
        "reddit": reddit_links,
        "tavily": tavily_links,
    }


def _get_top_rss(project_root: Path, since_date: str, top_n: int) -> list[dict]:
    db_path = project_root / "RSS_Feeder" / "db" / "news.db"
    if not db_path.exists():
        return []

    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    c.execute("""
        SELECT title, link, score, matched_keywords, published, fetched_date
        FROM news
        WHERE fetched_date >= ?
        ORDER BY score DESC, fetched_date DESC
        LIMIT ?
    """, (since_date, top_n))
    rows = c.fetchall()
    conn.close()

    results = []
    for row in rows:
        try:
            keywords = json.loads(row[3] or "[]")
        except Exception:
            keywords = []

        # Extract readable source domain from link
        link = row[1] or ""
        try:
            from urllib.parse import urlparse
            source = urlparse(link).netloc.replace("www.", "")
        except Exception:
            source = ""

        results.append({
            "title":            row[0] or "",
            "link":             link,
            "score":            row[2] or 0,
            "matched_keywords": keywords,
            "source":           source,
            "published":        (row[4] or row[5] or "")[:10],
        })
    return results


def _get_top_reddit(project_root: Path, top_n: int) -> list[dict]:
    json_path = project_root / "reddit_watcher" / "output" / "reddit_raw.json"
    if not json_path.exists():
        return []

    try:
        with open(json_path, encoding="utf-8") as f:
            posts = json.load(f)
    except Exception:
        return []

    posts.sort(key=lambda p: p.get("score", 0), reverse=True)

    results = []
    for post in posts[:top_n]:
        comment_bodies = [
            c.get("body", "")[:120]
            for c in post.get("top_comments", [])
            if c.get("body") and c["body"] != "[deleted]"
        ]
        results.append({
            "title":        post.get("title", ""),
            "link":         post.get("permalink", ""),
            "score":        post.get("score", 0),
            "subreddit":    post.get("subreddit", ""),
            "top_comments": comment_bodies,
            "published":    (post.get("created_utc", "") or "")[:10],
            "num_comments": post.get("num_comments", 0),
        })
    return results


def _get_top_tavily(project_root: Path, since_date: str, top_n: int) -> list[dict]:
    """Get top Tavily results sorted by relevance score."""
    results_dir = project_root / "tavily_feeder" / "results"
    if not results_dir.exists():
        return []

    since_dt = datetime.strptime(since_date, "%Y-%m-%d")
    all_results = []

    for json_file in sorted(results_dir.glob("*.json")):
        try:
            date_str = json_file.stem[:10]
            if datetime.strptime(date_str, "%Y-%m-%d") < since_dt:
                continue
        except Exception:
            pass
        try:
            with open(json_file, encoding="utf-8") as f:
                raw = json.load(f)
            for entry in raw.get("search_results", []):
                subject  = entry.get("subject", "")
                category = entry.get("category", "")
                for r in entry.get("results", []):
                    all_results.append({
                        "title":    r.get("title", ""),
                        "link":     r.get("url", ""),
                        "score":    r.get("score", 0),
                        "subject":  subject,
                        "category": category,
                        "snippet":  (r.get("content", "") or "")[:200],
                    })
        except Exception:
            pass

    all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return all_results[:top_n]