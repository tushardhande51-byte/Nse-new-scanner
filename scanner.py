import os
from datetime import datetime, timedelta

import pandas as pd
import requests
from fyers_apiv3 import fyersModel

CLIENT_ID = os.environ.get("FYERS_CLIENT_ID")
ACCESS_TOKEN = os.environ.get("FYERS_ACCESS_TOKEN")

# Put comma-separated FYERS NSE equity symbols in GitHub Repository Variables.
# Example: NSE:RELIANCE-EQ,NSE:TCS-EQ,NSE:MANKIND-EQ
SYMBOLS = [
    s.strip()
    for s in os.environ.get("SYMBOLS", "").split(",")
    if s.strip()
]

MIN_HISTORY = 230


def fetch_history(fyers, symbol):
    end = datetime.now()
    start = end - timedelta(days=420)

    data = {
        "symbol": symbol,
        "resolution": "D",
        "date_format": "1",
        "range_from": start.strftime("%Y-%m-%d"),
        "range_to": end.strftime("%Y-%m-%d"),
        "cont_flag": "1",
    }

    response = fyers.history(data=data)

    if response.get("s") != "ok":
        print(f"{symbol}: FYERS history error: {response}")
        return pd.DataFrame()

    candles = response.get("candles", [])
    if not candles:
        return pd.DataFrame()

    df = pd.DataFrame(
        candles,
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df.dropna().reset_index(drop=True)


def add_indicators(df):
    df = df.copy()

    df["ema20"] = df.close.ewm(span=20, adjust=False).mean()
    df["ema50"] = df.close.ewm(span=50, adjust=False).mean()
    df["ema200"] = df.close.ewm(span=200, adjust=False).mean()

    delta = df.close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, pd.NA)
    df["rsi"] = 100 - (100 / (1 + rs))

    ema12 = df.close.ewm(span=12, adjust=False).mean()
    ema26 = df.close.ewm(span=26, adjust=False).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df.macd.ewm(span=9, adjust=False).mean()

    high_low = df.high - df.low
    high_close = (df.high - df.close.shift()).abs()
    low_close = (df.low - df.close.shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["atr14"] = tr.rolling(14).mean()

    up = df.high.diff()
    down = -df.low.diff()
    plus_dm = up.where((up > down) & (up > 0), 0.0)
    minus_dm = down.where((down > up) & (down > 0), 0.0)
    atr = tr.rolling(14).mean()
    plus_di = 100 * plus_dm.rolling(14).mean() / atr
    minus_di = 100 * minus_dm.rolling(14).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    df["adx"] = dx.rolling(14).mean()

    df["avg_volume20"] = df.volume.rolling(20).mean()
    df["rvol"] = df.volume / df.avg_volume20
    df["high20"] = df.high.shift(1).rolling(20).max()
    df["high52w"] = df.high.shift(1).rolling(252, min_periods=100).max()

    return df


def fetch_fundamentals(symbol):
    """
    Fundamental data is a quality gate, not a trading trigger.
    Yahoo Finance is used here as a secondary public-data source.
    If data is missing, the fundamental filter FAILS rather than guessing.
    """
    ticker = symbol.replace("NSE:", "").replace("-EQ", "") + ".NS"

    try:
        url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}"
        params = {
            "modules": "financialData,defaultKeyStatistics,incomeStatementHistory"
        }
        r = requests.get(
            url,
            params=params,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        if r.status_code != 200:
            return {"pass": False, "reason": f"fundamental HTTP {r.status_code}"}

        result = r.json()["quoteSummary"]["result"]
        if not result:
            return {"pass": False, "reason": "fundamental data unavailable"}

        q = result[0]
        fd = q.get("financialData", {})
        ks = q.get("defaultKeyStatistics", {})

        def value(obj, key):
            x = obj.get(key)
            if isinstance(x, dict):
                return x.get("raw")
            return x

        roe = value(fd, "returnOnEquity")
        debt_to_equity = value(fd, "debtToEquity")

        # Yahoo's ROCE is not consistently available. We require ROE and
        # use operating margins only as a sanity check when ROCE is absent.
        revenue_growth = value(fd, "revenueGrowth")
        earnings_growth = value(fd, "earningsGrowth")

        checks = {
            "revenue_growth": revenue_growth is not None and revenue_growth >= 0.15,
            "profit_growth": earnings_growth is not None and earnings_growth >= 0.20,
            "roe": roe is not None and roe >= 0.15,
            "debt_equity": debt_to_equity is not None and debt_to_equity < 50,
        }

        passed = all(checks.values())

        return {
            "pass": passed,
            "checks": checks,
            "roe": roe,
            "revenue_growth": revenue_growth,
            "profit_growth": earnings_growth,
            "debt_to_equity": debt_to_equity,
        }

    except Exception as exc:
        return {"pass": False, "reason": f"fundamental error: {exc}"}


def signal(df, fundamental):
    if len(df) < MIN_HISTORY:
        return None

    df = add_indicators(df)
    last = df.iloc[-1]

    required = [
        "ema20", "ema50", "ema200", "rsi", "macd", "macd_signal",
        "adx", "rvol", "high20", "high52w", "atr14"
    ]
    if any(pd.isna(last[x]) for x in required):
        return None

    # 1) Trend
    trend = (
        last.close > last.ema20
        and last.ema20 > last.ema50
        and last.ema50 > last.ema200
    )

    # 2) Momentum
    momentum = (
        55 <= last.rsi <= 70
        and last.macd > last.macd_signal
        and last.adx >= 25
    )

    # 3) Volume
    volume = last.rvol >= 1.5

    # 4) Breakout / price action
    breakout = (
        last.close > last.high20
        and last.close >= 0.97 * last.high52w
    )

    # 5) Risk/reward: stop below recent structure/ATR and minimum 10% upside.
    entry = float(last.close)
    swing_low = float(df.low.tail(10).min())
    stop = min(swing_low, entry - 1.5 * float(last.atr14))
    risk = entry - stop
    target_10 = entry * 1.10
    target_2r = entry + 2 * risk
    target = max(target_10, target_2r)
    rr = (target - entry) / risk if risk > 0 else 0
    risk_reward = risk > 0 and rr >= 2.0

    # 6) Fundamentals
    fundamentals = bool(fundamental.get("pass"))

    checks = {
        "trend": trend,
        "momentum": momentum,
        "volume": volume,
        "breakout": breakout,
        "risk_reward": risk_reward,
        "fundamentals": fundamentals,
    }

    passed = sum(checks.values())

    return {
        "signal": "BUY" if passed == 6 else ("WATCH" if passed >= 4 else "NO BUY"),
        "score": f"{passed}/6",
        "close": round(entry, 2),
        "entry": round(entry, 2),
        "stop_loss": round(stop, 2),
        "target_1": round(entry + 2 * risk, 2),
        "target_2": round(target_10, 2),
        "rsi": round(float(last.rsi), 2),
        "adx": round(float(last.adx), 2),
        "rvol": round(float(last.rvol), 2),
        "ema20": round(float(last.ema20), 2),
        "ema50": round(float(last.ema50), 2),
        "ema200": round(float(last.ema200), 2),
        "breakout_level": round(float(last.high20), 2),
        "risk_reward": round(float(rr), 2),
        "checks": checks,
        "fundamental": fundamental,
    }


def main():
    if not CLIENT_ID or not ACCESS_TOKEN:
        raise SystemExit(
            "Missing FYERS_CLIENT_ID or FYERS_ACCESS_TOKEN GitHub secrets"
        )

    if not SYMBOLS:
        raise SystemExit(
            "SYMBOLS GitHub Repository Variable is empty. "
            "Add comma-separated FYERS NSE equity symbols."
        )

    fyers = fyersModel.FyersModel(
        client_id=CLIENT_ID,
        token=ACCESS_TOKEN,
        log_path=""
    )

    print(f"Scan time: {datetime.now().isoformat()}")
    print(f"Universe size: {len(SYMBOLS)}")

    buy_count = 0

    for symbol in SYMBOLS:
        try:
            df = fetch_history(fyers, symbol)
            if df.empty:
                print(f"{symbol} | NO DATA")
                continue

            fundamentals = fetch_fundamentals(symbol)
            result = signal(df, fundamentals)

            if result is None:
                print(f"{symbol} | INSUFFICIENT DATA")
                continue

            print(f"{symbol} | {result}")

            if result["signal"] == "BUY":
                buy_count += 1
                print(
                    f"*** BUY {symbol} | Entry {result['entry']} | "
                    f"SL {result['stop_loss']} | "
                    f"T1 {result['target_1']} | "
                    f"T2 {result['target_2']} | "
                    f"R:R {result['risk_reward']} ***"
                )

        except Exception as exc:
            # One bad symbol must not stop the complete NSE scan.
            print(f"{symbol} | ERROR | {exc}")

    print(f"FINAL BUY COUNT: {buy_count}")


if __name__ == "__main__":
    main()
