"""
scripts/ai_enhancer.py — STEP 8: Use Groq to generate actionable insights.

Takes the structured signals (pain points, use cases, sentiment) and asks Groq to:
  1. Summarise the key customer behaviour patterns
  2. Identify the most critical unmet needs
  3. Suggest product/content opportunities
  4. Explain WHY users are struggling with each top pain point

Requires: pip install groq
Set GROQ_API_KEY in customer_behaviour/.env or parent project .env
"""

import os
import json
import re
from pathlib import Path
from datetime import datetime

try:
    from dotenv import load_dotenv
    _here = Path(__file__).parent.parent
    load_dotenv(_here / ".env")
    load_dotenv(_here.parent / ".env")
except ImportError:
    pass


_MARKDOWN_RE = re.compile(r"\*\*|\*")
_LIST_PREFIX_RE = re.compile(r"^\s*(?:\d+\.\s*|[-•\*]\s*)+")


def _normalize_line(line: str) -> str:
    """Strip markdown bold/italic, list bullets/numbers, and extra whitespace."""
    line = _LIST_PREFIX_RE.sub("", line)
    line = _MARKDOWN_RE.sub("", line)
    return line.strip()


def _get_client():
    try:
        from groq import Groq
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not set. Add it to customer_behaviour/.env")
        return Groq(api_key=api_key)
    except ImportError:
        raise ImportError("groq not installed. Run: pip install groq")


def _call_groq(client, system: str, user: str, model: str = "llama-3.3-70b-versatile") -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        temperature=0.3,
        max_tokens=2000,
    )
    return response.choices[0].message.content.strip()


# ── Input formatters ───────────────────────────────────────────

def _fmt_pain_points(pain_points: list) -> str:
    lines = []
    for pp in pain_points[:8]:
        lines.append(
            f"- {pp['label']} ({pp['mentions']} mentions, importance={pp['importance']:.0f}): "
            f"e.g. \"{pp['examples'][0] if pp['examples'] else ''}\" "
            f"[keywords: {', '.join(pp['keywords'][:4])}]"
        )
    return "\n".join(lines)


def _fmt_use_cases(use_cases: list) -> str:
    lines = []
    for uc in use_cases[:8]:
        lines.append(
            f"- {uc['case']} ({uc['mentions']} mentions): "
            f"e.g. \"{uc['examples'][0] if uc['examples'] else ''}\""
        )
    return "\n".join(lines)


def _fmt_sentiment(sentiment: dict) -> str:
    return (
        f"Positive: {sentiment.get('positive', 0)} ({sentiment.get('positive_pct', 0)}%), "
        f"Negative: {sentiment.get('negative', 0)} ({sentiment.get('negative_pct', 0)}%), "
        f"Neutral: {sentiment.get('neutral', 0)} ({sentiment.get('neutral_pct', 0)}%)"
    )


def _fmt_keywords(top_keywords: list) -> str:
    return ", ".join(f"{kw}({cnt})" for kw, cnt in top_keywords[:15])


# ── Individual insight generators ─────────────────────────────

def generate_behaviour_summary(client, pain_points, use_cases, sentiment, top_keywords) -> str:
    system = (
        "You are a customer behaviour analyst for a hardware tech company "
        "that makes single-board computers (SBCs) and IoT products. "
        "Write like a senior analyst: concise, specific, no filler."
    )
    user = f"""
Analyse these Reddit signals from the past week and write a 4-6 sentence behaviour summary.
Focus on: what users are struggling with, what they're building, and overall mood.

PAIN POINTS:
{_fmt_pain_points(pain_points)}

USE CASES:
{_fmt_use_cases(use_cases)}

SENTIMENT: {_fmt_sentiment(sentiment)}

TOP KEYWORDS: {_fmt_keywords(top_keywords)}

Date: {datetime.now().strftime('%B %Y')}

Write a concise customer behaviour summary.
"""
    return _call_groq(client, system, user)


def generate_unmet_needs(client, pain_points, use_cases) -> list[str]:
    system = (
        "You are a product strategist. Extract unmet customer needs from pain data. "
        "Be specific and actionable. No vague statements."
    )
    user = f"""
Based on these pain points and use cases, identify the top 5 UNMET NEEDS.
Each need should be a clear, specific statement about what customers lack or struggle with.

PAIN POINTS:
{_fmt_pain_points(pain_points)}

USE CASES:
{_fmt_use_cases(use_cases)}

Format each as:
NEED: [one sentence statement]

List exactly 5 unmet needs.
"""
    raw = _call_groq(client, system, user)
    needs = []
    for line in raw.splitlines():
        line = _normalize_line(line)
        if line.startswith("NEED:"):
            needs.append(line[5:].strip())
    return needs


def generate_opportunities(client, pain_points, use_cases, sentiment) -> list[dict]:
    system = (
        "You are a growth strategist for a hardware/SBC company. "
        "Identify content and product opportunities from community data."
    )
    user = f"""
Given these customer signals, suggest 5 specific opportunities (content, product, or support).
For each: give a title, type (content/product/support), and 1-sentence rationale.

PAIN POINTS:
{_fmt_pain_points(pain_points)}

USE CASES:
{_fmt_use_cases(use_cases)}

SENTIMENT: {_fmt_sentiment(sentiment)}

Format each as:
TITLE: ...
TYPE: content | product | support
RATIONALE: ...
"""
    raw = _call_groq(client, system, user)
    opportunities = []
    current = {}
    for line in raw.splitlines():
        line = _normalize_line(line)
        if line.startswith("TITLE:"):
            if current:
                opportunities.append(current)
            current = {"title": line[6:].strip()}
        elif line.startswith("TYPE:") and current:
            current["type"] = line[5:].strip()
        elif line.startswith("RATIONALE:") and current:
            current["rationale"] = line[10:].strip()
    if current:
        opportunities.append(current)
    return opportunities


def generate_pain_explanations(client, pain_points) -> list[dict]:
    system = (
        "You are a UX researcher analysing why hardware users struggle with specific issues. "
        "Be precise. Focus on root causes, not symptoms."
    )
    top3 = pain_points[:3]
    pp_list = "\n".join(f"- {pp['label']}: {', '.join(pp['examples'][:2])}" for pp in top3)

    user = f"""
For each of these top pain points, explain in 2-3 sentences WHY users struggle with this.
What is the root cause? Is it a documentation gap, hardware limitation, software bug, or complexity?

PAIN POINTS:
{pp_list}

Format:
PAIN: [name]
ROOT CAUSE: [explanation]
"""
    raw = _call_groq(client, system, user)
    explanations = []
    current = {}
    for line in raw.splitlines():
        line = _normalize_line(line)
        if line.startswith("PAIN:"):
            if current:
                explanations.append(current)
            current = {"pain": line[5:].strip()}
        elif line.startswith("ROOT CAUSE:") and current:
            current["root_cause"] = line[11:].strip()
    if current:
        explanations.append(current)
    return explanations


# ── Master function ────────────────────────────────────────────

def enhance_with_groq(
    pain_points: list,
    use_cases: list,
    sentiment: dict,
    top_keywords: list,
) -> list[str]:
    """
    Run all Groq enhancement steps.
    Returns a flat list of insight strings (for simple storage + display).
    Also returns structured data embedded in the list via special dicts.
    """
    try:
        client = _get_client()
    except (ImportError, ValueError) as e:
        print(f"  ⚠ Groq skipped: {e}")
        return []

    insights = []

    print("  → Generating behaviour summary...")
    try:
        summary = generate_behaviour_summary(client, pain_points, use_cases, sentiment, top_keywords)
        insights.append({"type": "behaviour_summary", "summary": summary})
        # Also print it
        print(f"     {summary[:200]}...")
    except Exception as e:
        print(f"  ⚠ Summary failed: {e}")

    print("  → Identifying unmet needs...")
    try:
        needs = generate_unmet_needs(client, pain_points, use_cases)
        insights.append({"type": "unmet_needs", "needs": needs})
    except Exception as e:
        print(f"  ⚠ Unmet needs failed: {e}")

    print("  → Finding opportunities...")
    try:
        opportunities = generate_opportunities(client, pain_points, use_cases, sentiment)
        insights.append({"type": "opportunities", "opportunities": opportunities})
    except Exception as e:
        print(f"  ⚠ Opportunities failed: {e}")

    print("  → Explaining root causes...")
    try:
        explanations = generate_pain_explanations(client, pain_points)
        insights.append({"type": "pain_explanations", "explanations": explanations})
    except Exception as e:
        print(f"  ⚠ Pain explanations failed: {e}")

    return insights