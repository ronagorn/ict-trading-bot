import streamlit as st
import pandas as pd
import os
from dotenv import load_dotenv
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timezone
import pytz

# โหลดค่าจาก .env อัตโนมัติ
env_path_parent = os.path.join(os.path.dirname(__file__), '..', '.env')
env_path_current = os.path.join(os.path.dirname(__file__), '.env')

if os.path.exists(env_path_current):
    load_dotenv(dotenv_path=env_path_current)
elif os.path.exists(env_path_parent):
    load_dotenv(dotenv_path=env_path_parent)
else:
    load_dotenv()

# นำเข้า supabase แบบ optional
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False

st.set_page_config(
    page_title="AURA Super Trader - AI Institutional Dashboard", 
    layout="wide", 
    page_icon="⚡",
    initial_sidebar_state="expanded"
)

# Custom CSS สำหรับดีไซน์สุดพรีเมียม (Futuristic Dark Glassmorphism)
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&family=JetBrains+Mono:wght@400;600&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Outfit', sans-serif;
    }
    
    .stApp {
        background-color: #0b0e14;
        background-image: 
            radial-gradient(at 10% 10%, rgba(30, 58, 138, 0.15) 0px, transparent 50%),
            radial-gradient(at 90% 90%, rgba(16, 185, 129, 0.1) 0px, transparent 50%);
    }
    
    /* Header Container */
    .header-box {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.7), rgba(15, 23, 42, 0.8));
        backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 16px;
        padding: 24px 32px;
        margin-bottom: 24px;
        box-shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.5);
    }
    .header-title {
        font-size: 32px;
        font-weight: 700;
        background: linear-gradient(90deg, #38bdf8, #3b82f6, #10b981);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 0;
    }
    .header-subtitle {
        color: #94a3b8;
        font-size: 14px;
        margin-top: 4px;
    }
    
    /* Metric Cards */
    .metric-card {
        background: rgba(15, 23, 42, 0.65);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 14px;
        padding: 18px 22px;
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .metric-card:hover {
        transform: translateY(-2px);
        border-color: rgba(56, 189, 248, 0.3);
    }
    .metric-label {
        font-size: 12px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: #64748b;
        margin-bottom: 6px;
    }
    .metric-value {
        font-size: 26px;
        font-weight: 700;
        color: #f8fafc;
        font-family: 'JetBrains Mono', monospace;
    }
    .metric-value-green { color: #10b981; }
    .metric-value-red { color: #f43f5e; }
    .metric-value-blue { color: #38bdf8; }
    
    /* Badges */
    .badge-win {
        background: rgba(16, 185, 129, 0.15);
        color: #10b981;
        border: 1px solid rgba(16, 185, 129, 0.3);
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
    }
    .badge-loss {
        background: rgba(244, 63, 94, 0.15);
        color: #f43f5e;
        border: 1px solid rgba(244, 63, 94, 0.3);
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
    }
    .badge-open {
        background: rgba(56, 189, 248, 0.15);
        color: #38bdf8;
        border: 1px solid rgba(56, 189, 248, 0.3);
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
    }
    
    /* Active Position Card */
    .pos-card {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.5), rgba(15, 23, 42, 0.6));
        border: 1px solid rgba(56, 189, 248, 0.2);
        border-radius: 12px;
        padding: 16px 20px;
        margin-bottom: 12px;
    }
    
    /* Tab Styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: rgba(15, 23, 42, 0.5);
        padding: 6px;
        border-radius: 12px;
        border: 1px solid rgba(255, 255, 255, 0.05);
    }
    .stTabs [data-baseweb="tab"] {
        height: 42px;
        border-radius: 8px;
        color: #94a3b8;
        font-weight: 600;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1e293b !important;
        color: #38bdf8 !important;
    }
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def init_connection():
    if not SUPABASE_AVAILABLE:
        return None
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        return None
    try:
        return create_client(url, key)
    except Exception:
        return None

supabase = init_connection()

def fetch_mt5_trades():
    """ดึงข้อมูลประวัติและออเดอร์เปิดอยู่จาก XM MT5 โดยตรง"""
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            return pd.DataFrame()
            
        from_time = datetime(2020, 1, 1, tzinfo=timezone.utc)
        to_time = datetime.now(timezone.utc)
        deals = mt5.history_deals_get(from_time, to_time)
        positions = mt5.positions_get()
        
        trades_dict = {}
        if deals:
            for d in deals:
                if not d.symbol: continue
                pos_id = d.position_id
                if pos_id not in trades_dict:
                    trades_dict[pos_id] = {
                        'ticket_id': pos_id,
                        'symbol': d.symbol,
                        'type': 'BUY' if d.type == 0 else 'SELL',
                        'entry_time': pd.to_datetime(datetime.fromtimestamp(d.time, tz=pytz.timezone('Asia/Bangkok'))),
                        'close_time': None,
                        'entry_price': d.price,
                        'sl': 0.0,
                        'tp': 0.0,
                        'lot_size': d.volume,
                        'profit_loss': 0.0,
                        'status': 'OPEN',
                        'session': 'London / NY'
                    }
                if d.entry == 0:
                    trades_dict[pos_id]['entry_price'] = d.price
                    trades_dict[pos_id]['lot_size'] = d.volume
                    trades_dict[pos_id]['type'] = 'BUY' if d.type == 0 else 'SELL'
                elif d.entry == 1:
                    trades_dict[pos_id]['close_time'] = pd.to_datetime(datetime.fromtimestamp(d.time, tz=pytz.timezone('Asia/Bangkok')))
                    trades_dict[pos_id]['profit_loss'] += d.profit
                    trades_dict[pos_id]['status'] = 'WIN' if d.profit > 0 else ('LOSS' if d.profit < 0 else 'EVEN')

        if positions:
            for pos in positions:
                pos_id = pos.ticket
                trades_dict[pos_id] = {
                    'ticket_id': pos_id,
                    'symbol': pos.symbol,
                    'type': 'BUY' if pos.type == 0 else 'SELL',
                    'entry_time': pd.to_datetime(datetime.fromtimestamp(pos.time, tz=pytz.timezone('Asia/Bangkok'))),
                    'close_time': None,
                    'entry_price': pos.price_open,
                    'sl': pos.sl,
                    'tp': pos.tp,
                    'lot_size': pos.volume,
                    'profit_loss': pos.profit,
                    'status': 'OPEN',
                    'session': 'London / NY'
                }

        df = pd.DataFrame(list(trades_dict.values()))
        mt5.shutdown()
        return df
    except Exception:
        return pd.DataFrame()

# Top Header Banner
st.markdown("""
<div class="header-box">
    <div style="display: flex; justify-content: space-between; align-items: center;">
        <div>
            <div class="header-title">⚡ AURA Super Trader AI Dashboard</div>
            <div class="header-subtitle">Institutional ICT / SMC Algorithmic Execution System • Live Monitoring</div>
        </div>
        <div style="text-align: right;">
            <span class="badge-win">LIVE BROKER FEED</span>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# Sidebar
st.sidebar.markdown("### ⚙️ System Controls")
data_source = st.sidebar.radio("Data Source:", ["Auto (Supabase + XM MT5 Direct)", "XM MT5 Direct Only"])

if st.sidebar.button("🔄 Refresh Data", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

@st.cache_data(ttl=10)
def load_data(source_mode):
    df_db = pd.DataFrame()
    err_msg = None

    if source_mode == "Auto (Supabase + XM MT5 Direct)" and supabase:
        try:
            response = supabase.table("trades").select("*").order("entry_time", desc=False).execute()
            df_db = pd.DataFrame(response.data)
            if not df_db.empty:
                df_db['entry_time'] = pd.to_datetime(df_db['entry_time'])
                if 'close_time' in df_db.columns:
                    df_db['close_time'] = pd.to_datetime(df_db['close_time'])
        except Exception as e:
            err_msg = str(e)

    if df_db.empty:
        df_mt5 = fetch_mt5_trades()
        if not df_mt5.empty:
            return df_mt5, None, "XM MT5 Direct Feed"

    return df_db, err_msg, "Supabase Database"

df, err_msg, source_used = load_data(data_source)
st.sidebar.caption(f"📡 Connection Source: **{source_used}**")

if df.empty:
    st.info("ℹ️ ยังไม่มีประวัติการเทรดบันทึกอยู่ (บอทกำลังรันสแกนตลาดเรียลไทม์เพื่อรอเข้าออเดอร์)")
else:
    # คำนวณ KPIs
    closed_trades = df[df['status'] != 'OPEN']
    open_trades = df[df['status'] == 'OPEN']
    
    total_trades = len(df)
    wins = len(closed_trades[closed_trades['status'] == 'WIN'])
    losses = len(closed_trades[closed_trades['status'] == 'LOSS'])
    win_rate = (wins / len(closed_trades) * 100) if len(closed_trades) > 0 else 0
    
    net_pnl = closed_trades['profit_loss'].sum() if not closed_trades.empty else 0
    floating_pnl = open_trades['profit_loss'].sum() if not open_trades.empty else 0
    
    # KPI Metric Cards Grid
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Net Profit / Loss</div>
            <div class="metric-value {'metric-value-green' if net_pnl >= 0 else 'metric-value-red'}">
                {"$" if net_pnl >= 0 else "-$"}{abs(net_pnl):,.2f}
            </div>
        </div>
        """, unsafe_allow_html=True)
        
    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Win Rate</div>
            <div class="metric-value metric-value-blue">{win_rate:.1f}%</div>
        </div>
        """, unsafe_allow_html=True)
        
    with col3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Active Open Trades</div>
            <div class="metric-value metric-value-blue">{len(open_trades)} ไม้</div>
        </div>
        """, unsafe_allow_html=True)

    with col4:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Floating P/L</div>
            <div class="metric-value {'metric-value-green' if floating_pnl >= 0 else 'metric-value-red'}">
                {"$" if floating_pnl >= 0 else "-$"}{abs(floating_pnl):,.2f}
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    
    # Tabs layout
    tab1, tab2, tab3 = st.tabs(["📊 Performance & Analytics", "⚡ Active Orders", "📜 Execution History"])
    
    with tab1:
        col_curve, col_breakdown = st.columns([2, 1])
        
        with col_curve:
            st.markdown("#### Cumulative Equity Curve")
            if not closed_trades.empty:
                closed_sorted = closed_trades.sort_values(by='close_time')
                closed_sorted['cum_pnl'] = closed_sorted['profit_loss'].cumsum()
                
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=closed_sorted['close_time'],
                    y=closed_sorted['cum_pnl'],
                    mode='lines+markers',
                    line=dict(color='#10b981', width=3, shape='spline'),
                    marker=dict(size=8, color='#38bdf8'),
                    fill='tozeroy',
                    fillcolor='rgba(16, 185, 129, 0.08)'
                ))
                fig.update_layout(
                    template='plotly_dark',
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    margin=dict(l=10, r=10, t=10, b=10),
                    height=340,
                    xaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.05)'),
                    yaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.05)', title='USD ($)')
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("ยังไม่มีออเดอร์ปิดสำหรับวาด Equity Curve")

        with col_breakdown:
            st.markdown("#### Win / Loss Distribution")
            if not closed_trades.empty:
                pie_fig = go.Figure(data=[go.Pie(
                    labels=['Win', 'Loss'],
                    values=[wins, losses],
                    hole=.6,
                    marker=dict(colors=['#10b981', '#f43f5e'])
                )])
                pie_fig.update_layout(
                    template='plotly_dark',
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    margin=dict(l=0, r=0, t=10, b=10),
                    height=340,
                    showlegend=True
                )
                st.plotly_chart(pie_fig, use_container_width=True)
            else:
                st.info("ไม่มีข้อมูลสถิติปิด")

    with tab2:
        st.markdown("#### Live Active Open Positions")
        if not open_trades.empty:
            for idx, row in open_trades.iterrows():
                pnl = row['profit_loss']
                pnl_color = "#10b981" if pnl >= 0 else "#f43f5e"
                st.markdown(f"""
                <div class="pos-card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <div>
                            <span class="badge-open">#{row['ticket_id']}</span>
                            <span style="font-size:18px; font-weight:700; color:#f8fafc; margin-left:8px;">{row['symbol']}</span>
                            <span style="color:{'#10b981' if row['type']=='BUY' else '#f43f5e'}; font-weight:700; margin-left:8px;">{row['type']}</span>
                        </div>
                        <div style="font-size:20px; font-weight:700; color:{pnl_color}; font-family:'JetBrains Mono';">
                            {"$" if pnl >= 0 else "-$"}{abs(pnl):.2f}
                        </div>
                    </div>
                    <div style="display:flex; gap:24px; margin-top:10px; color:#94a3b8; font-size:13px;">
                        <div>Entry: <b>{row['entry_price']:.2f}</b></div>
                        <div>SL: <b>{row['sl']:.2f}</b></div>
                        <div>TP: <b>{row['tp']:.2f}</b></div>
                        <div>Lot: <b>{row['lot_size']}</b></div>
                        <div>Time: <b>{row['entry_time']}</b></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("ℹ️ ไม่มีออเดอร์เปิดค้างอยู่ ณ ขณะนี้")

    with tab3:
        st.markdown("#### Complete Trade Log")
        display_df = df.copy()
        display_df = display_df.sort_values(by='entry_time', ascending=False)
        st.dataframe(
            display_df,
            column_config={
                "ticket_id": "Ticket #",
                "symbol": "Symbol",
                "type": "Type",
                "entry_price": st.column_config.NumberColumn("Entry Price", format="%.2f"),
                "sl": st.column_config.NumberColumn("Stop Loss", format="%.2f"),
                "tp": st.column_config.NumberColumn("Take Profit", format="%.2f"),
                "profit_loss": st.column_config.NumberColumn("P/L (USD)", format="$%.2f"),
                "status": "Status"
            },
            use_container_width=True,
            hide_index=True
        )
