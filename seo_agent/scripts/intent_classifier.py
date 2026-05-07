"""
intent_classifier.py — Classify keywords by search intent.
Rule-based first, no ML needed.
"""

PROBLEM_SIGNALS   = ["issue", "problem", "fix", "error", "not working",
                      "fail", "broken", "crash", "help", "stuck", "troubleshoot"]
COMPARISON_SIGNALS= ["vs", "versus", "alternative", "compare", "best",
                      "difference", "which", "better"]
BUYING_SIGNALS    = ["buy", "price", "cheap", "cost", "where to get",
                      "purchase", "order", "shop", "deal", "under $"]
INFO_SIGNALS      = ["how", "what is", "tutorial", "guide", "beginner",
                      "explained", "introduction", "learn"]


def classify(keyword: str) -> str:
    kw = keyword.lower()
    if any(s in kw for s in PROBLEM_SIGNALS):
        return "problem"
    if any(s in kw for s in COMPARISON_SIGNALS):
        return "comparison"
    if any(s in kw for s in BUYING_SIGNALS):
        return "buying"
    if any(s in kw for s in INFO_SIGNALS):
        return "info"
    return "info"  # default


def classify_all(keywords: list[str]) -> list[dict]:
    return [{"keyword": kw, "intent": classify(kw)} for kw in keywords]