"""
parser.py — Parses raw SerpAPI Google Trends responses into clean structures.
"""

def parse_timeseries(raw: dict) -> list:
    """Extract clean timeline [{date, values: {kw: n}, is_partial}]"""
    if not raw:
        return []
    timeline = raw.get("interest_over_time", {}).get("timeline_data", [])
    keywords = raw.get("_meta", {}).get("keywords", [])
    result = []
    for point in timeline:
        vals = point.get("values", [])
        entry = {
            "date": point.get("date", ""),
            "is_partial": point.get("is_partial", False),
            "values": {}
        }
        for i, kw in enumerate(keywords):
            v = vals[i] if i < len(vals) else {}
            entry["values"][kw] = v.get("extracted_value", 0)
        result.append(entry)
    return result


def parse_related_queries(raw: dict) -> dict:
    if not raw:
        return {"rising": [], "top": []}
    related = raw.get("related_queries", {})
    def clean(items):
        return [{"query": i.get("query", ""), "value": i.get("extracted_value", i.get("value", ""))}
                for i in (items or [])[:10]]
    return {"rising": clean(related.get("rising")), "top": clean(related.get("top"))}


def parse_related_topics(raw: dict) -> dict:
    if not raw:
        return {"rising": [], "top": []}
    related = raw.get("related_topics", {})
    def clean(items):
        return [{"topic": i.get("topic", {}).get("title", ""),
                 "type": i.get("topic", {}).get("type", ""),
                 "value": i.get("extracted_value", i.get("value", ""))}
                for i in (items or [])[:10]]
    return {"rising": clean(related.get("rising")), "top": clean(related.get("top"))}


def summarize_keyword(kw: str, timeline: list) -> dict:
    """Compute stats for one keyword across timeline points."""
    values = [p["values"].get(kw, 0) for p in timeline if not p.get("is_partial")]
    if not values:
        return {}
    avg = sum(values) / len(values)
    trend = "rising" if values[-1] > values[0] else ("falling" if values[-1] < values[0] else "flat")
    peak_idx = values.index(max(values))
    peak_date = timeline[peak_idx]["date"] if peak_idx < len(timeline) else ""
    return {
        "min": min(values),
        "max": max(values),
        "avg": round(avg, 1),
        "latest": values[-1],
        "trend": trend,
        "peak_date": peak_date,
        "data_points": len(values),
    }


def build_market_summary(market_key: str, market_cfg: dict, layer_results: dict) -> dict:
    """
    Aggregates all layer results for a market into a clean summary dict.
    """
    label = market_cfg.get("label", market_key)
    keyword_summaries = {}

    for layer_name, batches in layer_results.items():
        for batch_raw in batches:
            if not batch_raw:
                continue
            timeline = parse_timeseries(batch_raw)
            keywords = batch_raw.get("_meta", {}).get("keywords", [])

            for kw in keywords:
                summary = summarize_keyword(kw, timeline)
                keyword_summaries[kw] = {
                    "layer": layer_name,
                    "summary": summary,
                    "timeline": [
                        {"date": p["date"], "value": p["values"].get(kw, 0), "is_partial": p["is_partial"]}
                        for p in timeline
                    ]
                }

    # Rank all keywords by avg interest
    ranked = sorted(
        [{"keyword": kw, **data["summary"]} for kw, data in keyword_summaries.items() if data.get("summary")],
        key=lambda x: x.get("avg", 0),
        reverse=True
    )

    return {
        "label": label,
        "keyword_data": keyword_summaries,
        "ranking": ranked,
    }