import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import json
from dotenv import load_dotenv
from smartmoneyconcepts import smc
from bot.mt5_client import MT5Client

load_dotenv()

def calculate_atr(df, period=14):
    high = df['high']
    low = df['low']
    close = df['close']
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean().bfill()

def run_drawdown_capped_backtest(days=365):
    print(f"🚀 Running Realistic Backtest WITH Daily Drawdown Limit (Max 3% Loss/Day) for {days} Days...")
    client = MT5Client()
    if not client.connect():
        print("Failed to connect to MT5.")
        return
        
    symbols = ["GOLD#", "BTCUSD#", "EURUSD#", "GBPUSD#", "USDJPY#"]
    bars_needed = days * 96
    
    total_portfolio_equity = 100.0 * len(symbols) # ทุน $100 ต่อคู่เงิน
    initial_total_capital = total_portfolio_equity
    
    portfolio_daily_pnl = {}
    
    for symbol in symbols:
        mt5.symbol_select(symbol, True)
        rates_m15 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, bars_needed)
        rates_h4 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H4, 0, 1000)
        
        if rates_m15 is None: continue
        
        df = pd.DataFrame(rates_m15)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df['date'] = df['time'].dt.date
        df.rename(columns={'tick_volume': 'volume'}, inplace=True)
        df['ema200'] = df['close'].ewm(span=200).mean()
        df['atr'] = calculate_atr(df, 14)
        
        mss_h4 = None
        if "GOLD" in symbol and rates_h4 is not None:
            df_h4 = pd.DataFrame(rates_h4)
            df_h4['time'] = pd.to_datetime(df_h4['time'], unit='s')
            df_h4.rename(columns={'tick_volume': 'volume'}, inplace=True)
            swing_h4 = smc.swing_highs_lows(df_h4)
            mss_h4 = smc.bos_choch(df_h4, swing_h4)

        try:
            fvg_df = smc.fvg(df)
        except Exception:
            continue
            
        symbol_trades = []
        
        # จำลองเทรดทีละวันเพื่อบังคับใช้ Daily Drawdown Limit
        grouped_by_date = df.groupby('date')
        
        for date_val, group in grouped_by_date:
            if len(group) < 10: continue
            
            day_pnl_percent = 0.0
            day_stopped = False
            
            indices = group.index
            for i in indices:
                if i < 200 or i >= len(df) - 30: continue
                if day_stopped: break # หากสะสมขาดทุนแตะ 3% หยุดเทรดวันที่เหลือทันที
                
                c_close = df.loc[i, 'close']
                c_low = df.loc[i, 'low']
                c_high = df.loc[i, 'high']
                c_open = df.loc[i, 'open']
                ema200 = df.loc[i, 'ema200']
                atr = df.loc[i, 'atr']
                t_utc = df.loc[i, 'time']
                
                m15_trend = 1 if c_close > ema200 else -1
                
                if "GOLD" in symbol and mss_h4 is not None:
                    slice_h4 = mss_h4[df_h4['time'] <= t_utc]
                    if slice_h4.empty: continue
                    v_bos = slice_h4[slice_h4['BOS'].isin([1, -1])].tail(1)
                    v_choch = slice_h4[slice_h4['CHOCH'].isin([1, -1])].tail(1)
                    h4_trend = 0
                    if not v_bos.empty: h4_trend = int(v_bos['BOS'].iloc[0])
                    if not v_choch.empty and (v_bos.empty or v_choch.index[0] > v_bos.index[0]):
                        h4_trend = int(v_choch['CHOCH'].iloc[0])
                    if h4_trend != m15_trend: continue

                recent_fvg = fvg_df.iloc[i-5:i]
                if recent_fvg.empty: continue
                
                last_fvg = recent_fvg[recent_fvg['FVG'].notna()].tail(1)
                if last_fvg.empty: continue
                
                fvg_dir = int(last_fvg['FVG'].iloc[0])
                fvg_top = last_fvg['Top'].iloc[0]
                fvg_bot = last_fvg['Bottom'].iloc[0]
                fvg_size = abs(fvg_top - fvg_bot)
                
                if fvg_size < (atr * 0.3): continue
                
                # BUY
                if fvg_dir == 1 and m15_trend == 1 and c_low <= fvg_top and c_high >= fvg_bot:
                    entry = fvg_top if c_open > fvg_top else c_open
                    sl = fvg_bot - (atr * 0.8)
                    risk = abs(entry - sl)
                    if risk == 0: continue
                    tp = entry + (risk * 1.5)
                    
                    for m in range(i+1, min(i+40, len(df))):
                        if df.loc[m, 'low'] <= sl:
                            symbol_trades.append("LOSS")
                            day_pnl_percent -= 1.0
                            if day_pnl_percent <= -3.0:
                                day_stopped = True # ตัดหยุดเทรดประจำวัน!
                            break
                        if df.loc[m, 'high'] >= tp:
                            symbol_trades.append("WIN")
                            day_pnl_percent += 1.5
                            break

                # SELL
                elif fvg_dir == -1 and m15_trend == -1 and c_high >= fvg_bot and c_low <= fvg_top:
                    entry = fvg_bot if c_open < fvg_bot else c_open
                    sl = fvg_top + (atr * 0.8)
                    risk = abs(sl - entry)
                    if risk == 0: continue
                    tp = entry - (risk * 1.5)
                    
                    for m in range(i+1, min(i+40, len(df))):
                        if df.loc[m, 'high'] <= sl:
                            symbol_trades.append("LOSS")
                            day_pnl_percent -= 1.0
                            if day_pnl_percent <= -3.0:
                                day_stopped = True # ตัดหยุดเทรดประจำวัน!
                            break
                        if df.loc[m, 'low'] <= tp:
                            symbol_trades.append("WIN")
                            day_pnl_percent += 1.5
                            break
                            
        w = symbol_trades.count("WIN")
        l = symbol_trades.count("LOSS")
        tot = len(symbol_trades)
        net_pnl = (w * 1.5) - (l * 1.0) # $100 base
        wr = (w / tot * 100) if tot > 0 else 0
        print(f"📌 {symbol} (WITH Daily 3% Cap): Trades: {tot} | Win Rate: {wr:.2f}% | Net Return: +{net_pnl:.2f}% ($100 base)")

    client.shutdown()

if __name__ == "__main__":
    run_drawdown_capped_backtest(365)
