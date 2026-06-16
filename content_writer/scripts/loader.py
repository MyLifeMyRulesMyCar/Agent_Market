"""
scripts/loader.py — Load intelligence data from existing agent outputs.

Reads:
  - seo_agent/output/latest.json          → keywords, clusters, AI titles
  - customer_behaviour/output/latest.json  → pain points, use cases, sentiment
  - shared/intelligence_snapshot.json      → executive summary, strategic context
  - competitor_analysis/config/competitors.yaml → my_products capabilities

Returns a unified context dict the article generator uses.
"""

import json
import yaml
from pathlib import Path


def load_all(project_root: Path) -> dict:
    print("  Loading SEO agent data...")
    seo = _load_seo(project_root)

    print("  Loading customer behaviour data...")
    behaviour = _load_behaviour(project_root)

    print("  Loading intelligence snapshot...")
    snapshot = _load_snapshot(project_root)

    print("  Loading enriched brief from orchestrator...")
    enriched_brief = _load_enriched_brief(project_root)

    print("  Loading product capabilities...")
    products = _load_my_products(project_root)

    return {
        "seo":            seo,
        "behaviour":      behaviour,
        "snapshot":       snapshot,
        "enriched_brief": enriched_brief,
        "products":       products,
    }


def _load_seo(project_root: Path) -> dict:
    path = project_root / "seo_agent" / "output" / "latest.json"
    if not path.exists():
        print(f"  [!] SEO output not found: {path}")
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        kws = data.get("top_keywords", [])
        clusters = data.get("clusters", {})
        insights = data.get("insights", [])

        # Extract AI-generated titles if available
        titles = []
        for ins in insights:
            if ins.get("type") == "seo_titles":
                titles = ins.get("titles", [])
                break

        print(f"    Keywords: {len(kws)}  Clusters: {len(clusters)}  AI titles: {len(titles)}")
        return {
            "top_keywords": kws,
            "clusters":     clusters,
            "ai_titles":    titles,
            "run_date":     data.get("run_date", ""),
        }
    except Exception as e:
        print(f"  [!] SEO load error: {e}")
        return {}


def _load_behaviour(project_root: Path) -> dict:
    path = project_root / "customer_behaviour" / "output" / "latest.json"
    if not path.exists():
        print(f"  [!] Customer behaviour output not found: {path}")
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        pain_points = data.get("pain_points", [])
        use_cases   = data.get("use_cases", [])
        sentiment   = data.get("sentiment", {})
        insights    = data.get("insights", [])

        # Extract AI-generated unmet needs if available
        unmet_needs = []
        for ins in insights:
            if ins.get("type") == "unmet_needs":
                unmet_needs = ins.get("needs", [])
                break

        print(f"    Pain clusters: {len(pain_points)}  Use cases: {len(use_cases)}")
        return {
            "pain_points": pain_points,
            "use_cases":   use_cases,
            "sentiment":   sentiment,
            "unmet_needs": unmet_needs,
            "run_date":    data.get("run_at", data.get("timestamp", "")),
        }
    except Exception as e:
        print(f"  [!] Behaviour load error: {e}")
        return {}


def _load_snapshot(project_root: Path) -> dict:
    path = project_root / "shared" / "intelligence_snapshot.json"
    if not path.exists():
        print(f"  [!] Intelligence snapshot not found: {path}")
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return {
            "executive_summary":      data.get("executive_summary", ""),
            "emerging_opportunities": data.get("market_intelligence", {}).get("emerging_opportunities", []),
            "strategic_recommendations": data.get("strategic_recommendations", []),
            "top_trends":             data.get("market_intelligence", {}).get("top_trends", []),
            "snapshot_date":          data.get("snapshot_date", ""),
        }
    except Exception as e:
        print(f"  [!] Snapshot load error: {e}")
        return {}


def _load_enriched_brief(project_root: Path) -> dict:
    """Load the orchestrator's enriched brief if available."""
    path = project_root / "shared" / "enriched_brief_latest.json"
    if not path.exists():
        print(f"    [INFO] No enriched brief found: {path}")
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        brief = data.get("brief", {})
        opp = data.get("opportunity", {})
        comp_ctx = data.get("competitor_context", {})
        print(f"    Enriched brief loaded: '{brief.get('title', 'N/A')}'")
        return {
            "title": brief.get("title", ""),
            "angle": brief.get("angle", ""),
            "hook": brief.get("hook", ""),
            "key_claim": brief.get("key_claim", ""),
            "cta": brief.get("cta", ""),
            "keyword": opp.get("keyword", ""),
            "pain_link": opp.get("pain_link", ""),
            "competitor_name": comp_ctx.get("competitor_name", ""),
            "competitor_context": comp_ctx,
        }
    except Exception as e:
        print(f"    [!] Enriched brief load error: {e}")
        return {}


def _load_my_products(project_root: Path) -> list[dict]:
    """
    Load my_products from competitor_analysis config.
    This gives us the actual feature lists used in articles.
    """
    path = project_root / "competitor_analysis" / "config" / "competitors.yaml"
    if not path.exists():
        print(f"  [!] Competitors config not found: {path}")
        return []
    try:
        with open(path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        products = cfg.get("my_products", [])
        print(f"    Products loaded: {len(products)}")
        return products
    except Exception as e:
        print(f"  [!] Products load error: {e}")
        return []


def build_article_context(data: dict, config: dict) -> list[dict]:
    """
    Combine all loaded data into a list of article contexts —
    one per article to be written.

    Each context contains:
      - target_keyword + intent
      - primary_pain_point (label + examples)
      - relevant_use_case
      - product_capabilities (features relevant to this pain/keyword)
      - suggested_title (from AI titles if available, else generated)
      - strategic_angle (from snapshot recommendations)
    """
    seo       = data.get("seo", {})
    behaviour = data.get("behaviour", {})
    snapshot  = data.get("snapshot", {})
    products  = data.get("products", [])

    top_keywords  = seo.get("top_keywords", [])
    pain_points   = behaviour.get("pain_points", [])
    use_cases     = behaviour.get("use_cases", [])
    ai_titles     = seo.get("ai_titles", [])
    unmet_needs   = behaviour.get("unmet_needs", [])

    gen_cfg       = config.get("generation", {})
    src_cfg       = config.get("sources", {})
    n_articles    = gen_cfg.get("articles_per_run", 3)
    top_kw_n      = src_cfg.get("seo_keywords_top_n", 10)
    top_pain_n    = src_cfg.get("pain_points_top_n", 5)
    top_uc_n      = src_cfg.get("use_cases_top_n", 4)
    min_score     = src_cfg.get("min_seo_score", 5.0)

    # Filter keywords by minimum score
    candidate_kws = [
        kw for kw in top_keywords[:top_kw_n]
        if kw.get("score", 0) >= min_score
    ]

    if not candidate_kws:
        print("  [!] No keywords above minimum score threshold")
        candidate_kws = top_keywords[:5]  # fallback

    top_pains = pain_points[:top_pain_n]
    top_ucs   = use_cases[:top_uc_n]

    # Build a product features lookup: category → features list
    product_features = {}
    for prod in products:
        cat = prod.get("category", "general")
        product_features[cat] = {
            "name":     prod.get("name", ""),
            "price":    prod.get("price_usd"),
            "features": prod.get("key_features", []),
        }

    # If orchestrator produced an enriched brief, use it to override the first article
    enriched_brief = data.get("enriched_brief", {})

    contexts = []
    for i, kw_data in enumerate(candidate_kws[:n_articles]):
        keyword = kw_data.get("keyword", "")

        # If this keyword matches the orchestrator's chosen keyword, use the brief
        if enriched_brief and keyword.lower() in enriched_brief.get("keyword", "").lower():
            ctx = _build_context_from_brief(enriched_brief, kw_data, i, config, snapshot)
            if ctx:
                contexts.append(ctx)
                continue


        keyword = kw_data.get("keyword", "")
        intent  = kw_data.get("intent", "info")
        cluster = kw_data.get("cluster", "general")

        # Find best matching pain point for this keyword
        pain = _match_pain_to_keyword(keyword, top_pains)

        # Find best matching use case
        use_case = _match_usecase_to_keyword(keyword, top_ucs)

        # Find AI title or build one
        title = _find_title(keyword, ai_titles, intent)

        # Pick relevant products based on cluster
        relevant_products = _pick_relevant_products(cluster, keyword, product_features)

        # Strategic angle from snapshot
        angle = _pick_strategic_angle(keyword, snapshot.get("strategic_recommendations", []))

        contexts.append({
            "index":       i + 1,
            "keyword":     keyword,
            "intent":      intent,
            "cluster":     cluster,
            "seo_score":   round(kw_data.get("score", 0), 1),
            "title":       title,
            "pain_point":  pain,
            "use_case":    use_case,
            "products":    relevant_products,
            "unmet_needs": unmet_needs[:3],
            "angle":       angle,
            "snapshot_summary": snapshot.get("executive_summary", ""),
            "placeholders": config.get("placeholders", {}),
        })

    return contexts


# ── Matching helpers ──────────────────────────────────────────

def _match_pain_to_keyword(keyword: str, pain_points: list) -> dict:
    """Find the pain point most relevant to this keyword."""
    kw_lower = keyword.lower()
    for pain in pain_points:
        label = pain.get("label", "").lower()
        kws   = [k.lower() for k in pain.get("keywords", [])]
        if any(term in kw_lower for term in kws) or any(term in label for term in kw_lower.split()):
            return pain
    # Fallback: return highest-mention pain point
    return pain_points[0] if pain_points else {}


def _match_usecase_to_keyword(keyword: str, use_cases: list) -> dict:
    """Find the use case most relevant to this keyword."""
    kw_lower = keyword.lower()
    home_terms  = ["home", "automation", "smart", "zigbee", "mqtt", "assistant"]
    edge_terms  = ["edge", "industrial", "iot", "controller", "modbus"]
    server_terms= ["server", "nas", "kubernetes", "docker", "cluster"]

    for uc in use_cases:
        case_lower = uc.get("case", "").lower()
        if any(t in kw_lower for t in home_terms) and "home" in case_lower:
            return uc
        if any(t in kw_lower for t in edge_terms) and ("edge" in case_lower or "iot" in case_lower):
            return uc
        if any(t in kw_lower for t in server_terms) and any(t in case_lower for t in server_terms):
            return uc
    return use_cases[0] if use_cases else {}


def _find_title(keyword: str, ai_titles: list, intent: str) -> str:
    """Find an AI-generated title targeting this keyword, or return a placeholder."""
    kw_lower = keyword.lower()
    for t in ai_titles:
        target = t.get("target_keyword", "").lower()
        title  = t.get("title", "")
        if kw_lower in target or target in kw_lower or kw_lower in title.lower():
            return title
    # Fallback title templates by intent
    templates = {
        "info":       f"Getting Started with {keyword.title()}: A Practical Guide",
        "problem":    f"How to Fix {keyword.title()} Issues (Step-by-Step)",
        "comparison": f"{keyword.title()} vs Alternatives: What Actually Works in 2026",
        "buying":     f"Best {keyword.title()} for Home Automation in 2026",
    }
    return templates.get(intent, f"The Complete Guide to {keyword.title()}")


def _pick_relevant_products(cluster: str, keyword: str, product_features: dict) -> list[dict]:
    """Return the most relevant products for this article's topic."""
    kw_lower = keyword.lower()

    # Map clusters/keywords to product categories
    if any(t in kw_lower for t in ["home assistant", "zigbee", "smart home", "mqtt", "esphome"]):
        cats = ["ha_device", "sbc"]
    elif any(t in kw_lower for t in ["edge", "industrial", "modbus", "lorawan", "gateway"]):
        cats = ["edge_controller", "sbc"]
    elif any(t in kw_lower for t in ["cluster", "kubernetes", "nas", "server", "docker"]):
        cats = ["sbc"]
    elif cluster in ("home_auto",):
        cats = ["ha_device", "sbc"]
    elif cluster in ("ai_ml", "cluster"):
        cats = ["sbc", "edge_controller"]
    else:
        cats = ["sbc"]  # default to SBC

    result = []
    for cat in cats:
        if cat in product_features:
            result.append(product_features[cat])
    return result


def _pick_strategic_angle(keyword: str, recommendations: list) -> str:
    """Pick the most relevant strategic recommendation as the article's angle."""
    if not recommendations:
        return ""
    kw_lower = keyword.lower()
    for rec in recommendations:
        action = rec.get("action", "").lower()
        if any(term in action for term in kw_lower.split()):
            return rec.get("action", "")
    return recommendations[0].get("action", "") if recommendations else ""


def _build_context_from_brief(enriched_brief: dict, kw_data: dict, index: int, config: dict, snapshot: dict) -> dict | None:
    """Build an article context directly from the orchestrator's enriched brief."""
    if not enriched_brief.get("title"):
        return None

    keyword = enriched_brief.get("keyword") or kw_data.get("keyword", "")
    intent = kw_data.get("intent", "info")
    cluster = kw_data.get("cluster", "general")

    return {
        "index":              index + 1,
        "keyword":            keyword,
        "intent":             intent,
        "cluster":            cluster,
        "seo_score":          round(kw_data.get("score", 0), 1),
        "title":              enriched_brief.get("title", ""),
        "pain_point":         {"label": enriched_brief.get("pain_link", "")},
        "use_case":           {},
        "products":           [],
        "unmet_needs":        [],
        "angle":              enriched_brief.get("angle", ""),
        "hook":               enriched_brief.get("hook", ""),
        "key_claim":          enriched_brief.get("key_claim", ""),
        "cta":                enriched_brief.get("cta", ""),
        "snapshot_summary":   snapshot.get("executive_summary", ""),
        "placeholders":       config.get("placeholders", {}),
        "from_enriched_brief": True,
        "competitor_context":  enriched_brief.get("competitor_context", {}),
    }
