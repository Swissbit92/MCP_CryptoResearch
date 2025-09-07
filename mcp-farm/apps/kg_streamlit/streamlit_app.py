import os, json
import streamlit as st
from pathlib import Path

# Minimal: import the store directly (local-first)
from mcp_kg.kg_store import KGStore, KGConfig

st.set_page_config(page_title="Strategy KG", layout="wide")

cfg = KGConfig()
store = KGStore(cfg)

st.sidebar.header("Search")
indicators = st.sidebar.multiselect("Indicators", ["RSI","MACD","ATR","SMA","EMA"])
timeframe = st.sidebar.selectbox("Timeframe", ["","1h","4h","1d"])
universe = st.sidebar.text_input("Universe (comma)", value="BTCUSDT")
limit = st.sidebar.slider("Limit", 1, 100, 20)

search_btn = st.sidebar.button("Search")

def render_card(card):
    st.subheader(card["name"])
    st.caption(f"Signature: `{card['signature']}` • Timeframe: {card['timeframe']}")
    with st.expander("Show JSON-LD"):
        data = store.get_strategy_by_signature(card["signature"])
        st.code(json.dumps(json.loads(data), indent=2), language="json")

if search_btn:
    uni = [u.strip() for u in universe.split(",") if u.strip()] if universe else None
    tf = timeframe or None
    hits = store.search_strategies(indicators, tf, uni, limit)
    st.write(f"**{len(hits)}** result(s)")
    for h in hits:
        render_card(h)
else:
    st.info("Use the left sidebar to search by indicators / timeframe / universe.")
