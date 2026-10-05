import os
from datetime import datetime, timedelta

import pandas as pd
from fyers_apiv3 import fyersModel

CLIENT_ID = os.environ.get("FYERS_CLIENT_ID")
ACCESS_TOKEN = os.environ.get("FYERS_ACCESS_TOKEN")

UNDERLYING = "NSE:NIFTY50-INDEX"
STRIKECOUNT = 10


def fetch_history(fyers):
    end = datetime.now()
    start = end - timedelta(days=10)
    data = {
        "symbol": UNDERLYING,
        "resolution": "15",
        "date_format": "1",
        "range_from": start.strftime("%Y-%m-%d"),
        "range_to": end.strftime("%Y-%m-%d"),
        "cont_flag": "1",
    }
    r = fyers.history(data=data)
    if r.get("s") != "ok" or not r.get("candles"):
        print("NIFTY history error:", r)
        return pd.DataFrame()

    df = pd.DataFrame(
        r["candles"],
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna().reset_index(drop=True)


def indicators(df):
    df = df.copy()
    df["ema20"] = df.close.ewm(span=20, adjust=False).mean()
    df["ema50"] = df.close.ewm(span=50, adjust=False).mean()

    delta = df.close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, pd.NA)
    df["rsi"] = 100 - (100 / (1 + rs))

    df["avg_volume20"] = df.volume.rolling(20).mean()
    df["rvol"] = df.volume / df.avg_volume20
    df["prev20_high"] = df.high.shift(1).rolling(20).max()
    df["prev20_low"] = df.low.shift(1).rolling(20).min()
    return df


def get_chain(fyers):
    first = fyers.optionchain(
        data={"symbol": UNDERLYING, "strikecount": STRIKECOUNT, "greeks": "1"}
    )
    if first.get("s") != "ok":
        print("Option-chain error:", first)
        return None

    data = first.get("data", {})
    expiries = data.get("expiryData", [])
    if not expiries:
        print("No NIFTY expiry returned.")
        return None

    # Nearest available expiry. We intentionally do not hard-code a date.
    expiry = expiries[0]
    second = fyers.optionchain(
        data={
            "symbol": UNDERLYING,
            "strikecount": STRIKECOUNT,
            "timestamp": str(expiry["expiry"]),
            "greeks": "1",
        }
    )
    if second.get("s") != "ok":
        print("Selected-expiry option-chain error:", second)
        return None

    return second.get("data", {}), expiry


def pct_spread(row):
    bid = float(row.get("bid") or 0)
    ask = float(row.get("ask") or 0)
    ltp = float(row.get("ltp") or 0)
    if bid <= 0 or ask <= 0 or ltp <= 0:
        return 999.0
    return (ask - bid) / ltp * 100


def choose_option(chain, side, spot):
    legs = [
        x for x in chain
        if x.get("option_type") == side
        and float(x.get("ltp") or 0) > 0
        and float(x.get("volume") or 0) > 0
    ]
    if not legs:
        return None

    # Prefer near-ATM contracts with usable delta and liquidity.
    def score(x):
        strike = float(x.get("strike_price") or 0)
        delta = float((x.get("greeks") or {}).get("delta") or 0)
        abs_delta = abs(delta)
        distance = abs(strike - spot) / spot * 100
        spread = pct_spread(x)
        delta_penalty = abs(abs_delta - 0.50) * 100
        return distance * 5 + delta_penalty + spread * 2

    candidates = [
        x for x in legs
        if 0.35 <= abs(float((x.get("greeks") or {}).get("delta") or 0)) <= 0.70
        and pct_spread(x) <= 2.5
    ]
    if not candidates:
        candidates = legs

    return min(candidates, key=score)


def evaluate(df, data):
    if len(df) < 55:
        return None

    df = indicators(df)
    last = df.iloc[-1]

    spot = next(
        float(x["ltp"]) for x in data["optionsChain"]
        if x.get("option_type", "") == ""
    )

    call_oi = float(data.get("callOi") or 0)
    put_oi = float(data.get("putOi") or 0)
    pcr = put_oi / call_oi if call_oi > 0 else 0

    # Underlying 6/6 direction filters.
    bullish = {
        "trend": bool(last.close > last.ema20 > last.ema50),
        "rsi": bool(55 <= last.rsi <= 70),
        "volume": bool(last.rvol >= 1.20),
        "breakout": bool(last.close > last.prev20_high),
        "pcr": bool(0.80 <= pcr <= 1.20),
    }
    bearish = {
        "trend": bool(last.close < last.ema20 < last.ema50),
        "rsi": bool(30 <= last.rsi <= 45),
        "volume": bool(last.rvol >= 1.20),
        "breakdown": bool(last.close < last.prev20_low),
        "pcr": bool(0.80 <= pcr <= 1.20),
    }

    call = choose_option(data["optionsChain"], "CE", spot)
    put = choose_option(data["optionsChain"], "PE", spot)

    # Sixth filter is option confirmation: OI + volume + positive premium momentum.
    def option_confirmation(leg, direction):
        if not leg:
            return False
        ltp = float(leg.get("ltp") or 0)
        ltpchp = float(leg.get("ltpchp") or 0)
        oichp = float(leg.get("oichp") or 0)
        volume = float(leg.get("volume") or 0)
        oi = float(leg.get("oi") or 0)
        spread = pct_spread(leg)
        iv = float((leg.get("greeks") or {}).get("iv") or 0)

        return (
            ltp > 0
            and ltpchp > 0
            and oichp > 0
            and volume > 0
            and oi > 0
            and spread <= 2.5
            and iv > 0
        )

    call_ok = option_confirmation(call, "CE")
    put_ok = option_confirmation(put, "PE")

    bull_checks = {**bullish, "option_confirmation": call_ok}
    bear_checks = {**bearish, "option_confirmation": put_ok}

    bull_score = sum(bull_checks.values())
    bear_score = sum(bear_checks.values())

    if bull_score == 6:
        signal = "CALL BUY"
        leg = call
        checks = bull_checks
    elif bear_score == 6:
        signal = "PUT BUY"
        leg = put
        checks = bear_checks
    else:
        signal = "NO TRADE"
        leg = call if bull_score >= bear_score else put
        checks = bull_checks if bull_score >= bear_score else bear_checks

    result = {
        "signal": signal,
        "score": f"{max(bull_score, bear_score)}/6",
        "spot": round(spot, 2),
        "pcr": round(pcr, 2),
        "expiry": None,
        "option": None,
        "entry": None,
        "stop_loss": None,
        "target_1": None,
        "target_2": None,
        "checks": checks,
        "rsi": round(float(last.rsi), 2),
        "rvol": round(float(last.rvol), 2),
        "ema20": round(float(last.ema20), 2),
        "ema50": round(float(last.ema50), 2),
    }

    if leg:
        ltp = float(leg.get("ltp") or 0)
        result["option"] = leg.get("symbol")
        result["strike"] = leg.get("strike_price")
        result["entry"] = round(ltp, 2)
        result["option_ltp_change_pct"] = round(float(leg.get("ltpchp") or 0), 2)
        result["oi_change_pct"] = round(float(leg.get("oichp") or 0), 2)
        result["volume"] = int(float(leg.get("volume") or 0))
        result["iv"] = round(float((leg.get("greeks") or {}).get("iv") or 0), 2)
        result["delta"] = round(float((leg.get("greeks") or {}).get("delta") or 0), 3)
        result["spread_pct"] = round(pct_spread(leg), 2)

        if signal != "NO TRADE":
            # Premium-based risk model for buying options.
            sl = ltp * 0.70
            t1 = ltp * 1.30
            t2 = ltp * 1.50
            result["stop_loss"] = round(sl, 2)
            result["target_1"] = round(t1, 2)
            result["target_2"] = round(t2, 2)

    return result


def main():
    if not CLIENT_ID or not ACCESS_TOKEN:
        raise SystemExit("Missing FYERS_CLIENT_ID or FYERS_ACCESS_TOKEN.")

    fyers = fyersModel.FyersModel(
        client_id=CLIENT_ID,
        token=ACCESS_TOKEN,
        is_async=False,
        log_path="",
    )

    print("=" * 60)
    print("NIFTY 50 OPTIONS SCANNER | STRICT 6/6")
    print("Scan time:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 60)

    df = fetch_history(fyers)
    if df.empty:
        raise SystemExit("No NIFTY history data.")

    chain_result = get_chain(fyers)
    if not chain_result:
        raise SystemExit("No option-chain data.")

    data, expiry = chain_result
    result = evaluate(df, data)
    result["expiry"] = expiry.get("date") or expiry.get("expiry")

    print(result)

    if result["signal"] == "CALL BUY":
        print(
            f"\n🟢 NIFTY CALL BUY | {result['option']} | "
            f"Entry ₹{result['entry']} | SL ₹{result['stop_loss']} | "
            f"T1 ₹{result['target_1']} | T2 ₹{result['target_2']}"
        )
    elif result["signal"] == "PUT BUY":
        print(
            f"\n🔴 NIFTY PUT BUY | {result['option']} | "
            f"Entry ₹{result['entry']} | SL ₹{result['stop_loss']} | "
            f"T1 ₹{result['target_1']} | T2 ₹{result['target_2']}"
        )
    else:
        print("\n⚪ NO TRADE — strict 6/6 condition not met.")

    print("\nFINAL SIGNAL:", result["signal"], "|", result["score"])


if __name__ == "__main__":
    main()
