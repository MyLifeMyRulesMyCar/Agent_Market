"""
shared/brief_generator.py — Marketing Agents Brief Generator

Reads shared/opportunity_ranking.json, takes the top opportunity,
and generates a structured content brief via one focused Groq call.

Output:
  shared/content_brief_{timestamp}.json
  shared/content_brief_latest.json  (symlink/copy for downstream consumers)
"""

from __future__ import annotations

import json
import os
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import requests


PROJECT_ROOT = Path(__file__).parent.parent
SHARED_DIR   = PROJECT_ROOT / "shared"

OPPORTUNITY_PATH = SHARED_DIR / "opportunity_ranking.json"
MEMORY_DIGEST_PATH = SHARED_DIR / "memory_digest_latest.json"
OUTPUT_DIR = SHARED_DIR
LATEST_PATH = SHARED_DIR / "content_brief_latest.json"

GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def _log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [brief_generator] {msg}"
    safe = line.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
           sys.stdout.encoding or "utf-8", errors="replace")
    print(safe)


def get_groq_key() -> str:
    """Find GROQ_API_KEY in project root .env or any agent .env."""
    from dotenv import load_dotenv
    root_env = PROJECT_ROOT / ".env"
    if root_env.exists():
        load_dotenv(root_env)
    # Fallback: check content_writer .env
    cw_env = PROJECT_ROOT / "content_writer" / ".env"
    if cw_env.exists():
        load_dotenv(cw_env, override=False)
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY not found in any .env")
    return key


def load_opportunity_ranking(path: Path = OPPORTUNITY_PATH) -> dict:
    if not path.exists():
        _log(f"[MISSING] {path}")
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    _log(f"[LOADED]  opportunity_ranking: {len(json.dumps(data))} chars")
    return data


def build_prompt(opportunity: dict) -> tuple[str, str]:
    """Build system + user prompts for the brief generator."""

    system_prompt = textwrap.dedent("""\
        You are a senior content strategist for a hardware company called Elephantronics.
        Your job is to write a tight, actionable content brief based on a market opportunity.

        Rules:
        - Be specific. No generic filler.
        - The brief must be grounded in the evidence provided.
        - Output ONLY a valid JSON object. No markdown fences, no commentary.

        Required JSON schema:
        {
          "title": "one specific, SEO-targeted title (max 80 chars)",
          "angle": "the specific argument or framing (2 sentences)",
          "hook": "the opening pain point to lead with (1 sentence)",
          "key_claim": "what we prove that competitors can't (1 sentence)",
          "cta": "what action we want the reader to take (1 sentence)"
        }
    """)

    keyword = opportunity.get("keyword", "")
    keyword_conf = opportunity.get("keyword_confidence", 0)
    pain = opportunity.get("pain_link", "")
    pain_quote = opportunity.get("pain_example_quote", "")
    competitor = opportunity.get("competitor_link", "")
    missing_feature = opportunity.get("missing_feature", "")
    rationale = opportunity.get("rationale", "")
    strength = opportunity.get("strength", 0)

    memory_digest = ""
    if MEMORY_DIGEST_PATH.exists():
        try:
            with open(MEMORY_DIGEST_PATH, "r", encoding="utf-8") as f:
                digest_data = json.load(f)
            memory_digest = "\n\n" + str(digest_data.get("digest", ""))
        except Exception:
            memory_digest = ""

    user_prompt = f"""Write a content brief for this opportunity:

OPPORTUNITY:
- Keyword: {keyword} (confidence: {keyword_conf})
- Pain point: {pain}
- Real community quote: "{pain_quote}"
- Competitor gap: {competitor} lacks {missing_feature}
- Evidence: {rationale}
- Opportunity strength: {strength}/10
{memory_digest}

Write the brief now. Return ONLY valid JSON."""

    return system_prompt, user_prompt


def call_groq(system: str, user: str, api_key: str) -> dict:
    body = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.4,
        "max_tokens": 800,
        "response_format": {"type": "json_object"},
    }

    _log("[GROQ] Sending brief generation request...")
    resp = requests.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=body,
        timeout=120,
    )
    resp.raise_for_status()
    result = resp.json()
    content = result["choices"][0]["message"]["content"]
    usage = result.get("usage", {})
    _log(f"[GROQ] OK — prompt_tokens={usage.get('prompt_tokens','?')}, "
         f"completion_tokens={usage.get('completion_tokens','?')}")

    return {
        "brief": json.loads(content),
        "tokens_used": usage,
    }


def write_brief(brief_data: dict, opportunity: dict, tokens_used: dict):
    timestamp = datetime.now(timezone.utc).isoformat()
    output = {
        "opportunity": opportunity,
        "brief": brief_data,
        "generated_at": timestamp,
        "tokens_used": tokens_used,
    }

    # Timestamped file
    ts_file = f"content_brief_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    ts_path = OUTPUT_DIR / ts_file
    SHARED_DIR.mkdir(exist_ok=True)
    with open(ts_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    _log(f"[SAVED]   {ts_path}")

    # Latest symlink (copy on Windows)
    with open(LATEST_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    _log(f"[SAVED]   {LATEST_PATH}")


def main():
    _log("=" * 55)
    _log("Brief Generator starting")
    _log("=" * 55)

    ranking = load_opportunity_ranking()
    if not ranking or not ranking.get("ranking"):
        _log("[ABORT] No opportunities found.")
        sys.exit(1)

    top_opp = ranking["ranking"][0]
    _log(f"Selected opportunity #{top_opp.get('rank', 1)}: '{top_opp.get('keyword', '')}'")

    try:
        api_key = get_groq_key()
    except RuntimeError as e:
        _log(f"[ERROR] {e}")
        sys.exit(1)

    system_prompt, user_prompt = build_prompt(top_opp)

    try:
        result = call_groq(system_prompt, user_prompt, api_key)
    except Exception as e:
        _log(f"[ERROR] Groq call failed: {e}")
        sys.exit(1)

    brief_data = result["brief"]
    tokens_used = result["tokens_used"]

    write_brief(brief_data, top_opp, tokens_used)

    _log(f"Brief title: {brief_data.get('title', 'N/A')}")
    _log("=" * 55)
    _log("Brief Generator complete")


if __name__ == "__main__":
    main()
