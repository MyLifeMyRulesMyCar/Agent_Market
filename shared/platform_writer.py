"""
shared/platform_writer.py — Platform Writer

Takes the enriched brief and writes platform-specific content.
One focused Groq call per platform with platform-specific system prompts.

Model routing:
  Short-form (X, Facebook, LinkedIn) → llama-3.1-8b-instant
  Long-form (YouTube script, blog outline) → llama-3.3-70b-versatile

Usage:
    python platform_writer.py           # generate all platforms
    python platform_writer.py --platforms linkedin x  # generate selected
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
SEO_DIR = PROJECT_ROOT / "seo_agent"
CONTENT_WRITER_CONFIG = PROJECT_ROOT / "content_writer" / "config" / "content.yaml"

BRIEF_PATH = SHARED_DIR / "enriched_brief_latest.json"
SEO_PATH = SEO_DIR / "output" / "latest.json"
OUTPUT_DIR = SHARED_DIR
LATEST_PATH = SHARED_DIR / "platform_content_latest.json"

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

SHORT_FORM_MODEL = "llama-3.1-8b-instant"
LONG_FORM_MODEL = "llama-3.3-70b-versatile"

BRAND = {
    "name": "Elephantronics",
    "products": ["Purple Pi OH2", "Flamingo Edge Controller", "Moes Smart Devices"],
    "url": "docs.elephantronics.com",
    "tone": "practical, knowledgeable, community-friendly — not corporate or salesy",
    "audience": "makers, home automation enthusiasts, IoT developers, edge computing engineers",
}

PLATFORM_PROMPTS = {
    "linkedin": textwrap.dedent("""\
        You are writing a LinkedIn post for Elephantronics, a hardware company.
        Rules:
        - Lead with an insight or observation, not a product pitch
        - Professional but not boring
        - 1-2 paragraphs, 150-300 words
        - Include 2-3 relevant hashtags at the end
        - End with a clear CTA
    """),
    "x": textwrap.dedent("""\
        You are writing an X (Twitter) thread for Elephantronics, a hardware company.
        Rules:
        - Tweet 1 must be a hook that makes people want to read the thread
        - Each tweet max 280 characters
        - 5-7 tweets total
        - Punchy, no filler
        - End with a CTA in the last tweet
        - Include 1-2 relevant hashtags in the last tweet only
    """),
    "facebook": textwrap.dedent("""\
        You are writing a Facebook post for Elephantronics, a hardware company.
        Rules:
        - Write like you're posting in a maker/HA community group
        - Friendly, helpful tone
        - 1 paragraph, 100-250 words
        - Include 2-3 relevant hashtags
        - End with a question or CTA to drive comments
    """),
    "youtube": textwrap.dedent("""\
        You are writing a YouTube video script outline for Elephantronics, a hardware company.
        Rules:
        - Conversational, not formal
        - Practical tutorial or demo structure
        - Return a JSON object with: title, hook, sections (list of 5 strings), cta, description
        - Sections should be clear video segments
        - Description should be SEO-friendly with relevant keywords
    """),
    "blog": textwrap.dedent("""\
        You are writing a blog article outline for Elephantronics, a hardware company.
        Rules:
        - SEO-optimized title and meta description
        - Return a JSON object with: title, meta_description, sections (list of section names)
        - Sections should cover: intro, problem, solution, how-to, comparison, conclusion
        - Include placeholder tokens like [PRODUCT_NAME] and [SHOP_LINK] where appropriate
    """),
}

PLATFORM_MODELS = {
    "linkedin": SHORT_FORM_MODEL,
    "x": SHORT_FORM_MODEL,
    "facebook": SHORT_FORM_MODEL,
    "youtube": LONG_FORM_MODEL,
    "blog": LONG_FORM_MODEL,
}

PLATFORM_MAX_TOKENS = {
    "linkedin": 600,
    "x": 800,
    "facebook": 600,
    "youtube": 1200,
    "blog": 1000,
}


def _log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [platform_writer] {msg}"
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


def load_brief(path: Path = BRIEF_PATH) -> dict:
    if not path.exists():
        _log(f"[MISSING] {path}")
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_seo_hashtags(path: Path = SEO_PATH) -> list[str]:
    """Extract top 3 hashtags from SEO agent output."""
    if not path.exists():
        return ["#HomeAutomation", "#IoT", "#MakerLife"]
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Try to get keywords from clusters
    clusters = data.get("clusters", {})
    hashtags = []
    for cluster_name, keywords in clusters.items():
        if keywords:
            tag = f"#{cluster_name.replace('_', '').title()}"
            hashtags.append(tag)
        if len(hashtags) >= 3:
            break
    if not hashtags:
        hashtags = ["#HomeAutomation", "#IoT", "#MakerLife"]
    return hashtags[:3]


def build_platform_prompt(platform: str, brief: dict, hashtags: list[str]) -> tuple[str, str]:
    """Build system + user prompts for a specific platform."""
    system = PLATFORM_PROMPTS.get(platform, PLATFORM_PROMPTS["linkedin"])

    brief_data = brief.get("brief", {})
    comp_ctx = brief.get("competitor_context", {})
    opp = brief.get("opportunity", {})

    context_block = f"""CONTENT BRIEF:
- Title: {brief_data.get('title', '')}
- Angle: {brief_data.get('angle', '')}
- Hook: {brief_data.get('hook', '')}
- Key claim: {brief_data.get('key_claim', '')}
- CTA: {brief_data.get('cta', '')}
"""

    if comp_ctx and comp_ctx.get("competitor_name"):
        context_block += f"""
COMPETITOR CONTEXT:
- Competitor: {comp_ctx.get('competitor_name', '')}
- Their price: ${comp_ctx.get('their_price', 'N/A')}
- Feature gap: {comp_ctx.get('feature_gap', 'N/A')}
- Our advantage: {comp_ctx.get('our_advantage', '')}
"""

    context_block += f"""
BRAND:
- Name: {BRAND['name']}
- Products: {', '.join(BRAND['products'])}
- Tone: {BRAND['tone']}
- Docs: {BRAND['url']}

HASHTAGS: {', '.join(hashtags)}
"""

    user = f"Write the {platform} content now. Return ONLY the content."
    if platform in ("youtube", "blog"):
        user += " Return ONLY valid JSON."

    return system, context_block + "\n" + user


def call_groq(system: str, user: str, model: str, max_tokens: int, api_key: str,
              retries: int = 3, base_delay: float = 2.0) -> tuple[str, dict]:
    import time

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.6,
        "max_tokens": max_tokens,
    }

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
            usage = result.get("usage", {})
            return content, usage
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


def parse_platform_content(platform: str, raw: str) -> dict | str:
    """Parse Groq response for a specific platform."""
    raw = raw.strip()
    # Remove markdown fences
    if raw.startswith("```json"):
        raw = raw[7:].strip()
    if raw.startswith("```"):
        raw = raw[3:].strip()
    if raw.endswith("```"):
        raw = raw[:-3].strip()

    if platform in ("youtube", "blog"):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Fallback: wrap raw text in a basic structure
            if platform == "youtube":
                return {"title": "YouTube Video", "hook": raw[:200], "sections": [raw[:400]], "cta": "Subscribe for more", "description": ""}
            else:
                return {"title": "Blog Post", "meta_description": raw[:160], "sections": ["Introduction", "Body", "Conclusion"]}

    if platform == "x":
        # Split into tweets by newlines or numbers
        tweets = []
        for line in raw.split("\n"):
            line = line.strip()
            if line and not line.startswith(("Thread:", "---")):
                # Remove leading numbers like "1. " or "Tweet 1:"
                cleaned = line
                for prefix in ("1.", "2.", "3.", "4.", "5.", "6.", "7.", "Tweet 1:", "Tweet 2:", "Tweet 3:", "Tweet 4:", "Tweet 5:", "Tweet 6:", "Tweet 7:"):
                    if cleaned.startswith(prefix):
                        cleaned = cleaned[len(prefix):].strip()
                        break
                if cleaned:
                    tweets.append(cleaned)
        if not tweets:
            tweets = [raw[:280]]
        return tweets

    # linkedin, facebook — just return the text
    return raw


def generate_platform_content(platforms: list[str]) -> dict:
    brief = load_brief()
    if not brief:
        _log("[ABORT] No enriched brief found.")
        return {}

    hashtags = load_seo_hashtags()
    api_key = get_groq_key()

    result = {
        "topic": brief.get("brief", {}).get("title", ""),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "platforms": {},
        "_orchestration": {
            "brief_title": brief.get("brief", {}).get("title", ""),
            "competitor_context_injected": bool(brief.get("competitor_context")),
            "model_routing": {},
            "tokens_used": {},
        },
    }

    for platform in platforms:
        model = PLATFORM_MODELS.get(platform, SHORT_FORM_MODEL)
        max_tokens = PLATFORM_MAX_TOKENS.get(platform, 800)

        _log(f"Generating {platform} with {model}...")
        system, user = build_platform_prompt(platform, brief, hashtags)

        try:
            raw, usage = call_groq(system, user, model, max_tokens, api_key)
            parsed = parse_platform_content(platform, raw)
            result["platforms"][platform] = parsed
            result["_orchestration"]["model_routing"][platform] = model
            result["_orchestration"]["tokens_used"][platform] = usage
            _log(f"  {platform}: OK ({usage.get('total_tokens', '?')} tokens)")
        except Exception as e:
            _log(f"  {platform}: FAILED — {e}")
            result["platforms"][platform] = f"[ERROR: {e}]"

    # Add hashtags to result
    result["hashtags"] = {p: hashtags for p in platforms}

    return result


def write_output(content: dict):
    SHARED_DIR.mkdir(exist_ok=True)
    ts_file = f"platform_content_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    ts_path = OUTPUT_DIR / ts_file
    with open(ts_path, "w", encoding="utf-8") as f:
        json.dump(content, f, ensure_ascii=False, indent=2)
    _log(f"[SAVED]   {ts_path}")

    with open(LATEST_PATH, "w", encoding="utf-8") as f:
        json.dump(content, f, ensure_ascii=False, indent=2)
    _log(f"[SAVED]   {LATEST_PATH}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Platform Writer")
    parser.add_argument("--platforms", nargs="+", default=["linkedin", "x", "facebook", "youtube", "blog"],
                        help="Platforms to generate content for")
    args = parser.parse_args()

    _log("=" * 55)
    _log("Platform Writer starting")
    _log("=" * 55)

    content = generate_platform_content(args.platforms)
    if content:
        write_output(content)

    _log("=" * 55)
    _log("Platform Writer complete")


if __name__ == "__main__":
    main()
