import sys
import os

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from smartmoneyconcepts import smc

def calculate_atr(df, period=14):
    high = df['high']
    low = df['low']
    close = df['close']
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean().bfill()

from bot.mt5_client import MT5Client

def run_fast_comparison(days=60):
    client = MT5Client()
    if not client.connect():
        print("❌ Failed to connect to MT5.")
        return
        
    symbols = ["GOLD#", "BTCUSD#", "EURUSD#", "GBPUSD#", "USDJPY#"]
    bars_needed = days * 96
    initial_capital = 500.0
    
    res_no_dd = {"trades": 0, "wins": 0, "losses": 0, "net_pnl": 0.0, "max_dd": 0.0}
    res_with_dd = {"trades": 0, "wins": 0, "losses": 0, "net_pnl": 0.0, "max_dd": 0.0}
    
    for symbol in symbols:
        mt5.symbol_select(symbol, True)
        rates_m15 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, bars_needed)
        if rates_m15 is None or len(rates_m15) < 200: continue
            
        df = pd.DataFrame(rates_m15)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df['date'] = df['time'].dt.date
        df.rename(columns={'tick_volume': 'volume'}, inplace=True)
        df['ema200'] = df['close'].ewm(span=200).mean()
        df['atr'] = calculate_atr(df, 14)
        
        try:
            fvg_df = smc.fvg(df)
        except Exception:
            continue
            
        grouped = df.groupby('date')
        
        # PASS 1: NO DD LIMIT
        eq_no = 100.0
        peak_no = eq_no
        dd_no_max = 0.0
        for date_val, group in grouped:
            for i in group.index:
                if i < 200 or i >= len(df) - 30: continue
                c_close = df.loc[i, 'close']
                ema200 = df.loc[i, 'ema200']
                atr = df.loc[i, 'atr']
                trend = 1 if c_close > ema200 else -1
                
                sub_fvg = fvg_df.loc[:i].tail(10)
                valid = sub_fvg[sub_fvg['FVG'].notna()]
                if valid.empty: continue
                
                last_fvg = valid.tail(1)
                fvg_dir = int(last_fvg['FVG'].iloc[0])
                fvg_top = last_fvg['Top'].iloc[0]
                fvg_bot = last_fvg['Bottom'].iloc[0]
                
                setup = None
                if trend == 1 and fvg_dir == 1 and c_close > ema200:
                    if df.loc[i, 'low'] <= fvg_top and df.loc[i, 'high'] >= fvg_bot:
                        setup = ("BUY", fvg_top, fvg_bot - (atr * 0.8), fvg_top + (abs(fvg_top - (fvg_bot - (atr*0.8))) * 2.0))
                elif trend == -1 and fvg_dir == -1 and c_close < ema200:
                    if df.loc[i, 'high'] >= fvg_bot and df.loc[i, 'low'] <= fvg_top:
                        setup = ("SELL", fvg_bot, fvg_top + (atr * 0.8), fvg_bot - (abs(fvg_top + (atr*0.8) - fvg_bot) * 2.0))
                        
                if setup:
                    stype, entry, sl, tp = setup
                    fut = df.loc[i+1:i+30]
                    won = False; lost = False
                    for _, rf in fut.iterrows():
                        if stype == "BUY":
                            if rf['low'] <= sl: lost = True; break
                            if rf['high'] >= tp: won = True; break
                        else:
                            if rf['high'] >= sl: lost = True; break
                            if rf['low'] <= tp: won = True; break
                    res_no_dd['trades'] += 1
                    if won:
                        res_no_dd['wins'] += 1
                        eq_no += 2.0
                    elif lost:
                        res_no_dd['losses'] += 1
                        eq_no -= 1.0
                    if eq_no > peak_no: peak_no = eq_no
                    dd = ((peak_no - eq_no) / peak_no) * 100
                    if dd > dd_no_max: dd_no_max = dd
        res_no_dd['net_pnl'] += (eq_no - 100.0)
        if dd_no_max > res_no_dd['max_dd']: res_no_dd['max_dd'] = dd_no_max

        # PASS 2: WITH 3.0% DAILY DRAWDOWN LIMIT
        eq_with = 100.0
        peak_with = eq_with
        dd_with_max = 0.0
        for date_val, group in grouped:
            day_start_eq = eq_with
            day_stopped = False
            for i in group.index:
                if day_stopped: break
                if i < 200 or i >= len(df) - 30: continue
                
                day_loss_pct = ((day_start_eq - eq_with) / day_start_eq) * 100
                if day_loss_pct >= 3.0:
                    day_stopped = True
                    break
                    
                c_close = df.loc[i, 'close']
                ema200 = df.loc[i, 'ema200']
                atr = df.loc[i, 'atr']
                trend = 1 if c_close > ema200 else -1
                
                sub_fvg = fvg_df.loc[:i].tail(10)
                valid = sub_fvg[sub_fvg['FVG'].notna()]
                if valid.empty: continue
                
                last_fvg = valid.tail(1)
                fvg_dir = int(last_fvg['FVG'].iloc[0])
                fvg_top = last_fvg['Top'].iloc[0]
                fvg_bot = last_fvg['Bottom'].iloc[0]
                
                setup = None
                if trend == 1 and fvg_dir == 1 and c_close > ema200:
                    if df.loc[i, 'low'] <= fvg_top and df.loc[i, 'high'] >= fvg_bot:
                        setup = ("BUY", fvg_top, fvg_bot - (atr * 0.8), fvg_top + (abs(fvg_top - (fvg_bot - (atr*0.8))) * 2.0))
                elif trend == -1 and fvg_dir == -1 and c_close < ema200:
                    if df.loc[i, 'high'] >= fvg_bot and df.loc[i, 'low'] <= fvg_top:
                        setup = ("SELL", fvg_bot, fvg_top + (atr * 0.8), fvg_bot - (abs(fvg_top + (atr*0.8) - fvg_bot) * 2.0))
                        
                if setup:
                    stype, entry, sl, tp = setup
                    fut = df.loc[i+1:i+30]
                    won = False; lost = False
                    for _, rf in fut.iterrows():
                        if stype == "BUY":
                            if rf['low'] <= sl: lost = True; break
                            if rf['high'] >= tp: won = True; break
                        else:
                            if rf['high'] >= sl: lost = True; break
                            if rf['low'] <= tp: won = True; break
                    res_with_dd['trades'] += 1
                    if won:
                        res_with_dd['wins'] += 1
                        eq_with += 2.0
                    elif lost:
                        res_with_dd['losses'] += 1
                        eq_with -= 1.0
                    if eq_with > peak_with: peak_with = eq_with
                    dd = ((peak_with - eq_with) / peak_with) * 100
                    if dd > dd_with_max: dd_with_max = dd
        res_with_dd['net_pnl'] += (eq_with - 100.0)
        if dd_with_max > res_with_dd['max_dd']: res_with_dd['max_dd'] = dd_with_max

    mt5.shutdown()
    
    wr_no = (res_no_dd['wins'] / res_no_dd['trades'] * 100) if res_no_dd['trades'] > 0 else 0
    wr_with = (res_with_dd['wins'] / res_with_dd['trades'] * 100) if res_with_dd['trades'] > 0 else 0
    
    print("\n=========================================================================")
    print("                 🏆 FAST BACKTEST RESULTS (60 DAYS)                      ")
    print("=========================================================================")
    print(f"指標 (Metrics)                  | ❌ ไม่จำกัด DD          | ✅ มี DD Limit (3%)")
    print(f"-------------------------------------------------------------------------")
    print(f"จำนวนออเดอร์ทั้งหมด (Total Trades) | {res_no_dd['trades']:<23} | {res_with_dd['trades']:<23}")
    print(f"จำนวนไม้ที่ชนะ (Win Trades)       | {res_no_dd['wins']:<23} | {res_with_dd['wins']:<23}")
    print(f"จำนวนไม้ที่แพ้ (Loss Trades)      | {res_no_dd['losses']:<23} | {res_with_dd['losses']:<23}")
    print(f"อัตราการชนะ (Win Rate %)         | {wr_no:.2f}%{'':<17} | {wr_with:.2f}%{'':<17}")
    print(f"ผลตอบแทนสุทธิ (Net Return %)    | +{res_no_dd['net_pnl']:.2f}%{'':<16} | +{res_with_dd['net_pnl']:.2f}%{'':<16}")
    print(f"Drawdown สูงสุด (Max Drawdown %)  | {res_no_dd['max_dd']:.2f}%{'':<17} | {res_with_dd['max_dd']:.2f}%{'':<17}")
    print("=========================================================================\n")

if __name__ == "__main__":
    run_fast_comparison(60)
