"""
scripts/prompt_builder.py — Build Groq prompts from article context.

Assembles a rich, structured prompt that tells Groq:
  - What the article is about (keyword + intent)
  - Who the reader is (pain point + use case)
  - What capabilities to highlight (product features → placeholders)
  - What structure to follow
  - The placeholder tokens to use

The goal: Groq writes a genuine, helpful article where the
product capabilities are the natural solution to real user pain,
with [PLACEHOLDER] tokens wherever specific product info goes.
"""

from pathlib import Path


# ── System prompt ─────────────────────────────────────────────

SYSTEM_PROMPT = """You are a senior technical content writer for a hardware company that makes \
single-board computers (SBCs), edge controllers, and smart home devices.

Your articles are:
- Practical and specific (not generic AI fluff)
- Written for makers, home automation enthusiasts, and IoT engineers
- Structured to genuinely help readers solve a real problem
- Natural about product capabilities — the product is the solution, not an ad

PLACEHOLDER RULES (critical):
- Use [PRODUCT_NAME] wherever you would name the specific product
- Use [PRODUCT_LINK] wherever a product URL would go
- Use [PRICE_USD] wherever a price would be mentioned
- Use [SHOP_LINK] for the call-to-action purchase link
- Use [DOCS_LINK] for documentation/setup guide links
- Use [SETUP_GUIDE_LINK] for a dedicated setup tutorial link
- NEVER invent prices, URLs, or model numbers — use placeholders

FORMAT RULES:
- Output clean Markdown only
- Structure: H1 title, then H2 sections
- Include a front matter block at the top (YAML between --- markers)
- Target 500-800 words in the body
- One practical code/config example (YAML or bash) where relevant
- End with a CTA section pointing to [SHOP_LINK]
- Do NOT add "Written by AI" or any meta-commentary
"""


# ── Front matter template ─────────────────────────────────────

FRONTMATTER_TEMPLATE = """---
title: "{title}"
target_keyword: "{keyword}"
intent: "{intent}"
cluster: "{cluster}"
seo_score: {seo_score}
pain_addressed: "{pain_label}"
use_case: "{use_case}"
products_mentioned: {products_list}
generated: "{date}"
status: draft
---"""


# ── User prompt builder ───────────────────────────────────────

def build_prompt(context: dict, config: dict) -> tuple[str, str]:
    """
    Returns (system_prompt, user_prompt) tuple for Groq.
    """
    system = SYSTEM_PROMPT

    keyword    = context.get("keyword", "")
    intent     = context.get("intent", "info")
    title      = context.get("title", f"Guide to {keyword}")
    pain       = context.get("pain_point", {})
    use_case   = context.get("use_case", {})
    products   = context.get("products", [])
    unmet      = context.get("unmet_needs", [])
    angle      = context.get("angle", "")
    placeholders = context.get("placeholders", {})

    gen_cfg = config.get("generation", {})
    wmin    = gen_cfg.get("word_count_min", 500)
    wmax    = gen_cfg.get("word_count_max", 800)
    brand   = config.get("brand", {})
    struct  = config.get("structure", {})

    # Format pain point context
    pain_label    = pain.get("label", "Common technical challenges")
    pain_examples = pain.get("examples", [])[:2]
    pain_keywords = pain.get("keywords", [])[:5]
    pain_context  = _fmt_pain(pain_label, pain_examples, pain_keywords)

    # Format use case context
    uc_label    = use_case.get("case", "IoT projects")
    uc_examples = use_case.get("examples", [])[:2]
    uc_context  = _fmt_use_case(uc_label, uc_examples)

    # Format product capabilities
    product_context = _fmt_products(products, config)

    # Format unmet needs
    needs_context = _fmt_needs(unmet)

    # Article structure
    structure_guide = _fmt_structure(struct, intent)

    user = f"""Write a {wmin}-{wmax} word blog article for the {brand.get('name', 'Purple Pi')} blog.

## ARTICLE BRIEF

**Target Keyword:** {keyword}
**Search Intent:** {intent}
**Suggested Title:** {title}
**Brand Tone:** {brand.get('tone', 'practical, knowledgeable, community-friendly')}
**Target Audience:** {brand.get('audience', 'makers, home automation enthusiasts, IoT developers')}

## READER PAIN POINT (what they are struggling with)

{pain_context}

## WHAT THEY ARE BUILDING (use case context)

{uc_context}

## PRODUCT CAPABILITIES TO HIGHLIGHT (use [PRODUCT_NAME] placeholder)

{product_context}

## UNMET NEEDS IN THE COMMUNITY

{needs_context}

{f"## STRATEGIC ANGLE{chr(10)}{angle}{chr(10)}" if angle else ""}

## ARTICLE STRUCTURE TO FOLLOW

{structure_guide}

## PLACEHOLDER TOKENS TO USE

- Product name: {placeholders.get('product_name', '[PRODUCT_NAME]')}
- Product URL: {placeholders.get('product_link', '[PRODUCT_LINK]')}  
- Price: {placeholders.get('price', '[PRICE_USD]')}
- Shop link: {placeholders.get('cta_link', '[SHOP_LINK]')}
- Docs: {placeholders.get('docs_link', '[DOCS_LINK]')}
- Setup guide: {placeholders.get('setup_guide', '[SETUP_GUIDE_LINK]')}

## OUTPUT FORMAT

Start with the YAML front matter block, then the full article in Markdown.
Use H2 (##) for sections. Include one practical code example.
The article should feel like it was written by a knowledgeable engineer
who genuinely uses this hardware, not a marketing writer.
"""

    return system, user


# ── Context formatters ────────────────────────────────────────

def _fmt_pain(label: str, examples: list, keywords: list) -> str:
    lines = [f"**Pain cluster:** {label}"]
    if examples:
        lines.append("\n**Real user quotes from Reddit/forums:**")
        for ex in examples:
            lines.append(f'  - "{ex}"')
    if keywords:
        lines.append(f"\n**Related keywords:** {', '.join(keywords)}")
    return "\n".join(lines)


def _fmt_use_case(label: str, examples: list) -> str:
    lines = [f"**Use case:** {label}"]
    if examples:
        lines.append("\n**Example projects:**")
        for ex in examples:
            lines.append(f"  - {ex}")
    return "\n".join(lines)


def _fmt_products(products: list, config: dict) -> str:
    if not products:
        return "No specific product data loaded — use [PRODUCT_NAME] generically."

    lines = []
    brand_products = config.get("brand", {}).get("products", [])

    for prod in products:
        name     = prod.get("name", "")
        features = prod.get("features", [])
        price    = prod.get("price")

        # Find the matching placeholder token
        token = "[PRODUCT_NAME]"
        for bp in brand_products:
            if bp.get("name", "").lower() == name.lower():
                token = bp.get("token", "[PRODUCT_NAME]")
                break

        lines.append(f"**{name}** (use as `{token}` in article)")
        if price:
            lines.append(f"  Price reference: ~${price} (use `[PRICE_USD]` in article)")
        if features:
            lines.append("  Key capabilities to mention naturally:")
            for feat in features[:8]:
                lines.append(f"    - {feat}")
        lines.append("")

    return "\n".join(lines)


def _fmt_needs(needs: list) -> str:
    if not needs:
        return "Address the general frustration with setup complexity and documentation gaps."
    return "\n".join(f"- {need}" for need in needs)


def _fmt_structure(struct: dict, intent: str) -> str:
    sections = struct.get("sections", [
        "hook", "problem", "solution_intro", "how_it_works", "comparison", "cta"
    ])

    descriptions = {
        "hook":           "2-3 sentence opener that names the specific pain point. No generic intros.",
        "problem":        "Expand the problem with context — why it happens, what people try, why it fails.",
        "solution_intro": "Introduce [PRODUCT_NAME] capabilities as the natural answer. Not a pitch — a genuine fit.",
        "how_it_works":   "Practical: what you actually do. Include a config/YAML/bash snippet.",
        "comparison":     "1 brief paragraph on why common alternatives (Raspberry Pi, generic gateways) fall short for this use case.",
        "cta":            "2-3 sentences. Invite them to learn more or buy at [SHOP_LINK]. Link to [SETUP_GUIDE_LINK].",
    }

    # Adjust for intent
    if intent == "comparison":
        descriptions["comparison"] = "Side-by-side: what [PRODUCT_NAME] does vs alternatives. Be honest about tradeoffs."
    elif intent == "problem":
        descriptions["hook"] = "Start with the exact error or problem scenario the reader likely already hit."

    lines = []
    for i, sec in enumerate(sections, 1):
        desc = descriptions.get(sec, f"Write the {sec} section.")
        lines.append(f"{i}. **{sec.replace('_', ' ').title()}** — {desc}")

    return "\n".join(lines)


def build_frontmatter(context: dict, date_str: str) -> str:
    """Build the YAML front matter string separately (useful for post-processing)."""
    pain   = context.get("pain_point", {})
    uc     = context.get("use_case", {})
    prods  = [p.get("name", "") for p in context.get("products", [])]

    return FRONTMATTER_TEMPLATE.format(
        title       = context.get("title", ""),
        keyword     = context.get("keyword", ""),
        intent      = context.get("intent", ""),
        cluster     = context.get("cluster", ""),
        seo_score   = context.get("seo_score", 0),
        pain_label  = pain.get("label", ""),
        use_case    = uc.get("case", ""),
        products_list = str(prods),
        date        = date_str,
    )
