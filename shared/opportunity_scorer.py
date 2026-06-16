"""
shared/opportunity_scorer.py — Marketing Agents Opportunity Scorer

Reads shared/signal_matrix.json and ranks opportunity signals by a
multi-factor score that weights evidence quality (not just quantity).

Pure Python — zero LLM calls.

Output:
  shared/opportunity_ranking.json
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
SHARED_DIR   = PROJECT_ROOT / "shared"
CONTENT_WRITER_DIR = PROJECT_ROOT / "content_writer"

SIGNAL_MATRIX_PATH = SHARED_DIR / "signal_matrix.json"
TOPICS_HISTORY_PATH = CONTENT_WRITER_DIR / "topics_history.json"
QUALITY_HISTORY_PATH = SHARED_DIR / "quality_history.json"
OUTPUT_PATH = SHARED_DIR / "opportunity_ranking.json"

RECENCY_DAYS = 14
RECENCY_PENALTY = 0.5
VELOCITY_BONUS = 1.0
VELOCITY_THRESHOLD = 20.0

# Quality penalties for feedback loop
HALLUCINATION_PENALTY = 1.5
COMPETITOR_ERROR_PENALTY = 1.0
MISSING_PLACEHOLDER_PENALTY = 0.5


def _log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [opportunity_scorer] {msg}"
    safe = line.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
           sys.stdout.encoding or "utf-8", errors="replace")
    print(safe)


def load_signal_matrix(path: Path = SIGNAL_MATRIX_PATH) -> dict:
    if not path.exists():
        _log(f"[MISSING] {path}")
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    _log(f"[LOADED]  signal_matrix: {len(json.dumps(data))} chars")
    return data


def load_quality_history(path: Path = QUALITY_HISTORY_PATH) -> list[dict]:
    """Load quality gate history for feedback loop."""
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def compute_quality_penalty(keyword: str, history: list[dict], days: int = 30) -> float:
    """
    If this keyword was flagged by the quality gate recently, reduce its score.
    """
    keyword_norm = keyword.lower().strip()
    cutoff = datetime.now() - timedelta(days=days)
    penalty = 0.0

    for entry in history:
        if not isinstance(entry, dict):
            continue
        entry_kw = entry.get("opportunity_keyword", "").lower().strip()
        if entry_kw != keyword_norm:
            continue
        ts = entry.get("timestamp", "")
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt <= cutoff.astimezone(timezone.utc):
                continue
        except Exception:
            pass

        flags = entry.get("flags", [])
        for flag in flags:
            flag_lower = flag.lower()
            if "hallucination" in flag_lower:
                penalty += HALLUCINATION_PENALTY
            elif "competitor_error" in flag_lower:
                penalty += COMPETITOR_ERROR_PENALTY
            elif "missing_placeholder" in flag_lower:
                penalty += MISSING_PLACEHOLDER_PENALTY

    return round(min(penalty, 3.0), 2)


def load_topics_history(path: Path = TOPICS_HISTORY_PATH) -> list[dict]:
    if not path.exists():
        _log(f"[INFO] No topics history found at {path}")
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "history" in data:
        return data["history"]
    return []


def is_keyword_recent(keyword: str, history: list[dict], days: int = RECENCY_DAYS) -> bool:
    """Check if this keyword was written about within the last N days."""
    keyword_norm = keyword.lower().strip()
    cutoff = datetime.now() - timedelta(days=days)

    for entry in history:
        # Handle various history formats
        hist_kw = ""
        if isinstance(entry, dict):
            hist_kw = entry.get("keyword", "") or entry.get("topic", "") or ""
            hist_date = entry.get("date", "") or entry.get("written_at", "") or ""
        else:
            continue

        if hist_kw.lower().strip() == keyword_norm:
            try:
                # Try ISO format first
                if hist_date:
                    dt = datetime.fromisoformat(hist_date.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if dt > cutoff.astimezone(timezone.utc):
                        return True
            except Exception:
                pass
    return False


def score_opportunity(opp: dict, history: list[dict], quality_history: list[dict]) -> dict:
    """
    Compute the opportunity score.

    score = (
        keyword_confidence × 3.0
        + pain_confidence × 2.5
        + competitor_gap_confidence × 2.0
        + velocity_bonus
        - recency_penalty
    )
    """
    keyword_conf = opp.get("keyword_confidence", 0)
    pain_conf = opp.get("pain_confidence", 0)
    gap_conf = opp.get("competitor_gap_confidence", 0)
    velocity = opp.get("velocity", 0)
    keyword = opp.get("keyword", "")

    base_score = (
        keyword_conf * 3.0
        + pain_conf * 2.5
        + gap_conf * 2.0
    )

    # Velocity bonus
    velocity_bonus = VELOCITY_BONUS if velocity > VELOCITY_THRESHOLD else 0.0

    # Recency penalty
    recent = is_keyword_recent(keyword, history)
    recency_penalty = RECENCY_PENALTY if recent else 0.0

    # Quality feedback penalty
    quality_penalty = compute_quality_penalty(keyword, quality_history)

    final_score = base_score + velocity_bonus - recency_penalty - quality_penalty
    final_score = round(max(final_score, 0.0), 2)

    return {
        **opp,
        "base_score": round(base_score, 2),
        "velocity_bonus": round(velocity_bonus, 2),
        "recency_penalty": round(recency_penalty, 2),
        "quality_penalty": quality_penalty,
        "final_score": final_score,
    }


def rank_opportunities(signal_matrix: dict, history: list[dict], quality_history: list[dict]) -> list[dict]:
    opportunities = signal_matrix.get("opportunity_signals", [])
    _log(f"Scoring {len(opportunities)} opportunity signals...")

    scored = [score_opportunity(opp, history, quality_history) for opp in opportunities]
    scored.sort(key=lambda x: x["final_score"], reverse=True)

    # Add rank
    for i, opp in enumerate(scored):
        opp["rank"] = i + 1

    return scored


def write_ranking(ranking: list[dict], path: Path = OUTPUT_PATH):
    SHARED_DIR.mkdir(exist_ok=True)
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_opportunities": len(ranking),
        "top_3": ranking[:3],
        "ranking": ranking,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    _log(f"[SAVED]   {path}")


def main():
    _log("=" * 55)
    _log("Opportunity Scorer starting")
    _log("=" * 55)

    signal_matrix = load_signal_matrix()
    if not signal_matrix:
        _log("[ABORT] No signal matrix found.")
        sys.exit(1)

    history = load_topics_history()
    _log(f"Loaded {len(history)} topic history entries")

    quality_history = load_quality_history()
    _log(f"Loaded {len(quality_history)} quality history entries")

    ranking = rank_opportunities(signal_matrix, history, quality_history)
    _log(f"Top opportunity: '{ranking[0]['keyword']}' score={ranking[0]['final_score']}")

    write_ranking(ranking)

    _log("=" * 55)
    _log("Opportunity Scorer complete")


if __name__ == "__main__":
    main()
