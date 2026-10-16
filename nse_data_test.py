"""Check whether GitHub Actions can reach official NSE public pages/data files.

This is a connectivity test only; it does not scrape or score stocks.
"""
from datetime import datetime, timezone
import requests

URLS = {
    "nse_home": "https://www.nseindia.com/",
    "equity_list_csv": "https://archives.nseindia.com/content/equities/EQUITY_L.csv",
    "shareholding_page": "https://www.nseindia.com/companies-listing/corporate-filings-shareholding-pattern",
    "pledged_data_page": "https://www.nseindia.com/companies-listing/corporate-filings-pledged-data",
    "financial_results_page": "https://www.nseindia.com/companies-listing/corporate-filings-financial-results",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

def main():
    print("NSE OFFICIAL DATA CONNECTIVITY TEST")
    print("UTC:", datetime.now(timezone.utc).isoformat())
    session = requests.Session()
    session.headers.update(HEADERS)

    # Establish cookies from NSE homepage before requesting its filing pages.
    try:
        home = session.get(URLS["nse_home"], timeout=25)
        print(f"nse_home: HTTP {home.status_code}; content_type={home.headers.get('content-type', '')}; bytes={len(home.content)}")
    except Exception as exc:
        print(f"nse_home: ERROR {type(exc).__name__}: {exc}")

    passed = 0
    for name, url in URLS.items():
        if name == "nse_home":
            continue
        try:
            response = session.get(url, timeout=25, allow_redirects=True)
            content_type = response.headers.get("content-type", "")
            body = response.text[:180].replace("\\n", " ").replace("\\r", " ")
            ok = response.status_code == 200 and len(response.content) > 100
            passed += int(ok)
            print(f"{name}: {'PASS' if ok else 'CHECK'}; HTTP {response.status_code}; content_type={content_type}; bytes={len(response.content)}; preview={body!r}")
            if name == "equity_list_csv" and ok:
                print("equity_list_csv_header:", response.text.splitlines()[0][:250] if response.text.splitlines() else "(empty)")
        except Exception as exc:
            print(f"{name}: ERROR {type(exc).__name__}: {exc}")

    print(f"TEST COMPLETE: {passed}/4 target URLs returned HTTP 200 with a non-empty response.")
    print("Note: a reachable filing page does not by itself prove its dynamic table/API data is available.")
if __name__ == "__main__":
    main()
