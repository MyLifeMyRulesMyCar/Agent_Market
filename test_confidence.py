"""
Quick synthetic test for confidence scores across all agents.
Run: python test_confidence.py
"""

import subprocess
import sys


def run_test(agent, script):
    """Run a test snippet for one agent in a subprocess with its own PYTHONPATH."""
    code = f'''
import sys
sys.path.insert(0, "{agent}")

if "{agent}" == "seo_agent":
    from scripts.scorer import _calculate_confidence as fn
    print("=" * 55)
    print("SEO AGENT confidence")
    print("=" * 55)
    tests = [
        (51, 42, 8, 0, "home assistant (high)"),
        (0, 3, 0, 0, "smart home devices (low)"),
        (80, 20, 5, 2, "strong multi-source"),
        (0, 0, 0, 0, "no data"),
        (100, 50, 10, 5, "maxed out"),
    ]
    for t_avg, r, s, v, label in tests:
        c = fn(t_avg, r, s, v)
        print(f"  {{label:<35}} -> confidence = {{c:.3f}}")

    ok1 = fn(51, 42, 8, 0) > 0.7
    ok2 = fn(0, 3, 0, 0) < 0.3
    print(f"[{{'PASS' if ok1 else 'FAIL'}}] home assistant should be high confidence")
    print(f"[{{'PASS' if ok2 else 'FAIL'}}] smart home devices should be low confidence")

elif "{agent}" == "trend_analyser":
    from scripts.trending import detect_trending
    print("\\n" + "=" * 55)
    print("TREND ANALYSER confidence")
    print("=" * 55)
    mock_counts = {{
        "home assistant": {{
            "mention_count": 50, "source_score": 120.0, "total_score": 300.0,
            "source_counts": {{"reddit": 42, "rss": 8, "trends": 1}},
            "trends_avg": 51, "trends_latest": 48,
        }},
        "smart home devices": {{
            "mention_count": 3, "source_score": 6.0, "total_score": 9.0,
            "source_counts": {{"reddit": 3}},
            "trends_avg": 0, "trends_latest": 0,
        }},
    }}
    trending = detect_trending(mock_counts, [], None, top_n=5)
    for t in trending:
        print(f"  {{t['keyword']:<35}} -> confidence = {{t['confidence']:.3f}}")
    ok = trending[0]["confidence"] > trending[1]["confidence"]
    print(f"[{{'PASS' if ok else 'FAIL'}}] richer source > sparse source")

elif "{agent}" == "customer_behaviour":
    from scripts.clusterer import cluster_pain_points
    print("\\n" + "=" * 55)
    print("CUSTOMER BEHAVIOUR confidence")
    print("=" * 55)
    mock_issues = [
        {{"text_clean": "boot failure", "keywords": ["boot"], "importance": 120, "subreddit": "OrangePI"}},
        {{"text_clean": "cannot boot from nvme", "keywords": ["boot", "nvme"], "importance": 95, "subreddit": "OrangePI"}},
        {{"text_clean": "sd card not working", "keywords": ["sd card"], "importance": 80, "subreddit": "SBCs"}},
        {{"text_clean": "wifi drops", "keywords": ["wifi"], "importance": 5, "subreddit": "homeassistant"}},
        {{"text_clean": "wifi slow", "keywords": ["wifi"], "importance": 4, "subreddit": "homeassistant"}},
        {{"text_clean": "wifi disconnect", "keywords": ["wifi"], "importance": 3, "subreddit": "homeassistant"}},
    ]
    clusters = cluster_pain_points(mock_issues)
    for c in clusters:
        print(f"  {{c['label']:<35}} -> confidence = {{c['confidence']:.3f}}  ({{c['mentions']}} mentions, {{len(c['subreddits'])}} subreddits)")
    ok = clusters[0]["confidence"] > clusters[-1]["confidence"]
    print(f"[{{'PASS' if ok else 'FAIL'}}] more mentions > fewer mentions")

elif "{agent}" == "competitor_analysis":
    from scripts.strength_detector import _compute_data_confidence as fn
    print("\\n" + "=" * 55)
    print("COMPETITOR ANALYSIS confidence")
    print("=" * 55)
    profiles = [
        {{"vector_docs": [1,2,3,4,5], "rss_updates": [1]*12, "known_features": ["a","b","c","d"], "label": "Rich data"}},
        {{"vector_docs": [], "rss_updates": [], "known_features": [], "label": "No data"}},
        {{"vector_docs": [1,2], "rss_updates": [1]*3, "known_features": ["a"], "label": "Sparse data"}},
    ]
    for p in profiles:
        label = p.pop("label")
        c = fn(p)
        print(f"  {{label:<35}} -> data confidence = {{c:.3f}}")
    ok = fn({{"vector_docs": [], "rss_updates": [], "known_features": []}}) < 0.2
    print(f"[{{'PASS' if ok else 'FAIL'}}] no data = low confidence")
'''
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)


results = []
for agent in ["seo_agent", "trend_analyser", "customer_behaviour", "competitor_analysis"]:
    r = run_test(agent, "")
    print(r.stdout, end="")
    if r.stderr:
        print(r.stderr, end="", file=sys.stderr)
    results.append(r.returncode == 0)

print("\n" + "=" * 55)
all_ok = all(results)
print("OVERALL: " + ("ALL PASS" if all_ok else "SOME FAILED"))
sys.exit(0 if all_ok else 1)
