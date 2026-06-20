"""
test_orchestrator_chain.py — Integration smoke test for the orchestration chain.

Creates synthetic agent outputs in a temp directory, runs steps 1-4,
and verifies output schemas without making real API calls (except brief
generator, which is skipped by default — use --with-groq to test it).

Run:
    python test_orchestrator_chain.py
    python test_orchestrator_chain.py --with-groq
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "shared"))

# Use an isolated memory DB so tests don't read/write production history
import os
import tempfile
TEST_MEMORY_DB = Path(tempfile.gettempdir()) / "marketing_orchestrator_test_memory.db"
os.environ["MARKETING_MEMORY_DB_PATH"] = str(TEST_MEMORY_DB)
if TEST_MEMORY_DB.exists():
    TEST_MEMORY_DB.unlink()


def make_synthetic_agent_outputs(tmp_root: Path):
    """Create minimal agent outputs for testing."""
    (tmp_root / "customer_behaviour" / "output").mkdir(parents=True, exist_ok=True)
    (tmp_root / "trend_analyser" / "output").mkdir(parents=True, exist_ok=True)
    (tmp_root / "seo_agent" / "output").mkdir(parents=True, exist_ok=True)
    (tmp_root / "competitor_analysis" / "output").mkdir(parents=True, exist_ok=True)
    (tmp_root / "shared").mkdir(parents=True, exist_ok=True)

    customer = {
        "timestamp": "2026-06-08",
        "run_at": "2026-06-08T21:00:00",
        "source_posts": 100,
        "pain_points": [
            {
                "category": "setup",
                "label": "Zigbee pairing frustrating",
                "mentions": 42,
                "importance": 1200,
                "confidence": 0.85,
                "examples": ["I can't get my Zigbee sensors to pair reliably"],
                "subreddits": ["homeassistant"],
                "keywords": ["zigbee", "pairing", "sensor"],
            }
        ],
        "use_cases": [],
        "sentiment": {},
        "top_keywords": [{"keyword": "zigbee", "count": 42}],
    }

    trends = {
        "run_date": "2026-06-08T21:15:00",
        "trending_keywords": [
            {"keyword": "zigbee gateway", "score": 500, "confidence": 0.75, "mention_count": 80, "source_count": 3, "source_counts": {"reddit": 40, "tavily": 35, "rss": 5}, "trends_avg": 30, "trends_latest": 35, "recency_score": 50}
        ],
        "rising_topics": [
            {"keyword": "zigbee gateway", "velocity": 150, "recent_count": 20, "baseline_count": 5, "confidence": 0.9}
        ],
        "insights": [],
        "top_links": {},
    }

    seo = {
        "run_date": "2026-06-08T21:30:00",
        "top_keywords": [
            {"keyword": "zigbee gateway", "intent": "comparison", "long_tail": [], "score": 300, "confidence": 0.8, "trends_avg": 30, "reddit_count": 40, "rss_count": 5, "tavily_count": 35, "source_counts": {"trends": 1, "reddit": 40, "rss": 5, "tavily": 35}, "cluster": "home_auto"}
        ],
        "clusters": {"home_auto": []},
        "insights": [],
    }

    competitor = {
        "run_date": "2026-06-08T21:45:00",
        "my_products": [{"name": "Purple Pi OH2", "category": "sbc", "price_usd": 145, "key_features": ["Zigbee", "Home Assistant"]}],
        "competitors": [{"name": "Sonoff", "category": "gateway", "price_usd": 25, "features": ["Wi-Fi", "Zigbee"], "limitations": ["Cloud-only"]}],
        "feature_matrix": {
            "features": ["Home Assistant local", "Zigbee"],
            "products": ["Purple Pi OH2", "Sonoff"],
            "matrix": {"Sonoff": {"Home Assistant local": False, "Zigbee": True}},
            "confidence_matrix": {},
            "feature_gaps": {"Zigbee local gateway": ["Sonoff"]},
            "feature_advantages": {},
        },
        "sw_analysis": {
            "Sonoff": {
                "strengths": ["Cheap"],
                "weaknesses": ["Cloud-only"],
                "threat_score": 6.5,
                "threat_confidence": 0.7,
            }
        },
        "pricing_analysis": {
            "Sonoff": {"price_usd": 25, "tier": "low", "is_mine": False}
        },
        "rss_summary": {},
        "insights": [],
    }

    (tmp_root / "customer_behaviour" / "output" / "latest.json").write_text(json.dumps(customer), encoding="utf-8")
    (tmp_root / "trend_analyser" / "output" / "latest.json").write_text(json.dumps(trends), encoding="utf-8")
    (tmp_root / "seo_agent" / "output" / "latest.json").write_text(json.dumps(seo), encoding="utf-8")
    (tmp_root / "competitor_analysis" / "output" / "latest.json").write_text(json.dumps(competitor), encoding="utf-8")

    return tmp_root


def test_signal_merger(tmp_root: Path):
    print("\n[Test 1] Signal Merger")
    from signal_merger import merge_signals, AGENT_PATHS

    # Temporarily override paths
    original_paths = dict(AGENT_PATHS)
    AGENT_PATHS.update({
        "customer_behaviour": tmp_root / "customer_behaviour" / "output" / "latest.json",
        "trend_analyser": tmp_root / "trend_analyser" / "output" / "latest.json",
        "seo_agent": tmp_root / "seo_agent" / "output" / "latest.json",
        "competitor_analysis": tmp_root / "competitor_analysis" / "output" / "latest.json",
    })

    agent_data = {name: json.loads(p.read_text(encoding="utf-8")) for name, p in AGENT_PATHS.items()}
    matrix = merge_signals(agent_data)

    assert "opportunity_signals" in matrix
    assert len(matrix["opportunity_signals"]) > 0
    top = matrix["opportunity_signals"][0]
    assert top["keyword"] == "zigbee gateway"
    assert top["competitor_link"] == "Sonoff", f"Expected Sonoff, got {top['competitor_link']}"
    assert top["pain_link"] == "Zigbee pairing frustrating"
    print(f"   [OK] Top opportunity: {top['keyword']} / competitor: {top['competitor_link']}")

    # Restore paths
    AGENT_PATHS.update(original_paths)
    return matrix


def test_opportunity_scorer(matrix: dict, tmp_root: Path):
    print("\n[Test 2] Opportunity Scorer")
    from opportunity_scorer import rank_opportunities

    ranking = rank_opportunities(matrix, [], [])
    assert len(ranking) > 0
    assert ranking[0]["keyword"] == "zigbee gateway"
    assert ranking[0]["final_score"] > 0
    print(f"   [OK] Top ranked: {ranking[0]['keyword']} score={ranking[0]['final_score']}")
    return ranking


def test_quality_gate_penalty(matrix: dict):
    print("\n[Test 3] Quality Gate Feedback Loop")
    from opportunity_scorer import rank_opportunities, compute_quality_penalty

    quality_history = [
        {"opportunity_keyword": "zigbee gateway", "flags": ["HALLUCINATION: fake price"], "timestamp": datetime.now().isoformat()}
    ]
    penalty = compute_quality_penalty("zigbee gateway", quality_history)
    assert penalty > 0
    print(f"   [OK] Quality penalty applied: {penalty}")

    ranking_without = rank_opportunities(matrix, [], [])
    ranking_with = rank_opportunities(matrix, [], quality_history)
    assert ranking_with[0]["quality_penalty"] > 0
    print(f"   [OK] Score with penalty: {ranking_with[0]['final_score']} (was {ranking_without[0]['final_score']})")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-groq", action="store_true", help="Also test the brief generator with a real Groq call")
    args = parser.parse_args()

    print("=" * 60)
    print("  Orchestrator Chain Integration Test")
    print("=" * 60)

    tmp_dir = Path(tempfile.mkdtemp(prefix="marketing_orchestrator_test_"))
    print(f"\nTemp root: {tmp_dir}")

    try:
        make_synthetic_agent_outputs(tmp_dir)
        matrix = test_signal_merger(tmp_dir)
        ranking = test_opportunity_scorer(matrix, tmp_dir)
        test_quality_gate_penalty(matrix)

        if args.with_groq:
            print("\n[Test 4] Brief Generator (live Groq call)")
            from brief_generator import build_prompt, call_groq, get_groq_key
            system, user = build_prompt(ranking[0])
            api_key = get_groq_key()
            result = call_groq(system, user, api_key)
            assert "title" in result["brief"]
            print(f"   [OK] Brief title: {result['brief']['title']}")

        print("\n" + "=" * 60)
        print("  ALL TESTS PASSED [OK]")
        print("=" * 60)

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
        print(f"\nCleaned up temp dir: {tmp_dir}")


if __name__ == "__main__":
    main()
