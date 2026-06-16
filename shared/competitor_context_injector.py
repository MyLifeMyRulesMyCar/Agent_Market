"""
shared/competitor_context_injector.py — Competitor Context Injector

Reads shared/content_brief_latest.json, enriches it with real competitor
data from competitor_analysis/output/latest.json and the vector DB,
then writes shared/enriched_brief_{timestamp}.json.

Pure Python + ChromaDB + SQLite — no LLM call.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
SHARED_DIR   = PROJECT_ROOT / "shared"
COMPETITOR_DIR = PROJECT_ROOT / "competitor_analysis"
RSS_DB_PATH = PROJECT_ROOT / "RSS_Feeder" / "db" / "news.db"
VECTOR_DB_PATH = PROJECT_ROOT / "vector_db" / "db"

BRIEF_PATH = SHARED_DIR / "content_brief_latest.json"
COMPETITOR_JSON_PATH = COMPETITOR_DIR / "output" / "latest.json"
OUTPUT_DIR = SHARED_DIR
LATEST_PATH = SHARED_DIR / "enriched_brief_latest.json"


def _log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [competitor_context_injector] {msg}"
    safe = line.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
           sys.stdout.encoding or "utf-8", errors="replace")
    print(safe)


def load_brief(path: Path = BRIEF_PATH) -> dict:
    if not path.exists():
        _log(f"[MISSING] {path}")
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    _log(f"[LOADED]  brief: {path.name}")
    return data


def load_competitor_analysis(path: Path = COMPETITOR_JSON_PATH) -> dict:
    if not path.exists():
        _log(f"[MISSING] {path}")
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    _log(f"[LOADED]  competitor_analysis: {len(json.dumps(data))} chars")
    return data


def find_competitor_in_brief(brief: dict) -> str:
    """Extract competitor name from brief or opportunity."""
    opp = brief.get("opportunity", {})
    competitor = opp.get("competitor_link", "")
    if competitor:
        return competitor

    # If no direct competitor link, try to infer from brief title/angle
    title = brief.get("brief", {}).get("title", "").lower()
    angle = brief.get("brief", {}).get("angle", "").lower()

    # Load competitor names from analysis
    comp_data = load_competitor_analysis()
    competitors = comp_data.get("competitors", [])
    for comp in competitors:
        name = comp.get("name", "").lower()
        if name and (name in title or name in angle):
            return comp.get("name", "")

    return ""


def get_competitor_details(competitor_name: str, comp_data: dict) -> dict:
    """Extract pricing, features, and gaps for a specific competitor."""
    if not competitor_name:
        return {}

    pricing = comp_data.get("pricing_analysis", {}).get(competitor_name, {})
    feature_matrix = comp_data.get("feature_matrix", {})
    sw = comp_data.get("sw_analysis", {}).get(competitor_name, {})

    # Find feature gaps for this competitor
    gaps = []
    for feature, comps in feature_matrix.get("feature_gaps", {}).items():
        if competitor_name in comps:
            gaps.append(feature)

    # Find their known features
    competitors = comp_data.get("competitors", [])
    their_features = []
    for comp in competitors:
        if comp.get("name") == competitor_name:
            their_features = comp.get("features", [])
            break

    return {
        "competitor_name": competitor_name,
        "their_price": pricing.get("price_usd"),
        "their_tier": pricing.get("tier"),
        "their_features": their_features,
        "feature_gaps": gaps,
        "threat_score": sw.get("threat_score"),
        "threat_confidence": sw.get("threat_confidence"),
    }


def query_rss_for_competitor(competitor_name: str, days: int = 30) -> list[str]:
    """Query RSS Feeder DB for recent mentions of this competitor."""
    if not RSS_DB_PATH.exists() or not competitor_name:
        return []

    try:
        conn = sqlite3.connect(str(RSS_DB_PATH))
        cursor = conn.cursor()

        # Search for competitor name in title or summary
        like_pattern = f"%{competitor_name}%"
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        cursor.execute(
            """
            SELECT title, summary, link, published, fetched_date
            FROM news
            WHERE (title LIKE ? OR summary LIKE ?)
              AND (fetched_date >= ? OR published >= ?)
            ORDER BY fetched_date DESC
            LIMIT 5
            """,
            (like_pattern, like_pattern, cutoff, cutoff),
        )

        rows = cursor.fetchall()
        conn.close()

        results = []
        for row in rows:
            title, summary, link, published, fetched = row
            results.append({
                "title": title or "",
                "summary": (summary or "")[:200],
                "link": link or "",
                "published": published or fetched or "",
            })
        return results

    except Exception as e:
        _log(f"[WARN] RSS query failed: {e}")
        return []


def query_vector_db_for_competitor(competitor_name: str, feature_gap: str = "", top_k: int = 3) -> list[dict]:
    """Query vector DB knowledge_competitors collection for competitor info."""
    if not competitor_name:
        return []

    try:
        sys.path.insert(0, str(PROJECT_ROOT / "competitor_analysis"))
        from scripts.vector_retriever import query_vector_db

        query = f"{competitor_name} product specifications features"
        if feature_gap:
            query += f" {feature_gap}"

        docs = query_vector_db(
            PROJECT_ROOT,
            query=query,
            top_k=top_k * 4,  # over-fetch so we can filter by name
            min_score=0.25,
            category_filter="competitors",
        )

        # Post-filter: keep only chunks that mention the competitor by name
        # or whose source filename contains the name.
        name_lower = competitor_name.lower()
        filtered = []
        for d in docs:
            source = (d.get("source") or "").lower()
            text = (d.get("text") or "").lower()
            if name_lower in source or name_lower in text:
                filtered.append(d)

        return filtered[:top_k]
    except Exception as e:
        _log(f"[WARN] Vector DB query failed: {e}")
        return []


def build_competitor_context(brief: dict) -> dict:
    """Build the enriched competitor context block."""
    competitor_name = find_competitor_in_brief(brief)
    if not competitor_name:
        _log("No competitor identified in brief — skipping enrichment")
        return {}

    _log(f"Enriching brief for competitor: {competitor_name}")

    comp_data = load_competitor_analysis()
    details = get_competitor_details(competitor_name, comp_data)

    if not details:
        _log(f"No details found for competitor: {competitor_name}")
        return {}

    # Get our products for advantage framing
    my_products = comp_data.get("my_products", [])
    my_product_names = [p.get("name", "") for p in my_products]
    my_product = my_product_names[0] if my_product_names else "our product"

    # Find the most relevant feature gap
    feature_gap = ""
    if details.get("feature_gaps"):
        feature_gap = details["feature_gaps"][0]

    # Frame our advantage
    our_advantage = ""
    if feature_gap:
        our_advantage = f"{my_product} offers {feature_gap} out of the box"
    else:
        our_advantage = f"{my_product} provides a more integrated solution"

    # Query RSS for recent news
    recent_news = query_rss_for_competitor(competitor_name)
    _log(f"  Found {len(recent_news)} recent RSS mention(s)")

    # Query vector DB for additional context
    vector_docs = query_vector_db_for_competitor(competitor_name, feature_gap=feature_gap)
    _log(f"  Found {len(vector_docs)} vector DB chunk(s)")

    context = {
        "competitor_name": competitor_name,
        "their_price": details.get("their_price"),
        "their_tier": details.get("their_tier"),
        "their_features": details.get("their_features", []),
        "feature_gap": feature_gap,
        "our_advantage": our_advantage,
        "threat_score": details.get("threat_score"),
        "threat_confidence": details.get("threat_confidence"),
        "recent_news": [
            f"{n['title']} ({n.get('published', 'recent')})" for n in recent_news
        ],
        "vector_sources": [d.get("source", "") for d in vector_docs],
    }

    return context


def write_enriched_brief(brief: dict, competitor_context: dict):
    timestamp = datetime.now(timezone.utc).isoformat()
    output = {
        **brief,
        "competitor_context": competitor_context,
        "enriched_at": timestamp,
    }

    # Timestamped file
    ts_file = f"enriched_brief_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    ts_path = OUTPUT_DIR / ts_file
    SHARED_DIR.mkdir(exist_ok=True)
    with open(ts_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    _log(f"[SAVED]   {ts_path}")

    # Latest
    with open(LATEST_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    _log(f"[SAVED]   {LATEST_PATH}")


def main():
    _log("=" * 55)
    _log("Competitor Context Injector starting")
    _log("=" * 55)

    brief = load_brief()
    if not brief:
        _log("[ABORT] No brief found.")
        sys.exit(1)

    competitor_context = build_competitor_context(brief)
    write_enriched_brief(brief, competitor_context)

    _log("=" * 55)
    _log("Competitor Context Injector complete")


if __name__ == "__main__":
    main()
