"""
scripts/ai_enhancer.py — Use Groq LLM to generate human-readable insights.

Takes the structured signals (trending, rising, seasonal) and asks Groq to:
  1. Summarise the overall market mood
  2. Explain WHY the top trends are trending
  3. Generate actionable content ideas for each rising topic
  4. Flag seasonal opportunities right now

Requires: pip install groq
Set GROQ_API_KEY in trend_analyser/.env (or parent .env)
"""

import os
import json
from pathlib import Path
from datetime import datetime

try:
    from dotenv import load_dotenv
    # Try loading .env from the trend_analyser folder first, then project root
    _here = Path(__file__).parent.parent
    load_dotenv(_here / ".env")
    load_dotenv(_here.parent / ".env")
except ImportError:
    pass


def _get_client():
    try:
        from groq import Groq
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not set. Add it to trend_analyser/.env")
        return Groq(api_key=api_key)
    except ImportError:
        raise ImportError("groq package not installed. Run: pip install groq")


def _call_groq(client, system_prompt: str, user_prompt: str, model: str = "llama-3.3-70b-versatile") -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0.4,
        max_tokens=2000,
    )
    return response.choices[0].message.content.strip()


def _format_trending_for_prompt(trending: list[dict], top_n: int = 10) -> str:
    lines = []
    for kw in trending[:top_n]:
        sources = ", ".join(f"{s}:{c}" for s, c in kw.get("source_counts", {}).items())
        lines.append(
            f"- {kw['keyword']} (score={kw['score']:.0f}, "
            f"mentions={kw['mention_count']}, "
            f"trends_avg={kw.get('trends_avg', 0)}, "
            f"sources=[{sources}])"
        )
    return "\n".join(lines)


def _format_rising_for_prompt(rising: list[dict], top_n: int = 8) -> str:
    lines = []
    for t in rising[:top_n]:
        lines.append(
            f"- {t['keyword']} (velocity=+{t['velocity']:.0f}%, "
            f"signals={t.get('signals',[])})"
        )
    return "\n".join(lines)


def _format_seasonal_for_prompt(seasonal: list[dict]) -> str:
    peak_now = [s for s in seasonal if s.get("is_peak_now")]
    if not peak_now:
        return "No strong seasonal peaks detected for the current month."
    lines = []
    for s in peak_now[:5]:
        lines.append(
            f"- {s['keyword']} (peak months={s['peak_months']}, "
            f"trend={s['yoy_trend']}, strength={s['seasonality_strength']:.2f})"
        )
    return "\n".join(lines)


# ── Individual insight generators ────────────────────────────

def generate_market_summary(client, trending: list, rising: list, seasonal: list) -> dict:
    system = (
        "You are a market intelligence analyst specialising in electronics, "
        "single-board computers, solar energy, and home automation. "
        "Write concisely. No filler phrases. Use plain English."
    )
    user = f"""
Based on the following signals from the past week, write a 3-5 sentence market summary.
Focus on what's notable, surprising, or actionable.

TRENDING KEYWORDS:
{_format_trending_for_prompt(trending)}

RISING TOPICS (velocity):
{_format_rising_for_prompt(rising)}

SEASONAL PEAKS NOW:
{_format_seasonal_for_prompt(seasonal)}

Date: {datetime.now().strftime('%B %Y')}

Provide a concise summary paragraph.
"""
    summary = _call_groq(client, system, user)
    return {"type": "market_summary", "summary": summary}


def generate_content_ideas(client, trending: list, rising: list) -> dict:
    system = (
        "You are a content strategist for a tech blog covering SBCs, "
        "embedded hardware, solar, and smart home topics. "
        "Generate specific, actionable content ideas."
    )
    user = f"""
Based on these trending and rising topics, suggest 5 specific blog post or video ideas.
For each idea: give a title, 1-sentence description, and the target audience.

TRENDING:
{_format_trending_for_prompt(trending, top_n=8)}

RISING:
{_format_rising_for_prompt(rising, top_n=5)}

Format each idea as:
TITLE: ...
DESCRIPTION: ...
AUDIENCE: ...
"""
    raw = _call_groq(client, system, user)
    ideas = _parse_content_ideas(raw)
    return {"type": "content_ideas", "ideas": ideas, "raw": raw}


def _parse_content_ideas(raw: str) -> list[dict]:
    ideas = []
    current: dict = {}
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("TITLE:"):
            if current:
                ideas.append(current)
            current = {"title": line[6:].strip()}
        elif line.startswith("DESCRIPTION:") and current:
            current["description"] = line[12:].strip()
        elif line.startswith("AUDIENCE:") and current:
            current["audience"] = line[9:].strip()
    if current:
        ideas.append(current)
    return ideas


def generate_keyword_explanations(client, trending: list) -> dict:
    system = (
        "You are a hardware and electronics market analyst. "
        "Explain briefly WHY keywords are trending. Be specific. No waffle."
    )
    top5 = trending[:5]
    kw_list = "\n".join(f"- {k['keyword']}" for k in top5)
    user = f"""
For each of these trending keywords, give a 1-2 sentence explanation of WHY it's trending
right now in {datetime.now().strftime('%B %Y')}. Consider product releases, seasonal factors,
community events, or price changes.

KEYWORDS:
{kw_list}

Format:
KEYWORD: ...
WHY: ...
"""
    raw = _call_groq(client, system, user)
    explanations = _parse_explanations(raw)
    return {"type": "keyword_explanations", "explanations": explanations, "raw": raw}


def _parse_explanations(raw: str) -> list[dict]:
    items = []
    current: dict = {}
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("KEYWORD:"):
            if current:
                items.append(current)
            current = {"keyword": line[8:].strip()}
        elif line.startswith("WHY:") and current:
            current["explanation"] = line[4:].strip()
    if current:
        items.append(current)
    return items


# ── Master function ───────────────────────────────────────────

def enhance_with_ai(
    trending: list[dict],
    rising: list[dict],
    seasonal: list[dict],
) -> list[dict]:
    """
    Runs all AI enhancement steps. Returns list of insight dicts.
    Gracefully degrades if Groq is unavailable.
    """
    try:
        client = _get_client()
    except (ImportError, ValueError) as e:
        print(f"  ⚠ AI enhancement skipped: {e}")
        return []

    insights = []

    print("  → Generating market summary...")
    try:
        insights.append(generate_market_summary(client, trending, rising, seasonal))
    except Exception as e:
        print(f"  ⚠ Market summary failed: {e}")

    print("  → Generating content ideas...")
    try:
        insights.append(generate_content_ideas(client, trending, rising))
    except Exception as e:
        print(f"  ⚠ Content ideas failed: {e}")

    print("  → Generating keyword explanations...")
    try:
        insights.append(generate_keyword_explanations(client, trending))
    except Exception as e:
        print(f"  ⚠ Keyword explanations failed: {e}")

    return insights