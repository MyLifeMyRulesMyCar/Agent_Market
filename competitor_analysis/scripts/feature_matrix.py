"""
scripts/feature_matrix.py — Build a feature comparison matrix.

Compares all "my products" and competitors across a defined feature list.
Produces a structured matrix suitable for rendering in reports or dashboards.

Output format:
  {
    "features": [str],
    "products": [str],
    "matrix": {
      "product_name": {
        "feature_name": True | False | "partial" | "unknown"
      }
    },
    "coverage_scores": {
      "product_name": float   # percentage of features present
    }
  }
"""


def _has_feature(feature: str, features_list: list[str]) -> bool | str:
    """
    Check if a feature is in a product's feature list.
    Returns True, False, or "unknown".
    """
    feature_lower = feature.lower()
    features_lower = [f.lower() for f in features_list]

    # Direct substring match
    for f in features_lower:
        if feature_lower in f or f in feature_lower:
            return True

    # Keyword-based matching for common features
    keyword_map = {
        "nvme support":         ["nvme", "m.2 m-key", "pcie nvme"],
        "pcie":                 ["pcie", "pci express"],
        "usb 3.0":              ["usb 3.0", "usb 3.1", "usb 3.2", "superspeed"],
        "hdmi output":          ["hdmi"],
        "4k video output":      ["4k", "uhd"],
        "wi-fi":                ["wi-fi", "wifi", "wireless"],
        "wi-fi 6":              ["wi-fi 6", "wifi 6", "802.11ax"],
        "bluetooth":            ["bluetooth"],
        "gpio pins":            ["gpio", "40-pin", "26-pin"],
        "emmc":                 ["emmc"],
        "npu / ai accelerator": ["npu", "ai accelerator", "neural", "tops"],
        "dual ethernet":        ["dual ethernet", "2x ethernet", "dual gigabit"],
        "active cooling":       ["active cooling", "fan"],
        "ram capacity (max)":   ["gb ram", "gb lpddr", "gb memory"],
    }

    synonyms = keyword_map.get(feature_lower, [feature_lower])
    for f in features_lower:
        for syn in synonyms:
            if syn in f or f in syn:
                return True

    return False


def build_feature_matrix(
    my_products: list[dict],
    competitor_profiles: dict,
    features_to_compare: list[str],
) -> dict:
    """
    Build the full feature comparison matrix.
    Also builds a confidence_matrix where each cell reflects how reliable
    the feature presence assessment is:
      - 0.95 = from known_features (explicit, high confidence)
      - 0.60 = inferred from extracted text (lower confidence)
      - 0.00 = feature not found / unknown
    """
    all_products = {}

    # Add my products
    for prod in my_products:
        all_products[prod["name"]] = {
            "features":      prod.get("key_features", []),
            "known_features": prod.get("key_features", []),
            "is_mine":       True,
            "price_usd":     prod.get("price_usd"),
        }

    # Add competitors
    for name, profile in competitor_profiles.items():
        extracted = profile.get("extracted_info", {})
        known     = profile.get("known_features", [])
        all_feats = list(set(extracted.get("features", []) + known))
        all_products[name] = {
            "features":       all_feats,
            "known_features": known,
            "is_mine":        False,
            "price_usd":      profile.get("known_price_usd"),
        }

    matrix = {}
    confidence_matrix = {}
    coverage_scores = {}

    for prod_name, prod_data in all_products.items():
        product_features = prod_data["features"]
        known_features   = prod_data["known_features"]
        row = {}
        conf_row = {}
        present_count = 0

        for feature in features_to_compare:
            result = _has_feature(feature, product_features)
            row[feature] = result

            # Determine confidence based on data source
            if result is True:
                present_count += 1
                # Check if this match came from known_features (high confidence)
                if _has_feature(feature, known_features) is True:
                    conf_row[feature] = 0.95
                else:
                    conf_row[feature] = 0.60
            else:
                conf_row[feature] = 0.0

        matrix[prod_name] = row
        confidence_matrix[prod_name] = conf_row
        total = len(features_to_compare)
        coverage_scores[prod_name] = round((present_count / total * 100) if total > 0 else 0, 1)

    # Compute "feature gap" — features my products lack that competitors have
    my_names  = [p["name"] for p in my_products]
    comp_names = list(competitor_profiles.keys())

    feature_gaps = {}  # feature → list of competitors that have it while we don't
    for feature in features_to_compare:
        my_has     = any(matrix.get(n, {}).get(feature) for n in my_names)
        comps_have = [n for n in comp_names if matrix.get(n, {}).get(feature)]
        if not my_has and comps_have:
            feature_gaps[feature] = comps_have

    # Compute "feature advantages" — features we have that competitors lack
    feature_advantages = {}  # feature → list of competitors that DON'T have it
    for feature in features_to_compare:
        my_has     = any(matrix.get(n, {}).get(feature) for n in my_names)
        comps_lack = [n for n in comp_names if not matrix.get(n, {}).get(feature)]
        if my_has and comps_lack:
            feature_advantages[feature] = comps_lack

    return {
        "features":          features_to_compare,
        "products":          list(all_products.keys()),
        "my_products":       my_names,
        "competitor_names":  comp_names,
        "matrix":            matrix,
        "confidence_matrix": confidence_matrix,
        "coverage_scores":   coverage_scores,
        "feature_gaps":      feature_gaps,
        "feature_advantages": feature_advantages,
    }