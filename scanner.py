import os
from datetime import datetime, timedelta
import pandas as pd
from fyers_apiv3 import fyersModel

CLIENT_ID = os.environ.get('FYERS_CLIENT_ID')
ACCESS_TOKEN = os.environ.get('FYERS_ACCESS_TOKEN')
SYMBOLS = [s.strip() for s in os.environ.get('SYMBOLS', 'NSE:SBIN-EQ,NSE:RELIANCE-EQ,NSE:TCS-EQ').split(',') if s.strip()]


def fetch_history(fyers, symbol):
    end = datetime.now()
    start = end - timedelta(days=120)
    data = {
        'symbol': symbol,
        'resolution': 'D',
        'date_format': '1',
        'range_from': start.strftime('%Y-%m-%d'),
        'range_to': end.strftime('%Y-%m-%d'),
        'cont_flag': '1',
    }
    response = fyers.history(data=data)
    if response.get('s') != 'ok':
        print(f'{symbol}: history error: {response}')
        return pd.DataFrame()
    candles = response.get('candles', [])
    return pd.DataFrame(candles, columns=['timestamp','open','high','low','close','volume'])


def signal(df):
    if len(df) < 55:
        return None
    df['ema20'] = df.close.ewm(span=20, adjust=False).mean()
    df['ema50'] = df.close.ewm(span=50, adjust=False).mean()
    delta = df.close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, pd.NA)
    df['rsi'] = 100 - (100 / (1 + rs))
    df['avg_volume20'] = df.volume.rolling(20).mean()
    df['breakout_level'] = df.high.shift(1).rolling(20).max()
    last = df.iloc[-1]
    buy = (last.close > last.breakout_level and last.ema20 > last.ema50 and
           last.close > last.ema20 and 55 <= last.rsi <= 75 and
           last.volume >= 1.5 * last.avg_volume20)
    return {
        'signal': 'BUY' if buy else 'WAIT',
        'close': round(float(last.close), 2),
        'ema20': round(float(last.ema20), 2),
        'ema50': round(float(last.ema50), 2),
        'rsi': round(float(last.rsi), 2),
        'volume_ratio': round(float(last.volume / last.avg_volume20), 2) if last.avg_volume20 else None,
        'breakout_level': round(float(last.breakout_level), 2),
    }


def main():
    if not CLIENT_ID or not ACCESS_TOKEN:
        raise SystemExit('Missing FYERS_CLIENT_ID or FYERS_ACCESS_TOKEN GitHub secrets')
    fyers = fyersModel.FyersModel(client_id=CLIENT_ID, token=ACCESS_TOKEN, log_path='')
    print(f'Scan time: {datetime.now().isoformat()}')
    for symbol in SYMBOLS:
        result = signal(fetch_history(fyers, symbol))
        print(symbol, result or 'INSUFFICIENT DATA')


if __name__ == '__main__':
    main()
