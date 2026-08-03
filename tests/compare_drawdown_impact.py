import sys
import os
import io

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from smartmoneyconcepts import smc
from bot.mt5_client import MT5Client

def calculate_atr(df, period=14):
    high = df['high']
    low = df['low']
    close = df['close']
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean().bfill()

def run_comparison(days=180):
    print("=========================================================================")
    print(f"📊 Running Scientific Comparison: WITH DD Limit (3%) vs WITHOUT DD Limit ({days} Days)")
    print("=========================================================================")
    
    client = MT5Client()
    if not client.connect():
        print("❌ Failed to connect to MT5.")
        return
        
    symbols = ["GOLD#", "BTCUSD#", "EURUSD#", "GBPUSD#", "USDJPY#"]
    bars_needed = days * 96  # M15 bars
    
    # Capital per symbol $100
    initial_capital_per_sym = 100.0
    
    res_no_dd = {"trades": 0, "wins": 0, "losses": 0, "net_pnl": 0.0, "max_dd_pct": 0.0, "trades_list": []}
    res_with_dd = {"trades": 0, "wins": 0, "losses": 0, "net_pnl": 0.0, "max_dd_pct": 0.0, "trades_list": []}
    
    for symbol in symbols:
        mt5.symbol_select(symbol, True)
        rates_m15 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, bars_needed)
        rates_h4 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H4, 0, 1000)
        
        if rates_m15 is None or len(rates_m15) < 200:
            continue
            
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
            
        grouped = df.groupby('date')
        
        # -------------------------------------------------------------
        # PASS 1: WITHOUT DAILY DRAWDOWN LIMIT
        # -------------------------------------------------------------
        equity_no_dd = initial_capital_per_sym
        peak_equity_no_dd = equity_no_dd
        max_dd_no = 0.0
        
        for date_val, group in grouped:
            for i in group.index:
                if i < 200 or i >= len(df) - 30: continue
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
                    
                sub_fvg = fvg_df.loc[:i].tail(10)
                valid = sub_fvg[sub_fvg['FVG'].notna()]
                if valid.empty: continue
                
                last_fvg = valid.tail(1)
                fvg_dir = int(last_fvg['FVG'].iloc[0])
                fvg_top = last_fvg['Top'].iloc[0]
                fvg_bot = last_fvg['Bottom'].iloc[0]
                fvg_size = abs(fvg_top - fvg_bot)
                
                if fvg_size < (atr * 0.25): continue
                
                setup_type = None
                if m15_trend == 1 and fvg_dir == 1 and c_close > ema200:
                    if c_low <= fvg_top and c_high >= fvg_bot:
                        setup_type = "BUY"
                        entry = fvg_top if c_open > fvg_top else c_open
                        sl = fvg_bot - (atr * 0.8)
                        risk = abs(entry - sl)
                        tp = entry + (risk * 2.0)
                elif m15_trend == -1 and fvg_dir == -1 and c_close < ema200:
                    if c_high >= fvg_bot and c_low <= fvg_top:
                        setup_type = "SELL"
                        entry = fvg_bot if c_open < fvg_bot else c_open
                        sl = fvg_top + (atr * 0.8)
                        risk = abs(entry - sl)
                        tp = entry - (risk * 2.0)
                        
                if setup_type and risk > 0:
                    # Simulate trade outcome
                    future_df = df.loc[i+1:i+30]
                    won = False
                    lost = False
                    for _, row_f in future_df.iterrows():
                        if setup_type == "BUY":
                            if row_f['low'] <= sl: lost = True; break
                            if row_f['high'] >= tp: won = True; break
                        else:
                            if row_f['high'] >= sl: lost = True; break
                            if row_f['low'] <= tp: won = True; break
                            
                    res_no_dd['trades'] += 1
                    if won:
                        res_no_dd['wins'] += 1
                        pnl = 2.0  # +2% risk reward
                        equity_no_dd += pnl
                    elif lost:
                        res_no_dd['losses'] += 1
                        pnl = -1.0 # -1%
                        equity_no_dd += pnl
                        
                    if equity_no_dd > peak_equity_no_dd:
                        peak_equity_no_dd = equity_no_dd
                    dd = ((peak_equity_no_dd - equity_no_dd) / peak_equity_no_dd) * 100
                    if dd > max_dd_no: max_dd_no = dd

        res_no_dd['net_pnl'] += (equity_no_dd - initial_capital_per_sym)
        if max_dd_no > res_no_dd['max_dd_pct']: res_no_dd['max_dd_pct'] = max_dd_no

        # -------------------------------------------------------------
        # PASS 2: WITH 3.0% DAILY DRAWDOWN LIMIT (CIRCUIT BREAKER)
        # -------------------------------------------------------------
        equity_with_dd = initial_capital_per_sym
        peak_equity_with_dd = equity_with_dd
        max_dd_with = 0.0
        
        for date_val, group in grouped:
            day_start_equity = equity_with_dd
            day_stopped = False
            
            for i in group.index:
                if day_stopped: break
                if i < 200 or i >= len(df) - 30: continue
                
                # Check if daily drawdown reached 3.0%
                current_day_loss_pct = ((day_start_equity - equity_with_dd) / day_start_equity) * 100
                if current_day_loss_pct >= 3.0:
                    day_stopped = True
                    break
                    
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
                    
                sub_fvg = fvg_df.loc[:i].tail(10)
                valid = sub_fvg[sub_fvg['FVG'].notna()]
                if valid.empty: continue
                
                last_fvg = valid.tail(1)
                fvg_dir = int(last_fvg['FVG'].iloc[0])
                fvg_top = last_fvg['Top'].iloc[0]
                fvg_bot = last_fvg['Bottom'].iloc[0]
                fvg_size = abs(fvg_top - fvg_bot)
                
                if fvg_size < (atr * 0.25): continue
                
                setup_type = None
                if m15_trend == 1 and fvg_dir == 1 and c_close > ema200:
                    if c_low <= fvg_top and c_high >= fvg_bot:
                        setup_type = "BUY"
                        entry = fvg_top if c_open > fvg_top else c_open
                        sl = fvg_bot - (atr * 0.8)
                        risk = abs(entry - sl)
                        tp = entry + (risk * 2.0)
                elif m15_trend == -1 and fvg_dir == -1 and c_close < ema200:
                    if c_high >= fvg_bot and c_low <= fvg_top:
                        setup_type = "SELL"
                        entry = fvg_bot if c_open < fvg_bot else c_open
                        sl = fvg_top + (atr * 0.8)
                        risk = abs(entry - sl)
                        tp = entry - (risk * 2.0)
                        
                if setup_type and risk > 0:
                    future_df = df.loc[i+1:i+30]
                    won = False
                    lost = False
                    for _, row_f in future_df.iterrows():
                        if setup_type == "BUY":
                            if row_f['low'] <= sl: lost = True; break
                            if row_f['high'] >= tp: won = True; break
                        else:
                            if row_f['high'] >= sl: lost = True; break
                            if row_f['low'] <= tp: won = True; break
                            
                    res_with_dd['trades'] += 1
                    if won:
                        res_with_dd['wins'] += 1
                        pnl = 2.0
                        equity_with_dd += pnl
                    elif lost:
                        res_with_dd['losses'] += 1
                        pnl = -1.0
                        equity_with_dd += pnl
                        
                    if equity_with_dd > peak_equity_with_dd:
                        peak_equity_with_dd = equity_with_dd
                    dd = ((peak_equity_with_dd - equity_with_dd) / peak_equity_with_dd) * 100
                    if dd > max_dd_with: max_dd_with = dd

        res_with_dd['net_pnl'] += (equity_with_dd - initial_capital_per_sym)
        if max_dd_with > res_with_dd['max_dd_pct']: res_with_dd['max_dd_pct'] = max_dd_with

    mt5.shutdown()
    
    # -------------------------------------------------------------
    # DISPLAY COMPARISON RESULTS TABLE
    # -------------------------------------------------------------
    print("\n=========================================================================")
    print("                     🏆 BACKTEST COMPARISON RESULTS                      ")
    print("=========================================================================")
    
    winrate_no = (res_no_dd['wins'] / res_no_dd['trades'] * 100) if res_no_dd['trades'] > 0 else 0
    winrate_with = (res_with_dd['wins'] / res_with_dd['trades'] * 100) if res_with_dd['trades'] > 0 else 0
    
    print(f"指標 (Metrics)                  | ❌ ไม่มี DD Limit        | ✅ มี DD Limit (3%)")
    print(f"-------------------------------------------------------------------------")
    print(f"จำนวนออเดอร์ทั้งหมด (Total Trades) | {res_no_dd['trades']:<23} | {res_with_dd['trades']:<23}")
    print(f"จำนวนไม้ที่ชนะ (Win Trades)       | {res_no_dd['wins']:<23} | {res_with_dd['wins']:<23}")
    print(f"จำนวนไม้ที่แพ้ (Loss Trades)      | {res_no_dd['losses']:<23} | {res_with_dd['losses']:<23}")
    print(f"อัตราการชนะ (Win Rate %)         | {winrate_no:.2f}%{'':<17} | {winrate_with:.2f}%{'':<17}")
    print(f"ผลตอบแทนสุทธิ (Net Return %)    | +{res_no_dd['net_pnl']:.2f}%{'':<16} | +{res_with_dd['net_pnl']:.2f}%{'':<16}")
    print(f"Drawdown สูงสุด (Max Drawdown %)  | {res_no_dd['max_dd_pct']:.2f}%{'':<17} | {res_with_dd['max_dd_pct']:.2f}%{'':<17}")
    print("=========================================================================\n")

if __name__ == "__main__":
    run_comparison(180)
