"""
scripts/loaders.py — Load raw data from all Marketing Agents outputs.

Reads:
  - RSS Feeder     → RSS_Feeder/db/news.db  (SQLite)
  - Serpi Feeder   → Serpi_feeder/data/**/*.json
  - Tavily Feeder  → tavily_feeder/results/*.json
  - Reddit Watcher → reddit_watcher/output/reddit_raw.json

Returns a unified dict:
  {
    "rss":    [{"title", "summary", "link", "score", "matched_keywords", "fetched_date"}],
    "trends": [{"market", "layer", "keywords": [...], "timeline": [...]}],
    "tavily": [{"query", "category", "subject", "results": [...]}],
    "reddit": [{"subreddit", "title", "score", "selftext", "top_comments"}],
  }
"""

import json
import sqlite3
import os
from datetime import datetime
from pathlib import Path
from typing import Optional


# ── RSS ──────────────────────────────────────────────────────

def load_rss(project_root: Path, since_date: str) -> list[dict]:
    db_path = project_root / "RSS_Feeder" / "db" / "news.db"
    if not db_path.exists():
        print(f"  ⚠ RSS DB not found: {db_path}")
        return []

    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    c.execute("""
        SELECT title, summary, link, published, score, matched_keywords, fetched_date
        FROM news
        WHERE fetched_date >= ?
        ORDER BY score DESC, fetched_date DESC
    """, (since_date,))
    rows = c.fetchall()
    conn.close()

    articles = []
    for row in rows:
        try:
            keywords = json.loads(row[5] or "[]")
        except Exception:
            keywords = []
        articles.append({
            "title":            row[0] or "",
            "summary":          row[1] or "",
            "link":             row[2] or "",
            "published":        row[3] or "",
            "score":            row[4] or 0,
            "matched_keywords": keywords,
            "fetched_date":     row[6] or "",
            "source_type":      "rss",
        })
    return articles


# ── Google Trends ─────────────────────────────────────────────

def load_trends(project_root: Path) -> list[dict]:
    """
    Reads all TIMESERIES JSON files from Serpi_feeder/data/
    Returns flat list of timeline series per keyword batch.
    """
    data_dir = project_root / "Serpi_feeder" / "data"
    if not data_dir.exists():
        print(f"  ⚠ Serpi data dir not found: {data_dir}")
        return []

    results = []
    for json_file in sorted(data_dir.rglob("*TIMESERIES*.json")):
        try:
            with open(json_file, encoding="utf-8") as f:
                raw = json.load(f)

            meta     = raw.get("_meta", {})
            timeline = raw.get("interest_over_time", {}).get("timeline_data", [])
            averages = raw.get("interest_over_time", {}).get("averages", [])
            keywords = meta.get("keywords", [])

            # Build clean per-keyword series
            for kw_idx, kw in enumerate(keywords):
                series = []
                for point in timeline:
                    vals = point.get("values", [])
                    v = vals[kw_idx] if kw_idx < len(vals) else {}
                    series.append({
                        "date":       point.get("date", ""),
                        "timestamp":  int(point.get("timestamp", 0)),
                        "value":      v.get("extracted_value", 0),
                        "is_partial": point.get("partial_data", False),
                    })

                avg_val = 0
                if kw_idx < len(averages):
                    avg_val = averages[kw_idx].get("value", 0)

                results.append({
                    "keyword":    kw,
                    "market":     meta.get("market", ""),
                    "layer":      meta.get("layer", ""),
                    "geo":        meta.get("geo", ""),
                    "date_param": meta.get("date_param", ""),
                    "avg":        avg_val,
                    "timeline":   series,
                    "source_type": "trends",
                })
        except Exception as e:
            print(f"  ⚠ Could not load {json_file.name}: {e}")

    return results


# ── Tavily ────────────────────────────────────────────────────

def load_tavily(project_root: Path, since_date: str) -> list[dict]:
    results_dir = project_root / "tavily_feeder" / "results"
    if not results_dir.exists():
        print(f"  ⚠ Tavily results dir not found: {results_dir}")
        return []

    # Find all date-based JSON files (not results.json)
    date_files = []
    for json_file in results_dir.glob("*.json"):
        if json_file.name == "results.json":
            continue  # Skip results.json
        try:
            # Parse date from filename (YYYY-MM-DD_HH-MM.json)
            date_str = json_file.stem[:10]
            datetime.strptime(date_str, "%Y-%m-%d")
            date_files.append(json_file)
        except Exception:
            continue  # Skip files that don't match date pattern

    if not date_files:
        print(f"  ⚠ No valid date-based Tavily files found in {results_dir}")
        return []

    # Sort by date and pick the latest
    date_files.sort(key=lambda f: f.stem[:10], reverse=True)
    latest_file = date_files[0]
    print(f"  Loading latest Tavily file: {latest_file.name}")

    try:
        # Skip empty files
        if latest_file.stat().st_size == 0:
            print(f"  ⚠ Latest Tavily file is empty: {latest_file.name}")
            return []
        
        with open(latest_file, encoding="utf-8") as f:
            raw = json.load(f)

        all_results = []
        for entry in raw.get("search_results", []):
            for result in entry.get("results", []):
                all_results.append({
                    "query":       entry.get("query", ""),
                    "category":    entry.get("category", ""),
                    "subject":     entry.get("subject", ""),
                    "title":       result.get("title", ""),
                    "url":         result.get("url", ""),
                    "content":     result.get("content", ""),
                    "score":       result.get("score", 0),
                    "source_type": "tavily",
                })
        return all_results
    except Exception as e:
        print(f"  ⚠ Could not load latest Tavily file {latest_file.name}: {e}")
        return []


# ── Reddit ────────────────────────────────────────────────────

def load_reddit(project_root: Path) -> list[dict]:
    json_path = project_root / "reddit_watcher" / "output" / "reddit_raw.json"
    if not json_path.exists():
        print(f"  ⚠ Reddit JSON not found: {json_path}")
        return []

    # Skip empty files
    if json_path.stat().st_size == 0:
        print(f"  ⚠ Reddit JSON is empty: {json_path}")
        return []

    try:
        with open(json_path, encoding="utf-8") as f:
            posts = json.load(f)
        for p in posts:
            p["source_type"] = "reddit"
        return posts
    except Exception as e:
        print(f"  ⚠ Could not load reddit data: {e}")
        return []


# ── Master loader ─────────────────────────────────────────────

def load_all_sources(project_root: Path, since_date: str) -> dict:
    print("  Loading RSS...")
    rss     = load_rss(project_root, since_date)

    print("  Loading Google Trends...")
    trends  = load_trends(project_root)

    print("  Loading Tavily...")
    tavily  = load_tavily(project_root, since_date)

    print("  Loading Reddit...")
    reddit  = load_reddit(project_root)

    return {
        "rss":    rss,
        "trends": trends,
        "tavily": tavily,
        "reddit": reddit,
    }