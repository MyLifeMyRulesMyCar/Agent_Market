"""
scripts/pricing_analyzer.py — Analyse pricing positioning.

Categories each product as:
  - low:  budget segment
  - mid:  value segment
  - high: premium segment

Computes:
  - Price tier per product
  - Price delta vs each of my products
  - Value score (features per dollar)
  - Positioning recommendation
"""


def _tier(price: float, pricing_config: dict) -> str:
    if price is None:
        return "unknown"
    low_max  = pricing_config.get("low_max", 35)
    mid_max  = pricing_config.get("mid_max", 75)
    if price <= low_max:
        return "low"
    if price <= mid_max:
        return "mid"
    return "high"


def _value_score(price: float, feature_count: int) -> float:
    """Features per dollar — higher is better value."""
    if not price or price == 0:
        return 0.0
    return round(feature_count / price, 4)


def analyze_pricing(
    my_products: list[dict],
    competitor_profiles: dict,
    pricing_config: dict,
) -> dict:
    """
    Returns:
      {
        "product_name": {
          "price_usd":      float | None,
          "tier":           str,
          "value_score":    float,
          "vs_my_products": {my_name: {"delta": float, "cheaper_by": str}},
          "positioning":    str,
          "recommendation": str,
        }
      }
    """
    result = {}

    # ── My products ───────────────────────────────────────────
    for prod in my_products:
        name          = prod["name"]
        price         = prod.get("price_usd")
        feature_count = len(prod.get("key_features", []))
        tier          = _tier(price, pricing_config)
        val           = _value_score(price, feature_count)

        result[name] = {
            "price_usd":     price,
            "tier":          tier,
            "value_score":   val,
            "is_mine":       True,
            "positioning":   _positioning_text(tier, True),
            "recommendation": "",
        }

    # ── Competitors ───────────────────────────────────────────
    my_prices = [(p["name"], p.get("price_usd")) for p in my_products if p.get("price_usd")]

    for comp_name, profile in competitor_profiles.items():
        extracted     = profile.get("extracted_info", {})
        price         = profile.get("known_price_usd") or extracted.get("price_usd")
        feature_count = len(extracted.get("features", []) + profile.get("known_features", []))
        tier          = _tier(price, pricing_config)
        val           = _value_score(price, feature_count)

        # Delta vs each of my products
        vs_mine = {}
        for my_name, my_price in my_prices:
            if price is not None and my_price is not None:
                delta = round(price - my_price, 2)
                vs_mine[my_name] = {
                    "delta":       delta,
                    "direction":   "more expensive" if delta > 0 else ("cheaper" if delta < 0 else "same price"),
                    "delta_pct":   round(abs(delta) / (my_price + 0.01) * 100, 1),
                }

        positioning  = _positioning_text(tier, False)
        recommendation = _pricing_recommendation(tier, price, my_prices, val)

        result[comp_name] = {
            "price_usd":       price,
            "tier":            tier,
            "value_score":     val,
            "is_mine":         False,
            "vs_my_products":  vs_mine,
            "positioning":     positioning,
            "recommendation":  recommendation,
        }

    return result


def _positioning_text(tier: str, is_mine: bool) -> str:
    subject = "We are" if is_mine else "Competitor is"
    mapping = {
        "low":     f"{subject} positioned in the budget segment.",
        "mid":     f"{subject} positioned in the value / mainstream segment.",
        "high":    f"{subject} positioned in the premium segment.",
        "unknown": "Price unknown — positioning unclear.",
    }
    return mapping.get(tier, "")


def _pricing_recommendation(
    tier: str,
    comp_price: float,
    my_prices: list[tuple],
    value_score: float,
) -> str:
    if not my_prices or comp_price is None:
        return "Insufficient pricing data for recommendation."

    my_avg = sum(p for _, p in my_prices if p) / max(len(my_prices), 1)

    if comp_price < my_avg * 0.85:
        return (
            f"Competitor undercuts our average by {round((my_avg - comp_price) / my_avg * 100, 0):.0f}%. "
            "Consider value-add differentiation or feature highlighting."
        )
    elif comp_price > my_avg * 1.15:
        return (
            f"Competitor is priced {round((comp_price - my_avg) / my_avg * 100, 0):.0f}% above our average. "
            "We have a pricing advantage — reinforce value narrative."
        )
    else:
        return (
            "Competitor is in the same price band as our products. "
            "Differentiate on feature set, software support, or ecosystem."
        )