# NSE Scanner & AI Options Dashboard

This repository contains the existing NSE scanners and a Streamlit dashboard UI for NIFTY options analysis.

## Run the dashboard locally

1. Install Python 3.10 or newer.
2. Install dependencies: `pip install -r requirements.txt`
3. Start the app: `streamlit run app.py`

The dashboard currently opens in offline/demo mode. It deliberately leaves market values blank until a valid FYERS connection is implemented and verified.

## Deploy on Streamlit Community Cloud

1. Sign in to https://share.streamlit.io/ with GitHub.
2. Choose this repository: `tushardhande51-byte/Nse-new-scanner`.
3. Select branch `main` and main file `app.py`.
4. Deploy the app.
5. Add FYERS credentials only in the app's private Secrets settings after the live integration is ready. Never commit API credentials or access tokens.

## Existing options scanner

`options_scanner.py` is retained. It currently uses FYERS history and option-chain endpoints and applies a strict 6/6 directional filter. Live dashboard integration is a separate next step; the earlier FYERS authentication error must be resolved and data validated before live signals are displayed.

## Safety

The dashboard is signal/research only. It does not place orders. Any future signal must be tested in paper trading before being considered for live use.
