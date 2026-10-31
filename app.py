import io
import re
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

st.set_page_config(page_title="AI Options Dashboard", page_icon="📊", layout="wide")

st.markdown("""
<style>
.block-container{padding-top:1rem;padding-bottom:2rem;max-width:1500px}
[data-testid="stSidebar"]{background:#f5f7fb}
div[data-testid="stMetric"]{background:#f8f9fc;border:1px solid #e7eaf0;padding:12px;border-radius:10px}
.small-muted{color:#667085;font-size:12px}
</style>
""", unsafe_allow_html=True)

def norm(s):
    return re.sub(r"[^A-Z0-9]+", " ", str(s).upper()).strip()

def read_option_csv(upload):
    raw = pd.read_csv(upload)
    raw.columns = [str(c).strip() for c in raw.columns]
    names = [norm(c) for c in raw.columns]
    strike_candidates = [i for i,n in enumerate(names) if "STRIKE" in n]
    if not strike_candidates:
        raise ValueError("Strike Price column nahi mila. NSE Option Chain ka original CSV upload karein.")
    si = strike_candidates[0]
    def find_col(prefix, words, fallback=None):
        for i,n in enumerate(names):
            if i == si: continue
            if prefix in n and any(w in n for w in words): return raw.columns[i]
        if fallback is not None and 0 <= fallback < len(raw.columns): return raw.columns[fallback]
        return None
    # Supports both clearly named CE/PE CSVs and NSE's standard left/right column layout.
    mapping = {
        "CE OI": find_col("CE", ["OI"], si-11),
        "CE CHNG IN OI": find_col("CE", ["CHNG IN OI","CHANGE IN OI"], si-10),
        "CE VOLUME": find_col("CE", ["VOLUME"], si-9),
        "CE IV": find_col("CE", ["IV"], si-8),
        "CE LTP": find_col("CE", ["LTP"], si-7),
        "PE OI": find_col("PE", ["OI"], si+10),
        "PE CHNG IN OI": find_col("PE", ["CHNG IN OI","CHANGE IN OI"], si+9),
        "PE VOLUME": find_col("PE", ["VOLUME"], si+8),
        "PE IV": find_col("PE", ["IV"], si+7),
        "PE LTP": find_col("PE", ["LTP"], si+6),
    }
    out = pd.DataFrame()
    out["STRIKE"] = pd.to_numeric(raw.iloc[:,si].astype(str).str.replace(",","",regex=False), errors="coerce")
    for target, source in mapping.items():
        if source is not None:
            out[target] = pd.to_numeric(raw[source].astype(str).str.replace(",","",regex=False).str.replace("-","",regex=False), errors="coerce")
        else:
            out[target] = 0
    out = out.dropna(subset=["STRIKE"])
    out = out[(out["STRIKE"] > 0)].copy()
    if out.empty: raise ValueError("CSV mein valid strike data nahi mila.")
    for c in mapping: out[c] = out[c].fillna(0)
    return out.sort_values("STRIKE").reset_index(drop=True)

def analyse(df, spot):
    ceoi, peoi = df["CE OI"].sum(), df["PE OI"].sum()
    ceco, peco = df["CE CHNG IN OI"].sum(), df["PE CHNG IN OI"].sum()
    cevol, pevol = df["CE VOLUME"].sum(), df["PE VOLUME"].sum()
    pcr = peoi / ceoi if ceoi else 0
    support_row = df.loc[df["PE OI"].idxmax()]
    resistance_row = df.loc[df["CE OI"].idxmax()]
    near = df.iloc[(df["STRIKE"]-spot).abs().argsort()[:1]].iloc[0] if spot else None
    checks = [
        ("PCR above 1", pcr > 1, "Put OI call OI se zyada"),
        ("Put OI stronger", peoi > ceoi, "Total put open interest"),
        ("Put writing stronger", peco > ceco, "Change in OI comparison"),
        ("Put volume stronger", pevol > cevol, "Put vs call volume"),
        ("Support OI wall", support_row["STRIKE"] < spot if spot else False, "Spot ke neeche highest put OI"),
        ("Resistance OI wall", resistance_row["STRIKE"] > spot if spot else False, "Spot ke upar highest call OI"),
        ("PCR bullish zone", pcr >= 1.2, "PCR 1.20 ya usse zyada"),
        ("PCR bearish zone", pcr <= 0.8, "PCR 0.80 ya usse kam"),
        ("Put OI addition", peco > 0, "Put side OI mein addition"),
        ("Call OI unwinding", ceco < 0, "Call side OI mein reduction"),
        ("Put volume dominance", pevol > cevol*1.1, "Put volume 10% se zyada"),
    ]
    positive = sum(1 for _,v,_ in checks if v)
    negative = sum(1 for _,v,_ in checks if not v)
    score = round(positive/len(checks)*100)
    if pcr >= 1.2 and peco > ceco: bias = "BULLISH"
    elif pcr <= .8 and ceco > peco: bias = "BEARISH"
    else: bias = "NEUTRAL / MIXED"
    return {"pcr":pcr,"ceoi":ceoi,"peoi":peoi,"ceco":ceco,"peco":peco,"cevol":cevol,"pevol":pevol,
            "support":float(support_row["STRIKE"]),"resistance":float(resistance_row["STRIKE"]),
            "score":score,"bias":bias,"checks":checks,"positive":positive,"negative":negative}

with st.sidebar:
    st.markdown("## 📊 AI Options Dashboard")
    index = st.selectbox("Select Index", ["NIFTY 50","BANK NIFTY","FINNIFTY","MIDCPNIFTY"])
    st.markdown("---")
    st.markdown("### Upload market data")
    upload = st.file_uploader("NSE Option Chain CSV", type=["csv"])
    spot = st.number_input("Current Spot Price (optional)", min_value=0.0, value=0.0, step=1.0)
    st.caption("NSE website se CSV manually download karke yahan upload karein.")
    st.markdown("---")
    st.caption("FREE MODE · No broker API · No paid data API")

st.title("AI Options Dashboard")
st.caption("Option Chain · OI Analysis · Market Sentiment · Support & Resistance")
if not upload:
    st.info("Shuru karne ke liye NSE Option Chain CSV upload karein. Live market values tab tak blank rahengi.")
    st.markdown("**CSV kaise milegi:** NSE website → Option Chain → Index select karein → Download CSV → yahan upload karein.")
    st.markdown("No API key, broker login, subscription, ya automated website scraping required.")
    st.stop()

try:
    df = read_option_csv(upload)
    stats = analyse(df, spot if spot > 0 else None)
except Exception as e:
    st.error(f"CSV read nahi ho payi: {e}")
    st.stop()

st.success(f"CSV loaded: {len(df)} strike rows · {index}")
st.caption("Analysis uploaded CSV ke snapshot par based hai; yeh real-time feed nahi hai.")
tabs = st.tabs(["AI Analysis","Option Chain","How to read"])
with tabs[0]:
    a,b,c,d = st.columns(4)
    a.metric("Market Bias",stats["bias"])
    b.metric("PCR",f'{stats["pcr"]:.2f}')
    c.metric("Positive checks",f'{stats["positive"]}/11')
    d.metric("Directional score",f'{stats["score"]}%')
    l,r = st.columns([1,2])
    with l:
        fig=go.Figure(go.Indicator(mode="gauge+number",value=stats["score"],number={"suffix":"%"},
            title={"text":"11-Check Score"},gauge={"axis":{"range":[0,100]},
            "steps":[{"range":[0,35],"color":"#fce8e8"},{"range":[35,65],"color":"#f2f4f7"},{"range":[65,100],"color":"#e4f4ed"}]}))
        fig.update_layout(height=260,margin=dict(l=15,r=15,t=55,b=10))
        st.plotly_chart(fig,use_container_width=True,config={"displayModeBar":False})
    with r:
        st.subheader("11 AI rule checks")
        for name, passed, detail in stats["checks"]:
            st.write(("🟢 " if passed else "⚪ ")+f"**{name}** — {detail}")
    st.subheader("Support & Resistance")
    x,y,z=st.columns(3)
    x.metric("Put OI Support",f'{stats["support"]:,.0f}')
    y.metric("Spot",f'{spot:,.2f}' if spot else "Not entered")
    z.metric("Call OI Resistance",f'{stats["resistance"]:,.0f}')
    st.subheader("Market participation")
    x,y,z=st.columns(3)
    x.metric("Call OI",f'{stats["ceoi"]:,.0f}')
    y.metric("Put OI",f'{stats["peoi"]:,.0f}')
    z.metric("PCR",f'{stats["pcr"]:.2f}')
    st.caption("Score ek rule-count indicator hai, guaranteed probability ya buy/sell recommendation nahi.")
with tabs[1]:
    st.subheader("Uploaded Option Chain")
    st.dataframe(df,use_container_width=True,hide_index=True)
    st.download_button("Download analysed CSV",df.to_csv(index=False).encode("utf-8"),"analysed_option_chain.csv","text/csv")
with tabs[2]:
    st.markdown("""
- **PCR:** Put OI ÷ Call OI. Isse market positioning ka ek rough idea milta hai.
- **Support:** Sabse zyada Put OI wala strike.
- **Resistance:** Sabse zyada Call OI wala strike.
- **11 checks:** Uploaded CSV ke OI, change in OI aur volume se simple rule-based analysis.
- **Limitations:** CSV purana ho sakta hai; IV/Greeks/news/order-book/live price is file se reliable tarike se nahi milte.
- **Use:** Pehle paper trading mein test karein. Yeh financial advice ya guaranteed signal nahi hai.
""")
