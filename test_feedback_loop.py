"""
test_feedback_loop.py — Smoke-test the performance feedback loop
without making any API calls.

Run from the project root:
    python test_feedback_loop.py

Tests:
  1. performance_reader correctly computes engagement scores
  2. bias_engine produces correct directives from signals
  3. prompt_builder injects performance context into prompts
  4. The whole chain produces expected output types

Creates a small synthetic tracker log in /tmp, runs the pipeline,
then cleans up. Does not touch your real posts_log.json.
"""

import sys
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta

# ── Add project paths ─────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "content_writer"))

# Use an isolated memory DB so tests don't read/write production history
import os
import tempfile
TEST_MEMORY_DB = Path(tempfile.gettempdir()) / "marketing_feedback_test_memory.db"
os.environ["MARKETING_MEMORY_DB_PATH"] = str(TEST_MEMORY_DB)
if TEST_MEMORY_DB.exists():
    TEST_MEMORY_DB.unlink()


def make_synthetic_log(log_path: Path):
    """
    Create a synthetic tracker log that has clear winners:
    YouTube tutorials outperform everything else 3:1.
    """
    now = datetime.now()

    posts = []

    # YouTube tutorials — high engagement
    for i in range(5):
        posts.append({
            "platform":     "youtube",
            "topic":        f"Purple Pi OH2 Setup Tutorial #{i+1}",
            "content_type": "tutorial",
            "posted_date":  (now - timedelta(days=i*7)).strftime("%Y-%m-%d"),
            "metrics": {
                "views":              2000 + i * 300,
                "likes":              180  + i * 20,
                "comments":           45   + i * 5,
                "watch_time_hours":   120  + i * 15,
                "subscribers_gained": 12   + i * 2,
            },
            "logged_at": now.isoformat(),
        })

    # LinkedIn posts — medium engagement
    for i in range(4):
        posts.append({
            "platform":     "linkedin",
            "topic":        f"IoT Edge Computing Insight #{i+1}",
            "content_type": "tip",
            "posted_date":  (now - timedelta(days=i*5+3)).strftime("%Y-%m-%d"),
            "metrics": {
                "likes":    55 + i * 8,
                "comments": 12 + i * 2,
                "shares":   8  + i,
                "reach":    800 + i * 100,
                "clicks":   25  + i * 3,
            },
            "logged_at": now.isoformat(),
        })

    # Facebook posts — low engagement
    for i in range(3):
        posts.append({
            "platform":     "facebook",
            "topic":        f"Product Update #{i+1}",
            "content_type": "announcement",
            "posted_date":  (now - timedelta(days=i*10+5)).strftime("%Y-%m-%d"),
            "metrics": {
                "likes":   8  + i,
                "comments": 2 + i,
                "shares":   1,
                "reach":    120 + i * 20,
            },
            "logged_at": now.isoformat(),
        })

    # X / Twitter — minimal engagement
    for i in range(2):
        posts.append({
            "platform":     "x",
            "topic":        f"Quick tip #{i+1}",
            "content_type": "tip",
            "posted_date":  (now - timedelta(days=i*14+2)).strftime("%Y-%m-%d"),
            "metrics": {
                "likes":  12 + i * 3,
                "shares": 2,
                "reach":  200 + i * 50,
            },
            "logged_at": now.isoformat(),
        })

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(posts, f, indent=2)

    print(f"   [OK] Synthetic log written: {len(posts)} posts -> {log_path}")
    return posts


def test_performance_reader(tmp_root: Path):
    print("\n[Test 1] performance_reader.read_performance()")

    from content_writer.scripts.performance_reader import read_performance

    signals = read_performance(tmp_root, lookback_days=365, min_posts=1)

    assert signals.has_data,                        "FAIL: has_data should be True"
    assert signals.total_posts >= 14,               "FAIL: should have 14 posts"
    assert signals.best_platform == "youtube",      f"FAIL: expected youtube, got {signals.best_platform}"
    assert signals.worst_platform in ("x","facebook"), f"FAIL: worst should be x or facebook, got {signals.worst_platform}"
    assert "youtube" in signals.platform_scores,    "FAIL: youtube missing from platform_scores"
    assert signals.platform_scores["youtube"] > signals.platform_scores.get("facebook", 0), \
        "FAIL: youtube should score higher than facebook"
    assert len(signals.insights) > 0,              "FAIL: should have at least one insight"
    assert signals.format_bias.get("youtube", 0) >= 1.0, \
        "FAIL: youtube format_bias should be >= 1.0"

    print(f"   [OK] best_platform  : {signals.best_platform}")
    print(f"   [OK] worst_platform : {signals.worst_platform}")
    print(f"   [OK] best_type      : {signals.best_content_type}")
    print(f"   [OK] platform_scores: {json.dumps(signals.platform_scores, indent=6)}")
    print(f"   [OK] format_bias    : {json.dumps(signals.format_bias, indent=6)}")
    print(f"   [OK] insights[0]    : {signals.insights[0][:80]}")

    return signals


def test_bias_engine(signals):
    print("\n[Test 2] bias_engine.compute_directives()")

    from content_writer.scripts.bias_engine import compute_directives, format_bias_report

    directives = compute_directives(signals, requested_article_count=3)

    assert directives.data_driven,                     "FAIL: should be data-driven"
    assert directives.primary_platforms[0] == "youtube", \
        f"FAIL: primary platform should be youtube, got {directives.primary_platforms[0]}"
    assert directives.platform_bias.get("youtube", 0) >= 1.0, \
        "FAIL: youtube bias should be >= 1.0"
    assert directives.platform_bias.get("facebook", 1) <= directives.platform_bias.get("youtube", 1), \
        "FAIL: facebook bias should be <= youtube bias"
    assert "tutorial" in directives.preferred_formats or len(directives.preferred_formats) > 0, \
        "FAIL: should have at least one preferred format"
    assert directives.summary != "",                    "FAIL: summary should not be empty"

    print(f"   [OK] data_driven         : {directives.data_driven}")
    print(f"   [OK] primary_platforms   : {directives.primary_platforms[:3]}")
    print(f"   [OK] preferred_formats   : {directives.preferred_formats}")
    print(f"   [OK] recommended_framing : {directives.recommended_framing[:60]}...")
    print(f"   [OK] summary             : {directives.summary}")

    report = format_bias_report(signals, directives)
    assert "youtube" in report.lower(),  "FAIL: report should mention youtube"
    assert len(report) > 100,            "FAIL: report should be non-trivial"
    print(f"   [OK] bias report generated ({len(report)} chars)")

    return directives


def test_prompt_injection(directives):
    print("\n[Test 3] bias_engine.inject_bias_into_contexts()")

    from content_writer.scripts.bias_engine import inject_bias_into_contexts

    # Minimal fake contexts
    contexts = [
        {"index": 1, "keyword": "home assistant sbc", "intent": "info",
         "title": "Home Assistant on Purple Pi OH2", "cluster": "home_auto",
         "seo_score": 8.5, "pain_point": {}, "use_case": {}, "products": [],
         "unmet_needs": [], "angle": "", "placeholders": {},
         "snapshot_summary": ""},
        {"index": 2, "keyword": "zigbee gateway", "intent": "comparison",
         "title": "Best Zigbee Gateway 2026", "cluster": "home_auto",
         "seo_score": 7.0, "pain_point": {}, "use_case": {}, "products": [],
         "unmet_needs": [], "angle": "", "placeholders": {},
         "snapshot_summary": ""},
    ]

    enriched = inject_bias_into_contexts(contexts, directives)

    for ctx in enriched:
        assert "preferred_platform"    in ctx, "FAIL: missing preferred_platform"
        assert "preferred_format"      in ctx, "FAIL: missing preferred_format"
        assert "recommended_framing"   in ctx, "FAIL: missing recommended_framing"
        assert "is_performance_biased" in ctx, "FAIL: missing is_performance_biased"
        assert "performance_context"   in ctx, "FAIL: missing performance_context"
        assert ctx["is_performance_biased"] is True, "FAIL: should be marked as biased"
        assert ctx["preferred_platform"] == "youtube", \
            f"FAIL: preferred_platform should be youtube, got {ctx['preferred_platform']}"

    print(f"   [OK] {len(enriched)} contexts enriched")
    print(f"   [OK] preferred_platform : {enriched[0]['preferred_platform']}")
    print(f"   [OK] preferred_format   : {enriched[0]['preferred_format']}")
    print(f"   [OK] is_performance_biased : {enriched[0]['is_performance_biased']}")
    print(f"   [OK] performance_context length : {len(enriched[0]['performance_context'])} chars")

    return enriched


def test_prompt_builder(contexts):
    print("\n[Test 4] prompt_builder.build_prompt()")

    from content_writer.scripts.prompt_builder import build_prompt

    # Minimal config
    config = {
        "generation": {"articles_per_run": 3, "word_count_min": 500, "word_count_max": 800},
        "brand": {
            "name":     "Purple Pi",
            "tone":     "practical",
            "audience": "makers",
            "products": [{"token": "PRODUCT_SBC", "name": "Purple Pi OH2", "category": "sbc"}],
        },
        "structure": {"sections": ["hook", "problem", "solution_intro", "how_it_works", "comparison", "cta"]},
        "placeholders": {
            "product_name": "[PRODUCT_NAME]",
            "cta_link":     "[SHOP_LINK]",
            "docs_link":    "[DOCS_LINK]",
            "setup_guide":  "[SETUP_GUIDE_LINK]",
        },
    }

    for ctx in contexts:
        system, user = build_prompt(ctx, config)

        assert len(system) > 100,         "FAIL: system prompt too short"
        assert len(user) > 200,           "FAIL: user prompt too short"
        assert "PERFORMANCE" in user,     "FAIL: performance block missing from user prompt"
        assert "youtube" in user.lower(), "FAIL: should mention youtube in prompt"
        assert "[PRODUCT_NAME]" in user,  "FAIL: placeholder instructions missing"

    print(f"   [OK] system prompt: {len(system)} chars")
    print(f"   [OK] user prompt  : {len(user)} chars")
    print(f"   [OK] performance block present: {'PERFORMANCE' in user}")
    print(f"   [OK] platform emphasis present: {'youtube' in user.lower()}")

    # Print the performance section from the prompt so we can inspect it
    lines = user.split("\n")
    in_perf = False
    perf_lines = []
    for line in lines:
        if "PERFORMANCE" in line.upper():
            in_perf = True
        if in_perf:
            perf_lines.append(line)
        if in_perf and line.strip() == "":
            break
    print(f"\n   Performance block preview:")
    for line in perf_lines[:8]:
        print(f"     {line}")


def test_no_data_path():
    print("\n[Test 5] Graceful handling when no tracker data exists")

    from content_writer.scripts.performance_reader import read_performance, PerformanceSignals
    from content_writer.scripts.bias_engine import compute_directives

    # Point at a non-existent path
    fake_root = Path("/tmp/fake_marketing_root_xyz")

    signals = read_performance(fake_root)

    assert not signals.has_data,           "FAIL: has_data should be False for empty root"
    assert signals.total_posts == 0,       "FAIL: total_posts should be 0"

    directives = compute_directives(signals)

    assert not directives.data_driven,                 "FAIL: directives should not be data-driven"
    assert len(directives.primary_platforms) > 0,      "FAIL: should still have default platforms"
    assert len(directives.preferred_formats) > 0,      "FAIL: should still have default formats"
    assert directives.platform_bias.get("blog") == 1.0,"FAIL: default bias should be 1.0"

    print(f"   [OK] no-data path handled gracefully")
    print(f"   [OK] data_driven        : {directives.data_driven}")
    print(f"   [OK] primary_platforms  : {directives.primary_platforms}")
    print(f"   [OK] summary            : {directives.summary}")


# ── Main ──────────────────────────────────────────────────────

def main():
    print("\n" + "="*60)
    print("  Feedback Loop Integration Test")
    print("="*60)

    # Create a temp directory that mirrors the project structure
    tmp_dir = Path(tempfile.mkdtemp(prefix="marketing_feedback_test_"))
    tmp_log  = tmp_dir / "social_media_generator" / "data" / "posts_log.json"

    print(f"\n   Temp project root: {tmp_dir}")

    try:
        # Create synthetic data
        print("\n[Setup] Creating synthetic tracker log...")
        make_synthetic_log(tmp_log)

        # Run tests
        signals    = test_performance_reader(tmp_dir)
        directives = test_bias_engine(signals)
        contexts   = test_prompt_injection(directives)
        test_prompt_builder(contexts)
        test_no_data_path()

        print("\n" + "="*60)
        print("  ALL TESTS PASSED [OK]")
        print("="*60)
        print(f"""
What the feedback loop does:
  1. Reads {tmp_log.name} (your real file: social_media_generator/data/posts_log.json)
  2. Computes weighted engagement score per platform/format
  3. YouTube scored highest in this test -> bias multiplier = 1.0x (reference)
  4. Facebook scored lowest -> deprioritised in article generation
  5. prompt_builder injects the performance block so Groq knows what's working
  6. Content writer article contexts gain preferred_platform + preferred_format keys

To activate in production:
  python content_writer/main.py          -> performance-biased generation
  python content_writer/main.py --no-bias -> skip bias, use defaults
  python content_writer/main.py --dry-run -> inspect prompts without API calls
""")

    except AssertionError as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        import traceback
        print(f"\n[FAIL] UNEXPECTED ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        try:
            if TEST_MEMORY_DB.exists():
                TEST_MEMORY_DB.unlink()
        except PermissionError:
            pass  # SQLite may still hold the file handle on Windows
        print(f"   Cleaned up temp dir: {tmp_dir}")


if __name__ == "__main__":
    main()