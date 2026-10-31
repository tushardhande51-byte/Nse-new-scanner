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


## NIFTY 50 Options Swing Signal Engine (new)

New file: `nifty_options_engine.py`

This signal-only engine combines NIFTY spot candles on 15-minute and 1-hour timeframes with a FYERS option-chain snapshot. It checks EMA trend alignment, RSI, ADX, relative volume, 20-bar breakout/breakdown, PCR context, and option liquidity (delta, volume and bid/ask spread). It prints CALL BUY, PUT BUY, or NO TRADE with the selected contract and a provisional premium-based risk plan. It never places orders.

### Run it
```bash
pip install -r requirements.txt
export FYERS_CLIENT_ID="your_client_id"
export FYERS_ACCESS_TOKEN="your_access_token"
python nifty_options_engine.py
```
On Windows, set the two environment variables in the terminal before running. Keep credentials private; do not commit tokens to GitHub.

### Important validation notes
- FYERS access token must be valid and the account/API must return NIFTY history and option-chain data. If FYERS returns an error, the engine stops instead of fabricating a signal.
- The first version needs at least 220 candles on each timeframe for EMA200 calculations.
- The premium stop/targets (25% stop, 50%/75% targets) are provisional defaults, not proven settings. Configure and validate them through historical option-premium backtesting.
- A spot-index backtest alone is not a valid options backtest: option expiry, strike selection, bid/ask spread, IV, theta decay, slippage and brokerage must be represented.
- The score threshold is a research rule, not a win probability. Do not use real money until historical testing and paper trading show acceptable results.
