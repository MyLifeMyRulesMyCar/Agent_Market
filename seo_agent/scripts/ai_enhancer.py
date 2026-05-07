"""
ai_enhancer.py — Groq-powered content generation.
Same pattern as competitor_analysis and customer_behaviour agents.
"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    _here = Path(__file__).parent.parent
    load_dotenv(_here / ".env")
    load_dotenv(_here.parent / ".env")
except ImportError:
    pass


def _get_client():
    from groq import Groq
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise ValueError("GROQ_API_KEY not set")
    return Groq(api_key=key)


def _call(client, system: str, user: str) -> str:
    r = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "system", "content": system},
                  {"role": "user",   "content": user}],
        temperature=0.4, max_tokens=2000,
    )
    return r.choices[0].message.content.strip()


def _fmt_top(scored: list[dict], n: int = 12) -> str:
    lines = []
    for kw in scored[:n]:
        lines.append(
            f"- [{kw['intent']}] {kw['keyword']} "
            f"(score={kw['score']:.1f}, "
            f"trends={kw['trends_avg']}, reddit={kw['reddit_count']})"
        )
    return "\n".join(lines)


import re

_MARKDOWN_RE = re.compile(r"\*\*|\*")
_LIST_PREFIX_RE = re.compile(r"^\s*(?:\d+\.\s*|[-•\*]\s*)+")


def _normalize_line(line: str) -> str:
    """Strip markdown bold/italic, list bullets/numbers, and extra whitespace."""
    line = _LIST_PREFIX_RE.sub("", line)
    line = _MARKDOWN_RE.sub("", line)
    return line.strip()


def generate_seo_titles(client, scored: list[dict]) -> dict:
    system = (
        "You are an SEO content strategist for a tech blog covering single-board "
        "computers, IoT, solar energy, and home automation. Write clickable, "
        "search-optimised titles. No clickbait. Specific and accurate."
    )
    user = f"""
Given these trending keywords with their intent classification, generate 8 SEO-optimised
blog post titles. Mix intents: some how-to, some comparison, some troubleshooting.

KEYWORDS:
{_fmt_top(scored)}

Format each as:
TITLE: ...
TARGET KEYWORD: ...
INTENT: ...
"""
    raw = _call(client, system, user)
    titles = []
    current = {}
    for line in raw.splitlines():
        line = _normalize_line(line)
        if line.startswith("TITLE:"):
            if current:
                titles.append(current)
            current = {"title": line[6:].strip()}
        elif line.startswith("TARGET KEYWORD:") and current:
            current["target_keyword"] = line[15:].strip()
        elif line.startswith("INTENT:") and current:
            current["intent"] = line[7:].strip()
    if current:
        titles.append(current)
    return {"type": "seo_titles", "titles": titles}


def generate_content_ideas(client, scored: list[dict], clusters: dict) -> dict:
    system = (
        "You are a content strategist. Generate specific, actionable content ideas "
        "for a hardware tech blog. Include YouTube video ideas too."
    )
    cluster_summary = "\n".join(
        f"- {k}: {', '.join(i['keyword'] for i in v[:3])}"
        for k, v in list(clusters.items())[:6]
    )
    user = f"""
Generate 6 content ideas (mix of blog posts and YouTube videos) based on these
keyword clusters. Each idea should target a specific cluster's pain or interest.

CLUSTERS:
{cluster_summary}

Format:
FORMAT: blog | youtube
TITLE: ...
CLUSTER: ...
DESCRIPTION: ...
"""
    raw = _call(client, system, user)
    ideas = []
    current = {}
    for line in raw.splitlines():
        line = _normalize_line(line)
        if line.startswith("FORMAT:"):
            if current:
                ideas.append(current)
            current = {"format": line[7:].strip()}
        elif line.startswith("TITLE:") and current:
            current["title"] = line[6:].strip()
        elif line.startswith("CLUSTER:") and current:
            current["cluster"] = line[8:].strip()
        elif line.startswith("DESCRIPTION:") and current:
            current["description"] = line[12:].strip()
    if current:
        ideas.append(current)
    return {"type": "content_ideas", "ideas": ideas}


def enhance(scored: list[dict], clusters: dict) -> list[dict]:
    try:
        client = _get_client()
    except Exception as e:
        print(f"  ⚠ AI skipped: {e}")
        return []

    insights = []
    print("  → Generating SEO titles...")
    try:
        insights.append(generate_seo_titles(client, scored))
    except Exception as e:
        print(f"  ⚠ titles failed: {e}")

    print("  → Generating content ideas...")
    try:
        insights.append(generate_content_ideas(client, scored, clusters))
    except Exception as e:
        print(f"  ⚠ ideas failed: {e}")

    return insights