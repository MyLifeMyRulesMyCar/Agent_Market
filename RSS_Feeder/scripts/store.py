import sqlite3
import os

DB_PATH = "db/news.db"

def init_db():
    os.makedirs("db", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS news (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT UNIQUE,
        summary TEXT,
        link TEXT UNIQUE,
        published TEXT,
        score INTEGER DEFAULT 0,
        matched_keywords TEXT,
        fetched_date TEXT
    )
    """)

    conn.commit()
    conn.close()

def save_news(entries):
    from datetime import datetime
    import json

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    saved = 0
    skipped = 0

    today = datetime.now().strftime("%Y-%m-%d")

    for e in entries:
        try:
            c.execute("""
            INSERT INTO news (title, summary, link, published, score, matched_keywords, fetched_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                e["title"],
                e["summary"],
                e["link"],
                e["published"],
                e.get("score", 0),
                json.dumps(e.get("matched_keywords", [])),
                today
            ))
            saved += 1
        except sqlite3.IntegrityError:
            skipped += 1

    conn.commit()
    conn.close()
    print(f"Saved {saved} new articles, skipped {skipped} duplicates")

def get_articles_since(date_str):
    """Fetch articles stored since a given date (YYYY-MM-DD)."""
    import json
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT title, summary, link, published, score, matched_keywords, fetched_date
        FROM news
        WHERE fetched_date >= ?
        ORDER BY score DESC, fetched_date DESC
    """, (date_str,))

    rows = c.fetchall()
    conn.close()

    articles = []
    for row in rows:
        articles.append({
            "title": row[0],
            "summary": row[1],
            "link": row[2],
            "published": row[3],
            "score": row[4],
            "matched_keywords": json.loads(row[5] or "[]"),
            "fetched_date": row[6]
        })
    return articles