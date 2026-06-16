"""
shared/quality_gate.py — Marketing Agents Quality Gate

Checks each generated content piece for:
  1. Hallucinations — prices, URLs, model numbers not in brief/context
  2. Missing placeholders — [PRODUCT_NAME], [SHOP_LINK], etc.
  3. Competitor accuracy — claims contradicting known_features

Uses one cheap Groq call per piece (llama-3.1-8b-instant).

Output:
  - Appends quality_flags[] to each piece
  - Moves flagged pieces to a review/ queue
  - Writes shared/quality_history.json for feedback loop
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
SHARED_DIR = PROJECT_ROOT / "shared"
CONTENT_WRITER_DIR = PROJECT_ROOT / "content_writer"
SOCIAL_DIR = PROJECT_ROOT / "social_media_generator"

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GATE_MODEL = "llama-3.3-70b-versatile"

QUALITY_HISTORY_PATH = SHARED_DIR / "quality_history.json"

REVIEW_DIRS = {
    "content_writer": CONTENT_WRITER_DIR / "review",
    "social_media": SOCIAL_DIR / "review",
}

BRAND = {
    "name": "Elephantronics",
    "products": ["Purple Pi OH2", "Flamingo Edge Controller", "Moes Smart Devices"],
    "url": "docs.elephantronics.com",
}


def _log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [quality_gate] {msg}"
    safe = line.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
           sys.stdout.encoding or "utf-8", errors="replace")
    print(safe)


def get_groq_key() -> str:
    from dotenv import load_dotenv
    for env_path in [PROJECT_ROOT / ".env", PROJECT_ROOT / "content_writer" / ".env"]:
        if env_path.exists():
            load_dotenv(env_path, override=False)
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY not found")
    return key


def load_enriched_brief(path: Path = SHARED_DIR / "enriched_brief_latest.json") -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_competitor_analysis(path: Path = PROJECT_ROOT / "competitor_analysis" / "output" / "latest.json") -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_gate_prompt(platform: str, content_piece: str, brief: dict, comp_ctx: dict, known_features: list[str]) -> tuple[str, str]:
    system_prompt = textwrap.dedent("""\
        You are a strict but fair quality assurance reviewer for Elephantronics marketing content.
        Your job is to catch FACTUAL errors and missing required tokens. Do not flag normal marketing language, reasonable inferences, or creative phrasing.

        Return ONLY a valid JSON object in this exact format:
        {
          "hallucinations": [{"claim": "specific claim", "reason": "not in brief/context"}],
          "competitor_errors": ["Claims X has no WiFi, but known_features says WiFi is present"]
        }

        Rules — be precise:

        1. HALLUCINATIONS (only flag these):
           - A specific price, URL, or exact model number that is NOT in the brief, brand context, or competitor context.
           - A concrete technical specification (e.g., "Wi-Fi 6", "2GB RAM", "Zigbee 3.0") that is NOT supported by the provided context.
           - Do NOT flag general marketing phrases like "robust ecosystem", "hours spent troubleshooting", "large hard drive", "easy setup", or "friendly community".
           - Do NOT flag the Elephantronics products: Purple Pi OH2, Flamingo Edge Controller, Moes Smart Devices. These are valid brand products.
           - Do NOT flag "$" followed by a price if the price matches the competitor price in the context.

        2. COMPETITOR ERRORS:
           - Only flag a direct contradiction between what the content claims about the competitor and the known_features list.
           - Treat "no X", "lacks X", "missing X", and "X is not supported" as EQUIVALENT statements — do NOT flag them as errors.
           - If known_features says "Matter support is missing" and the content says "no Matter support", that is CONSISTENT, not an error.
           - If known_features says "WiFi present" and the content says "no WiFi", that IS an error.

        3. If no issues, return empty arrays for both fields.
    """)

    brief_data = brief.get("brief", {})
    brief_text = f"""BRIEF:
- Title: {brief_data.get('title', '')}
- Angle: {brief_data.get('angle', '')}
- Hook: {brief_data.get('hook', '')}
- Key claim: {brief_data.get('key_claim', '')}
- CTA: {brief_data.get('cta', '')}
"""

    comp_text = ""
    if comp_ctx and comp_ctx.get("competitor_name"):
        comp_text = f"""
COMPETITOR CONTEXT:
- Name: {comp_ctx.get('competitor_name', '')}
- Price: ${comp_ctx.get('their_price', 'N/A')}
- Tier: {comp_ctx.get('their_tier', 'N/A')}
- Feature gap: {comp_ctx.get('feature_gap', 'N/A')}
- Known features: {', '.join(known_features) if known_features else 'Not provided'}
"""

    brand_text = f"""
BRAND CONTEXT:
- Name: {BRAND['name']}
- Products: {', '.join(BRAND['products'])}
- Docs URL: {BRAND['url']}
"""

    user_prompt = f"{brief_text}{comp_text}{brand_text}\n\nPLATFORM: {platform}\n\nCONTENT TO REVIEW:\n{content_piece}\n\nReturn JSON only."
    return system_prompt, user_prompt


def call_groq(system: str, user: str, api_key: str, retries: int = 3, base_delay: float = 2.0) -> dict:
    body = {
        "model": GATE_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "max_tokens": 600,
        "response_format": {"type": "json_object"},
    }

    import time
    last_exception = None
    for attempt in range(retries):
        try:
            resp = requests.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=body,
                timeout=120,
            )
            resp.raise_for_status()
            result = resp.json()
            content = result["choices"][0]["message"]["content"]
            return json.loads(content)
        except requests.exceptions.HTTPError as e:
            last_exception = e
            if e.response is not None and e.response.status_code == 429:
                delay = base_delay * (2 ** attempt)
                _log(f"  Rate limited (429). Retrying in {delay}s...")
                time.sleep(delay)
                continue
            raise
        except Exception as e:
            last_exception = e
            delay = base_delay * (2 ** attempt)
            _log(f"  API call failed: {e}. Retrying in {delay}s...")
            time.sleep(delay)
    raise last_exception or RuntimeError("call_groq failed after retries")


def get_known_features(competitor_name: str, comp_data: dict) -> list[str]:
    if not competitor_name:
        return []
    for comp in comp_data.get("competitors", []):
        if comp.get("name") == competitor_name:
            return comp.get("features", [])
    return []


def check_piece(content_piece: str, brief: dict, comp_data: dict, api_key: str,
                platform: str = "article") -> list[str]:
    """Run quality gate on a single content piece. Returns list of flags."""
    comp_ctx = brief.get("competitor_context", {})
    competitor_name = comp_ctx.get("competitor_name", "")
    known_features = get_known_features(competitor_name, comp_data)

    system, user = build_gate_prompt(platform, content_piece, brief, comp_ctx, known_features)
    try:
        result = call_groq(system, user, api_key)
    except Exception as e:
        _log(f"  Gate API call failed: {e}")
        return [f"GATE_ERROR: {e}"]

    flags = []
    for h in result.get("hallucinations", []):
        claim = h.get("claim", "")
        reason = h.get("reason", "")
        if claim:
            flags.append(f"HALLUCINATION: '{claim}' — {reason}")

    for ce in result.get("competitor_errors", []):
        if ce:
            flags.append(f"COMPETITOR_ERROR: {ce}")

    # Deterministic placeholder checks for blog platform output
    if platform == "blog":
        text = json.dumps(content_piece) if isinstance(content_piece, (dict, list)) else str(content_piece)
        if "[PRODUCT_NAME]" not in text:
            flags.append("MISSING_PLACEHOLDER: [PRODUCT_NAME]")
        if "[SHOP_LINK]" not in text:
            flags.append("MISSING_PLACEHOLDER: [SHOP_LINK]")

    return flags


def log_quality_result(keyword: str, platform: str, flags: list[str]):
    """Append quality result to shared/quality_history.json for feedback loop."""
    SHARED_DIR.mkdir(exist_ok=True)
    history = []
    if QUALITY_HISTORY_PATH.exists():
        try:
            with open(QUALITY_HISTORY_PATH, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = []

    history.append({
        "opportunity_keyword": keyword,
        "platform": platform,
        "flags": flags,
        "flagged": bool(flags),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    with open(QUALITY_HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def run_gate_on_platform_content():
    """Run quality gate on the latest platform content output."""
    import time

    brief = load_enriched_brief()
    keyword = brief.get("opportunity", {}).get("keyword", "")

    content_path = SHARED_DIR / "platform_content_latest.json"
    if not content_path.exists():
        _log("[INFO] No platform content to check.")
        return {}

    with open(content_path, "r", encoding="utf-8") as f:
        content = json.load(f)

    api_key = get_groq_key()
    comp_data = load_competitor_analysis()

    all_flags = {}
    platforms = content.get("platforms", {})

    for platform, piece in platforms.items():
        text_to_check = ""
        if isinstance(piece, str):
            text_to_check = piece
        elif isinstance(piece, dict):
            text_to_check = json.dumps(piece)
        elif isinstance(piece, list):
            text_to_check = "\n".join(str(x) for x in piece)

        if not text_to_check.strip():
            continue

        _log(f"Checking {platform}...")
        flags = check_piece(text_to_check, brief, comp_data, api_key, platform=platform)
        all_flags[platform] = flags
        log_quality_result(keyword, platform, flags)

        # Small pause between gate calls to respect rate limits
        time.sleep(0.5)

        if flags:
            _log(f"  ⚠ {len(flags)} flag(s) on {platform}")
        else:
            _log(f"  ✓ {platform} passed")

    # Add flags to content output
    content["quality_flags"] = all_flags

    # Save updated content with flags
    with open(content_path, "w", encoding="utf-8") as f:
        json.dump(content, f, ensure_ascii=False, indent=2)

    return all_flags


def main():
    _log("=" * 55)
    _log("Quality Gate starting")
    _log("=" * 55)

    flags = run_gate_on_platform_content()
    total_flags = sum(len(v) for v in flags.values())
    _log(f"Total flags: {total_flags}")

    _log("=" * 55)
    _log("Quality Gate complete")


if __name__ == "__main__":
    main()
