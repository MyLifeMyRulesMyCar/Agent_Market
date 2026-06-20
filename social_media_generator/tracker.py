"""
social_media_generator/tracker.py

Tracks published posts and calls Groq to analyse what's working.

Usage:
    python tracker.py --log        # add a post to the tracker manually
    python tracker.py --analyse    # Groq analysis of your post history
    python tracker.py --show       # print all logged posts

Data stored in: social_media_generator/data/posts_log.json
"""

import os
import json
import argparse
import sys
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

_HERE = Path(__file__).parent
PROJECT_ROOT = _HERE.parent
sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(_HERE / ".env")
load_dotenv(_HERE.parent / ".env")

LOG_PATH = _HERE / "data" / "posts_log.json"


try:
    from shared.memory import record_engagement, record_content_published
except Exception:
    record_engagement = None
    record_content_published = None

PLATFORMS = ["linkedin", "x", "facebook", "youtube", "blog"]

# ── Storage ────────────────────────────────────────────────────

def load_log() -> list:
    if not LOG_PATH.exists():
        return []
    try:
        return json.loads(LOG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_log(entries: list):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text(
        json.dumps(entries, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    # Mirror each entry to the shared memory database
    if record_engagement is None or record_content_published is None:
        return

    week_label = datetime.now().strftime("%G-W%V")
    for entry in entries:
        platform = entry.get("platform", "unknown")
        topic_title = entry.get("topic", "")
        content_type = entry.get("content_type", "")
        metrics = entry.get("metrics", {})
        keywords = entry.get("keywords", [])
        keyword = (keywords[0] if keywords else "").lower()

        try:
            record_engagement(
                week_label=week_label,
                platform=platform,
                keyword=keyword,
                metrics_dict=metrics,
                topic_title=topic_title,
                content_type=content_type,
            )
            record_content_published(
                week_label=week_label,
                keyword=keyword,
                title=topic_title,
                platform=platform,
                content_type=content_type,
                status="published",
                agent="social_media_generator",
            )
        except Exception as e:
            print(f"[WARN] Could not mirror post to shared memory: {e}")


# ── Groq client ────────────────────────────────────────────────

def get_groq_client():
    try:
        from groq import Groq
        key = os.getenv("GROQ_API_KEY")
        if not key:
            raise ValueError("GROQ_API_KEY not set in .env")
        return Groq(api_key=key)
    except ImportError:
        raise ImportError("groq not installed — run: pip install groq")


def call_groq(system: str, user: str, max_tokens: int = 2000) -> str:
    client = get_groq_client()
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        temperature=0.3,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()


# ── Log a post ─────────────────────────────────────────────────

def log_post_interactive():
    """Interactive CLI to log a published post."""
    print("\n📊 Log a Published Post")
    print("=" * 40)

    entry = {}

    # Platform
    print(f"\nPlatform: {', '.join(PLATFORMS)}")
    while True:
        p = input("Platform: ").strip().lower()
        if p in PLATFORMS:
            entry["platform"] = p
            break
        print(f"  Choose from: {', '.join(PLATFORMS)}")

    # Topic
    entry["topic"] = input("Topic/title of the post: ").strip()

    # URL
    url = input("Post URL (optional, press Enter to skip): ").strip()
    if url:
        entry["url"] = url

    # Date posted
    date_str = input(f"Date posted (YYYY-MM-DD, press Enter for today): ").strip()
    if date_str:
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            entry["posted_date"] = date_str
        except ValueError:
            print("  Invalid date, using today")
            entry["posted_date"] = datetime.now().strftime("%Y-%m-%d")
    else:
        entry["posted_date"] = datetime.now().strftime("%Y-%m-%d")

    # Metrics
    print("\nEngagement metrics (press Enter to skip any):")
    metrics = {}

    if entry["platform"] in ("linkedin", "x", "facebook"):
        for field in ["likes", "comments", "shares", "reach", "clicks"]:
            val = input(f"  {field}: ").strip()
            if val:
                try:
                    metrics[field] = int(val)
                except ValueError:
                    pass

    elif entry["platform"] == "youtube":
        for field in ["views", "likes", "comments", "watch_time_hours", "subscribers_gained"]:
            val = input(f"  {field}: ").strip()
            if val:
                try:
                    metrics[field] = int(val) if field != "watch_time_hours" else float(val)
                except ValueError:
                    pass

    elif entry["platform"] == "blog":
        for field in ["page_views", "unique_visitors", "avg_time_on_page_seconds", "clicks_to_shop"]:
            val = input(f"  {field}: ").strip()
            if val:
                try:
                    metrics[field] = int(val)
                except ValueError:
                    pass

    entry["metrics"] = metrics

    # Keywords used
    kws = input("Keywords/hashtags used (comma separated, optional): ").strip()
    if kws:
        entry["keywords"] = [k.strip() for k in kws.split(",")]

    # Content type
    print("\nContent type:")
    content_types = ["tutorial", "comparison", "news", "tip", "demo", "announcement", "community"]
    for i, ct in enumerate(content_types, 1):
        print(f"  {i}. {ct}")
    ct_idx = input("Type number (or press Enter to skip): ").strip()
    if ct_idx.isdigit() and 1 <= int(ct_idx) <= len(content_types):
        entry["content_type"] = content_types[int(ct_idx) - 1]

    entry["logged_at"] = datetime.now().isoformat()

    # Save
    log = load_log()
    log.append(entry)
    save_log(log)

    print(f"\n✅ Logged: {entry['platform']} · {entry['topic']}")
    print(f"   Total posts in log: {len(log)}")


# ── Format log for Groq ────────────────────────────────────────

def format_log_for_analysis(entries: list, days: int = 90) -> str:
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    recent = [e for e in entries if e.get("posted_date", "") >= cutoff]

    if not recent:
        return "No posts logged in the last 90 days."

    lines = []
    for e in recent:
        m = e.get("metrics", {})
        metric_str = ", ".join(f"{k}={v}" for k, v in m.items()) if m else "no metrics"
        kws = ", ".join(e.get("keywords", []))
        lines.append(
            f"[{e.get('posted_date','')}] {e.get('platform','').upper()} | "
            f"{e.get('content_type', '?')} | "
            f"\"{e.get('topic','')}\" | "
            f"metrics: {metric_str}"
            + (f" | keywords: {kws}" if kws else "")
        )
    return "\n".join(lines)


# ── Groq analysis ──────────────────────────────────────────────

def analyse_posts():
    entries = load_log()
    if not entries:
        print("\n⚠  No posts logged yet.")
        print("   Run: python tracker.py --log")
        return

    print(f"\n🤖 Analysing {len(entries)} posts with Groq…\n")

    log_text = format_log_for_analysis(entries)

    system = """You are a social media performance analyst for Elephantronics, a hardware 
company making single-board computers (Purple Pi OH2) and smart home devices 
(Flamingo Edge Controller, Moes devices).

Analyse the post performance data and give specific, actionable insights.
Be direct. Use numbers where available. No filler phrases."""

    user = f"""Analyse this social media post history for Elephantronics:

POST LOG:
{log_text}

Answer these questions:
1. Which platform is performing best and why?
2. Which content type (tutorial, comparison, tip, etc.) gets the most engagement?
3. What topics seem to resonate most with the audience?
4. Which platform/content type combination should they post MORE of?
5. What should they STOP doing or do less of?
6. Give 3 specific content recommendations for next week based on what's working.

Be specific. Reference actual post topics and metrics where available.
Format your response clearly with numbered sections."""

    try:
        analysis = call_groq(system, user, max_tokens=2000)

        print("=" * 60)
        print("📊 GROQ PERFORMANCE ANALYSIS")
        print("=" * 60)
        print(analysis)
        print("=" * 60)

        # Save analysis
        output = {
            "analysed_at": datetime.now().isoformat(),
            "posts_analysed": len(entries),
            "analysis": analysis,
        }
        out_path = _HERE / "data" / f"analysis_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n✅ Analysis saved → {out_path}")

    except Exception as e:
        print(f"\n⚠  Groq analysis failed: {e}")


# ── Show all posts ─────────────────────────────────────────────

def show_posts():
    entries = load_log()
    if not entries:
        print("\n  No posts logged yet. Run: python tracker.py --log")
        return

    print(f"\n📋 All Logged Posts ({len(entries)} total)")
    print("=" * 70)

    by_platform: dict = {}
    for e in entries:
        p = e.get("platform", "unknown")
        by_platform.setdefault(p, []).append(e)

    for platform, posts in by_platform.items():
        print(f"\n  {platform.upper()} ({len(posts)} posts)")
        print("  " + "-" * 40)
        for post in sorted(posts, key=lambda x: x.get("posted_date",""), reverse=True):
            m = post.get("metrics", {})
            metric_str = "  ".join(f"{k}: {v}" for k, v in list(m.items())[:3])
            print(f"  [{post.get('posted_date','')}] {post.get('topic','')[:55]}")
            if metric_str:
                print(f"           {metric_str}")


# ── Tracker Flask routes (called from server.py) ───────────────

def get_tracker_summary() -> dict:
    """Returns summary stats for the server /context endpoint."""
    entries = load_log()
    if not entries:
        return {"total": 0, "platforms": {}, "best_platform": None}

    by_plat: dict = {}
    for e in entries:
        p = e.get("platform", "unknown")
        by_plat.setdefault(p, {"count": 0, "total_engagement": 0})
        by_plat[p]["count"] += 1

        m = e.get("metrics", {})
        engagement = (
            m.get("likes", 0) +
            m.get("comments", 0) * 2 +
            m.get("shares", 0) * 3 +
            m.get("views", 0) // 10
        )
        by_plat[p]["total_engagement"] += engagement

    best = max(by_plat.items(), key=lambda x: x[1]["total_engagement"])[0] if by_plat else None

    return {
        "total":        len(entries),
        "platforms":    by_plat,
        "best_platform": best,
    }


# ── Main ───────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Social Media Post Tracker")
    parser.add_argument("--log",     action="store_true", help="Log a new published post")
    parser.add_argument("--analyse", action="store_true", help="Run Groq analysis on post history")
    parser.add_argument("--show",    action="store_true", help="Show all logged posts")
    args = parser.parse_args()

    if args.log:
        log_post_interactive()
    elif args.analyse:
        analyse_posts()
    elif args.show:
        show_posts()
    else:
        parser.print_help()
        print("\nExamples:")
        print("  python tracker.py --log        # log a post you published")
        print("  python tracker.py --show       # see all logged posts")
        print("  python tracker.py --analyse    # Groq analysis of what's working")


if __name__ == "__main__":
    main()