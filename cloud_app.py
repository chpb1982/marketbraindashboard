
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import time

# ─── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="MarketBrain Command Centre (Cloud)",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Global CSS (Consistent with Local Dashboard) ──────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background: linear-gradient(135deg, #0a0e1a 0%, #0d1526 50%, #0a1020 100%); }
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0d1526 0%, #111827 100%);
    border-right: 1px solid rgba(59,130,246,0.2);
}
[data-testid="metric-container"] {
    background: rgba(15,23,42,0.8);
    border: 1px solid rgba(59,130,246,0.25);
    border-radius: 12px;
    padding: 16px 20px;
}
[data-testid="stMetricValue"] { color: #60a5fa !important; font-weight: 700 !important; }
[data-testid="stMetricLabel"] { color: #94a3b8 !important; font-size: 0.8rem !important; }
[data-testid="stDataFrame"] { border: 1px solid rgba(59,130,246,0.2); border-radius: 10px; overflow: hidden; }
.badge-live   { background:linear-gradient(135deg,#10b981,#059669);color:#fff;padding:3px 10px;border-radius:20px;font-size:0.75rem;font-weight:600; }
.badge-historic { background:linear-gradient(135deg,#64748b,#475569);color:#fff;padding:3px 10px;border-radius:20px;font-size:0.75rem;font-weight:600; }
.badge-long   { background:rgba(16,185,129,0.2);color:#10b981;border:1px solid #10b981;padding:2px 9px;border-radius:20px;font-size:0.8rem;font-weight:600; }
.badge-short  { background:rgba(239,68,68,0.2);color:#ef4444;border:1px solid #ef4444;padding:2px 9px;border-radius:20px;font-size:0.8rem;font-weight:600; }
.section-header {
    font-size:1rem;font-weight:600;color:#60a5fa;text-transform:uppercase;
    letter-spacing:0.08em;margin:12px 0 8px 0;padding-bottom:6px;
    border-bottom:1px solid rgba(59,130,246,0.2);
}
.signal-card {
    background:rgba(15,23,42,0.7);border:1px solid rgba(59,130,246,0.2);
    border-radius:12px;padding:16px;margin-bottom:10px;
}
h1 { color:#f1f5f9 !important; }
h2, h3 { color:#cbd5e1 !important; }
p, li, label { color:#94a3b8 !important; }
</style>
""", unsafe_allow_html=True)

SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1jWqSHHTXBD4-tAQsTrf4-BGQKMHhwASGdbPn3LTLun4"

@st.cache_data(ttl=300) # Fast cache refresh (5 min)
def load_data():
    try:
        # Use Official GSheets Connection
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection)
        
        # Read the sheet using the direct URL (it's often more robust than ID only)
        # We specify worksheet="Sheet1" because that's where agents log.
        df = conn.read(spreadsheet=SPREADSHEET_URL, ttl=300)
        
        if df is None or df.empty:
            return pd.DataFrame()

        # Clean up column names and basic normalization
        df.columns = [str(c).strip() for c in df.columns]
        
        # Convert timestamp
        if "Timestamp" in df.columns:
            df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors='coerce')
        
        # Sort reverse chronological
        df = df.sort_values("Timestamp", ascending=False)
        return df
    except Exception as e:
        # If it's the strange <Response 200> error, show more detail
        st.error(f"📡 Data Feed Error: {str(e)}")
        if "200" in str(e):
            st.info("💡 Tip: Try clearing your Streamlit Cache (sidebar button) if you just shared the sheet.")
        return pd.DataFrame()

# ─── KPI Bar ────────────────────────────────────────────────────────────────────
def show_kpis(df):
    t1, t2, t3, t4 = st.columns(4)
    t1.metric("📊 Total Signals", len(df))
    t2.metric("🤖 Agents", df["Agent"].nunique() if "Agent" in df.columns else 0)
    t3.metric("🎯 Unique Tickers", df["Symbol"].nunique() if "Symbol" in df.columns else 0)
    
    # Calculate Avg Confidence
    avg_conf = 0
    if "Confidence" in df.columns:
        avg_conf = df["Confidence"].dropna().astype(float).mean()
    t4.metric("📈 Avg. Score", f"{avg_conf:.3f}")

# ─── Main Interface ─────────────────────────────────────────────────────────────
st.markdown("# 🧠 MarketBrain Command Centre")
st.markdown("<p style='color:#64748b;margin-top:-12px;font-size:0.9rem;'>Public Dashboard · Live Google Sheets Backend · Multi-Agent View</p>", unsafe_allow_html=True)
st.markdown("---")

df = load_data()

if df.empty:
    st.info("📡 Application ready. Streaming historic records from Master Google Sheet...")
    st.stop()

# ─── Sidebar Filters ────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🔎 Display Filters")
    
    agents = sorted(df["Agent"].dropna().unique().tolist())
    selected_agents = st.multiselect("Agents", options=agents, default=agents)
    
    tickers = sorted(df["Symbol"].dropna().unique().tolist())
    selected_tickers = st.multiselect("Symbols", options=tickers, default=[], placeholder="All Tickers")

    st.markdown("---")
    if st.button("🔄 Force Refresh"):
        st.cache_data.clear()
        st.rerun()
    
    st.caption(f"Last synced: {datetime.now().strftime('%H:%M:%S')}")

# Filter Data
filtered_df = df.copy()
if selected_agents:
    filtered_df = filtered_df[filtered_df["Agent"].isin(selected_agents)]
if selected_tickers:
    filtered_df = filtered_df[filtered_df["Symbol"].isin(selected_tickers)]

show_kpis(filtered_df)

# ─── Tables ───────────────────────────────────────────────────────────────────
tab1, tab2 = st.tabs(["📋 Trade Ledger", "🔬 Factor Deep-Dive"])

with tab1:
    st.markdown("<div class='section-header'>Synchronized Signal Master List</div>", unsafe_allow_html=True)
    
    # Clean up display columns
    display_cols = ["Timestamp", "Agent", "Symbol", "Direction", "Entry", "Stop", "Target", "Confidence", "Regime", "Explanation"]
    # Ensure columns exist
    for c in display_cols:
        if c not in filtered_df.columns:
            filtered_df[c] = "—"
            
    disp = filtered_df[display_cols].copy()
    
    # Formatting
    disp["Timestamp"] = disp["Timestamp"].dt.strftime("%Y-%m-%d %H:%M")
    
    st.dataframe(
        disp,
        use_container_width=True,
        height=600,
        column_config={
            "Timestamp": st.column_config.TextColumn("Time (ET)"),
            "Symbol": st.column_config.TextColumn("Ticker", width="small"),
            "Confidence": st.column_config.NumberColumn("Score", format="%.3f"),
            "Explanation": st.column_config.TextColumn("Analysis Reasoning", width="large"),
        }
    )

with tab2:
    st.markdown("<div class='section-header'>High-Resolution Alpha Factors (Max3 & Max2)</div>", unsafe_allow_html=True)
    
    # Specific columns for advanced agents
    adv_cols = ["Timestamp", "Agent", "Symbol", "Confidence", "ML_Prob", "Sentiment", "Momentum", "Regime"]
    adv_df = filtered_df[filtered_df["Agent"].str.contains("Max3|Max2", na=False)]
    
    if adv_df.empty:
        st.info("No advanced (Max1/2/3) signals found in the sheet.")
    else:
        # Fill missing values for cleaner display
        adv_df = adv_df[adv_cols].fillna("—")
        st.dataframe(adv_df, use_container_width=True)

st.markdown("---")
st.caption("☁️ This dashboard is running on Streamlit Cloud and is connected to the Master Google Sheets API. Zero sync latency for live signals.")
