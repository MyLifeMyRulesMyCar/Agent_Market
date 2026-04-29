"""
scripts/strength_detector.py — Detect strengths and weaknesses for each product.

Logic:
  - Has feature from strength_signals → strength
  - Has feature from weakness_signals → weakness
  - Feature present in competitor but not in my product → gap (potential weakness)
  - Feature present in my product but missing in competitor → advantage (strength)
  - Calculates a threat score per competitor (0-10)
"""

from collections import defaultdict


def detect_strengths_weaknesses(
    my_products: list[dict],
    competitor_profiles: dict,
    feature_matrix: dict,
    strength_signals: list[str],
    weakness_signals: list[str],
) -> dict:
    """
    Returns sw_analysis dict:
      {
        "product_name": {
          "strengths":      [str],
          "weaknesses":     [str],
          "advantages_over_competitors": {comp_name: [features]},
          "gaps_vs_competitors":         {comp_name: [features]},
          "threat_score":   float,   # how threatening is this competitor (0-10)
          "is_mine":        bool,
        }
      }
    """
    matrix       = feature_matrix.get("matrix", {})
    my_names     = [p["name"] for p in my_products]
    comp_names   = list(competitor_profiles.keys())
    all_features = feature_matrix.get("features", [])

    sw = {}

    # ── Analyse each product (mine + competitors) ────────────
    for prod_name, feature_row in matrix.items():
        is_mine  = prod_name in my_names
        features = [f for f, v in feature_row.items() if v is True]
        feat_text = " ".join(features).lower()

        # Strengths from signal keywords
        strengths = []
        for sig in strength_signals:
            if sig.lower() in feat_text:
                # Find which feature this matches
                matching = [f for f in features if sig.lower() in f.lower()]
                if matching and matching[0] not in strengths:
                    strengths.extend(matching[:1])

        # Weaknesses from signal keywords  
        weaknesses = []
        for sig in weakness_signals:
            if sig.lower() in feat_text:
                if sig not in weaknesses:
                    weaknesses.append(sig)

        sw[prod_name] = {
            "strengths":   strengths,
            "weaknesses":  weaknesses,
            "advantages_over_competitors": defaultdict(list),
            "gaps_vs_competitors":         defaultdict(list),
            "is_mine":     is_mine,
            "threat_score": 0.0,
        }

    # ── Compute advantages and gaps (my products vs competitors) ──
    for my_name in my_names:
        my_row = matrix.get(my_name, {})

        for comp_name in comp_names:
            comp_row = matrix.get(comp_name, {})

            advantages = []
            gaps       = []

            for feat in all_features:
                my_has   = my_row.get(feat, False)
                comp_has = comp_row.get(feat, False)

                if my_has and not comp_has:
                    advantages.append(feat)
                elif not my_has and comp_has:
                    gaps.append(feat)

            sw[my_name]["advantages_over_competitors"][comp_name] = advantages
            sw[my_name]["gaps_vs_competitors"][comp_name]         = gaps

    # ── Compute threat scores for competitors ─────────────────
    # Threat score = how many features the competitor has that we lack,
    # weighted by how many of our products they beat
    for comp_name in comp_names:
        comp_row        = matrix.get(comp_name, {})
        comp_features   = sum(1 for v in comp_row.values() if v is True)
        total_features  = len(all_features) if all_features else 1

        # Feature coverage vs ours
        my_avg_coverage = 0
        for my_name in my_names:
            my_row = matrix.get(my_name, {})
            my_coverage = sum(1 for v in my_row.values() if v is True)
            my_avg_coverage += my_coverage
        my_avg_coverage /= max(len(my_names), 1)

        # How many features does competitor have that we don't?
        gaps_count = 0
        for feat in all_features:
            comp_has = comp_row.get(feat, False)
            my_has   = any(matrix.get(n, {}).get(feat, False) for n in my_names)
            if comp_has and not my_has:
                gaps_count += 1

        # Threat = (competitor coverage / total) * 5 + (gaps / total) * 5
        cov_score  = (comp_features / total_features) * 5
        gap_score  = (gaps_count   / total_features) * 5
        threat     = round(min(cov_score + gap_score, 10.0), 2)

        sw[comp_name]["threat_score"] = threat
        sw[comp_name]["feature_coverage_pct"] = round(comp_features / total_features * 100, 1)

    # Convert defaultdicts to plain dicts for JSON serialisation
    for name in sw:
        sw[name]["advantages_over_competitors"] = dict(sw[name]["advantages_over_competitors"])
        sw[name]["gaps_vs_competitors"]          = dict(sw[name]["gaps_vs_competitors"])

    return sw