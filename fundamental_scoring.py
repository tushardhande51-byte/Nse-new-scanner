"""Fundamental scoring engine for the NSE stock screener.

This module scores 11 fundamental metrics out of 100. P/E is a score, not a hard
pass/fail filter: high-P/E stocks can score well when profit growth is strong.

Expected metric keys (percentages are expressed as percentage points, e.g. 25 for 25%):
sales_growth, profit_growth, eps_growth, roce, roe, debt_to_equity,
pe_ratio, operating_margin, free_cash_flow_positive, pledged_pct, promoter_holding.

Missing values receive zero points and are listed in missing_metrics. Do not treat
a missing metric as a pass. This scoring engine does not itself fetch market data.
"""

from math import isfinite

WEIGHTS = {
    "sales_growth": 15,
    "profit_growth": 15,
    "eps_growth": 10,
    "roce": 15,
    "roe": 10,
    "debt_to_equity": 10,
    "pe_ratio": 10,
    "operating_margin": 5,
    "free_cash_flow_positive": 5,
    "pledged_pct": 3,
    "promoter_holding": 2,
}

def _number(metrics, key):
    value = metrics.get(key)
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if isfinite(value) else None


def _growth_score(value, weight, full_at, partial_at):
    if value is None:
        return 0
    if value >= full_at:
        return weight
    if value >= partial_at:
        return round(weight * 0.6, 2)
    if value > 0:
        return round(weight * 0.25, 2)
    return 0


def _pe_score(pe, profit_growth):
    """Return P/E points out of 10; reward high growth without ignoring valuation risk."""
    if pe is None or pe <= 0 or profit_growth is None:
        return 0
    if pe <= 15:
        return 10
    if pe <= 25:
        if profit_growth >= 25:
            return 8
        if profit_growth >= 15:
            return 5
        return 2
    if pe <= 40:
        if profit_growth >= 35:
            return 8
        if profit_growth >= 25:
            return 6
        if profit_growth >= 15:
            return 3
        return 1
    # Above 40 P/E needs exceptional, sustained growth to earn meaningful points.
    if profit_growth >= 50:
        return 7
    if profit_growth >= 40:
        return 5
    if profit_growth >= 30:
        return 3
    return 0


def score_fundamentals(metrics):
    """Score metrics and return total, grade, component scores, and missing fields."""
    metrics = metrics or {}
    missing = [
        key for key in WEIGHTS
        if (
            (key == "free_cash_flow_positive" and not isinstance(metrics.get(key), bool))
            or (key != "free_cash_flow_positive" and _number(metrics, key) is None)
        )
    ]
    scores = {}

    sales = _number(metrics, "sales_growth")
    profit = _number(metrics, "profit_growth")
    eps = _number(metrics, "eps_growth")
    roce = _number(metrics, "roce")
    roe = _number(metrics, "roe")
    debt = _number(metrics, "debt_to_equity")
    pe = _number(metrics, "pe_ratio")
    opm = _number(metrics, "operating_margin")
    fcf = metrics.get("free_cash_flow_positive")
    pledge = _number(metrics, "pledged_pct")
    promoter = _number(metrics, "promoter_holding")

    scores["sales_growth"] = _growth_score(sales, 15, 15, 8)
    scores["profit_growth"] = _growth_score(profit, 15, 20, 10)
    scores["eps_growth"] = _growth_score(eps, 10, 20, 10)

    scores["roce"] = 15 if roce is not None and roce >= 20 else (10 if roce is not None and roce >= 15 else (4 if roce is not None and roce > 0 else 0))
    scores["roe"] = 10 if roe is not None and roe >= 18 else (7 if roe is not None and roe >= 15 else (3 if roe is not None and roe > 0 else 0))
    scores["debt_to_equity"] = 10 if debt is not None and debt < 0.25 else (7 if debt is not None and debt < 0.5 else (3 if debt is not None and debt <= 1 else 0))
    scores["pe_ratio"] = _pe_score(pe, profit)
    scores["operating_margin"] = 5 if opm is not None and opm >= 15 else (3 if opm is not None and opm >= 8 else (1 if opm is not None and opm > 0 else 0))

    scores["free_cash_flow_positive"] = 5 if fcf is True else 0
    scores["pledged_pct"] = 3 if pledge is not None and pledge == 0 else (2 if pledge is not None and pledge < 1 else (1 if pledge is not None and pledge < 5 else 0))
    scores["promoter_holding"] = 2 if promoter is not None and promoter >= 50 else (1 if promoter is not None and promoter >= 35 else 0)

    total = round(sum(scores.values()), 2)
    if total >= 85:
        grade = "A"
    elif total >= 75:
        grade = "B"
    elif total >= 60:
        grade = "C"
    else:
        grade = "D"

    return {
        "score": total,
        "grade": grade,
        "shortlist": total >= 75 and not missing,
        "component_scores": scores,
        "missing_metrics": missing,
        "note": "Screening score only; verify source data, sector context, cash flow quality, and latest results before investing.",
    }


if __name__ == "__main__":
    # Example: high P/E can still score well when growth is strong.
    example = {
        "sales_growth": 20,
        "profit_growth": 35,
        "eps_growth": 30,
        "roce": 22,
        "roe": 18,
        "debt_to_equity": 0.2,
        "pe_ratio": 30,
        "operating_margin": 16,
        "free_cash_flow_positive": True,
        "pledged_pct": 0,
        "promoter_holding": 55,
    }
    print(score_fundamentals(example))
