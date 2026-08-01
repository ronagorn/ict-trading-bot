import streamlit as st
import pandas as pd
import os
from supabase import create_client, Client
from dotenv import load_dotenv
import plotly.express as px

# โหลดตัวแปรสภาพแวดล้อม
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

st.set_page_config(page_title="ICT Trading Bot Dashboard", layout="wide", page_icon="📈")

@st.cache_resource
def init_connection():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        return None
    return create_client(url, key)

supabase = init_connection()

if not supabase:
    st.error("ไม่สามารถเชื่อมต่อฐานข้อมูล Supabase ได้ กรุณาตรวจสอบ .env")
    st.stop()

st.title("📈 ICT & SMC Algorithmic Trading Dashboard")
st.markdown("ระบบเทรดอัตโนมัติตามหลักการ Inner Circle Trader (ICT) - บริหารโดย **AURA-QUANT**")

@st.cache_data(ttl=60)
def load_data():
    try:
        response = supabase.table("trades").select("*").order("entry_time", desc=False).execute()
        df = pd.DataFrame(response.data)
        if not df.empty:
            df['entry_time'] = pd.to_datetime(df['entry_time'])
            if 'close_time' in df.columns:
                df['close_time'] = pd.to_datetime(df['close_time'])
        return df
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return pd.DataFrame()

df = load_data()

if df.empty:
    st.info("ยังไม่มีข้อมูลการเทรดในฐานข้อมูล")
else:
    # คำนวณสถิติ
    total_trades = len(df)
    closed_trades = df[df['status'] != 'OPEN']
    wins = len(closed_trades[closed_trades['status'] == 'WIN'])
    losses = len(closed_trades[closed_trades['status'] == 'LOSS'])
    win_rate = (wins / len(closed_trades) * 100) if len(closed_trades) > 0 else 0
    total_pl = closed_trades['profit_loss'].sum() if not closed_trades.empty else 0
    
    # แสดง KPI
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Trades", total_trades)
    col2.metric("Win Rate", f"{win_rate:.2f}%")
    col3.metric("Total P/L (USD)", f"${total_pl:.2f}")
    col4.metric("Active Open Trades", len(df[df['status'] == 'OPEN']))

    st.markdown("---")
    
    col_chart, col_stats = st.columns([2, 1])
    
    with col_chart:
        st.subheader("Equity Curve (Cumulative P/L)")
        if not closed_trades.empty:
            closed_trades = closed_trades.sort_values(by='close_time')
            closed_trades['cum_pl'] = closed_trades['profit_loss'].cumsum()
            fig = px.line(closed_trades, x='close_time', y='cum_pl', title='Cumulative Profit/Loss over time')
            st.plotly_chart(fig, use_container_width=True)
            
    with col_stats:
        st.subheader("Performance by Session")
        if not closed_trades.empty and 'session' in closed_trades.columns:
            session_stats = closed_trades.groupby('session').agg(
                Trades=('ticket_id', 'count'),
                Win_Rate=('status', lambda x: (x == 'WIN').mean() * 100),
                Total_PL=('profit_loss', 'sum')
            ).reset_index()
            session_stats['Win_Rate'] = session_stats['Win_Rate'].round(2)
            st.dataframe(session_stats, use_container_width=True)

    st.markdown("---")
    st.subheader("Trade History")
    
    # จัดเรียงใหม่ให้ข้อมูลล่าสุดอยู่บน
    st.dataframe(df.sort_values(by='entry_time', desc=True), use_container_width=True)
