def build_queries(config):
    """
    Build all search queries from config.
    Returns a list of dicts with query + context about what it's for.
    """
    queries = []

    # Product questions (your own products)
    for product in config.get("my_products", []):
        for q_template in config.get("questions", []):
            queries.append({
                "query": q_template.replace("{product}", product),
                "category": "my_product",
                "subject": product
            })

    # Competitor questions
    for competitor in config.get("competitors", []):
        for q_template in config.get("competitor_questions", []):
            queries.append({
                "query": q_template.replace("{product}", competitor),
                "category": "competitor",
                "subject": competitor
            })

    return queries