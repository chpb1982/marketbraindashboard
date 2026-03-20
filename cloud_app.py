
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
        
        # ─── Data Pre-Processing & Extractions ──────────────────────────────────
        if "Agent" in df.columns and "Status" not in df.columns:
            df["Status"] = df["Agent"].apply(
                lambda x: "REJECTED" if "REJECTED" in str(x).upper() else "APPROVED"
            )
            df["Agent"] = df["Agent"].apply(
                lambda x: str(x).replace(" (APPROVED)", "").replace(" (REJECTED)", "")
            )
            
        return df
    except Exception as e:
        # If it's the strange <Response 200> error, show more detail
        st.error(f"📡 Data Feed Error: {str(e)}")
        if "200" in str(e):
            st.info("💡 Tip: Try clearing your Streamlit Cache (sidebar button) if you just shared the sheet.")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def load_ml_logs():
    try:
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection)
        # Assuming the tab created by the sync script is named "ML_Logs"
        df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="ML_Logs", ttl=300)
        if df is None or df.empty:
            return pd.DataFrame()
        df.columns = [str(c).strip() for c in df.columns]
        if "trained_at" in df.columns:
            df["trained_at"] = pd.to_datetime(df["trained_at"], errors='coerce')
            df = df.sort_values("trained_at", ascending=False)
        return df
# ─── KPI Bar ────────────────────────────────────────────────────────────────────
def show_kpis(df):
    t1, t2, t3, t4, t5, t6 = st.columns(6)
    
    total = len(df)
    
    approved = len(df[df["Status"] == "APPROVED"]) if "Status" in df.columns else total
    rejected = len(df[df["Status"] == "REJECTED"]) if "Status" in df.columns else 0
        
    unique_tickers = df["Symbol"].nunique() if "Symbol" in df.columns else 0
    
    # Calculate Avg Confidence
    avg_conf = 0.0
    if "Confidence" in df.columns:
        avg_conf = pd.to_numeric(df["Confidence"].replace("—", pd.NA), errors='coerce').dropna().mean()

    t1.metric("📋 Total Analysed", total)
    t2.metric("✅ Approved", int(approved))
    t3.metric("❌ Rejected", int(rejected))
    t4.metric("🎯 Unique Tickers", int(unique_tickers))
    t5.metric("📊 Avg Score", f"{avg_conf:.3f}" if not pd.isna(avg_conf) else "0.000")
    t6.metric("🏆 Win Rate", "—", "0W / 0L")

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
    
    statuses = sorted(df["Status"].dropna().unique().tolist()) if "Status" in df.columns else ["APPROVED"]
    selected_statuses = st.multiselect("Status", options=statuses, default=statuses)
    
    tickers = sorted(df["Symbol"].dropna().unique().tolist())
    selected_tickers = st.multiselect("Symbols", options=tickers, default=[], placeholder="All Tickers")
    
    time_window = st.selectbox("Time Window", ["All Time", "Today", "Last 7 Days", "Last 30 Days", "YTD"], index=0)

    st.markdown("---")
    if st.button("🔄 Force Refresh"):
        st.cache_data.clear()
        st.rerun()
    
    st.caption(f"Last synced: {datetime.now().strftime('%H:%M:%S')}")

# Filter Data
filtered_df = df.copy()

if selected_agents:
    filtered_df = filtered_df[filtered_df["Agent"].isin(selected_agents)]
if selected_statuses and "Status" in filtered_df.columns:
    filtered_df = filtered_df[filtered_df["Status"].isin(selected_statuses)]
if selected_tickers:
    filtered_df = filtered_df[filtered_df["Symbol"].isin(selected_tickers)]

if time_window != "All Time" and "Timestamp" in filtered_df.columns:
    now = pd.Timestamp.now()
    if time_window == "Today":
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif time_window == "Last 7 Days":
        start_date = now - pd.Timedelta(days=7)
    elif time_window == "Last 30 Days":
        start_date = now - pd.Timedelta(days=30)
    elif time_window == "YTD":
        start_date = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Timezone handling if Timestamp has a tz attached
    if pd.api.types.is_datetime64tz_dtype(filtered_df["Timestamp"]):
        start_date = start_date.tz_localize(now.tz).tz_convert(filtered_df["Timestamp"].dt.tz) if start_date.tz is None else start_date.tz_convert(filtered_df["Timestamp"].dt.tz)
    else:
        start_date = start_date.tz_localize(None)

    filtered_df = filtered_df[filtered_df["Timestamp"] >= start_date]

show_kpis(filtered_df)

# ─── Tables ───────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(["📋 Trade Ledger", "🔬 Factor Deep-Dive", "🧠 Self-Learning Progress", "📖 Help & Terminology"])

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
    
    # Convert Symbol to Yahoo Finance URL
    disp["Symbol"] = "https://finance.yahoo.com/quote/" + disp["Symbol"].astype(str)
    
    st.dataframe(
        disp,
        use_container_width=True,
        height=600,
        column_config={
            "Timestamp": st.column_config.TextColumn("Time (ET)"),
            "Symbol": st.column_config.LinkColumn("Ticker", display_text=r"https://finance\.yahoo\.com/quote/(.*)", width="small"),
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

        # Convert Symbol to Yahoo Finance URL
        adv_df["Symbol"] = "https://finance.yahoo.com/quote/" + adv_df["Symbol"].astype(str)

        st.dataframe(
            adv_df, 
            use_container_width=True,
            column_config={
                "Symbol": st.column_config.LinkColumn("Ticker", display_text=r"https://finance\.yahoo\.com/quote/(.*)"),
                "Confidence": st.column_config.NumberColumn("Score", format="%.3f"),
            }
        )

with tab3:
    st.markdown("<div class='section-header'>Machine Learning Model Progress & Auto-Calibration</div>", unsafe_allow_html=True)
    
    ml_df = load_ml_logs()
    if ml_df.empty:
        st.info("Waiting for the nightly ML Retraining Cron-Job to publish logs...")
    else:
        # Extract Top Level KPIs from latest run
        latest_run = ml_df.iloc[0]
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Latest Training", getattr(latest_run, "trained_at", "Unknown").strftime("%b %d, %H:%M"))
        m2.metric("Base Accuracy", f"{getattr(latest_run, 'accuracy', 0)*100:.1f}%")
        m3.metric("Train Samples", int(getattr(latest_run, 'train_samples', 0)))
        m4.metric("Active Features", int(getattr(latest_run, 'feature_count', 0)))
        
        # Line chart of accuracy progress
        st.markdown("#### Retraining Trend (Accuracy & ROC AUC)")
        temp = ml_df.dropna(subset=['accuracy']).sort_values('trained_at').tail(20)
        if not temp.empty and "trained_at" in temp.columns:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=temp["trained_at"], y=temp["accuracy"], mode='lines+markers', name='Global Accuracy', line=dict(color='#10b981', width=3)))
            fig.add_trace(go.Scatter(x=temp["trained_at"], y=temp["roc_auc"], mode='lines+markers', name='ROC AUC (Predictive Power)', line=dict(color='#3b82f6', width=2)))
            fig.update_layout(height=350, plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#94a3b8'), margin=dict(l=0,r=0,t=20,b=0))
            st.plotly_chart(fig, use_container_width=True)
            
        st.markdown("#### Full Autonomic Logs")
        show_cols = ["trained_at", "model_type", "accuracy", "roc_auc", "f1_score", "train_samples", "test_samples", "feature_count"]
        avail_cols = [c for c in show_cols if c in ml_df.columns]
        st.dataframe(ml_df[avail_cols], use_container_width=True, hide_index=True)

with tab4:
    st.markdown("<div class='section-header'>MarketBrain System Guide</div>", unsafe_allow_html=True)
    st.markdown("""
    ### 🧭 Quick Navigation
    *   **📋 Trade Ledger**: Your unified master list of all generated signals across every running agent.
    *   **🔬 Factor Deep-Dive**: A raw look at the internal fundamental metrics (ML, Sentiment, Momentum) that the newer generation of agents (Max2 & Max3) use to build their confidence scores.
    *   **🧠 Self-Learning Progress**: A live tracker visualizing how the AI models are evolving, recalibrating, and dropping useless features using real market data and outcome feedback.
    
    ### 🤖 Agent Directory
    *   **MarketBrain_Historic**: Legacy signals originating from standard intraday databases.
    *   **MarketBrain_Pro (Classic)**: The original rule-based trend-following system.
    *   **Max1**: Upgraded with early implementations of basic ensemble scoring.
    *   **Max2**: Integrates deep sentiment analysis and dynamic real-time regime filtering.
    *   **Max3**: The flagship agent featuring automated self-learning, XGBoost/LightGBM probability calibration, and Bayesian feedback loops.
    
    ### 📈 Key Terminology
    *   **Score / Confidence**: An agent's final voting strength (0.0 to 1.0) on whether a ticker should be traded. Usually requires > 0.60 to generate a real trade.
    *   **ML_Prob**: A percentage chance of the trade's success generated exclusively by the Machine Learning ensemble, detached from human-written rules.
    *   **Sentiment**: NLP integration scanning for bullish/bearish news velocity.
    *   **Regime**: Describes the broad market's current phase (e.g. `BULL_STRONG`, `BEAR_WEAK`) which directly alters how aggressively the agents position stop-losses and required minimum scores.
    
    ### 🧠 Machine Learning Metrics
    *   **ROC AUC**: The predictive power of the model. A score of 0.5 is a random coin toss. A resilient score > 0.60 represents statistically significant edge.
    *   **Base Accuracy**: The sheer percentage of labels the model guessed correctly during Walk-Forward Verification on out-of-sample data.
    """)

st.markdown("---")
st.caption("☁️ This dashboard is running on Streamlit Cloud and is connected to the Master Google Sheets API. Zero sync latency for live signals.")
