"""Manual smoke test for the 11-metric fundamental scoring engine.

This validates scoring logic with clearly labelled SAMPLE data only.
It does NOT scan live NSE stocks or fetch current fundamentals.
"""
from fundamental_scoring import score_fundamentals

SAMPLE_METRICS = {
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

if __name__ == "__main__":
    result = score_fundamentals(SAMPLE_METRICS)
    print("FUNDAMENTAL SCORER CHECK — SAMPLE DATA ONLY")
    print(f"Score: {result['score']}/100")
    print(f"Grade: {result['grade']}")
    print(f"Shortlist: {result['shortlist']}")
    print(f"Missing metrics: {result['missing_metrics']}")
    print("Component scores:")
    for metric, points in result["component_scores"].items():
        print(f"  {metric}: {points}")
    if result["missing_metrics"]:
        raise SystemExit("FAIL: sample test has missing metrics")
    print("PASS: scoring engine ran successfully (sample data, not a live stock scan)")
