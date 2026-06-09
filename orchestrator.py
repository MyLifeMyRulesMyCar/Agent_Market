"""
orchestrator.py — Marketing Intelligence Orchestrator

Reads the four latest agent outputs (customer_behaviour, trend_analyser,
seo_agent, competitor_analysis), sends them to Groq in a single prompt,
and writes a unified intelligence_snapshot.json to shared/.

Usage:
    python orchestrator.py
"""

import os
import sys
import json
import textwrap
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv

import requests

PROJECT_ROOT = Path(__file__).parent
SHARED_DIR   = PROJECT_ROOT / "shared"
LOG_FILE     = SHARED_DIR / "orchestrator_log.txt"
OUTPUT_FILE  = SHARED_DIR / "intelligence_snapshot.json"

# ── Agent JSON paths ──────────────────────────────────────────
AGENTS = {
    "customer_behaviour": PROJECT_ROOT / "customer_behaviour" / "output" / "latest.json",
    "trend_analyser":     PROJECT_ROOT / "trend_analyser"     / "output" / "latest.json",
    "seo_agent":          PROJECT_ROOT / "seo_agent"          / "output" / "latest.json",
    "competitor_analysis":PROJECT_ROOT / "competitor_analysis"/ "output" / "latest.json",
}

# ── Logging ───────────────────────────────────────────────────

def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    safe = line.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
           sys.stdout.encoding or "utf-8", errors="replace")
    print(safe)
    SHARED_DIR.mkdir(exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ── Helpers ───────────────────────────────────────────────────

def load_json(path: Path, label: str) -> dict:
    if not path.exists():
        log(f"[MISSING] {label}: {path}")
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        log(f"[LOADED]  {label}: {len(json.dumps(data))} chars")
        return data
    except Exception as e:
        log(f"[ERROR]   {label}: {e}")
        return {}


def truncate_agent_data(data: dict, max_items: int = 20, max_chars: int = 4000) -> str:
    """Trim bulky lists to stay within token budget."""
    # Deep copy so we don't mutate original
    trimmed = json.loads(json.dumps(data))

    # Truncate known large arrays
    for key in ["pain_points", "trending_keywords", "top_keywords", "competitors",
                "rss_updates", "my_products", "flat_items", "source_posts",
                "references"]:
        if isinstance(trimmed, dict) and key in trimmed and isinstance(trimmed[key], list):
            trimmed[key] = trimmed[key][:max_items]

    # Also trim nested example arrays inside pain_points
    if isinstance(trimmed, dict) and "pain_points" in trimmed:
        for pp in trimmed["pain_points"]:
            for sub in ["examples", "subreddits", "keywords"]:
                if sub in pp and isinstance(pp[sub], list):
                    pp[sub] = pp[sub][:10]

    out = json.dumps(trimmed, ensure_ascii=False, indent=2)
    if len(out) > max_chars:
        out = out[:max_chars] + "\n... [truncated]"
    return out


def get_groq_key() -> str:
    # Try root .env first
    root_env = PROJECT_ROOT / ".env"
    if root_env.exists():
        load_dotenv(root_env)
    # Fallback: any agent .env with GROQ key
    for agent_path in AGENTS.values():
        env_path = agent_path.parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=False)
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY not found in any .env")
    return key


# ── Groq synthesis ────────────────────────────────────────────

SYSTEM_PROMPT = textwrap.dedent("""\
    You are a senior market intelligence analyst.
    You receive four JSON reports from specialized marketing agents:
    1. Customer Behaviour — pain points, sentiment, community signals
    2. Trend Analyser — trending keywords, cross-source momentum
    3. SEO Agent — keyword clusters, search intent, content gaps
    4. Competitor Analysis — competitor features, pricing, news/rss updates

    Each agent now includes a confidence score (0.0–1.0) with its signals.
    Treat items with confidence < 0.4 as weak signals only.
    Weight your synthesis by confidence — high-confidence data should drive
    stronger recommendations; low-confidence data should be noted as tentative.

    Synthesize these into ONE unified JSON object with the following schema.
    Be concise but insightful. Use bullet arrays where appropriate.
    Output **only** valid JSON — no markdown fences, no commentary.

    {
      "sources": ["customer_behaviour", "trend_analyser", "seo_agent", "competitor_analysis"],
      "executive_summary": "2-3 sentence strategic overview",
      "market_intelligence": {
        "top_trends": [
          {"trend": "...", "momentum": "high|medium|low", "confidence": 0.0-1.0, "insight": "..."}
        ],
        "emerging_opportunities": ["..."],
        "threats": ["..."]
      },
      "customer_insights": {
        "top_pain_points": [
          {"issue": "...", "severity": "high|medium|low", "confidence": 0.0-1.0, "evidence": "..."}
        ],
        "sentiment_summary": "...",
        "unmet_needs": ["..."]
      },
      "competitive_landscape": {
        "competitor_moves": [
          {"competitor": "...", "move": "...", "impact": "high|medium|low"}
        ],
        "positioning_gaps": ["..."],
        "pricing_signals": ["..."]
      },
      "seo_and_content_opportunities": {
        "high_value_keywords": [
          {"keyword": "...", "intent": "...", "priority": "high|medium|low"}
        ],
        "content_gaps": ["..."],
        "recommended_actions": ["..."]
      },
      "strategic_recommendations": [
        {"action": "...", "rationale": "...", "priority": "high|medium|low"}
      ]
    }
""")


def synthesize_with_groq(agent_payloads: dict, api_key: str) -> dict:
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    user_content = "Here are the four agent reports:\n\n"
    for name, payload in agent_payloads.items():
        user_content += f"--- {name.upper().replace('_', ' ')} ---\n"
        user_content += payload + "\n\n"

    body = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_content},
        ],
        "temperature": 0.3,
        "max_tokens": 4096,
        "response_format": {"type": "json_object"},
    }

    log("[GROQ] Sending synthesis request...")
    resp = requests.post(url, headers=headers, json=body, timeout=120)
    resp.raise_for_status()
    result = resp.json()
    content = result["choices"][0]["message"]["content"]
    usage = result.get("usage", {})
    log(f"[GROQ] OK — prompt_tokens={usage.get('prompt_tokens','?')}, "
        f"completion_tokens={usage.get('completion_tokens','?')}")
    return json.loads(content)


# ── Main ──────────────────────────────────────────────────────

def main():
    log("=" * 55)
    log("Orchestrator starting")
    log("=" * 55)

    # 1. Load agent data
    payloads = {}
    for name, path in AGENTS.items():
        data = load_json(path, name)
        if data:
            payloads[name] = truncate_agent_data(data)
        else:
            payloads[name] = "{}"

    missing = [name for name, p in payloads.items() if p == "{}"]
    if missing:
        log(f"[WARN] Missing data for: {', '.join(missing)}")
    if len(missing) == len(payloads):
        log("[ABORT] No agent data available.")
        sys.exit(1)

    # 2. Get key
    try:
        api_key = get_groq_key()
    except RuntimeError as e:
        log(f"[ERROR] {e}")
        sys.exit(1)

    # 3. Synthesize
    try:
        snapshot = synthesize_with_groq(payloads, api_key)
    except Exception as e:
        log(f"[ERROR] Groq call failed: {e}")
        sys.exit(1)

    # 4. Enrich with metadata
    snapshot["snapshot_date"] = datetime.now(timezone.utc).isoformat()
    snapshot["sources"] = list(AGENTS.keys())

    # 5. Write
    SHARED_DIR.mkdir(exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    log(f"[SAVED]   {OUTPUT_FILE}")
    log("=" * 55)
    log("Orchestrator complete")


if __name__ == "__main__":
    main()
