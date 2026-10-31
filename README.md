# NSE Scanner & Free AI Options Dashboard

A free, manual-upload NIFTY/BANKNIFTY options-chain analyzer. It does not require a broker API, market-data API, or paid subscription.

## Run the dashboard

1. Install Python 3.10 or newer.
2. Install dependencies: `pip install -r requirements.txt`
3. Start: `streamlit run app.py`
4. In the sidebar, choose the index, upload the NSE Option Chain CSV, and optionally enter the current spot price.

## Get the CSV

1. Open the official NSE website: https://www.nseindia.com/option-chain
2. Choose the relevant index option chain.
3. Use the website's own CSV download control.
4. Upload the downloaded CSV into the dashboard.

The dashboard calculates PCR, total Call/Put OI, change in OI, volume comparison, largest Put OI strike (support reference), largest Call OI strike (resistance reference), and 11 transparent rule checks.

## Deploy free on Streamlit Community Cloud

1. Sign in at https://share.streamlit.io/ using GitHub.
2. Select repository `tushardhande51-byte/Nse-new-scanner`, branch `main`, file `app.py`.
3. Deploy. No secrets or API keys are required for CSV mode.

## Important limitations

- Data is only as fresh as the CSV you upload. It is not a live/auto-refreshing feed.
- The 11-check score is a rule-count indicator, not a statistically validated probability or guaranteed trading signal.
- A CSV does not provide a reliable live order book, live news, or all Greeks. Those features require other data sources.
- Use the dashboard for research and paper trading first. It does not place orders.
- Download CSV manually from NSE. Do not automate scraping or scripted downloading from NSE's website, and follow NSE website terms.

## Existing scanner

The existing `options_scanner.py` and equity scanner files are retained. The free dashboard CSV workflow is separate and does not call FYERS.
