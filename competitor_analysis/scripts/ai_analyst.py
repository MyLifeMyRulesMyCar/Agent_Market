"""
scripts/ai_analyst.py — Run strategic analysis via Groq LLM.

Generates:
  1. strategic_summary     — overall competitive landscape
  2. threat_assessment     — ranked threat analysis per competitor
  3. positioning_advice    — how to position my products
  4. opportunity_signals   — gaps in competitor offerings we can exploit
  5. rss_news_digest       — summary of recent RSS competitor news
"""

import os
import json
from pathlib import Path
from datetime import datetime

try:
    from dotenv import load_dotenv
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
            raise ValueError("GROQ_API_KEY not set. Add it to competitor_analysis/.env")
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


# ── Input formatters ──────────────────────────────────────────

def _fmt_my_products(my_products: list[dict]) -> str:
    lines = []
    for p in my_products:
        feats = ", ".join(p.get("key_features", [])[:6])
        lines.append(f"- {p['name']} (${p.get('price_usd','?')}): {feats}")
    return "\n".join(lines)


def _fmt_competitors(competitor_profiles: dict, sw: dict, pricing: dict) -> str:
    lines = []
    for name, profile in competitor_profiles.items():
        price   = pricing.get(name, {}).get("price_usd", "?")
        tier    = pricing.get(name, {}).get("tier", "?")
        threat  = sw.get(name, {}).get("threat_score", 0)
        feats   = profile.get("extracted_info", {}).get("features", [])
        known   = profile.get("known_features", [])
        all_f   = list(set(feats + known))[:6]
        lines.append(
            f"- {name} (${price}, {tier} tier, threat={threat:.1f}/10): "
            f"{', '.join(all_f)}"
        )
    return "\n".join(lines)


def _fmt_feature_gaps(feature_matrix: dict) -> str:
    gaps = feature_matrix.get("feature_gaps", {})
    if not gaps:
        return "No significant feature gaps detected."
    lines = []
    for feat, comps in list(gaps.items())[:8]:
        lines.append(f"- {feat} → missing in our products, but {', '.join(comps[:3])} have it")
    return "\n".join(lines)


def _fmt_advantages(feature_matrix: dict) -> str:
    adv = feature_matrix.get("feature_advantages", {})
    if not adv:
        return "No clear feature advantages detected."
    lines = []
    for feat, comps in list(adv.items())[:8]:
        lines.append(f"- {feat} → we have it, but {', '.join(comps[:3])} lack it")
    return "\n".join(lines)


def _fmt_rss_news(rss_data: dict) -> str:
    lines = []
    for comp_name, articles in rss_data.get("by_competitor", {}).items():
        if articles:
            for a in articles[:2]:
                lines.append(f"- [{comp_name}] {a['title'][:100]} ({a.get('published','')})")
    if not lines:
        return "No recent RSS news found for tracked competitors."
    return "\n".join(lines)


# ── Individual generators ─────────────────────────────────────

def generate_strategic_summary(client, my_products, competitor_profiles, sw, pricing, feature_matrix) -> dict:
    system = (
        "You are a senior competitive intelligence analyst specialising in "
        "single-board computers and embedded hardware. "
        "Write like a professional analyst: concise, specific, actionable. No filler."
    )
    user = f"""
Analyse this competitive landscape and write a 4-6 sentence strategic summary.
Focus on: key threats, our positioning, and what we should do next.

OUR PRODUCTS:
{_fmt_my_products(my_products)}

COMPETITORS (sorted by threat):
{_fmt_competitors(competitor_profiles, sw, pricing)}

FEATURE GAPS (competitors have, we don't):
{_fmt_feature_gaps(feature_matrix)}

OUR ADVANTAGES (we have, competitors lack):
{_fmt_advantages(feature_matrix)}

Date: {datetime.now().strftime('%B %Y')}

Write the strategic summary.
"""
    summary = _call_groq(client, system, user)
    return {"type": "strategic_summary", "summary": summary}


def generate_threat_assessment(client, sw, pricing) -> dict:
    system = "You are a competitive intelligence analyst. Be direct and ranked."
    competitors = sorted(
        [(n, d) for n, d in sw.items() if not d.get("is_mine")],
        key=lambda x: x[1].get("threat_score", 0), reverse=True
    )
    comp_list = "\n".join(
        f"- {n}: threat={d.get('threat_score',0):.1f}/10, "
        f"strengths={len(d.get('strengths',[]))}, "
        f"weaknesses={len(d.get('weaknesses',[]))}, "
        f"price=${pricing.get(n,{}).get('price_usd','?')}"
        for n, d in competitors[:5]
    )
    user = f"""
Rank these competitors by threat level and explain WHY each is a threat or not.
Give 1-2 sentences per competitor.

COMPETITORS:
{comp_list}

Format:
RANK: [1-5]
COMPETITOR: [name]
THREAT LEVEL: High/Medium/Low
REASON: [why]
"""
    raw = _call_groq(client, system, user)
    assessments = _parse_threat_assessment(raw)
    return {"type": "threat_assessment", "assessments": assessments, "raw": raw}


def _parse_threat_assessment(raw: str) -> list[dict]:
    results = []
    current = {}
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("RANK:"):
            if current:
                results.append(current)
            current = {"rank": line[5:].strip()}
        elif line.startswith("COMPETITOR:") and current:
            current["competitor"] = line[11:].strip()
        elif line.startswith("THREAT LEVEL:") and current:
            current["threat_level"] = line[13:].strip()
        elif line.startswith("REASON:") and current:
            current["reason"] = line[7:].strip()
    if current:
        results.append(current)
    return results


def generate_positioning_advice(client, my_products, feature_matrix, pricing) -> dict:
    system = (
        "You are a product marketing strategist for a hardware company. "
        "Give specific, actionable advice."
    )
    user = f"""
Based on this competitive data, give positioning and go-to-market advice for our products.
Give 3-5 specific recommendations.

OUR PRODUCTS:
{_fmt_my_products(my_products)}

FEATURE ADVANTAGES WE HAVE:
{_fmt_advantages(feature_matrix)}

FEATURE GAPS WE NEED TO ADDRESS:
{_fmt_feature_gaps(feature_matrix)}

Format each recommendation as:
TITLE: ...
ACTION: ...
PRIORITY: High/Medium/Low
"""
    raw = _call_groq(client, system, user)
    recommendations = _parse_recommendations(raw)
    return {"type": "positioning_advice", "recommendations": recommendations, "raw": raw}


def _parse_recommendations(raw: str) -> list[dict]:
    results = []
    current = {}
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("TITLE:"):
            if current:
                results.append(current)
            current = {"title": line[6:].strip()}
        elif line.startswith("ACTION:") and current:
            current["action"] = line[7:].strip()
        elif line.startswith("PRIORITY:") and current:
            current["priority"] = line[9:].strip()
    if current:
        results.append(current)
    return results


def generate_opportunity_signals(client, feature_matrix, rss_data) -> dict:
    system = "You are a product strategist. Find market opportunities in competitor weaknesses."
    user = f"""
Identify 3-5 market opportunities we can exploit based on competitor gaps.

RECENT COMPETITOR NEWS:
{_fmt_rss_news(rss_data)}

FEATURES COMPETITORS LACK (that we have or could build):
{_fmt_advantages(feature_matrix)}

FEATURE GAPS IN THE MARKET:
{_fmt_feature_gaps(feature_matrix)}

Format:
OPPORTUNITY: [title]
RATIONALE: [why this is an opportunity]
ACTION: [what to do]
"""
    raw = _call_groq(client, system, user)
    opportunities = _parse_opportunities(raw)
    return {"type": "opportunity_signals", "opportunities": opportunities, "raw": raw}


def _parse_opportunities(raw: str) -> list[dict]:
    results = []
    current = {}
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("OPPORTUNITY:"):
            if current:
                results.append(current)
            current = {"title": line[12:].strip()}
        elif line.startswith("RATIONALE:") and current:
            current["rationale"] = line[10:].strip()
        elif line.startswith("ACTION:") and current:
            current["action"] = line[7:].strip()
    if current:
        results.append(current)
    return results


def generate_rss_news_digest(client, rss_data) -> dict:
    news_text = _fmt_rss_news(rss_data)
    if "No recent" in news_text:
        return {"type": "rss_news_digest", "digest": "No recent competitor news found in RSS feeds."}

    system = "You are a tech news analyst. Summarise competitor news concisely."
    user = f"""
Summarise these recent competitor news items in 3-4 sentences.
Highlight product launches, pricing changes, or notable community reactions.

NEWS:
{news_text}
"""
    digest = _call_groq(client, system, user)
    return {"type": "rss_news_digest", "digest": digest}


# ── Master function ───────────────────────────────────────────

def run_ai_analysis(
    my_products: list[dict],
    competitor_profiles: dict,
    sw_analysis: dict,
    pricing_analysis: dict,
    feature_matrix: dict,
    rss_data: dict,
) -> list[dict]:
    """
    Run all AI analysis steps. Returns list of insight dicts.
    Gracefully skips if Groq is unavailable.
    """
    try:
        client = _get_client()
    except (ImportError, ValueError) as e:
        print(f"  ⚠  AI skipped: {e}")
        return []

    insights = []

    steps = [
        ("Strategic summary",     lambda: generate_strategic_summary(client, my_products, competitor_profiles, sw_analysis, pricing_analysis, feature_matrix)),
        ("Threat assessment",     lambda: generate_threat_assessment(client, sw_analysis, pricing_analysis)),
        ("Positioning advice",    lambda: generate_positioning_advice(client, my_products, feature_matrix, pricing_analysis)),
        ("Opportunity signals",   lambda: generate_opportunity_signals(client, feature_matrix, rss_data)),
        ("RSS news digest",       lambda: generate_rss_news_digest(client, rss_data)),
    ]

    for label, fn in steps:
        print(f"  → {label}...")
        try:
            result = fn()
            insights.append(result)
        except Exception as e:
            print(f"  ⚠  {label} failed: {e}")

    return insights