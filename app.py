import os
import streamlit as st
import plotly.graph_objects as go
import pandas as pd

st.set_page_config(page_title="AI Options Analyzer", page_icon="📊", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 1rem; padding-bottom: 2rem; max-width: 1500px;}
[data-testid="stSidebar"] {background: #f5f7fb;}
.metric-card {background:#f7f8fb;border:1px solid #e5e8ef;border-radius:12px;padding:14px;text-align:center;}
.metric-label {font-size:11px;color:#667085;text-transform:uppercase;letter-spacing:.06em;}
.metric-value {font-size:25px;font-weight:700;color:#344054;margin-top:5px;}
.status {display:inline-block;padding:5px 10px;border-radius:20px;background:#fff4e5;color:#a15c00;font-size:12px;font-weight:700;}
.small-muted {color:#667085;font-size:12px;}
div[data-testid="stMetric"] {background:#f8f9fc;border:1px solid #e7eaf0;padding:12px;border-radius:10px;}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("## 🟢 Stockan · Live")
    st.caption("Market overview")
    index = st.selectbox("Select Index", ["NIFTY 50", "BANK NIFTY", "FINNIFTY", "MIDCPNIFTY"])
    st.divider()
    st.markdown("### Watchlist")
    for symbol in ["NIFTY", "BANKNIFTY", "RELIANCE", "HDFCBANK", "ICICIBANK", "SBIN"]:
        st.write("•", symbol)
    st.divider()
    st.caption("Data source: FYERS API")
    st.caption("Live connection: Not connected")

top1, top2, top3, top4 = st.columns([2.2, 1, 1, 1])
with top1:
    st.title("AI Options Analyzer")
    st.caption("Market sentiment · Options chain · Directional analysis")
with top2:
    st.metric("Selected Index", index)
with top3:
    st.metric("Market Status", "Awaiting data")
with top4:
    st.markdown('<span class="status">● DEMO / OFFLINE</span>', unsafe_allow_html=True)
    st.caption("No live prices are being shown")

tabs = st.tabs(["Option Chain", "Fundamentals", "AI Analysis"])
with tabs[0]:
    st.subheader("Options Chain")
    c1, c2, c3 = st.columns([1, 1, 2])
    c1.metric("Spot Price", "—")
    c2.metric("PCR", "—")
    c3.info("Connect FYERS to load the live option chain. No sample prices are presented as market data.")
    st.markdown("#### Calls · Puts")
    empty_chain = pd.DataFrame(columns=["CE OI", "CE Change OI", "CE Volume", "Strike", "PE Volume", "PE Change OI", "PE OI"])
    st.dataframe(empty_chain, use_container_width=True, hide_index=True)

with tabs[1]:
    st.subheader("Fundamentals")
    st.info("Fundamental stock filters belong to the separate equity scanner. This panel is reserved for index/underlying context.")

with tabs[2]:
    left, right = st.columns([1, 2.4])
    with left:
        st.markdown("#### Market direction")
        fig = go.Figure(go.Indicator(
            mode="gauge+number", value=0,
            number={"suffix":"%", "font":{"size":30}, "valueformat":".0f"},
            title={"text":"Directional confidence"},
            gauge={"axis":{"range":[0,100]}, "bar":{"color":"#667085"},
                   "steps":[{"range":[0,35],"color":"#fce8e8"},{"range":[35,65],"color":"#f2f4f7"},{"range":[65,100],"color":"#e4f4ed"}]}
        ))
        fig.update_layout(height=260, margin=dict(l=15,r=15,t=55,b=10), paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar":False})
        st.caption("Confidence will appear after valid market data is received.")
    with right:
        st.markdown("#### Parameters · 11")
        cards = st.columns(4)
        for col, label in zip(cards, ["Positive", "Neutral", "Negative", "Stretched"]):
            with col:
                st.metric(label, "—")
        st.markdown("#### Reversal watch")
        st.progress(0)
        st.caption("Waiting for price and options-chain confirmation.")
        st.markdown("#### Analysis by group")
        groups = ["Order book", "Option chain", "Price action", "Momentum (RSI)", "News"]
        for group in groups:
            a, b = st.columns([1, 4])
            a.write(group)
            b.progress(0)
        st.markdown("#### Market probability")
        p1, p2, p3 = st.columns(3)
        p1.metric("Bullish", "—")
        p2.metric("Bearish", "—")
        p3.metric("Volatile", "—")

st.divider()
st.subheader("Support and Resistance")
s1, s2, s3 = st.columns(3)
s1.metric("Support", "—")
s2.metric("Spot", "—")
s3.metric("Resistance", "—")
st.caption("All live fields remain blank until FYERS authentication and data validation succeed.")

with st.expander("Connection setup status"):
    has_client = bool(os.getenv("FYERS_CLIENT_ID"))
    has_token = bool(os.getenv("FYERS_ACCESS_TOKEN"))
    st.write("FYERS Client ID configured:", "Yes" if has_client else "No")
    st.write("FYERS Access Token configured:", "Yes" if has_token else "No")
    st.warning("Do not paste API keys or access tokens into chat or public GitHub files. Configure them only in the deployment platform's private Secrets settings.")
