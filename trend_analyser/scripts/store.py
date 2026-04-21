"""
scripts/store.py — Save trend analysis results to JSON and/or SQLite.

JSON output:
  output/YYYY-MM-DD_HH-MM.json  — full run output
  output/latest.json            — always the most recent run

SQLite output:
  output/trend_history.db       — historical runs for charting/querying
    Tables: runs, trending_keywords, rising_topics, insights
"""

import json
import sqlite3
import os
from datetime import datetime
from pathlib import Path


def save_results(output: dict, output_dir: Path, format: str = "both") -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_label = datetime.now().strftime("%Y-%m-%d_%H-%M")
    paths = []

    if format in ("json", "both"):
        p = _save_json(output, output_dir, run_label)
        paths.append(p)

    if format in ("sqlite", "both"):
        p = _save_sqlite(output, output_dir)
        paths.append(p)

    return " + ".join(paths)


def _save_json(output: dict, output_dir: Path, run_label: str) -> str:
    path   = output_dir / f"{run_label}.json"
    latest = output_dir / "latest.json"

    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    with open(latest, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"  ✅ JSON  → {path}")
    return str(path)


def _save_sqlite(output: dict, output_dir: Path) -> str:
    db_path = output_dir / "trend_history.db"
    conn    = sqlite3.connect(str(db_path))
    c       = conn.cursor()

    _init_db(c)
    conn.commit()

    run_date   = output.get("run_date", datetime.now().isoformat())
    since_date = output.get("since_date", "")

    # Insert run record
    c.execute(
        "INSERT INTO runs (run_date, since_date) VALUES (?, ?)",
        (run_date, since_date)
    )
    run_id = c.lastrowid

    # Insert trending keywords
    for kw in output.get("trending_keywords", []):
        c.execute("""
            INSERT INTO trending_keywords
              (run_id, keyword, score, mention_count, source_count,
               trends_avg, trends_latest, recency_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_id,
            kw.get("keyword", ""),
            kw.get("score", 0),
            kw.get("mention_count", 0),
            kw.get("source_count", 0),
            kw.get("trends_avg", 0),
            kw.get("trends_latest", 0),
            kw.get("recency_score", 0),
        ))

    # Insert rising topics
    for t in output.get("rising_topics", []):
        c.execute("""
            INSERT INTO rising_topics
              (run_id, keyword, velocity, recent_avg, baseline_avg,
               peak_value, peak_date, market, signals)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_id,
            t.get("keyword", ""),
            t.get("velocity", 0),
            t.get("recent_avg", 0),
            t.get("baseline_avg", 0),
            t.get("peak_value", 0),
            t.get("peak_date", ""),
            t.get("market", ""),
            json.dumps(t.get("signals", [])),
        ))

    # Insert AI insights
    for ins in output.get("insights", []):
        c.execute("""
            INSERT INTO insights (run_id, type, content)
            VALUES (?, ?, ?)
        """, (
            run_id,
            ins.get("type", ""),
            json.dumps(ins, ensure_ascii=False),
        ))

    conn.commit()
    conn.close()

    print(f"  ✅ SQLite → {db_path}")
    return str(db_path)


def _init_db(c: sqlite3.Cursor):
    c.execute("""
    CREATE TABLE IF NOT EXISTS runs (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        run_date   TEXT,
        since_date TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS trending_keywords (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id         INTEGER REFERENCES runs(id),
        keyword        TEXT,
        score          REAL,
        mention_count  INTEGER,
        source_count   INTEGER,
        trends_avg     REAL,
        trends_latest  REAL,
        recency_score  REAL
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS rising_topics (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id         INTEGER REFERENCES runs(id),
        keyword        TEXT,
        velocity       REAL,
        recent_avg     REAL,
        baseline_avg   REAL,
        peak_value     REAL,
        peak_date      TEXT,
        market         TEXT,
        signals        TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS insights (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id  INTEGER REFERENCES runs(id),
        type    TEXT,
        content TEXT
    )""")


def load_latest(output_dir: Path) -> dict:
    """Load the most recent run from latest.json."""
    latest = output_dir / "latest.json"
    if not latest.exists():
        return {}
    with open(latest, encoding="utf-8") as f:
        return json.load(f)


def query_trending_history(output_dir: Path, keyword: str, limit: int = 10) -> list[dict]:
    """Query historical trending scores for a specific keyword."""
    db_path = output_dir / "trend_history.db"
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    c    = conn.cursor()
    c.execute("""
        SELECT r.run_date, t.score, t.mention_count, t.trends_avg
        FROM trending_keywords t
        JOIN runs r ON r.id = t.run_id
        WHERE t.keyword = ?
        ORDER BY r.run_date DESC
        LIMIT ?
    """, (keyword, limit))
    rows = c.fetchall()
    conn.close()
    return [
        {"run_date": r[0], "score": r[1], "mentions": r[2], "trends_avg": r[3]}
        for r in rows
    ]