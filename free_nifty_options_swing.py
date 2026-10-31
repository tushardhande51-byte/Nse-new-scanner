"""Free NIFTY 50 15m/1h options signal dashboard.

No broker, broker API, paid feed, order placement, or automated NSE scraping.
User supplies NIFTY OHLCV candle CSVs and an NSE option-chain CSV manually.
Missing/stale/insufficient inputs always result in NO TRADE.
"""
import re
from datetime import datetime, timedelta
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Free NIFTY Options Swing Engine", page_icon="📈", layout="wide")

def clean_name(x):
    return re.sub(r"[^a-z0-9]+", "", str(x).lower())

def read_candles(upload):
    d = pd.read_csv(upload)
    cols = {clean_name(c): c for c in d.columns}
    aliases = {
        "timestamp": ["timestamp", "datetime", "date", "time"],
        "open": ["open", "o"],
        "high": ["high", "h"],
        "low": ["low", "l"],
        "close": ["close", "ltp", "c"],
        "volume": ["volume", "vol", "v"],
    }
    found = {}
    for key, names in aliases.items():
        for name in names:
            if name in cols:
                found[key] = cols[name]
                break
        if key not in found:
            raise ValueError(f"Candle CSV mein {key.upper()} column nahi mila.")
    out = pd.DataFrame()
    out["timestamp"] = pd.to_datetime(d[found["timestamp"]], errors="coerce", dayfirst=True)
    for c in ["open", "high", "low", "close", "volume"]:
        out[c] = pd.to_numeric(d[found[c]].astype(str).str.replace(",", "", regex=False), errors="coerce")
    out = out.dropna().sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    if len(out) < 220:
        raise ValueError(f"Sirf {len(out)} candles mile. EMA200 ke liye kam-se-kam 220 candles chahiye.")
    return out

def read_chain(upload):
    raw = pd.read_csv(upload)
    raw.columns = [str(c).strip() for c in raw.columns]
    norm = [clean_name(c) for c in raw.columns]
    strike_idx = next((i for i, c in enumerate(norm) if "strike" in c), None)
    if strike_idx is None:
        raise ValueError("Option-chain CSV mein Strike Price column nahi mila.")
    def pick(side, field):
        # NSE CSV headers often have duplicate names with CE/PE prefixes or suffixes.
        tokens = {"oi": ["oi"], "change_oi": ["chginoi", "changeinoi"], "volume": ["volume"],
                  "iv": ["iv"], "ltp": ["ltp"], "bid": ["bid"], "ask": ["ask"]}
        candidates = []
        for i, name in enumerate(norm):
            if i == strike_idx:
                continue
            side_match = (name.startswith(side.lower()) or name.endswith(side.lower()) or side.lower() in name)
            if side_match and any(t in name for t in tokens[field]):
                candidates.append(raw.columns[i])
        if candidates:
            return candidates[0]
        # Standard NSE downloaded CSV has CE columns before Strike and PE columns after it.
        offset = {"oi": 0, "change_oi": 1, "volume": 2, "iv": 3, "ltp": 4, "bid": 7, "ask": 8}[field]
        idx = strike_idx - 10 + offset if side == "CE" else strike_idx + 1 + offset
        return raw.columns[idx] if 0 <= idx < len(raw.columns) else None
    out = pd.DataFrame()
    out["strike"] = pd.to_numeric(raw.iloc[:, strike_idx].astype(str).str.replace(",", "", regex=False), errors="coerce")
    for side in ["CE", "PE"]:
        for field in ["oi", "change_oi", "volume", "iv", "ltp", "bid", "ask"]:
            col = pick(side, field)
            out[f"{side}_{field}"] = pd.to_numeric(raw[col].astype(str).str.replace(",", "", regex=False).replace("-", "0"), errors="coerce") if col else 0
    out = out.dropna(subset=["strike"])
    out = out[out.strike > 0].copy()
    if out.empty:
        raise ValueError("Option-chain CSV mein valid strikes nahi mile.")
    return out.sort_values("strike").reset_index(drop=True)

def add_indicators(d):
    d = d.copy()
    c, h, l = d.close, d.high, d.low
    d["ema20"] = c.ewm(span=20, adjust=False).mean()
    d["ema50"] = c.ewm(span=50, adjust=False).mean()
    d["ema200"] = c.ewm(span=200, adjust=False).mean()
    delta = c.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    d["rsi"] = 100 - 100 / (1 + gain / loss.replace(0, float("nan")))
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    up, down = h.diff(), -l.diff()
    plus = up.where((up > down) & (up > 0), 0.0)
    minus = down.where((down > up) & (down > 0), 0.0)
    atr = tr.ewm(alpha=1/14, adjust=False).mean()
    pdi = 100 * plus.ewm(alpha=1/14, adjust=False).mean() / atr.replace(0, float("nan"))
    mdi = 100 * minus.ewm(alpha=1/14, adjust=False).mean() / atr.replace(0, float("nan"))
    dx = 100 * (pdi-mdi).abs() / (pdi+mdi).replace(0, float("nan"))
    d["adx"] = dx.ewm(alpha=1/14, adjust=False).mean()
    d["rvol"] = d.volume / d.volume.rolling(20).mean().replace(0, float("nan"))
    d["prior_high"] = h.shift(1).rolling(20).max()
    d["prior_low"] = l.shift(1).rolling(20).min()
    return d

def option_contract(chain, side, spot):
    candidates = []
    for _, row in chain.iterrows():
        ltp, bid, ask = row[f"{side}_ltp"], row[f"{side}_bid"], row[f"{side}_ask"]
        vol, iv = row[f"{side}_volume"], row[f"{side}_iv"]
        if pd.isna(ltp) or ltp <= 0 or pd.isna(vol) or vol <= 0:
            continue
        spread = (ask-bid)/ltp*100 if bid > 0 and ask >= bid else 999
        if spread > 2.5:
            continue
        # Near-ATM contract selection; delta is not present in standard NSE chain CSV.
        rank = abs(row.strike-spot)/spot*100 + spread*0.5
        candidates.append((rank, row, spread))
    if not candidates:
        return None
    _, row, spread = min(candidates, key=lambda x: x[0])
    return {"strike": float(row.strike), "ltp": float(row[f"{side}_ltp"]),
            "volume": int(row[f"{side}_volume"]), "iv": float(row[f"{side}_iv"]),
            "spread_pct": round(spread, 2), "oi": float(row[f"{side}_oi"]),
            "change_oi": float(row[f"{side}_change_oi"])}

def run_engine(c15, c60, chain, spot, snapshot_age):
    if snapshot_age > 20:
        return {"signal": "NO TRADE", "reason": "Option-chain snapshot 20 minute se purana hai."}
    m, h = add_indicators(c15), add_indicators(c60)
    a, b = m.iloc[-1], h.iloc[-1]
    if pd.isna(a.rsi) or pd.isna(a.adx) or pd.isna(a.rvol) or pd.isna(b.ema200):
        return {"signal": "NO TRADE", "reason": "Indicators calculate nahi hue; data insufficient hai."}
    call_oi, put_oi = chain.CE_oi.sum(), chain.PE_oi.sum()
    pcr = put_oi/call_oi if call_oi > 0 else 0
    bull = {
        "15m EMA20 > EMA50": bool(a.close > a.ema20 > a.ema50),
        "1h EMA20 > EMA50": bool(b.close > b.ema20 > b.ema50),
        "1h price > EMA200": bool(b.close > b.ema200),
        "15m RSI 52–70": bool(52 <= a.rsi <= 70),
        "15m ADX > 18": bool(a.adx > 18),
        "15m relative volume >= 1.2": bool(a.rvol >= 1.2),
        "20-candle breakout": bool(a.close > a.prior_high),
        "PCR >= 0.8": bool(pcr >= .8),
    }
    bear = {
        "15m EMA20 < EMA50": bool(a.close < a.ema20 < a.ema50),
        "1h EMA20 < EMA50": bool(b.close < b.ema20 < b.ema50),
        "1h price < EMA200": bool(b.close < b.ema200),
        "15m RSI 30–48": bool(30 <= a.rsi <= 48),
        "15m ADX > 18": bool(a.adx > 18),
        "15m relative volume >= 1.2": bool(a.rvol >= 1.2),
        "20-candle breakdown": bool(a.close < a.prior_low),
        "PCR <= 1.25": bool(pcr <= 1.25),
    }
    ce, pe = option_contract(chain, "CE", spot), option_contract(chain, "PE", spot)
    bull["liquid CALL contract"] = ce is not None
    bear["liquid PUT contract"] = pe is not None
    bs, ss = sum(bull.values()), sum(bear.values())
    signal, selected, checks = "NO TRADE", None, bull
    if bs >= 7 and bs > ss:
        signal, selected, checks = "CALL BUY", ce, bull
    elif ss >= 7 and ss > bs:
        signal, selected, checks = "PUT BUY", pe, bear
    result = {"signal": signal, "bull_score": f"{bs}/9", "bear_score": f"{ss}/9",
              "spot": round(float(spot), 2), "PCR": round(float(pcr), 2),
              "RSI_15m": round(float(a.rsi), 2), "ADX_15m": round(float(a.adx), 2),
              "RVOL_15m": round(float(a.rvol), 2), "checks": checks, "contract": selected}
    if selected and signal != "NO TRADE":
        entry = selected["ltp"]
        result.update({"entry": round(entry, 2), "stop_loss": round(entry*.75, 2),
                       "target_1": round(entry*1.30, 2), "target_2": round(entry*1.50, 2),
                       "note": "Provisional premium levels; not backtested or guaranteed."})
    return result

st.title("NIFTY 50 Options Swing Signal Engine")
st.caption("15-minute + 1-hour · Free CSV workflow · No broker/API · Signal only")
st.warning("Yeh live auto-feed nahi hai. NSE Option Chain aur NIFTY candles aapko manually CSV upload karne honge. NSE Option Chain ki terms follow karein; automated scraping nahi hoti.")
with st.expander("CSV data kahan se laayen?", expanded=True):
    st.markdown("- **Option Chain:** [NSE Option Chain](https://www.nseindia.com/option-chain) par NIFTY select karke CSV download karein.\n- **15m aur 1h NIFTY candles:** kisi free chart source se NIFTY 50 spot OHLCV CSV export karein. Dono files mein timestamp, open, high, low, close, volume columns hone chahiye.\n- CSV files mein kam-se-kam 220 candles chahiye. Option-chain snapshot 20 minute se purana ho to NO TRADE.")
c1,c2,c3 = st.columns(3)
with c1: f15 = st.file_uploader("NIFTY 15-minute candles CSV", type=["csv"])
with c2: f60 = st.file_uploader("NIFTY 1-hour candles CSV", type=["csv"])
with c3: fc = st.file_uploader("NSE NIFTY Option Chain CSV", type=["csv"])
spot = st.number_input("Current NIFTY Spot (CSV timestamp ke aas-paas)", min_value=0.0, value=0.0, step=1.0)
snapshot_age = st.number_input("Option-chain CSV kitne minute purana hai?", min_value=0, max_value=10000, value=0)
if st.button("Generate BUY / SELL Signal", type="primary", use_container_width=True):
    try:
        if not (f15 and f60 and fc) or spot <= 0:
            st.error("Koi bhi zaroori data missing hai — NO TRADE. 3 CSV aur current spot bharein.")
            st.metric("Signal", "NO TRADE")
        else:
            d15, d60, chain = read_candles(f15), read_candles(f60), read_chain(fc)
            result = run_engine(d15, d60, chain, spot, snapshot_age)
            st.subheader(result["signal"])
            if result["signal"] == "NO TRADE":
                st.info(result.get("reason", "Conditions fully match nahi hui."))
            else:
                a,b,c,d = st.columns(4)
                a.metric("Entry", result["entry"])
                b.metric("Stop Loss", result["stop_loss"])
                c.metric("Target 1", result["target_1"])
                d.metric("Target 2", result["target_2"])
                st.json(result["contract"])
            st.write("Bull score:", result.get("bull_score", "—"), "| Bear score:", result.get("bear_score", "—"))
            st.write("PCR:", result.get("PCR", "—"), "| RSI:", result.get("RSI_15m", "—"),
                     "| ADX:", result.get("ADX_15m", "—"), "| RVOL:", result.get("RVOL_15m", "—"))
            st.write("Rule checks")
            for k,v in result.get("checks", {}).items():
                st.write(("PASS" if v else "FAIL") + " — " + k)
            st.caption(result.get("note", "Research signal only. Backtest and paper trade first."))
    except Exception as e:
        st.error("Data read/validation failed: " + str(e))
        st.metric("Signal", "NO TRADE")
else:
    st.info("Data upload aur Generate button ke baad hi signal niklega. Missing/invalid data par NO TRADE.")
st.caption("No orders placed. No profit guarantee. Option buying mein premium loss, theta decay, IV change aur slippage ka risk hota hai.")
