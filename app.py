"""
MarketBrain Command Centre
Unified dashboard for MarketBrainPro, MAX-1 and MAX-2.
Surfaces ALL analysed tickers by parsing system_logs + trade_signals.
"""

import os
import re
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine, text
from datetime import datetime
import warnings
warnings.filterwarnings("ignore")

# ─── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="MarketBrain Command Centre",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Global CSS ────────────────────────────────────────────────────────────────
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
.stTabs [data-baseweb="tab-list"] {
    background: rgba(15,23,42,0.6); border-radius: 10px;
    padding: 4px; gap: 4px; border: 1px solid rgba(59,130,246,0.15);
}
.stTabs [data-baseweb="tab"] { border-radius: 8px; color: #94a3b8; font-weight: 500; }
.stTabs [aria-selected="true"] { background: rgba(59,130,246,0.25) !important; color: #60a5fa !important; }
.badge-pro  { background:linear-gradient(135deg,#7c3aed,#6d28d9);color:#fff;padding:3px 10px;border-radius:20px;font-size:0.75rem;font-weight:600; }
.badge-max1 { background:linear-gradient(135deg,#0ea5e9,#0284c7);color:#fff;padding:3px 10px;border-radius:20px;font-size:0.75rem;font-weight:600; }
.badge-max2 { background:linear-gradient(135deg,#10b981,#059669);color:#fff;padding:3px 10px;border-radius:20px;font-size:0.75rem;font-weight:600; }
.badge-long   { background:rgba(16,185,129,0.2);color:#10b981;border:1px solid #10b981;padding:2px 9px;border-radius:20px;font-size:0.8rem;font-weight:600; }
.badge-short  { background:rgba(239,68,68,0.2);color:#ef4444;border:1px solid #ef4444;padding:2px 9px;border-radius:20px;font-size:0.8rem;font-weight:600; }
.badge-accept { background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.4);padding:2px 9px;border-radius:20px;font-size:0.78rem;font-weight:600; }
.badge-reject { background:rgba(239,68,68,0.10);color:#f87171;border:1px solid rgba(239,68,68,0.3);padding:2px 9px;border-radius:20px;font-size:0.78rem;font-weight:600; }
.section-header {
    font-size:1rem;font-weight:600;color:#60a5fa;text-transform:uppercase;
    letter-spacing:0.08em;margin:12px 0 8px 0;padding-bottom:6px;
    border-bottom:1px solid rgba(59,130,246,0.2);
}
.signal-card {
    background:rgba(15,23,42,0.7);border:1px solid rgba(59,130,246,0.2);
    border-radius:12px;padding:16px;margin-bottom:10px;
}
.score-bar-wrap { background:rgba(255,255,255,0.07);border-radius:6px;height:8px;width:100%;margin-top:4px;overflow:hidden; }
.score-bar { height:8px;border-radius:6px; }
h1 { color:#f1f5f9 !important; }
h2, h3 { color:#cbd5e1 !important; }
p, li, label { color:#94a3b8 !important; }
</style>
""", unsafe_allow_html=True)

# ─── DB Connections ─────────────────────────────────────────────────────────────
# Priority: 
# 1. Streamlit secrets (cloud)
# 2. Environment variables (local/docker)
# 3. Defaults (local)

def get_db_cred(key, default):
    if key in st.secrets:
        return st.secrets[key]
    return os.getenv(key, default)

PG_USER = get_db_cred("POSTGRES_USER", "pb")
PG_PASS = get_db_cred("POSTGRES_PASSWORD", "")
PG_HOST = get_db_cred("POSTGRES_HOST", "localhost")

AGENTS = {
    "MarketBrainPro":   {"db": "market_brain",      "badge": "pro",  "label": "MarketBrainPro",  "color": "#7c3aed", "threshold": 0.60},
    "MarketBrainMAX-1": {"db": "market_brain_max",  "badge": "max1", "label": "MAX-1",           "color": "#0ea5e9", "threshold": 0.60},
    "MarketBrainMAX-2": {"db": "market_brain_max2", "badge": "max2", "label": "MAX-2",           "color": "#10b981", "threshold": 0.60},
}

@st.cache_resource
def get_engine(db_name: str):
    # Support for SSL (required for Neon)
    ssl_param = "?sslmode=require" if "neon.tech" in PG_HOST else ""
    url = f"postgresql://{PG_USER}:{PG_PASS}@{PG_HOST}:5432/{db_name}{ssl_param}"
    return create_engine(url, pool_pre_ping=True)

def safe_query(agent_key: str, sql: str, params: dict = None) -> pd.DataFrame:
    try:
        engine = get_engine(AGENTS[agent_key]["db"])
        with engine.connect() as conn:
            return pd.read_sql(text(sql), conn, params=params or {})
    except Exception:
        return pd.DataFrame()


# ─── Log Parsers — extract analysed stocks from system_logs ───────────────────

# MarketBrainPro log patterns:
# "[AAPL] ML Probability (78.0%) < 50%. Rejected."
# "[AAPL] Momentum (-0.33) < 0.3. Rejected."
# "[AAPL] ✅ APPROVED — LONG @ $150.23"
RE_PRO_TICKER   = re.compile(r'\[([A-Z]{1,5})\]')
RE_PRO_ML       = re.compile(r'\[([A-Z]{1,5})\] ML Probability \((\d+\.?\d*)%\)')
RE_PRO_MOM      = re.compile(r'\[([A-Z]{1,5})\] Momentum \(([+-]?\d+\.?\d*)\)')
RE_PRO_APPROVED = re.compile(r'\[([A-Z]{1,5})\].*APPROVED.*?(LONG|SHORT).*?\$(\d+\.?\d*)')
RE_PRO_REJECTED = re.compile(r'\[([A-Z]{1,5})\].*Rejected\.')

# MAX-1 log patterns:
# "REJECTED: AVAV Score (0.5) below threshold (0.6)"
# "Scanning AVAV factor models..."
RE_MAX1_SCAN     = re.compile(r'Scanning ([A-Z]{1,5}) factor')
RE_MAX1_REJECTED = re.compile(r'REJECTED:\s+([A-Z]{1,5})\s+Score\s+\((\d+\.?\d*)\)')
RE_MAX1_APPROVED = re.compile(r'APPROVED.*?([A-Z]{1,5}).*?(LONG|SHORT).*?\$(\d+\.?\d*)')

# MAX-2 log patterns:
# "[NATO] REJECTED: score=0.555, AI=BUY"
# "Scanning NATO | event=GENERAL | mentions=2"
# "[AAPL] ✅ APPROVED — LONG @ $150.23 | SL=$148.00 | TP=$155.00"
RE_MAX2_SCAN     = re.compile(r'Scanning ([A-Z]{1,5}) \|')
RE_MAX2_REJECTED = re.compile(r'\[([A-Z]{1,5})\] REJECTED: score=(\d+\.?\d*),\s*AI=(\w+)')
RE_MAX2_APPROVED = re.compile(r'\[([A-Z]{1,5})\].*APPROVED.*?(LONG|SHORT).*?\$(\d+\.?\d*)')
RE_MAX2_SCORE    = re.compile(r'score=(\d+\.?\d*)')
RE_MAX2_EVENT    = re.compile(r'event=(\w+)')
RE_MAX2_MENTIONS = re.compile(r'mentions=(\d+)')


def parse_pro_logs(df_logs: pd.DataFrame) -> pd.DataFrame:
    """Extract per-ticker analysis rows from MarketBrainPro system_logs."""
    rows = []
    ticker_data: dict = {}

    for _, row in df_logs.iterrows():
        msg = row["message"]
        ts  = row["timestamp"]

        m_ml = RE_PRO_ML.search(msg)
        if m_ml:
            sym = m_ml.group(1)
            ticker_data.setdefault(sym, {"timestamp": ts, "symbol": sym})
            ticker_data[sym]["ml_prob"] = float(m_ml.group(2)) / 100.0

        m_mom = RE_PRO_MOM.search(msg)
        if m_mom:
            sym = m_mom.group(1)
            ticker_data.setdefault(sym, {"timestamp": ts, "symbol": sym})
            ticker_data[sym]["momentum"] = float(m_mom.group(2))

        m_rej = RE_PRO_REJECTED.search(msg)
        if m_rej:
            sym = m_rej.group(1)
            ticker_data.setdefault(sym, {"timestamp": ts, "symbol": sym})
            ticker_data[sym]["status"] = "REJECTED"
            ticker_data[sym]["reject_reason"] = msg.split("] ", 1)[-1].strip() if "] " in msg else msg

        m_app = RE_PRO_APPROVED.search(msg)
        if m_app:
            sym = m_app.group(1)
            ticker_data.setdefault(sym, {"timestamp": ts, "symbol": sym})
            ticker_data[sym]["status"] = "APPROVED"
            ticker_data[sym]["direction"] = m_app.group(2)
            ticker_data[sym]["entry_price"] = float(m_app.group(3))

    for sym, d in ticker_data.items():
        rows.append({
            "symbol":        sym,
            "timestamp":     d.get("timestamp"),
            "status":        d.get("status", "SCANNED"),
            "direction":     d.get("direction", "—"),
            "score":         None,
            "ml_prob":       d.get("ml_prob"),
            "sentiment":     None,
            "momentum":      d.get("momentum"),
            "entry_price":   d.get("entry_price"),
            "stop_loss":     None,
            "take_profit":   None,
            "reject_reason": d.get("reject_reason", ""),
            "event_type":    "—",
            "news_mentions": None,
        })
    return pd.DataFrame(rows)


def parse_max1_logs(df_logs: pd.DataFrame) -> pd.DataFrame:
    """Extract per-ticker analysis rows from MAX-1 system_logs."""
    rows = []
    ticker_data: dict = {}

    for _, row in df_logs.iterrows():
        msg = row["message"]
        ts  = row["timestamp"]

        m_scan = RE_MAX1_SCAN.search(msg)
        if m_scan:
            sym = m_scan.group(1)
            ticker_data.setdefault(sym, {"timestamp": ts, "symbol": sym})

        m_rej = RE_MAX1_REJECTED.search(msg)
        if m_rej:
            sym = m_rej.group(1)
            ticker_data.setdefault(sym, {"timestamp": ts, "symbol": sym})
            ticker_data[sym]["status"] = "REJECTED"
            ticker_data[sym]["score"] = float(m_rej.group(2))
            ticker_data[sym]["reject_reason"] = f"Score {m_rej.group(2)} below threshold"

        m_app = RE_MAX1_APPROVED.search(msg)
        if m_app:
            sym = m_app.group(1)
            ticker_data.setdefault(sym, {"timestamp": ts, "symbol": sym})
            ticker_data[sym]["status"] = "APPROVED"
            ticker_data[sym]["direction"] = m_app.group(2)
            ticker_data[sym]["entry_price"] = float(m_app.group(3))

        # Score line: "score=0.534 | ml=0.43 | sentiment=..."
        if "score=" in msg:
            m_ticker = RE_PRO_TICKER.search(msg)
            score_m = re.search(r'score=(\d+\.?\d*)', msg)
            ml_m    = re.search(r'ml=(\d+\.?\d*)', msg)
            sent_m  = re.search(r'sentiment=([+-]?\d+\.?\d*)', msg)
            mom_m   = re.search(r'momentum=([+-]?\d+\.?\d*)', msg)
            if m_ticker and score_m:
                sym = m_ticker.group(1)
                ticker_data.setdefault(sym, {"timestamp": ts, "symbol": sym})
                ticker_data[sym]["score"]     = float(score_m.group(1))
                if ml_m:   ticker_data[sym]["ml_prob"]  = float(ml_m.group(1))
                if sent_m: ticker_data[sym]["sentiment"] = float(sent_m.group(1))
                if mom_m:  ticker_data[sym]["momentum"]  = float(mom_m.group(1))

    for sym, d in ticker_data.items():
        rows.append({
            "symbol":        sym,
            "timestamp":     d.get("timestamp"),
            "status":        d.get("status", "SCANNED"),
            "direction":     d.get("direction", "—"),
            "score":         d.get("score"),
            "ml_prob":       d.get("ml_prob"),
            "sentiment":     d.get("sentiment"),
            "momentum":      d.get("momentum"),
            "entry_price":   d.get("entry_price"),
            "stop_loss":     None,
            "take_profit":   None,
            "reject_reason": d.get("reject_reason", ""),
            "event_type":    "—",
            "news_mentions": None,
        })
    return pd.DataFrame(rows)


def parse_max2_logs(df_logs: pd.DataFrame) -> pd.DataFrame:
    """Extract per-ticker analysis rows from MAX-2 system_logs."""
    rows = []
    ticker_data: dict = {}

    for _, row in df_logs.iterrows():
        msg = row["message"]
        ts  = row["timestamp"]

        m_scan = RE_MAX2_SCAN.search(msg)
        if m_scan:
            sym = m_scan.group(1)
            ticker_data.setdefault(sym, {"timestamp": ts, "symbol": sym})
            m_ev  = RE_MAX2_EVENT.search(msg)
            m_men = RE_MAX2_MENTIONS.search(msg)
            if m_ev:  ticker_data[sym]["event_type"]    = m_ev.group(1)
            if m_men: ticker_data[sym]["news_mentions"] = int(m_men.group(1))

        m_rej = RE_MAX2_REJECTED.search(msg)
        if m_rej:
            sym = m_rej.group(1)
            ticker_data.setdefault(sym, {"timestamp": ts, "symbol": sym})
            ticker_data[sym]["status"]        = "REJECTED"
            ticker_data[sym]["score"]         = float(m_rej.group(2))
            ticker_data[sym]["ai_direction"]  = m_rej.group(3)
            ticker_data[sym]["reject_reason"] = f"Score {m_rej.group(2)} below threshold (AI said {m_rej.group(3)})"

        m_app = RE_MAX2_APPROVED.search(msg)
        if m_app:
            sym = m_app.group(1)
            ticker_data.setdefault(sym, {"timestamp": ts, "symbol": sym})
            ticker_data[sym]["status"]      = "APPROVED"
            ticker_data[sym]["direction"]   = m_app.group(2)
            ticker_data[sym]["entry_price"] = float(m_app.group(3))

        # Detailed score line: "[AAPL] score=0.73 | ml=0.68 | ai=BUY(82%) | sentiment=0.41"
        if "[" in msg and "score=" in msg:
            m_t = RE_PRO_TICKER.search(msg)
            if m_t:
                sym = m_t.group(1)
                ticker_data.setdefault(sym, {"timestamp": ts, "symbol": sym})
                for pattern, key in [
                    (r'score=(\d+\.?\d*)', "score"),
                    (r'ml=(\d+\.?\d*)', "ml_prob"),
                    (r'sentiment=([+-]?\d+\.?\d*)', "sentiment"),
                ]:
                    m = re.search(pattern, msg)
                    if m: ticker_data[sym][key] = float(m.group(1))

    for sym, d in ticker_data.items():
        rows.append({
            "symbol":        sym,
            "timestamp":     d.get("timestamp"),
            "status":        d.get("status", "SCANNED"),
            "direction":     d.get("direction", d.get("ai_direction", "—")),
            "score":         d.get("score"),
            "ml_prob":       d.get("ml_prob"),
            "sentiment":     d.get("sentiment"),
            "momentum":      None,
            "entry_price":   d.get("entry_price"),
            "stop_loss":     None,
            "take_profit":   None,
            "reject_reason": d.get("reject_reason", ""),
            "event_type":    d.get("event_type", "—"),
            "news_mentions": d.get("news_mentions"),
        })
    return pd.DataFrame(rows)


def load_analysis_logs(agent_keys: list, days_back: int) -> pd.DataFrame:
    """Load and parse all analysed tickers from system_logs for each agent."""
    frames = []
    parsers = {
        "MarketBrainPro":   parse_pro_logs,
        "MarketBrainMAX-1": parse_max1_logs,
        "MarketBrainMAX-2": parse_max2_logs,
    }

    for ak in agent_keys:
        df_logs = safe_query(ak, """
            SELECT timestamp, level, logger_name, message
            FROM system_logs
            WHERE timestamp >= NOW() - INTERVAL ':days days'
              AND (
                message ILIKE '%scanning%'
                OR message ILIKE '%rejected%'
                OR message ILIKE '%approved%'
                OR message ILIKE '%score=%'
                OR message ILIKE '%ml prob%'
                OR message ILIKE '%momentum%'
              )
            ORDER BY timestamp DESC
            LIMIT 5000
        """, {"days": days_back})

        if df_logs.empty:
            continue

        parsed = parsers[ak](df_logs)
        if not parsed.empty:
            parsed["agent"] = ak
            frames.append(parsed)

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    combined["timestamp"] = pd.to_datetime(combined["timestamp"], utc=True).dt.tz_convert('US/Eastern')
    return combined.sort_values("timestamp", ascending=False)


def load_approved_signals(agent_keys: list, days_back: int) -> pd.DataFrame:
    """Load fully detailed approved signals from trade_signals table."""
    frames = []
    for ak in agent_keys:
        df = safe_query(ak, """
            SELECT id, timestamp, symbol, direction, score, ml_prob,
                   sentiment, momentum, volume_score,
                   COALESCE(news_score, 0) AS news_score,
                   regime, entry_price, stop_loss, take_profit,
                   reasoning,
                   COALESCE(outcome_state, 'OPEN') AS outcome_state,
                   realized_pnl
            FROM trade_signals
            WHERE timestamp >= NOW() - INTERVAL ':days days'
            ORDER BY timestamp DESC
        """, {"days": days_back})
        if not df.empty:
            df["agent"] = ak
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True)
    combined["timestamp"] = pd.to_datetime(combined["timestamp"], utc=True).dt.tz_convert('US/Eastern')
    return combined.sort_values("timestamp", ascending=False)


def load_system_logs(agent_keys: list, days_back: int, level: str) -> pd.DataFrame:
    frames = []
    for ak in agent_keys:
        df = safe_query(ak, """
            SELECT timestamp, level, logger_name, message
            FROM system_logs
            WHERE timestamp >= NOW() - INTERVAL ':days days'
              AND (:level = 'ALL' OR level = :level)
            ORDER BY timestamp DESC LIMIT 300
        """, {"days": days_back, "level": level})
        if not df.empty:
            df["agent"] = ak
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True)
    combined["timestamp"] = pd.to_datetime(combined["timestamp"], utc=True).dt.tz_convert('US/Eastern')
    return combined.sort_values("timestamp", ascending=False)


def load_model_weights(agent_key: str) -> pd.DataFrame:
    if agent_key == "MarketBrainPro":
        return pd.DataFrame()
    df = safe_query(agent_key, """
        SELECT weight_name, value, win_rate, sample_size, updated_at
        FROM model_weights ORDER BY value DESC
    """)
    if not df.empty and "updated_at" in df.columns:
        df["updated_at"] = pd.to_datetime(df["updated_at"], utc=True).dt.tz_convert('US/Eastern')
    return df


def make_gauge(value: float, title: str, color: str) -> go.Figure:
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=round(value * 100, 1),
        number={"suffix": "%", "font": {"color": "#f1f5f9", "size": 28}},
        title={"text": title, "font": {"color": "#94a3b8", "size": 13}},
        gauge={
            "axis": {"range": [0, 100], "tickcolor": "#334155", "tickfont": {"color": "#64748b"}},
            "bar": {"color": color},
            "bgcolor": "rgba(15,23,42,0.5)",
            "borderwidth": 0,
            "steps": [
                {"range": [0, 40],  "color": "rgba(239,68,68,0.12)"},
                {"range": [40, 60], "color": "rgba(234,179,8,0.12)"},
                {"range": [60, 100],"color": "rgba(16,185,129,0.12)"},
            ],
            "threshold": {"line": {"color": "#f59e0b", "width": 2}, "thickness": 0.75, "value": 60}
        }
    ))
    fig.update_layout(
        height=180, margin=dict(t=30, b=0, l=20, r=20),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter")
    )
    return fig

# ─── Header ─────────────────────────────────────────────────────────────────────
st.markdown("# 🧠 MarketBrain Command Centre")
st.markdown("<p style='color:#64748b;margin-top:-12px;font-size:0.9rem;'>Real-time signal intelligence · All agents · All analysed stocks</p>", unsafe_allow_html=True)
st.markdown("---")

# ─── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🔎 Filters")

    selected_agents = st.multiselect(
        "Agent", options=list(AGENTS.keys()), default=list(AGENTS.keys()),
        format_func=lambda x: AGENTS[x]["label"]
    )

    days_back = st.select_slider(
        "Time Window", options=[1, 3, 7, 14, 30, 60, 90], value=7,
        format_func=lambda x: f"Last {x}d"
    )

    threshold = st.slider("Score Threshold", 0.0, 1.0, 0.60, 0.01)

    status_filter = st.multiselect(
        "Status", options=["APPROVED", "REJECTED", "SCANNED"],
        default=["APPROVED", "REJECTED", "SCANNED"]
    )

    st.markdown("---")
    st.markdown("### 🌐 1-Click Deploy")
    st.markdown("""
    <a href="https://share.streamlit.io" target="_blank">
    <button style="width:100%;background:linear-gradient(135deg,#3b82f6,#1d4ed8);color:white;border:none;
    padding:10px 16px;border-radius:8px;font-family:Inter;font-weight:600;cursor:pointer;font-size:0.87rem;">
    🚀 Deploy to Streamlit Cloud
    </button></a>
    """, unsafe_allow_html=True)
    st.caption("Push MarketBrainDashboard/ to GitHub then connect at share.streamlit.io")
    st.markdown("---")
    st.caption(f"🕐 {pd.Timestamp.now('US/Eastern').strftime('%Y-%m-%d %H:%M:%S')} ET")
    if st.button("🔄 Refresh Data"):
        st.cache_resource.clear()
        st.rerun()

# ─── Load Data ──────────────────────────────────────────────────────────────────
if not selected_agents:
    st.warning("Select at least one agent.")
    st.stop()

with st.spinner("Loading all analysed stocks from all databases..."):
    df_analysis = load_analysis_logs(selected_agents, days_back)
    df_approved = load_approved_signals(selected_agents, days_back)

# Merge: approved signals complement logs with full detail
if not df_approved.empty and not df_analysis.empty:
    df_analysis_clean = df_analysis[~df_analysis["symbol"].isin(
        df_approved[df_approved["agent"].isin(selected_agents)]["symbol"].unique()
    )]
    # Build approved rows from trade_signals (has more data)
    approved_rows = []
    for _, r in df_approved.iterrows():
        approved_rows.append({
            "symbol":        r["symbol"],
            "timestamp":     r["timestamp"],
            "status":        "APPROVED",
            "direction":     r.get("direction","—"),
            "score":         r.get("score"),
            "ml_prob":       r.get("ml_prob"),
            "sentiment":     r.get("sentiment"),
            "momentum":      r.get("momentum"),
            "entry_price":   r.get("entry_price"),
            "stop_loss":     r.get("stop_loss"),
            "take_profit":   r.get("take_profit"),
            "reject_reason": "",
            "event_type":    "—",
            "news_mentions": None,
            "agent":         r["agent"],
            "reasoning":     r.get("reasoning",""),
            "regime":        r.get("regime","—"),
            "volume_score":  r.get("volume_score"),
            "outcome_state": r.get("outcome_state","OPEN"),
            "realized_pnl":  r.get("realized_pnl"),
        })
    df_all = pd.concat([df_analysis_clean, pd.DataFrame(approved_rows)], ignore_index=True)
elif not df_approved.empty:
    df_all = df_approved.rename(columns={"outcome_state":"status"})
    df_all["status"] = "APPROVED"
elif not df_analysis.empty:
    df_all = df_analysis.copy()
else:
    df_all = pd.DataFrame()

if not df_all.empty:
    df_all = df_all.sort_values("timestamp", ascending=False)

# Apply ticker filter
all_tickers = sorted(df_all["symbol"].unique().tolist()) if not df_all.empty else []
with st.sidebar:
    selected_tickers = st.multiselect("Stock Ticker", options=all_tickers, default=[], placeholder="All tickers")

if selected_tickers and not df_all.empty:
    df_all = df_all[df_all["symbol"].isin(selected_tickers)]
if status_filter and not df_all.empty:
    df_all = df_all[df_all["status"].isin(status_filter)]

# ─── KPI Bar ────────────────────────────────────────────────────────────────────
total_scanned  = len(df_all)
approved_count = len(df_all[df_all["status"] == "APPROVED"]) if not df_all.empty else 0
rejected_count = len(df_all[df_all["status"] == "REJECTED"]) if not df_all.empty else 0
unique_tickers = df_all["symbol"].nunique() if not df_all.empty else 0
avg_score      = df_all["score"].dropna().mean() if not df_all.empty else 0.0
wins = len(df_approved[df_approved.get("outcome_state","") == "WIN"]) if not df_approved.empty and "outcome_state" in df_approved.columns else 0
losses = len(df_approved[df_approved.get("outcome_state","") == "LOSS"]) if not df_approved.empty and "outcome_state" in df_approved.columns else 0
win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0.0

k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("📋 Total Analysed", total_scanned)
k2.metric("✅ Approved",  approved_count)
k3.metric("❌ Rejected",  rejected_count)
k4.metric("🎯 Unique Tickers", unique_tickers)
k5.metric("📊 Avg Score", f"{avg_score:.3f}" if avg_score else "—")
k6.metric("🏆 Win Rate", f"{win_rate:.1f}%" if (wins+losses) > 0 else "—", delta=f"{wins}W / {losses}L")
st.markdown("")

# ─── Tabs ────────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "📡 All Analysed Stocks",
    "🤖 AI Analysis",
    "⚗️ Pipeline Breakdown",
    "📈 Analytics",
])

# ══════════════════════════════════════════════════════════
# TAB 1 — ALL ANALYSED STOCKS
# ══════════════════════════════════════════════════════════
with tab1:
    st.markdown("<div class='section-header'>Every Ticker Analysed — Approved & Rejected</div>", unsafe_allow_html=True)

    if df_all.empty:
        st.info("No data yet. Logs will populate here as pipelines run their cycles.")
    else:
        # Summary row per agent
        agent_cols = st.columns(len(selected_agents))
        for i, ak in enumerate(selected_agents):
            sub = df_all[df_all["agent"] == ak]
            with agent_cols[i]:
                badge = f"badge-{AGENTS[ak]['badge']}"
                n_approved = len(sub[sub["status"] == "APPROVED"])
                n_rejected = len(sub[sub["status"] == "REJECTED"])
                st.markdown(f"<span class='{badge}'>{AGENTS[ak]['label']}</span>", unsafe_allow_html=True)
                st.metric("Scanned", len(sub["symbol"].unique()))
                st.metric("Approved", n_approved, delta=f"{n_rejected} rejected")

        st.markdown("")
        # Full table
        disp = df_all[[
            "timestamp","agent","symbol","status","direction",
            "score","ml_prob","sentiment","momentum","entry_price",
            "stop_loss","take_profit","event_type","news_mentions","reject_reason"
        ]].copy()

        disp.columns = [
            "Timestamp","Agent","Symbol","Status","Direction",
            "Score","ML Prob","Sentiment","Momentum","Entry",
            "Stop Loss","Take Profit","Event","News Hits","Reject Reason"
        ]
        disp["Timestamp"] = pd.to_datetime(disp["Timestamp"]).dt.strftime("%m-%d %H:%M")
        for col in ["Score","ML Prob"]:
            disp[col] = disp[col].apply(lambda x: f"{x:.3f}" if pd.notna(x) else "—")
        for col in ["Sentiment","Momentum"]:
            disp[col] = disp[col].apply(lambda x: f"{x:+.2f}" if pd.notna(x) else "—")
        for col in ["Entry","Stop Loss","Take Profit"]:
            disp[col] = disp[col].apply(lambda x: f"${x:.2f}" if pd.notna(x) else "—")

        def row_color(row):
            if row["Status"] == "APPROVED":
                return ["background-color: rgba(16,185,129,0.08)"] * len(row)
            elif row["Status"] == "REJECTED":
                return ["background-color: rgba(239,68,68,0.05)"] * len(row)
            return [""] * len(row)

        st.dataframe(disp.style.apply(row_color, axis=1), use_container_width=True, height=520)

        # Download button
        csv = disp.to_csv(index=False)
        st.download_button("📥 Export to CSV", csv, "marketbrain_analysis.csv", "text/csv")


# ══════════════════════════════════════════════════════════
# TAB 2 — AI ANALYSIS
# ══════════════════════════════════════════════════════════
with tab2:
    if df_all.empty:
        st.info("No analysis data available yet.")
    else:
        st.markdown("<div class='section-header'>AI Factor Analysis — Per Ticker</div>", unsafe_allow_html=True)

        tickers_avail = df_all["symbol"].unique().tolist()
        c1, c2 = st.columns(2)
        with c1:
            ai_ticker = st.selectbox("Ticker", tickers_avail)
        with c2:
            agents_with_ticker = df_all[df_all["symbol"] == ai_ticker]["agent"].unique().tolist()
            ai_agent = st.selectbox("Agent", agents_with_ticker)

        row_data = df_all[(df_all["symbol"] == ai_ticker) & (df_all["agent"] == ai_agent)]
        if row_data.empty:
            st.warning("No data for this combination.")
        else:
            r = row_data.iloc[0]
            ml_v    = float(r["ml_prob"] if pd.notna(r["ml_prob"]) else 0)
            sent_v  = (float(r["sentiment"] if pd.notna(r["sentiment"]) else 0) + 1) / 2
            mom_v   = (float(r["momentum"] if pd.notna(r["momentum"]) else 0) + 1) / 2
            score_v = float(r["score"] if pd.notna(r["score"]) else 0)

            g1, g2, g3, g4 = st.columns(4)
            with g1: st.plotly_chart(make_gauge(ml_v, "ML Probability", "#3b82f6"), use_container_width=True)
            with g2: st.plotly_chart(make_gauge(sent_v, "Sentiment", "#8b5cf6"), use_container_width=True)
            with g3: st.plotly_chart(make_gauge(mom_v, "Momentum", "#ec4899"), use_container_width=True)
            with g4:
                color_s = "#10b981" if score_v >= threshold else "#ef4444"
                st.plotly_chart(make_gauge(score_v, "Final Score", color_s), use_container_width=True)

            # Status + details
            badge_cls = f"badge-{AGENTS[ai_agent]['badge']}"
            status = r.get("status","—")
            status_cls = "badge-accept" if status == "APPROVED" else "badge-reject"
            direction = r.get("direction","—")
            dir_cls = "badge-long" if direction == "LONG" else ("badge-short" if direction == "SHORT" else "")

            reasoning = r.get("reasoning","") or r.get("reject_reason","") or "Pending AI analysis."

            st.markdown(f"""
            <div class='signal-card'>
              <div style='display:flex;gap:8px;align-items:center;margin-bottom:10px;flex-wrap:wrap;'>
                <span style='color:#f1f5f9;font-size:1.15rem;font-weight:700;'>{ai_ticker}</span>
                <span class='{badge_cls}'>{AGENTS[ai_agent]['label']}</span>
                <span class='{status_cls}'>{status}</span>
                {"<span class='" + dir_cls + "'>" + direction + "</span>" if dir_cls else ""}
                <span style='color:#64748b;font-size:0.8rem;margin-left:auto;'>{str(r.get("timestamp",""))[:19]}</span>
              </div>
              <div style='display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:12px;'>
                <div><div style='color:#64748b;font-size:0.72rem;'>Entry</div>
                  <div style='color:#f1f5f9;font-weight:600;'>{"$"+str(round(r["entry_price"],2)) if pd.notna(r.get("entry_price")) else "—"}</div></div>
                <div><div style='color:#64748b;font-size:0.72rem;'>Stop Loss</div>
                  <div style='color:#ef4444;font-weight:600;'>{"$"+str(round(r["stop_loss"],2)) if pd.notna(r.get("stop_loss")) else "—"}</div></div>
                <div><div style='color:#64748b;font-size:0.72rem;'>Take Profit</div>
                  <div style='color:#10b981;font-weight:600;'>{"$"+str(round(r["take_profit"],2)) if pd.notna(r.get("take_profit")) else "—"}</div></div>
                <div><div style='color:#64748b;font-size:0.72rem;'>Event</div>
                  <div style='color:#fbbf24;font-weight:600;'>{r.get("event_type","—")}</div></div>
              </div>
              <p style='color:#cbd5e1;line-height:1.6;margin:0;font-size:0.9rem;'>{reasoning[:500]}</p>
            </div>
            """, unsafe_allow_html=True)

            # Score history
            if len(row_data) > 1:
                st.markdown("<div class='section-header'>Score History</div>", unsafe_allow_html=True)
                hist = row_data[["timestamp","score","ml_prob"]].dropna(subset=["score"]).copy()
                hist["timestamp"] = pd.to_datetime(hist["timestamp"]).dt.strftime("%m-%d %H:%M")
                fig_h = go.Figure()
                fig_h.add_trace(go.Scatter(x=hist["timestamp"], y=hist["score"], name="Score",
                    line=dict(color="#3b82f6", width=2), mode="lines+markers"))
                fig_h.add_trace(go.Scatter(x=hist["timestamp"], y=hist["ml_prob"], name="ML",
                    line=dict(color="#8b5cf6", width=1.5, dash="dot"), mode="lines"))
                fig_h.add_hline(y=threshold, line_dash="dash", line_color="#f59e0b",
                    annotation_text="Threshold", annotation_font_color="#f59e0b")
                fig_h.update_layout(
                    height=260, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(10,14,26,0.5)",
                    font=dict(family="Inter", color="#94a3b8"),
                    xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
                    yaxis=dict(gridcolor="rgba(255,255,255,0.05)", range=[0,1]),
                    legend=dict(bgcolor="rgba(0,0,0,0)"),
                    margin=dict(l=0, r=0, t=10, b=0)
                )
                st.plotly_chart(fig_h, use_container_width=True)


# ══════════════════════════════════════════════════════════
# TAB 3 — PIPELINE BREAKDOWN
# ══════════════════════════════════════════════════════════
with tab3:
    st.markdown("<div class='section-header'>Why Each Ticker Was Accepted or Rejected</div>", unsafe_allow_html=True)

    if df_all.empty:
        st.info("No pipeline data yet.")
    else:
        pipe_status = st.radio("Show", ["ALL","APPROVED","REJECTED"], horizontal=True)
        df_pipe = df_all.copy()
        if pipe_status != "ALL":
            df_pipe = df_pipe[df_pipe["status"] == pipe_status]

        # Group by symbol+agent for deduplication (latest per pair)
        df_pipe = df_pipe.sort_values("timestamp", ascending=False).drop_duplicates(["symbol","agent"])

        for _, row in df_pipe.iterrows():
            score   = float(row.get("score") if pd.notna(row.get("score")) else 0)
            ml_v    = float(row.get("ml_prob") if pd.notna(row.get("ml_prob")) else 0)
            sent_v  = float(row.get("sentiment") if pd.notna(row.get("sentiment")) else 0)
            mom_v   = float(row.get("momentum") if pd.notna(row.get("momentum")) else 0)
            status  = row.get("status","—")
            direction = row.get("direction","—")
            entry  = row.get("entry_price")
            sl     = row.get("stop_loss")
            tp     = row.get("take_profit")
            reject = row.get("reject_reason","—")
            badge_cls  = f"badge-{AGENTS[row['agent']]['badge']}"
            status_cls = "badge-accept" if status=="APPROVED" else "badge-reject"
            dir_cls    = "badge-long" if direction=="LONG" else ("badge-short" if direction=="SHORT" else "")

            score_pct = int(min(score * 100, 100))
            gap = round((score - threshold) * 100, 2)
            bar_color = "linear-gradient(90deg,#10b981,#34d399)" if score>=threshold else "linear-gradient(90deg,#ef4444,#f87171)"
            gap_txt = f"▲ +{gap}% above threshold" if gap >= 0 else f"▼ {abs(gap)}% below threshold"

            entry_str = f"${entry:.2f}" if pd.notna(entry) else "—"
            sl_str    = f"${sl:.2f}"    if pd.notna(sl)    else "—"
            tp_str    = f"${tp:.2f}"    if pd.notna(tp)    else "—"

            st.markdown(f"""
            <div class='signal-card'>
              <div style='display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:12px;'>
                <span style='color:#f1f5f9;font-size:1.1rem;font-weight:700;'>{row["symbol"]}</span>
                <span class='{badge_cls}'>{AGENTS[row["agent"]]["label"]}</span>
                <span class='{status_cls}'>{status}</span>
                {"<span class='" + dir_cls + "'>" + direction + "</span>" if dir_cls else ""}
                <span style='color:#64748b;font-size:0.78rem;margin-left:auto;'>{str(row.get("timestamp",""))[:16]}</span>
              </div>

              <div style='display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px;'>
                <div style='text-align:center;'>
                  <div style='color:#94a3b8;font-size:0.72rem;text-transform:uppercase;'>ML Prob</div>
                  <div style='color:#60a5fa;font-weight:700;font-size:1.05rem;'>{ml_v:.1%}</div>
                </div>
                <div style='text-align:center;'>
                  <div style='color:#94a3b8;font-size:0.72rem;text-transform:uppercase;'>Sentiment</div>
                  <div style='color:#a78bfa;font-weight:700;font-size:1.05rem;'>{sent_v:+.2f}</div>
                </div>
                <div style='text-align:center;'>
                  <div style='color:#94a3b8;font-size:0.72rem;text-transform:uppercase;'>Momentum</div>
                  <div style='color:#f472b6;font-weight:700;font-size:1.05rem;'>{mom_v:+.2f}</div>
                </div>
                <div style='text-align:center;'>
                  <div style='color:#94a3b8;font-size:0.72rem;text-transform:uppercase;'>Event</div>
                  <div style='color:#fbbf24;font-weight:600;font-size:0.9rem;'>{row.get("event_type","—")}</div>
                </div>
              </div>

              <div style='margin-bottom:10px;'>
                <div style='display:flex;justify-content:space-between;margin-bottom:4px;'>
                  <span style='color:#94a3b8;font-size:0.78rem;'>Final Score vs Threshold ({threshold:.0%})</span>
                  <span style='color:{"#10b981" if score>=threshold else "#ef4444"};font-weight:700;'>{score:.3f}</span>
                </div>
                <div class='score-bar-wrap'>
                  <div class='score-bar' style='width:{score_pct}%;background:{bar_color};'></div>
                </div>
                <div style='margin-top:4px;font-size:0.75rem;color:#64748b;'>{gap_txt}</div>
              </div>

              <div style='display:grid;grid-template-columns:repeat(4,1fr);gap:10px;border-top:1px solid rgba(255,255,255,0.05);padding-top:10px;'>
                <div><div style='color:#64748b;font-size:0.72rem;'>Entry</div><div style='color:#f1f5f9;font-weight:600;'>{entry_str}</div></div>
                <div><div style='color:#64748b;font-size:0.72rem;'>Stop Loss</div><div style='color:#ef4444;font-weight:600;'>{sl_str}</div></div>
                <div><div style='color:#64748b;font-size:0.72rem;'>Take Profit</div><div style='color:#10b981;font-weight:600;'>{tp_str}</div></div>
                <div><div style='color:#64748b;font-size:0.72rem;'>Reject Reason</div>
                  <div style='color:#94a3b8;font-size:0.8rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;'>{str(reject)[:60]}</div></div>
              </div>
            </div>
            """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════
# TAB 4 — ANALYTICS
# ══════════════════════════════════════════════════════════
with tab4:
    if df_all.empty:
        st.info("No data to analyse yet.")
    else:
        c1, c2 = st.columns(2)

        with c1:
            st.markdown("<div class='section-header'>Approval Rate by Agent</div>", unsafe_allow_html=True)
            rate_rows = []
            for ak in selected_agents:
                sub = df_all[df_all["agent"] == ak]
                total = len(sub)
                approved = len(sub[sub["status"]=="APPROVED"])
                if total > 0:
                    rate_rows.append({"Agent": AGENTS[ak]["label"], "Approved": approved, "Rejected": total-approved})
            if rate_rows:
                df_rate = pd.DataFrame(rate_rows)
                fig_rate = go.Figure()
                fig_rate.add_trace(go.Bar(x=df_rate["Agent"], y=df_rate["Approved"], name="Approved", marker_color="#10b981"))
                fig_rate.add_trace(go.Bar(x=df_rate["Agent"], y=df_rate["Rejected"], name="Rejected", marker_color="#ef4444", opacity=0.7))
                fig_rate.update_layout(
                    barmode="stack", height=280,
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(10,14,26,0.5)",
                    font=dict(family="Inter", color="#94a3b8"),
                    yaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
                    legend=dict(bgcolor="rgba(0,0,0,0)"),
                    margin=dict(l=0,r=0,t=10,b=0)
                )
                st.plotly_chart(fig_rate, use_container_width=True)

        with c2:
            st.markdown("<div class='section-header'>Score Distribution</div>", unsafe_allow_html=True)
            fig_dist = go.Figure()
            for ak in selected_agents:
                scores = df_all[df_all["agent"]==ak]["score"].dropna()
                if not scores.empty:
                    fig_dist.add_trace(go.Histogram(
                        x=scores, name=AGENTS[ak]["label"],
                        marker_color=AGENTS[ak]["color"], opacity=0.7, nbinsx=25
                    ))
            fig_dist.add_vline(x=threshold, line_dash="dash", line_color="#f59e0b",
                annotation_text=f"Threshold {threshold:.0%}", annotation_font_color="#f59e0b")
            fig_dist.update_layout(
                barmode="overlay", height=280,
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(10,14,26,0.5)",
                font=dict(family="Inter", color="#94a3b8"),
                xaxis=dict(title="Score", gridcolor="rgba(255,255,255,0.05)"),
                yaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
                legend=dict(bgcolor="rgba(0,0,0,0)"),
                margin=dict(l=0,r=0,t=10,b=0)
            )
            st.plotly_chart(fig_dist, use_container_width=True)

        # Top tickers
        st.markdown("<div class='section-header'>Most Frequently Analysed Tickers</div>", unsafe_allow_html=True)
        top = df_all.groupby("symbol").agg(
            count=("symbol","count"),
            approved=("status", lambda x: (x=="APPROVED").sum()),
            avg_score=("score","mean")
        ).reset_index().sort_values("count", ascending=True).tail(20)

        fig_top = go.Figure()
        fig_top.add_trace(go.Bar(
            x=top["count"], y=top["symbol"], orientation="h",
            marker_color=["#10b981" if a>0 else "#3b82f6" for a in top["approved"]],
            text=[f"{'✅' if a>0 else '❌'} Avg: {s:.3f}" if pd.notna(s) else "" for a,s in zip(top["approved"],top["avg_score"])],
            textposition="inside"
        ))
        fig_top.update_layout(
            height=500, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(10,14,26,0.5)",
            font=dict(family="Inter", color="#94a3b8"),
            xaxis=dict(title="Analysis Count", gridcolor="rgba(255,255,255,0.05)"),
            yaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
            margin=dict(l=0,r=0,t=10,b=0)
        )
        st.plotly_chart(fig_top, use_container_width=True)

        # Model weights
        st.markdown("<div class='section-header'>Self-Learning Model Weights</div>", unsafe_allow_html=True)
        wt_options = [a for a in selected_agents if a != "MarketBrainPro"]
        if wt_options:
            wt_agent = st.selectbox("Agent", wt_options, key="wt_sel")
            df_w = load_model_weights(wt_agent)
            if not df_w.empty:
                fig_w = go.Figure(go.Bar(
                    x=df_w["value"]*100,
                    y=df_w["weight_name"].str.replace("_factor","").str.title(),
                    orientation="h",
                    marker_color=["#3b82f6","#8b5cf6","#ec4899","#10b981","#f59e0b","#06b6d4"][:len(df_w)],
                    text=[f"{v:.1%}" for v in df_w["value"]], textposition="inside"
                ))
                fig_w.update_layout(
                    height=260, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(10,14,26,0.5)",
                    font=dict(family="Inter", color="#94a3b8"),
                    xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
                    yaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
                    margin=dict(l=0,r=0,t=10,b=0)
                )
                st.plotly_chart(fig_w, use_container_width=True)

        # Live logs
        st.markdown("<div class='section-header'>📋 Live System Logs</div>", unsafe_allow_html=True)
        log_level = st.selectbox("Level", ["ALL","INFO","WARNING","ERROR"], key="log_sel")
        df_sys = load_system_logs(selected_agents, 1, log_level)
        if not df_sys.empty:
            df_sys["timestamp"] = pd.to_datetime(df_sys["timestamp"]).dt.strftime("%H:%M:%S")
            st.dataframe(
                df_sys[["timestamp","agent","level","logger_name","message"]].rename(columns={
                    "timestamp":"Time","agent":"Agent","level":"Level",
                    "logger_name":"Logger","message":"Message"
                }),
                use_container_width=True, height=300
            )
        else:
            st.info("No recent logs found.")
