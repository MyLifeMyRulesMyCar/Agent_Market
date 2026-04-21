"""
scripts/seasonal.py — Detect seasonal patterns from Google Trends timeseries.

Looks for:
  1. Monthly seasonality: does this keyword peak at certain months?
  2. Year-over-year trend: is interest growing, flat, or declining overall?
  3. Current season signal: is this keyword in a seasonal peak RIGHT NOW?
"""

from datetime import datetime
from collections import defaultdict
import statistics


def detect_seasonal(trends_data: list[dict], current_month: int = None) -> list[dict]:
    """
    Analyse 12-month timeseries for seasonal patterns.

    Returns list of keywords with detected seasonal behaviour:
      [{
        "keyword":         str,
        "market":          str,
        "monthly_pattern": {1: avg, 2: avg, ..., 12: avg},
        "peak_months":     [int],   # months with above-average interest
        "trough_months":   [int],   # months with below-average interest
        "yoy_trend":       str,     # "growing" | "declining" | "flat"
        "is_peak_now":     bool,    # is the current month a peak?
        "seasonality_strength": float,  # 0-1, how pronounced the pattern is
      }]
    """
    if current_month is None:
        current_month = datetime.now().month

    results = []

    for series in trends_data:
        kw       = series.get("keyword", "")
        timeline = [p for p in series.get("timeline", []) if not p.get("is_partial")]
        market   = series.get("market", "")

        if len(timeline) < 20:
            continue  # need enough data for seasonal analysis

        # Group by month (approximated from date string)
        monthly: dict[int, list[int]] = defaultdict(list)
        for point in timeline:
            date_str = point.get("date", "")
            month = _parse_month(date_str)
            if month:
                monthly[month].append(point.get("value", 0))

        if len(monthly) < 6:
            continue

        # Compute monthly averages
        monthly_avg = {m: round(statistics.mean(vals), 1) for m, vals in monthly.items() if vals}
        if not monthly_avg:
            continue

        overall_avg = statistics.mean(monthly_avg.values())
        if overall_avg == 0:
            continue

        # Identify peak and trough months
        peak_months   = [m for m, avg in monthly_avg.items() if avg > overall_avg * 1.2]
        trough_months = [m for m, avg in monthly_avg.items() if avg < overall_avg * 0.8]

        # Seasonality strength = coefficient of variation across months
        try:
            stdev    = statistics.stdev(monthly_avg.values())
            strength = round(min(stdev / (overall_avg + 0.01), 1.0), 3)
        except Exception:
            strength = 0.0

        # Only include if there's meaningful seasonality
        if strength < 0.15:
            continue

        # YoY trend: compare first half of timeline vs second half
        mid    = len(timeline) // 2
        first  = statistics.mean(p["value"] for p in timeline[:mid]) if mid > 0 else 0
        second = statistics.mean(p["value"] for p in timeline[mid:]) if len(timeline) > mid else 0

        change = (second - first) / (first + 1) * 100
        if change > 15:
            yoy_trend = "growing"
        elif change < -15:
            yoy_trend = "declining"
        else:
            yoy_trend = "flat"

        is_peak_now = current_month in peak_months

        results.append({
            "keyword":              kw,
            "market":               market,
            "monthly_pattern":      {str(m): v for m, v in sorted(monthly_avg.items())},
            "peak_months":          sorted(peak_months),
            "trough_months":        sorted(trough_months),
            "yoy_trend":            yoy_trend,
            "yoy_change_pct":       round(change, 1),
            "is_peak_now":          is_peak_now,
            "seasonality_strength": strength,
            "overall_avg":          round(overall_avg, 1),
        })

    # Sort by seasonality strength desc, then peak-now keywords first
    results.sort(key=lambda x: (x["is_peak_now"], x["seasonality_strength"]), reverse=True)
    return results


def _parse_month(date_str: str) -> int:
    """Extract month integer from a date range string like 'Mar 15 – 21, 2026'."""
    month_map = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5,  "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    if not date_str:
        return 0
    first_word = date_str.strip().split()[0].lower()[:3]
    return month_map.get(first_word, 0)