"""
shared/memory.py — Cross-agent memory backbone.

Single shared SQLite database that replaces the fragmented JSON history files.
All agents read and write through this module; they never write raw SQL here.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_DB_PATH = Path(__file__).parent / "memory.db"

# Allow tests and alternative deployments to override the DB location.
ENV_DB_PATH = "MARKETING_MEMORY_DB_PATH"


def _db_path() -> Path:
    env = os.getenv(ENV_DB_PATH)
    if env:
        return Path(env)
    return DEFAULT_DB_PATH


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _week_label(dt: datetime | None = None) -> str:
    if dt is None:
        dt = datetime.now()
    return dt.strftime("%G-W%V")


def _parse_dt(value: str) -> datetime:
    """Parse an ISO datetime or date string as flexibly as possible."""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return datetime.strptime(value[:10], "%Y-%m-%d")


def _recency_weight(run_date_str: str, half_life_days: int = 30) -> float:
    try:
        dt = _parse_dt(run_date_str)
    except Exception:
        return 0.5
    age_days = (datetime.now() - dt).days
    return max(0.1, 0.5 ** (age_days / half_life_days))


def _compute_engagement(metrics: dict) -> float:
    """Weighted engagement score — kept here so the memory layer is self-contained."""
    m = metrics or {}
    return float(
        m.get("likes", 0) * 1.0
        + m.get("comments", 0) * 2.0
        + m.get("shares", 0) * 3.0
        + m.get("reach", 0) * 0.1
        + m.get("views", 0) * 0.05
        + m.get("clicks", 0) * 2.0
        + m.get("watch_time_hours", 0) * 5.0
        + m.get("page_views", 0) * 0.5
        + m.get("unique_visitors", 0) * 0.8
        + m.get("clicks_to_shop", 0) * 4.0
        + m.get("subscribers_gained", 0) * 10.0
    )


SCHEMA = """
CREATE TABLE IF NOT EXISTS content_published (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_label TEXT NOT NULL,
    run_date TEXT NOT NULL,
    agent TEXT NOT NULL,
    keyword TEXT NOT NULL,
    topic_title TEXT,
    platform TEXT,
    content_type TEXT,
    status TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_content_keyword ON content_published(keyword);
CREATE INDEX IF NOT EXISTS idx_content_week ON content_published(week_label);

CREATE TABLE IF NOT EXISTS keyword_scores_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_label TEXT NOT NULL,
    run_date TEXT NOT NULL,
    keyword TEXT NOT NULL,
    score REAL,
    confidence REAL,
    reddit_count INTEGER DEFAULT 0,
    trends_avg REAL DEFAULT 0,
    rss_count INTEGER DEFAULT 0,
    tavily_count INTEGER DEFAULT 0,
    cluster TEXT,
    intent TEXT
);
CREATE INDEX IF NOT EXISTS idx_scores_keyword ON keyword_scores_history(keyword);
CREATE INDEX IF NOT EXISTS idx_scores_week ON keyword_scores_history(week_label);

CREATE TABLE IF NOT EXISTS topic_momentum (
    keyword TEXT PRIMARY KEY,
    first_seen_week TEXT,
    last_seen_week TEXT,
    times_trending INTEGER DEFAULT 0,
    times_written INTEGER DEFAULT 0,
    times_published INTEGER DEFAULT 0,
    avg_score_last_4_weeks REAL DEFAULT 0.0,
    momentum_direction TEXT DEFAULT 'plateauing',
    saturation_score REAL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS engagement_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_label TEXT NOT NULL,
    run_date TEXT NOT NULL,
    platform TEXT NOT NULL,
    content_type TEXT,
    keyword TEXT,
    topic_title TEXT,
    likes INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0,
    shares INTEGER DEFAULT 0,
    reach INTEGER DEFAULT 0,
    clicks INTEGER DEFAULT 0,
    engagement_score REAL DEFAULT 0.0
);
CREATE INDEX IF NOT EXISTS idx_engagement_keyword ON engagement_signals(keyword);
CREATE INDEX IF NOT EXISTS idx_engagement_week ON engagement_signals(week_label);

CREATE TABLE IF NOT EXISTS agent_run_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_label TEXT NOT NULL,
    run_date TEXT NOT NULL,
    agent TEXT NOT NULL,
    keywords_processed INTEGER DEFAULT 0,
    opportunities_generated INTEGER DEFAULT 0,
    top_keyword TEXT,
    top_score REAL,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_run_agent ON agent_run_log(agent, week_label);
"""


def init_db() -> None:
    """Create tables and migrate legacy JSON history on first run."""
    with _connect() as conn:
        conn.executescript(SCHEMA)
        _migrate_legacy_data(conn)


def _migrate_legacy_data(conn: sqlite3.Connection) -> None:
    """One-way migration from the old flat JSON files. Safe to call repeatedly."""
    cur = conn.execute("SELECT COUNT(*) FROM content_published")
    if cur.fetchone()[0] == 0:
        _migrate_topics_history(conn)

    cur = conn.execute("SELECT COUNT(*) FROM engagement_signals")
    if cur.fetchone()[0] == 0:
        _migrate_posts_log(conn)


def _migrate_topics_history(conn: sqlite3.Connection) -> None:
    path = PROJECT_ROOT / "content_writer" / "output" / "topics_history.json"
    if not path.exists():
        return
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    if not isinstance(entries, list):
        return

    for entry in entries:
        keyword = (entry.get("keyword") or "").lower()
        title = entry.get("title") or ""
        run_date = entry.get("written_at") or datetime.now().isoformat()
        try:
            week_label = _week_label(_parse_dt(run_date))
        except Exception:
            week_label = _week_label()

        conn.execute(
            """
            INSERT INTO content_published
            (week_label, run_date, agent, keyword, topic_title, platform, content_type, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (week_label, run_date, "content_writer", keyword, title, "blog", "article", "draft"),
        )


def _migrate_posts_log(conn: sqlite3.Connection) -> None:
    path = PROJECT_ROOT / "social_media_generator" / "data" / "posts_log.json"
    if not path.exists():
        return
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    if not isinstance(entries, list):
        return

    for entry in entries:
        platform = (entry.get("platform") or "unknown").lower()
        content_type = (entry.get("content_type") or "").lower()
        topic_title = entry.get("topic") or ""
        metrics = entry.get("metrics") or {}
        keywords = entry.get("keywords") or []
        keyword = (keywords[0] or "").lower() if keywords else ""
        run_date = entry.get("logged_at") or entry.get("posted_date") or datetime.now().isoformat()
        try:
            week_label = _week_label(_parse_dt(run_date))
        except Exception:
            week_label = _week_label()

        engagement_score = _compute_engagement(metrics)
        conn.execute(
            """
            INSERT INTO engagement_signals
            (week_label, run_date, platform, content_type, keyword, topic_title,
             likes, comments, shares, reach, clicks, engagement_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                week_label,
                run_date,
                platform,
                content_type,
                keyword,
                topic_title,
                metrics.get("likes", 0),
                metrics.get("comments", 0),
                metrics.get("shares", 0),
                metrics.get("reach", 0),
                metrics.get("clicks", 0),
                engagement_score,
            ),
        )
        conn.execute(
            """
            INSERT INTO content_published
            (week_label, run_date, agent, keyword, topic_title, platform, content_type, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (week_label, run_date, "social_media_generator", keyword, topic_title, platform, content_type, "published"),
        )


# ── Public write API ─────────────────────────────────────────────


def record_keyword_scores(week_label: str, scored_keywords_list: list[dict]) -> None:
    """SEO agent writes the full set of scored keywords for this week."""
    run_date = datetime.now().isoformat()
    with _connect() as conn:
        conn.execute("DELETE FROM keyword_scores_history WHERE week_label = ?", (week_label,))
        for kw in scored_keywords_list:
            conn.execute(
                """
                INSERT INTO keyword_scores_history
                (week_label, run_date, keyword, score, confidence, reddit_count,
                 trends_avg, rss_count, tavily_count, cluster, intent)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    week_label,
                    run_date,
                    (kw.get("keyword") or "").lower(),
                    kw.get("score", 0),
                    kw.get("confidence", 0),
                    kw.get("reddit_count", 0),
                    kw.get("trends_avg", 0),
                    kw.get("rss_count", 0),
                    kw.get("tavily_count", 0),
                    kw.get("cluster") or "",
                    kw.get("intent") or "",
                ),
            )


def record_content_published(
    week_label: str,
    keyword: str,
    title: str,
    platform: str,
    content_type: str,
    status: str,
    agent: str = "content_writer",
) -> None:
    """Log a content item produced by any agent."""
    run_date = datetime.now().isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO content_published
            (week_label, run_date, agent, keyword, topic_title, platform, content_type, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                week_label,
                run_date,
                agent,
                (keyword or "").lower(),
                title or "",
                (platform or "").lower(),
                (content_type or "").lower(),
                status,
            ),
        )


def record_engagement(
    week_label: str,
    platform: str,
    keyword: str,
    metrics_dict: dict,
    topic_title: str | None = None,
    content_type: str | None = None,
) -> None:
    """Social tracker / manual log writes one engagement row per post."""
    run_date = datetime.now().isoformat()
    metrics = metrics_dict or {}
    engagement_score = _compute_engagement(metrics)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO engagement_signals
            (week_label, run_date, platform, content_type, keyword, topic_title,
             likes, comments, shares, reach, clicks, engagement_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                week_label,
                run_date,
                (platform or "").lower(),
                (content_type or "").lower(),
                (keyword or "").lower(),
                topic_title or "",
                metrics.get("likes", 0),
                metrics.get("comments", 0),
                metrics.get("shares", 0),
                metrics.get("reach", 0),
                metrics.get("clicks", 0),
                engagement_score,
            ),
        )


def record_agent_run(week_label: str, agent_name: str, stats_dict: dict | None = None) -> None:
    """One row per agent per run, for the orchestrator's skip-rerun logic."""
    run_date = datetime.now().isoformat()
    stats = stats_dict or {}
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO agent_run_log
            (week_label, run_date, agent, keywords_processed, opportunities_generated,
             top_keyword, top_score, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                week_label,
                run_date,
                agent_name,
                stats.get("keywords_processed", 0),
                stats.get("opportunities_generated", 0),
                stats.get("top_keyword") or "",
                stats.get("top_score", 0),
                stats.get("notes") or "",
            ),
        )


# ── Public read API ──────────────────────────────────────────────


def get_keyword_history(keyword: str, lookback_weeks: int = 8) -> list[dict[str, Any]]:
    """Return recent SEO score rows for a keyword (newest first)."""
    kw = (keyword or "").lower().strip()
    with _connect() as conn:
        cur = conn.execute(
            """
            SELECT * FROM keyword_scores_history
            WHERE keyword = ?
            ORDER BY run_date DESC
            LIMIT ?
            """,
            (kw, lookback_weeks),
        )
        return [dict(row) for row in cur.fetchall()]


def get_saturation_score(keyword: str) -> float:
    """0.0 = fresh, 1.0 = heavily saturated."""
    kw = (keyword or "").lower().strip()
    with _connect() as conn:
        cur = conn.execute("SELECT saturation_score FROM topic_momentum WHERE keyword = ?", (kw,))
        row = cur.fetchone()
        return float(row[0]) if row else 0.0


def get_published_this_cycle(lookback_weeks: int = 4) -> list[dict[str, Any]]:
    """All content_published rows from the last N weeks."""
    cutoff = datetime.now() - timedelta(weeks=lookback_weeks)
    cutoff_str = cutoff.isoformat()
    with _connect() as conn:
        cur = conn.execute(
            """
            SELECT * FROM content_published
            WHERE run_date >= ?
            ORDER BY run_date DESC
            """,
            (cutoff_str,),
        )
        return [dict(row) for row in cur.fetchall()]


def get_engagement_by_keyword(keyword: str) -> dict[str, Any]:
    """Aggregated engagement signals for a keyword across platforms."""
    kw = (keyword or "").lower().strip()
    with _connect() as conn:
        cur = conn.execute(
            """
            SELECT platform, engagement_score FROM engagement_signals
            WHERE keyword = ?
            ORDER BY run_date DESC
            """,
            (kw,),
        )
        rows = cur.fetchall()

    if not rows:
        return {"total_engagement_score": 0.0, "count": 0, "by_platform": {}}

    total = sum(row["engagement_score"] or 0 for row in rows)
    by_platform: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "total": 0.0})
    for row in rows:
        p = row["platform"] or "unknown"
        by_platform[p]["count"] += 1
        by_platform[p]["total"] += row["engagement_score"] or 0

    by_platform_out = {
        p: {"count": v["count"], "avg": round(v["total"] / v["count"], 2) if v["count"] else 0.0}
        for p, v in by_platform.items()
    }
    return {
        "total_engagement_score": round(total, 2),
        "count": len(rows),
        "by_platform": by_platform_out,
    }


def get_top_performing_content_types(lookback_weeks: int = 8) -> list[dict[str, Any]]:
    """Ranked platform+content_type combos by recency-weighted engagement score."""
    cutoff = datetime.now() - timedelta(weeks=lookback_weeks)
    cutoff_str = cutoff.isoformat()
    with _connect() as conn:
        cur = conn.execute(
            """
            SELECT * FROM engagement_signals
            WHERE run_date >= ?
            ORDER BY run_date DESC
            """,
            (cutoff_str,),
        )
        rows = cur.fetchall()

    if not rows:
        return []

    agg: dict[tuple[str, str], dict[str, Any]] = defaultdict(lambda: {"total_weighted": 0.0, "total_weight": 0.0, "count": 0})
    for row in rows:
        key = (row["platform"] or "unknown", row["content_type"] or "unknown")
        weight = _recency_weight(row["run_date"])
        score = row["engagement_score"] or 0
        agg[key]["total_weighted"] += score * weight
        agg[key]["total_weight"] += weight
        agg[key]["count"] += 1

    results = []
    for (platform, content_type), v in agg.items():
        avg = v["total_weighted"] / v["total_weight"] if v["total_weight"] > 0 else 0.0
        results.append(
            {
                "platform": platform,
                "content_type": content_type,
                "avg_engagement_score": round(avg, 2),
                "count": v["count"],
            }
        )
    results.sort(key=lambda x: x["avg_engagement_score"], reverse=True)
    return results


def get_momentum_direction(keyword: str) -> str:
    """One of: accelerating, plateauing, declining."""
    kw = (keyword or "").lower().strip()
    with _connect() as conn:
        cur = conn.execute("SELECT momentum_direction FROM topic_momentum WHERE keyword = ?", (kw,))
        row = cur.fetchone()
        return row[0] if row else "plateauing"


def get_agents_run_this_cycle(week_label: str) -> list[str]:
    """List agents already logged for the given week."""
    with _connect() as conn:
        cur = conn.execute(
            "SELECT DISTINCT agent FROM agent_run_log WHERE week_label = ?",
            (week_label,),
        )
        return [row[0] for row in cur.fetchall()]


# ── Compute / maintenance API ────────────────────────────────────


def recompute_topic_momentum() -> None:
    """Rebuild the derived topic_momentum table from the other four tables."""
    with _connect() as conn:
        cur = conn.execute("SELECT DISTINCT keyword FROM keyword_scores_history")
        score_keywords = {row[0] for row in cur.fetchall()}

        cur = conn.execute("SELECT DISTINCT keyword FROM content_published")
        pub_keywords = {row[0] for row in cur.fetchall()}

        all_keywords = score_keywords | pub_keywords

        conn.execute("DELETE FROM topic_momentum")

        for kw in all_keywords:
            cur = conn.execute(
                """
                SELECT week_label, score FROM keyword_scores_history
                WHERE keyword = ?
                ORDER BY run_date DESC
                """,
                (kw,),
            )
            score_rows = cur.fetchall()
            times_trending = len(score_rows)
            last4_scores = [s for _, s in score_rows[:4]]
            avg_last4 = sum(last4_scores) / len(last4_scores) if last4_scores else 0.0

            if len(score_rows) >= 4:
                recent = sum(s for _, s in score_rows[:2]) / 2
                prior = sum(s for _, s in score_rows[2:4]) / 2
                if prior == 0:
                    direction = "accelerating" if recent > 0 else "plateauing"
                else:
                    change = (recent - prior) / prior
                    if change > 0.05:
                        direction = "accelerating"
                    elif change < -0.05:
                        direction = "declining"
                    else:
                        direction = "plateauing"
            else:
                direction = "plateauing"

            weeks = [w for w, _ in score_rows]
            first_seen_week = min(weeks) if weeks else None
            last_seen_week = max(weeks) if weeks else None

            cur = conn.execute(
                """
                SELECT COUNT(*) FROM content_published
                WHERE keyword = ? AND agent = 'content_writer'
                """,
                (kw,),
            )
            times_written = cur.fetchone()[0]

            cur = conn.execute(
                """
                SELECT COUNT(*) FROM content_published
                WHERE keyword = ? AND agent = 'social_media_generator'
                """,
                (kw,),
            )
            times_published = cur.fetchone()[0]

            saturation = min(times_written / max(times_trending, 1), 1.0)

            conn.execute(
                """
                INSERT INTO topic_momentum
                (keyword, first_seen_week, last_seen_week, times_trending, times_written,
                 times_published, avg_score_last_4_weeks, momentum_direction, saturation_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    kw,
                    first_seen_week,
                    last_seen_week,
                    times_trending,
                    times_written,
                    times_published,
                    round(avg_last4, 2),
                    direction,
                    round(saturation, 4),
                ),
            )


def build_memory_digest() -> str:
    """Human-readable memory summary for the brief generator prompt."""
    with _connect() as conn:
        cur = conn.execute(
            """
            SELECT keyword, saturation_score, avg_score_last_4_weeks, momentum_direction
            FROM topic_momentum
            ORDER BY avg_score_last_4_weeks DESC
            LIMIT 5
            """
        )
        top = [dict(row) for row in cur.fetchall()]

        cur = conn.execute(
            """
            SELECT keyword, saturation_score FROM topic_momentum
            WHERE saturation_score >= 0.5
            ORDER BY saturation_score DESC
            LIMIT 5
            """
        )
        saturated = [dict(row) for row in cur.fetchall()]

        cur = conn.execute(
            """
            SELECT keyword FROM topic_momentum
            WHERE momentum_direction = 'accelerating'
            ORDER BY avg_score_last_4_weeks DESC
            LIMIT 5
            """
        )
        accelerating = [dict(row) for row in cur.fetchall()]

        cur = conn.execute(
            """
            SELECT platform, content_type, AVG(engagement_score) AS avg_engagement_score
            FROM engagement_signals
            GROUP BY platform, content_type
            ORDER BY avg_engagement_score DESC
            LIMIT 5
            """
        )
        combos = [dict(row) for row in cur.fetchall()]

    lines = ["=== MEMORY DIGEST (cross-agent history) ==="]

    if saturated:
        lines.append(
            "Saturated topics (avoid repeating soon): "
            + ", ".join(f"{r['keyword']} (sat={r['saturation_score']:.2f})" for r in saturated)
        )
    if accelerating:
        lines.append("Accelerating keywords: " + ", ".join(r["keyword"] for r in accelerating))
    if top:
        lines.append(
            "Top keywords by 4-week avg score: "
            + ", ".join(f"{r['keyword']} ({r['avg_score_last_4_weeks']:.1f})" for r in top)
        )
    if combos:
        lines.append(
            "Top performing content combos: "
            + ", ".join(
                f"{r['platform']}+{r['content_type']} ({r['avg_engagement_score']:.1f})"
                for r in combos
            )
        )

    if len(lines) == 1:
        lines.append("No accumulated memory yet — first run after deployment.")

    lines.append("=== END MEMORY DIGEST ===")
    return "\n".join(lines)


# Initialise on first import so consumers always have a ready schema.
init_db()
