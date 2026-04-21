"""
scripts/fetch_reddit.py — Fetch posts and comments from Reddit via PRAW.
"""

import os
import time
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()


def get_reddit_client():
    import praw

    client_id     = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    user_agent    = os.getenv("REDDIT_USER_AGENT", "reddit-watcher/1.0")

    if not client_id or not client_secret:
        raise ValueError(
            "Missing REDDIT_CLIENT_ID or REDDIT_CLIENT_SECRET in .env\n"
            "Get credentials at: https://www.reddit.com/prefs/apps"
        )

    return praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent,
    )


def fetch_subreddit(reddit, subreddit_name: str, config: dict) -> list[dict]:
    """Fetch posts from one subreddit using config settings."""
    fetch_cfg     = config.get("fetch", {})
    sort          = fetch_cfg.get("sort", "hot")
    limit         = fetch_cfg.get("limit", 50)
    time_filter   = fetch_cfg.get("time_filter", "week")
    fetch_comments = config.get("fetch_comments", True)
    top_comments  = config.get("top_comments_per_post", 3)

    filters       = config.get("filters", {})
    min_score     = filters.get("min_score", 0)
    exclude_nsfw  = filters.get("exclude_nsfw", True)
    exclude_flairs = [f.lower() for f in filters.get("exclude_flairs", [])]
    keywords      = [k.lower() for k in filters.get("keywords", [])]

    print(f"  📡 r/{subreddit_name} [{sort}] ...")

    try:
        sub = reddit.subreddit(subreddit_name)

        # Choose sort method
        if sort == "hot":
            posts_iter = sub.hot(limit=limit)
        elif sort == "top":
            posts_iter = sub.top(limit=limit, time_filter=time_filter)
        elif sort == "new":
            posts_iter = sub.new(limit=limit)
        elif sort == "rising":
            posts_iter = sub.rising(limit=limit)
        else:
            posts_iter = sub.hot(limit=limit)

        results = []

        for post in posts_iter:
            # ── Filters ──────────────────────────────────────
            if post.score < min_score:
                continue
            if exclude_nsfw and post.over_18:
                continue
            if exclude_flairs and post.link_flair_text:
                if post.link_flair_text.lower() in exclude_flairs:
                    continue

            full_text = f"{post.title} {post.selftext}".lower()
            if keywords and not any(kw in full_text for kw in keywords):
                continue

            # ── Post data ─────────────────────────────────────
            created = datetime.fromtimestamp(post.created_utc, tz=timezone.utc)

            entry = {
                "subreddit":    subreddit_name,
                "post_id":      post.id,
                "title":        post.title,
                "score":        post.score,
                "upvote_ratio": round(post.upvote_ratio * 100, 1),
                "num_comments": post.num_comments,
                "url":          post.url,
                "permalink":    f"https://reddit.com{post.permalink}",
                "author":       str(post.author) if post.author else "[deleted]",
                "flair":        post.link_flair_text or "",
                "is_self":      post.is_self,
                "selftext":     post.selftext[:500] if post.selftext else "",
                "created_utc":  created.strftime("%Y-%m-%d %H:%M"),
                "fetched_at":   datetime.now().strftime("%Y-%m-%d %H:%M"),
                "top_comments": [],
            }

            # ── Top comments ──────────────────────────────────
            if fetch_comments and post.num_comments > 0:
                try:
                    post.comments.replace_more(limit=0)
                    for comment in list(post.comments)[:top_comments]:
                        if hasattr(comment, "body") and comment.body != "[deleted]":
                            entry["top_comments"].append({
                                "author": str(comment.author) if comment.author else "[deleted]",
                                "score":  comment.score,
                                "body":   comment.body[:300],
                            })
                except Exception:
                    pass  # skip comment errors silently

            results.append(entry)

        print(f"     ✓ {len(results)} posts fetched")
        return results

    except Exception as e:
        print(f"     ✗ Failed r/{subreddit_name}: {e}")
        return []


def fetch_all(config: dict) -> list[dict]:
    """Fetch from all configured subreddits."""
    reddit = get_reddit_client()
    subreddits = config.get("reddit", {}).get("subreddits", [])
    reddit_cfg = config.get("reddit", {})

    all_posts = []

    for sub_name in subreddits:
        posts = fetch_subreddit(reddit, sub_name, reddit_cfg)
        all_posts.extend(posts)
        time.sleep(1)  # be polite to Reddit API

    return all_posts