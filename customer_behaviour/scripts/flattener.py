"""
scripts/flattener.py — STEP 1: Flatten nested Reddit posts + comments.

Input:  list of post dicts (from reddit_watcher format)
Output: flat list of items, each with:
  {
    "text":       str,    # combined text content
    "score":      int,    # upvotes / comment score
    "type":       str,    # "post" or "comment"
    "date":       str,    # YYYY-MM-DD
    "subreddit":  str,
    "post_title": str,    # always the parent post title
    "importance": float,  # score combining upvotes + comments + recency
    "raw":        dict,   # original data
  }

Why flatten?
  Reddit data is nested: post → [comment1, comment2, ...]
  We treat EACH piece of text as a separate signal unit.
  Title = problem summary, Body = detail, Comments = community signals.
"""

from datetime import datetime, timedelta


def compute_importance(score: int, num_comments: int = 0, date_str: str = "") -> float:
    """
    importance = upvotes + comments * 0.5 + recency bonus
    Posts within 7 days get +20% boost.
    """
    base = score * 1.0 + num_comments * 0.5
    recency_bonus = 0.0
    if date_str:
        try:
            post_date = datetime.strptime(date_str[:10], "%Y-%m-%d")
            age_days = (datetime.now() - post_date).days
            if age_days <= 7:
                recency_bonus = base * 0.20
        except Exception:
            pass
    return round(base + recency_bonus, 2)


def flatten_posts(posts: list[dict]) -> list[dict]:
    """
    Flatten all posts and their top_comments into a single list.
    Each item gets a 'text' field combining the most useful fields.
    """
    flat = []

    for post in posts:
        post_title    = post.get("title", "")
        post_body     = post.get("selftext", "")
        post_score    = post.get("score", 0)
        num_comments  = post.get("num_comments", 0)
        subreddit     = post.get("subreddit", "")
        date_str      = (post.get("created_utc") or post.get("fetched_at") or "")[:10]
        permalink     = post.get("permalink", "")

        # Combine title + body for the post item
        post_text = f"{post_title} {post_body}".strip()

        flat.append({
            "text":        post_text,
            "title":       post_title,
            "score":       post_score,
            "type":        "post",
            "date":        date_str,
            "subreddit":   subreddit,
            "post_title":  post_title,
            "num_comments": num_comments,
            "importance":  compute_importance(post_score, num_comments, date_str),
            "link":        permalink,
            "raw":         post,
        })

        # Flatten comments
        for comment in post.get("top_comments", []):
            body = comment.get("body", "")
            if not body or body == "[deleted]":
                continue

            comment_score = comment.get("score", 0)
            flat.append({
                "text":       body,
                "title":      "",
                "score":      comment_score,
                "type":       "comment",
                "date":       date_str,
                "subreddit":  subreddit,
                "post_title": post_title,
                "importance": compute_importance(comment_score, 0, date_str),
                "link":       permalink,
                "raw":        comment,
            })

    return flat