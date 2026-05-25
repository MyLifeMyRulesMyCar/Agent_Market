"""
social_media_generator/server.py
Flask backend for the Social Media Content Generator.

Holds GROQ_API_KEY securely — never exposed to the browser.
Accepts context from the frontend and returns platform-specific posts.

Usage:
    cd Marketing_agents/social_media_generator
    python server.py

Then open:
    http://localhost:5050
"""

import os
import json
import re
from pathlib import Path
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
from tracker import get_tracker_summary, load_log, save_log, LOG_PATH

# Load .env from this folder, then project root
_HERE = Path(__file__).parent
load_dotenv(_HERE / ".env")
load_dotenv(_HERE.parent / ".env")

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)

PROJECT_ROOT = _HERE.parent


# ── Groq client ────────────────────────────────────────────────

def get_groq_client():
    try:
        from groq import Groq
        key = os.getenv("GROQ_API_KEY")
        if not key:
            raise ValueError("GROQ_API_KEY not set in .env")
        return Groq(api_key=key)
    except ImportError:
        raise ImportError("groq not installed — run: pip install groq")


def call_groq(system: str, user: str, max_tokens: int = 3000) -> str:
    client = get_groq_client()
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        temperature=0.6,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()


# ── Prompt builders ────────────────────────────────────────────

BRAND = {
    "name":     "Elephantronics",
    "products": ["Purple Pi OH2", "Flamingo Edge Controller", "Moes Smart Devices"],
    "url":      "docs.elephantronics.com",
    "tone":     "practical, knowledgeable, community-friendly — not corporate or salesy",
    "audience": "makers, home automation enthusiasts, IoT developers, edge computing engineers",
}


def fmt_context(ctx: dict) -> str:
    """Format intelligence context into a compact prompt section."""
    lines = []

    if ctx.get("top_keywords"):
        kws = [k["keyword"] for k in ctx["top_keywords"][:5]]
        lines.append(f"TOP SEO KEYWORDS THIS WEEK: {', '.join(kws)}")

    if ctx.get("pain_points"):
        pp = ctx["pain_points"][0]
        lines.append(f"TOP COMMUNITY PAIN POINT: {pp.get('label','')} ({pp.get('mentions',0)} mentions)")
        ex = (pp.get("examples") or [])[:1]
        if ex:
            lines.append(f'  Real quote: "{ex[0][:120]}"')

    if ctx.get("rising_topics"):
        rt = ctx["rising_topics"][0]
        lines.append(f"RISING TOPIC: {rt.get('keyword','')} (+{round(rt.get('velocity',0))}% velocity)")

    if ctx.get("competitor_name"):
        lines.append(f"MAIN COMPETITOR TO REFERENCE: {ctx['competitor_name']}")

    return "\n".join(lines) if lines else "No additional context provided."


def build_system_prompt() -> str:
    return f"""You are a social media content writer for {BRAND['name']}, a hardware company \
making single-board computers (SBCs) and smart home devices.

BRAND VOICE: {BRAND['tone']}
TARGET AUDIENCE: {BRAND['audience']}
PRODUCTS: {', '.join(BRAND['products'])}
DOCS: {BRAND['url']}

RULES:
- Never use generic AI filler phrases ("In today's digital world", "It's worth noting", etc.)
- Be specific and technical — this audience respects accuracy
- Use the real product name: Purple Pi OH2, Flamingo Edge Controller
- Include the docs link {BRAND['url']} where relevant
- Hashtags should be relevant and specific, not generic spam
- YouTube scripts should be conversational, not formal
- LinkedIn should be professional but not boring
- X/Twitter threads should be punchy — each tweet max 280 chars
- Facebook should feel like a community post, not an ad
- Always end with a clear call to action

OUTPUT FORMAT: Return ONLY a valid JSON object. No markdown fences. No preamble.
The JSON must have exactly these keys:
{{
  "linkedin": "...",
  "twitter_thread": ["tweet1", "tweet2", "tweet3", "tweet4", "tweet5"],
  "facebook": "...",
  "youtube_script": {{
    "title": "...",
    "hook": "...",
    "sections": ["section1", "section2", "section3", "section4", "section5"],
    "cta": "...",
    "description": "..."
  }},
  "hashtags": {{
    "linkedin": ["#tag1", "#tag2"],
    "twitter":  ["#tag1", "#tag2"],
    "facebook": ["#tag1", "#tag2"],
    "youtube":  ["#tag1", "#tag2"]
  }},
  "blog_outline": {{
    "title": "...",
    "meta_description": "...",
    "sections": ["intro", "section2", "section3", "conclusion"]
  }}
}}"""


def build_user_prompt(topic: str, platforms: list, tone_override: str,
                      ctx: dict, custom_notes: str) -> str:
    platform_str = ", ".join(platforms) if platforms else "all platforms"
    tone = tone_override or BRAND["tone"]

    return f"""Create social media content for the following topic.

TOPIC: {topic}
PLATFORMS REQUESTED: {platform_str}
TONE: {tone}
{f"ADDITIONAL NOTES: {custom_notes}" if custom_notes else ""}

INTELLIGENCE CONTEXT (use this to make content timely and relevant):
{fmt_context(ctx)}

Generate all platform content for this topic. Make each piece platform-native — \
what works on LinkedIn reads differently than an X thread or a YouTube hook.

For the YouTube script, structure it as a practical tutorial or demo video.
For LinkedIn, lead with an insight or observation, not a product pitch.
For X/Twitter, make tweet 1 the hook that makes people want to read the thread.
For Facebook, write like you're posting in a maker/HA community group.

Return only the JSON object. No markdown. No extra text."""


# ── Routes ─────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/generate", methods=["POST"])
def generate():
    try:
        body = request.get_json()

        topic          = body.get("topic", "").strip()
        platforms      = body.get("platforms", ["linkedin", "twitter", "facebook", "youtube"])
        tone_override  = body.get("tone", "")
        custom_notes   = body.get("notes", "")
        ctx            = body.get("context", {})

        if not topic:
            return jsonify({"error": "Topic is required"}), 400

        system = build_system_prompt()
        user   = build_user_prompt(topic, platforms, tone_override, ctx, custom_notes)

        raw = call_groq(system, user, max_tokens=3500)

        # Strip markdown fences if model wrapped the response
        raw = re.sub(r"^```json\s*", "", raw.strip())
        raw = re.sub(r"```$", "", raw.strip())

        result = json.loads(raw)
        result["topic"]       = topic
        result["generated_at"] = datetime.now().isoformat()

        return jsonify({"ok": True, "data": result})

    except json.JSONDecodeError as e:
        return jsonify({"error": f"Groq returned malformed JSON: {e}", "raw": raw}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/context", methods=["GET"])
def get_context():
    """Load agent outputs and return the context the frontend needs."""
    def load(path):
        p = PROJECT_ROOT / path
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None

    seo        = load("seo_agent/output/latest.json")
    behaviour  = load("customer_behaviour/output/latest.json")
    trends     = load("trend_analyser/output/latest.json")
    competitor = load("competitor_analysis/output/latest.json")
    snapshot   = load("shared/intelligence_snapshot.json")

    # Extract AI titles from SEO agent
    ai_titles = []
    if seo and seo.get("insights"):
        for ins in seo["insights"]:
            if ins.get("type") == "seo_titles":
                ai_titles = ins.get("titles", [])
                break

    # Top keywords
    top_kws = (seo or {}).get("top_keywords", [])[:8]

    # Pain points
    pain_points = (behaviour or {}).get("pain_points", [])[:5]

    # Rising topics
    rising = (trends or {}).get("rising_topics", [])[:5]

    # Top competitors
    comps = (competitor or {}).get("competitors", [])[:5]
    sw    = (competitor or {}).get("sw_analysis", {})

    # Executive summary
    summary = (snapshot or {}).get("executive_summary", "")
    if not summary and trends and trends.get("insights"):
        for ins in trends["insights"]:
            if ins.get("type") == "market_summary":
                summary = ins.get("summary", "")
                break

    # Suggested topics (from AI titles + top keywords)
    suggested_topics = []
    for t in ai_titles[:6]:
        suggested_topics.append({
            "title":   t.get("title", ""),
            "keyword": t.get("target_keyword", ""),
            "intent":  t.get("intent", ""),
        })

    # Always include Purple Pi OH2 + HA as a suggested topic
    ha_exists = any("home assistant" in (t.get("title","")).lower() and "purple" in (t.get("title","")).lower()
                    for t in suggested_topics)
    if not ha_exists:
        suggested_topics.insert(0, {
            "title":   "Purple Pi OH2 + Home Assistant: Complete Setup Guide",
            "keyword": "purple pi home assistant",
            "intent":  "how-to",
        })

    return jsonify({
        "ok": True,
        "data": {
            "top_keywords":      top_kws,
            "pain_points":       pain_points,
            "rising_topics":     rising,
            "competitors":       comps,
            "sw_analysis":       sw,
            "ai_titles":         ai_titles,
            "suggested_topics":  suggested_topics,
            "executive_summary": summary,
            "sources": {
                "seo":        bool(seo),
                "behaviour":  bool(behaviour),
                "trends":     bool(trends),
                "competitor": bool(competitor),
                "snapshot":   bool(snapshot),
            }
        }
    })


@app.route("/health", methods=["GET"])
def health():
    groq_ok = bool(os.getenv("GROQ_API_KEY"))
    return jsonify({
        "ok":      groq_ok,
        "groq":    groq_ok,
        "time":    datetime.now().isoformat(),
    })


@app.route("/tracker/log", methods=["POST"])
def tracker_log():
    """Log a published post from the frontend."""
    try:
        entry = request.get_json()
        if not entry.get("topic") or not entry.get("platform"):
            return jsonify({"error": "topic and platform are required"}), 400
        entry["logged_at"] = datetime.now().isoformat()
        log = load_log()
        log.append(entry)
        save_log(log)
        return jsonify({"ok": True, "total": len(log)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/tracker/summary", methods=["GET"])
def tracker_summary():
    """Return post history summary for the frontend dashboard."""
    try:
        summary = get_tracker_summary()
        entries = load_log()
        # Return last 20 posts for display
        recent = sorted(entries, key=lambda x: x.get("posted_date",""), reverse=True)[:20]
        return jsonify({"ok": True, "summary": summary, "recent": recent})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/tracker/analyse", methods=["POST"])
def tracker_analyse():
    """Run Groq analysis on post history and return result."""
    try:
        from tracker import format_log_for_analysis

        entries = load_log()
        if not entries:
            return jsonify({"error": "No posts logged yet. Add posts via /tracker/log first."}), 400

        log_text = format_log_for_analysis(entries)

        system = """You are a social media performance analyst for Elephantronics, a hardware 
company making single-board computers (Purple Pi OH2) and smart home devices 
(Flamingo Edge Controller, Moes devices). 
Analyse the post performance data and give specific, actionable insights.
Be direct. Use numbers where available. No filler phrases."""

        user = f"""Analyse this social media post history for Elephantronics:

POST LOG:
{log_text}

Answer these 6 questions clearly:
1. Which platform is performing best and why?
2. Which content type gets the most engagement?
3. What topics resonate most with the audience?
4. Which platform/content combination should they do MORE of?
5. What should they STOP or reduce?
6. Three specific content recommendations for next week based on what works.

Be specific. Reference actual post topics and metrics where available.
Format with numbered sections."""

        analysis = call_groq(system, user, max_tokens=2000)

        # Save to file as well
        out_path = _HERE / "data" / f"analysis_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps({"analysed_at": datetime.now().isoformat(),
                        "posts_analysed": len(entries),
                        "analysis": analysis}, indent=2),
            encoding="utf-8"
        )

        return jsonify({"ok": True, "analysis": analysis, "posts_analysed": len(entries)})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Main ───────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n🎯 Social Media Generator")
    print("=" * 42)
    print(f"   Project root : {PROJECT_ROOT}")
    print(f"   GROQ_API_KEY : {'✓ found' if os.getenv('GROQ_API_KEY') else '✗ NOT SET — add to .env'}")
    print(f"   Listening on : http://localhost:5050")
    print("=" * 42)
    print("\n   Open http://localhost:5050 in your browser\n")
    app.run(host="0.0.0.0", port=5050, debug=False)