"""NIFTY 50 options swing signal engine. Signal-only; never places orders."""
import os, json
from datetime import datetime, timedelta
import pandas as pd
from fyers_apiv3 import fyersModel

SYMBOL = "NSE:NIFTY50-INDEX"
MIN_SCORE = 7
MAX_SPREAD = 1.5

def candles(api, resolution, days):
    end = datetime.now()
    r = api.history(data={"symbol": SYMBOL, "resolution": str(resolution),
        "date_format": "1", "range_from": (end-timedelta(days=days)).strftime("%Y-%m-%d"),
        "range_to": end.strftime("%Y-%m-%d"), "cont_flag": "1"})
    if r.get("s") != "ok" or not r.get("candles"):
        raise RuntimeError("FYERS candle data unavailable: " + str(r))
    d = pd.DataFrame(r["candles"], columns=["ts","open","high","low","close","volume"])
    for c in ["open","high","low","close","volume"]: d[c] = pd.to_numeric(d[c], errors="coerce")
    return d.dropna().sort_values("ts").reset_index(drop=True)

def indicators(d):
    d=d.copy(); c,h,l=d.close,d.high,d.low
    d["ema20"]=c.ewm(span=20,adjust=False).mean()
    d["ema50"]=c.ewm(span=50,adjust=False).mean()
    d["ema200"]=c.ewm(span=200,adjust=False).mean()
    delta=c.diff(); gain=delta.clip(lower=0).ewm(alpha=1/14,adjust=False).mean()
    loss=(-delta.clip(upper=0)).ewm(alpha=1/14,adjust=False).mean()
    d["rsi"]=100-100/(1+gain/loss.replace(0,float("nan")))
    tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    up=h.diff(); dn=-l.diff()
    pdm=up.where((up>dn)&(up>0),0); mdm=dn.where((dn>up)&(dn>0),0)
    atr=tr.ewm(alpha=1/14,adjust=False).mean()
    pdi=100*pdm.ewm(alpha=1/14,adjust=False).mean()/atr
    mdi=100*mdm.ewm(alpha=1/14,adjust=False).mean()/atr
    dx=100*(pdi-mdi).abs()/(pdi+mdi).replace(0,float("nan"))
    d["adx"]=dx.ewm(alpha=1/14,adjust=False).mean()
    d["rvol"]=d.volume/d.volume.rolling(20).mean()
    d["prior_high"]=h.shift().rolling(20).max()
    d["prior_low"]=l.shift().rolling(20).min()
    return d

def n(x): 
    try: return float(x or 0)
    except (ValueError,TypeError): return 0.0

def spread(x):
    bid,ask,ltp=n(x.get("bid")),n(x.get("ask")),n(x.get("ltp"))
    return (ask-bid)/ltp*100 if bid>0 and ask>=bid and ltp>0 else 999

def option_pick(chain, side, spot):
    picks=[]
    for x in chain:
        g=x.get("greeks") or {}; delta=abs(n(g.get("delta")))
        if x.get("option_type")!=side or n(x.get("ltp"))<=0: continue
        sp=spread(x); vol=n(x.get("volume")); strike=n(x.get("strike_price"))
        if .35<=delta<=.70 and sp<=MAX_SPREAD and vol>0:
            score=abs(strike-spot)/spot*100+abs(delta-.5)*2+sp*.5
            picks.append((score,x))
    return min(picks,key=lambda z:z[0])[1] if picks else None

def get_chain(api):
    a=api.optionchain(data={"symbol":SYMBOL,"strikecount":10,"greeks":"1"})
    if a.get("s")!="ok": raise RuntimeError("FYERS option-chain unavailable: "+str(a))
    ex=a.get("data",{}).get("expiryData",[])
    if not ex: raise RuntimeError("No expiry returned by FYERS.")
    e=ex[0]
    b=api.optionchain(data={"symbol":SYMBOL,"strikecount":10,"timestamp":str(e["expiry"]),"greeks":"1"})
    if b.get("s")!="ok": raise RuntimeError("Expiry chain unavailable: "+str(b))
    return b.get("data",{}),e

def evaluate(c15,c60,data,expiry):
    m,h=indicators(c15),indicators(c60)
    if len(m)<220 or len(h)<220: raise RuntimeError("Need at least 220 candles in both timeframes.")
    a,b=m.iloc[-1],h.iloc[-1]
    chain=data.get("optionsChain",[])
    spot=next((n(x.get("ltp")) for x in chain if x.get("option_type","")=="" and n(x.get("ltp"))>0),n(a.close))
    coi,poi=n(data.get("callOi")),n(data.get("putOi")); pcr=poi/coi if coi>0 else 0
    bull={
      "15m EMA trend":bool(a.close>a.ema20>a.ema50),
      "1h EMA trend":bool(b.close>b.ema20>b.ema50),
      "above 1h EMA200":bool(b.close>b.ema200),
      "RSI 52-70":bool(52<=a.rsi<=70),
      "ADX above 18":bool(a.adx>18),
      "relative volume >=1.2":bool(a.rvol>=1.2),
      "20-bar breakout":bool(a.close>a.prior_high),
      "PCR not bearish":bool(pcr>=.8)}
    bear={
      "15m EMA trend":bool(a.close<a.ema20<a.ema50),
      "1h EMA trend":bool(b.close<b.ema20<b.ema50),
      "below 1h EMA200":bool(b.close<b.ema200),
      "RSI 30-48":bool(30<=a.rsi<=48),
      "ADX above 18":bool(a.adx>18),
      "relative volume >=1.2":bool(a.rvol>=1.2),
      "20-bar breakdown":bool(a.close<a.prior_low),
      "PCR not bullish":bool(pcr<=1.25)}
    ce,pe=option_pick(chain,"CE",spot),option_pick(chain,"PE",spot)
    bull["liquid CALL available"]=ce is not None
    bear["liquid PUT available"]=pe is not None
    bs,ss=sum(bull.values()),sum(bear.values())
    signal,leg,checks="NO TRADE",None,bull
    if bs>=MIN_SCORE and bs>ss: signal,leg,checks="CALL BUY",ce,bull
    elif ss>=MIN_SCORE and ss>bs: signal,leg,checks="PUT BUY",pe,bear
    out={"time":datetime.now().isoformat(timespec="seconds"),"signal":signal,
      "score":str(max(bs,ss))+"/9","bull_score":str(bs)+"/9","bear_score":str(ss)+"/9",
      "spot":round(spot,2),"expiry":expiry.get("date") or expiry.get("expiry"),
      "PCR":round(pcr,2),"RSI_15m":round(n(a.rsi),2),"ADX_15m":round(n(a.adx),2),
      "RVOL_15m":round(n(a.rvol),2),"checks":checks,"contract":None,
      "entry":None,"stop_loss":None,"target_1":None,"target_2":None,
      "warning":"Unvalidated research signal. Paper trade first; no orders are placed."}
    if leg:
        entry=n(leg.get("ltp"))
        out.update({"contract":leg.get("symbol"),"strike":leg.get("strike_price"),
          "entry":round(entry,2),"stop_loss":round(entry*.75,2),
          "target_1":round(entry*1.5,2),"target_2":round(entry*1.75,2),
          "spread_pct":round(spread(leg),2),"delta":n((leg.get("greeks") or {}).get("delta"))})
    return out

def main():
    cid,token=os.getenv("FYERS_CLIENT_ID"),os.getenv("FYERS_ACCESS_TOKEN")
    if not cid or not token: raise SystemExit("Set FYERS_CLIENT_ID and FYERS_ACCESS_TOKEN.")
    api=fyersModel.FyersModel(client_id=cid,token=token,is_async=False,log_path="")
    result=evaluate(candles(api,"15",90),candles(api,"60",365),*get_chain(api))
    print(json.dumps(result,indent=2,default=str))

if __name__=="__main__": main()
