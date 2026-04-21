"""
scripts/clusterer.py — STEP 5: Cluster detected pain points into categories.

Groups similar issues using keyword matching against cluster definitions
from config.yaml.

"boot failure"
"cannot boot"
"sd card not working"
→ ONE cluster: "Boot / Startup Issues"

Output:
  [{
    "category":   str,
    "label":      str,
    "mentions":   int,
    "importance": float,   # sum of all issue importances
    "examples":   [str],   # top 3 representative snippets
    "subreddits": [str],   # which subreddits this appears in
    "keywords":   [str],   # top keywords in this cluster
  }]
"""

import yaml
from pathlib import Path
from collections import defaultdict, Counter

CONFIG_PATH = Path(__file__).parent.parent / "config" / "config.yaml"


def load_cluster_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        return cfg.get("pain_clusters", {})
    return {}


def assign_to_cluster(issue: dict, clusters: dict) -> str:
    """
    Return the best matching cluster key for an issue,
    or 'other' if no cluster matches.
    """
    text = issue.get("text_clean", "")
    keywords = issue.get("keywords", [])
    combined = text + " " + " ".join(keywords)

    best_cluster = "other"
    best_hits = 0

    for cluster_key, cluster_cfg in clusters.items():
        cluster_kws = [k.lower() for k in cluster_cfg.get("keywords", [])]
        hits = sum(1 for kw in cluster_kws if kw in combined)
        if hits > best_hits:
            best_hits = hits
            best_cluster = cluster_key

    return best_cluster


def cluster_pain_points(detected_issues: list[dict]) -> list[dict]:
    """
    Assign each detected issue to a cluster.
    Aggregate into cluster summaries sorted by mention count.
    """
    clusters_cfg = load_cluster_config()

    # Bucket issues into clusters
    buckets: dict[str, list[dict]] = defaultdict(list)
    for issue in detected_issues:
        cluster_key = assign_to_cluster(issue, clusters_cfg)
        buckets[cluster_key].append(issue)

    # Build output
    result = []
    for cluster_key, issues in buckets.items():
        # Aggregate metadata
        total_importance = sum(i.get("importance", 0) for i in issues)
        subreddits = list(set(i.get("subreddit", "") for i in issues if i.get("subreddit")))

        # Top keywords across all issues in this cluster
        all_keywords = []
        for i in issues:
            all_keywords.extend(i.get("keywords", []))
        top_keywords = [kw for kw, _ in Counter(all_keywords).most_common(8)]

        # Example snippets — take the highest-importance ones
        sorted_issues = sorted(issues, key=lambda x: x.get("importance", 0), reverse=True)
        examples = []
        for iss in sorted_issues[:5]:
            snippet = iss.get("post_title") or iss.get("text", "")
            snippet = snippet[:120].strip()
            if snippet and snippet not in examples:
                examples.append(snippet)

        # Get label from config or format from key
        label = clusters_cfg.get(cluster_key, {}).get("label", cluster_key.replace("_", " ").title())

        result.append({
            "category":   cluster_key,
            "label":      label,
            "mentions":   len(issues),
            "importance": round(total_importance, 1),
            "examples":   examples,
            "subreddits": subreddits,
            "keywords":   top_keywords,
        })

    # Sort by mentions descending
    result.sort(key=lambda x: x["mentions"], reverse=True)
    return result