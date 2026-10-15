"""Manual Yahoo Finance fundamental scan for NSE-listed stocks.

Yahoo/yfinance data is unofficial and uneven across Indian tickers. The script
keeps unavailable metrics blank; the existing scorer will not shortlist records
with missing metrics. It never treats missing promoter/pledge data as zero.
"""
import os
import time
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

from fundamental_scoring import score_fundamentals

NSE_LIST_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
MAX_STOCKS = int(os.getenv("MAX_STOCKS", "250"))
PAUSE_SECONDS = float(os.getenv("YAHOO_PAUSE_SECONDS", "0.15"))
OUTPUT = "yahoo_fundamental_results.csv"


def raw_value(info, *keys):
    for key in keys:
        value = info.get(key)
        if value is not None:
            try:
                value = float(value)
                if pd.notna(value):
                    return value
            except (TypeError, ValueError):
                pass
    return None


def pct(value):
    return None if value is None else value * 100


def statement_row(frame, names):
    if frame is None or frame.empty:
        return None
    for name in names:
        if name in frame.index:
            series = pd.to_numeric(frame.loc[name], errors="coerce").dropna()
            if len(series):
                return series
    return None


def growth_from_statement(frame, names):
    series = statement_row(frame, names)
    if series is None or len(series) < 2:
        return None
    prior = float(series.iloc[1])
    current = float(series.iloc[0])
    if prior == 0:
        return None
    return (current - prior) / abs(prior) * 100


def get_metrics(symbol):
    ticker = yf.Ticker(symbol + ".NS")
    info = ticker.get_info()

    # Prefer Yahoo's reported growth fields when available.
    sales_growth = pct(raw_value(info, "revenueGrowth"))
    profit_growth = pct(raw_value(info, "earningsGrowth"))
    eps_growth = pct(raw_value(info, "earningsQuarterlyGrowth"))

    try:
        income = ticker.income_stmt
    except Exception:
        income = pd.DataFrame()
    try:
        balance = ticker.balance_sheet
    except Exception:
        balance = pd.DataFrame()
    try:
        cashflow = ticker.cashflow
    except Exception:
        cashflow = pd.DataFrame()

    if sales_growth is None:
        sales_growth = growth_from_statement(income, ["Total Revenue", "Operating Revenue"])
    if profit_growth is None:
        profit_growth = growth_from_statement(income, ["Net Income", "Net Income Common Stockholders"])
    if eps_growth is None:
        eps_growth = pct(raw_value(info, "earningsGrowth"))

    roe = pct(raw_value(info, "returnOnEquity"))
    debt_to_equity_raw = raw_value(info, "debtToEquity")
    debt_to_equity = None if debt_to_equity_raw is None else debt_to_equity_raw / 100

    # ROCE: estimate from operating income / (total debt + stockholders' equity).
    roce = None
    op_income = statement_row(income, ["Operating Income", "EBIT"])
    debt = statement_row(balance, ["Total Debt"])
    equity = statement_row(balance, ["Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest"])
    if op_income is not None and debt is not None and equity is not None:
        capital = float(debt.iloc[0]) + float(equity.iloc[0])
        if capital > 0:
            roce = float(op_income.iloc[0]) / capital * 100

    op_margin = pct(raw_value(info, "operatingMargins"))
    pe = raw_value(info, "trailingPE", "forwardPE")

    # Positive FCF is derived from Yahoo cash-flow statement if available.
    fcf_positive = None
    if cashflow is not None and not cashflow.empty:
        operating_cf = statement_row(cashflow, ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"])
        capex = statement_row(cashflow, ["Capital Expenditure", "Capital Expenditures"])
        if operating_cf is not None and capex is not None:
            fcf_positive = (float(operating_cf.iloc[0]) + float(capex.iloc[0])) > 0

    # Yahoo does not reliably provide Indian promoter pledge % or promoter holding.
    # Insider ownership is not interchangeable with promoter shareholding.
    pledged_pct = None
    promoter_holding = None

    metrics = {
        "sales_growth": sales_growth,
        "profit_growth": profit_growth,
        "eps_growth": eps_growth,
        "roce": roce,
        "roe": roe,
        "debt_to_equity": debt_to_equity,
        "pe_ratio": pe,
        "operating_margin": op_margin,
        "free_cash_flow_positive": fcf_positive,
        "pledged_pct": pledged_pct,
        "promoter_holding": promoter_holding,
    }
    return info.get("shortName") or info.get("longName") or symbol, metrics


def main():
    print("Yahoo Finance NSE Fundamental Scan")
    print("Started:", datetime.now(timezone.utc).isoformat())
    print("Universe: NSE equity list; maximum symbols this run:", MAX_STOCKS)
    print("Note: Yahoo may omit ROCE, promoter holding, and pledged shares.")

    symbols_df = pd.read_csv(NSE_LIST_URL)
    symbol_col = "SYMBOL" if "SYMBOL" in symbols_df.columns else symbols_df.columns[0]
    symbols = (
        symbols_df[symbol_col].astype(str).str.strip()
        .replace("", pd.NA).dropna().drop_duplicates().tolist()
    )
    symbols = [s for s in symbols if s.replace(".", "").isalnum()]
    if MAX_STOCKS > 0:
        symbols = symbols[:MAX_STOCKS]

    rows = []
    errors = 0
    for index, symbol in enumerate(symbols, start=1):
        try:
            name, metrics = get_metrics(symbol)
            result = score_fundamentals(metrics)
            row = {
                "symbol": symbol,
                "name": name,
                **metrics,
                "score": result["score"],
                "grade": result["grade"],
                "shortlist": result["shortlist"],
                "missing_metrics": ", ".join(result["missing_metrics"]),
                "data_source": "Yahoo Finance via yfinance",
                "scan_utc": datetime.now(timezone.utc).isoformat(),
            }
            rows.append(row)
            print(f"[{index}/{len(symbols)}] {symbol}: score={result['score']} grade={result['grade']} shortlist={result['shortlist']} missing={len(result['missing_metrics'])}")
        except Exception as exc:
            errors += 1
            print(f"[{index}/{len(symbols)}] {symbol}: DATA ERROR: {exc}")
            rows.append({
                "symbol": symbol, "name": "", "score": 0, "grade": "D",
                "shortlist": False, "missing_metrics": "all_metrics_unavailable",
                "data_source": "Yahoo Finance via yfinance",
                "scan_utc": datetime.now(timezone.utc).isoformat(),
            })
        if PAUSE_SECONDS > 0:
            time.sleep(PAUSE_SECONDS)

    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["shortlist", "score"], ascending=[False, False])
    out.to_csv(OUTPUT, index=False)
    shortlist_count = int(out["shortlist"].fillna(False).sum()) if not out.empty else 0
    print(f"COMPLETE: scanned={len(symbols)}, errors={errors}, fully-populated shortlists={shortlist_count}")
    print(f"CSV saved to {OUTPUT}")


if __name__ == "__main__":
    main()
