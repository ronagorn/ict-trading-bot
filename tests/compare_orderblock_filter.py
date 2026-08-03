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
from bot.mt5_client import MT5Client

def calculate_atr(df, period=14):
    high = df['high']
    low = df['low']
    close = df['close']
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean().bfill()

def run_ob_comparison(days=90):
    print("=========================================================================")
    print(f"📊 Testing Step 3 & Step 4: HTF Order Block Confluence & Compound Interest ({days} Days)")
    print("=========================================================================")
    
    client = MT5Client()
    if not client.connect():
        print("❌ Failed to connect to MT5.")
        return
        
    symbols = ["GOLD#", "BTCUSD#", "EURUSD#", "GBPUSD#", "USDJPY#"]
    bars_needed = days * 96
    
    # ---------------------------------------------------------
    # STRATEGY A: Standard M15 FVG + Premium/Discount
    # STRATEGY B: Step 3 (M15 FVG + HTF 4H Order Block Confluence)
    # STRATEGY C: Step 3 + Step 4 (HTF Order Block + Compound Interest)
    # ---------------------------------------------------------
    res_a = {"trades": 0, "wins": 0, "losses": 0, "final_eq": 500.0, "max_dd": 0.0}
    res_b = {"trades": 0, "wins": 0, "losses": 0, "final_eq": 500.0, "max_dd": 0.0}
    res_c = {"trades": 0, "wins": 0, "losses": 0, "final_eq": 500.0, "max_dd": 0.0}

    for symbol in symbols:
        mt5.symbol_select(symbol, True)
        rates_m15 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, bars_needed)
        rates_h4 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H4, 0, 1000)
        
        if rates_m15 is None or len(rates_m15) < 200: continue
            
        df_m15 = pd.DataFrame(rates_m15)
        df_m15['time'] = pd.to_datetime(df_m15['time'], unit='s')
        df_m15['date'] = df_m15['time'].dt.date
        df_m15.rename(columns={'tick_volume': 'volume'}, inplace=True)
        df_m15['ema200'] = df_m15['close'].ewm(span=200).mean()
        df_m15['atr'] = calculate_atr(df_m15, 14)
        
        ob_h4 = None
        if rates_h4 is not None and len(rates_h4) > 50:
            df_h4 = pd.DataFrame(rates_h4)
            df_h4['time'] = pd.to_datetime(df_h4['time'], unit='s')
            df_h4.rename(columns={'tick_volume': 'volume'}, inplace=True)
            swings_h4 = smc.swing_highs_lows(df_h4)
            try:
                ob_h4 = smc.ob(df_h4, swings_h4)
            except Exception:
                ob_h4 = None

        try:
            fvg_m15 = smc.fvg(df_m15)
        except Exception:
            continue

        grouped = df_m15.groupby('date')
        
        # Track equities per symbol
        eq_a = 100.0; peak_a = eq_a; max_dd_a = 0.0
        eq_b = 100.0; peak_b = eq_b; max_dd_b = 0.0
        eq_c = 100.0; peak_c = eq_c; max_dd_c = 0.0

        for date_val, group in grouped:
            for i in group.index:
                if i < 200 or i >= len(df_m15) - 30: continue
                c_close = df_m15.loc[i, 'close']
                c_open = df_m15.loc[i, 'open']
                c_high = df_m15.loc[i, 'high']
                c_low = df_m15.loc[i, 'low']
                ema200 = df_m15.loc[i, 'ema200']
                atr = df_m15.loc[i, 'atr']
                t_utc = df_m15.loc[i, 'time']
                
                trend = 1 if c_close > ema200 else -1
                
                sub_fvg = fvg_m15.loc[:i].tail(10)
                valid_fvg = sub_fvg[sub_fvg['FVG'].notna()]
                if valid_fvg.empty: continue
                
                last_fvg = valid_fvg.tail(1)
                fvg_dir = int(last_fvg['FVG'].iloc[0])
                fvg_top = last_fvg['Top'].iloc[0]
                fvg_bot = last_fvg['Bottom'].iloc[0]
                fvg_size = abs(fvg_top - fvg_bot)
                
                if fvg_size < (atr * 0.25): continue
                
                # Check HTF 4H Order Block Confluence
                in_h4_ob = False
                h4_ob_dir = 0
                if ob_h4 is not None and rates_h4 is not None:
                    # Find active unmitigated or recent H4 OBs up to time t_utc
                    slice_h4 = df_h4[df_h4['time'] <= t_utc]
                    if not slice_h4.empty:
                        last_idx = slice_h4.index[-1]
                        recent_obs = ob_h4.loc[:last_idx]
                        valid_obs = recent_obs[recent_obs['OB'].notna()]
                        if not valid_obs.empty:
                            last_ob = valid_obs.tail(3)
                            for _, ob_row in last_ob.iterrows():
                                ob_top = ob_row['Top']
                                ob_bot = ob_row['Bottom']
                                if c_low <= ob_top and c_high >= ob_bot:
                                    in_h4_ob = True
                                    h4_ob_dir = int(ob_row['OB'])
                                    break
                
                # Setup check
                setup = None
                if trend == 1 and fvg_dir == 1 and c_close > ema200:
                    if c_low <= fvg_top and c_high >= fvg_bot:
                        entry = fvg_top if c_open > fvg_top else c_open
                        sl = fvg_bot - (atr * 0.8)
                        risk = abs(entry - sl)
                        tp = entry + (risk * 2.5) # High 1:2.5 R:R for HTF OB
                        setup = ("BUY", entry, sl, tp)
                elif trend == -1 and fvg_dir == -1 and c_close < ema200:
                    if c_high >= fvg_bot and c_low <= fvg_top:
                        entry = fvg_bot if c_open < fvg_bot else c_open
                        sl = fvg_top + (atr * 0.8)
                        risk = abs(entry - sl)
                        tp = entry - (risk * 2.5)
                        setup = ("SELL", entry, sl, tp)
                        
                if setup:
                    stype, entry, sl, tp = setup
                    fut = df_m15.loc[i+1:i+30]
                    won = False; lost = False
                    for _, rf in fut.iterrows():
                        if stype == "BUY":
                            if rf['low'] <= sl: lost = True; break
                            if rf['high'] >= tp: won = True; break
                        else:
                            if rf['high'] >= sl: lost = True; break
                            if rf['low'] <= tp: won = True; break

                    # --- Strategy A: Standard FVG ---
                    res_a['trades'] += 1
                    if won:
                        res_a['wins'] += 1; eq_a += 2.5
                    elif lost:
                        res_a['losses'] += 1; eq_a -= 1.0
                    if eq_a > peak_a: peak_a = eq_a
                    dd_a = ((peak_a - eq_a) / peak_a) * 100
                    if dd_a > max_dd_a: max_dd_a = dd_a

                    # --- Strategy B & C: Filtered by HTF Order Block Confluence ---
                    is_ob_match = in_h4_ob and ((stype == "BUY" and h4_ob_dir == 1) or (stype == "SELL" and h4_ob_dir == -1))
                    if is_ob_match or "GOLD" in symbol:  # GOLD or OB Confluence
                        res_b['trades'] += 1
                        res_c['trades'] += 1
                        
                        if won:
                            res_b['wins'] += 1
                            res_c['wins'] += 1
                            eq_b += 2.5
                            # Compound 2.5% of current equity
                            eq_c += (eq_c * 0.025)
                        elif lost:
                            res_b['losses'] += 1
                            res_c['losses'] += 1
                            eq_b -= 1.0
                            # Risk 1.0% of current equity
                            eq_c -= (eq_c * 0.01)
                            
                        if eq_b > peak_b: peak_b = eq_b
                        dd_b = ((peak_b - eq_b) / peak_b) * 100
                        if dd_b > max_dd_b: max_dd_b = dd_b
                        
                        if eq_c > peak_c: peak_c = eq_c
                        dd_c = ((peak_c - eq_c) / peak_c) * 100
                        if dd_c > max_dd_c: max_dd_c = dd_c

        res_a['final_eq'] += (eq_a - 100.0)
        res_b['final_eq'] += (eq_b - 100.0)
        res_c['final_eq'] += (eq_c - 100.0)
        if max_dd_a > res_a['max_dd']: res_a['max_dd'] = max_dd_a
        if max_dd_b > res_b['max_dd']: res_b['max_dd'] = max_dd_b
        if max_dd_c > res_c['max_dd']: res_c['max_dd'] = max_dd_c

    mt5.shutdown()
    
    wr_a = (res_a['wins'] / res_a['trades'] * 100) if res_a['trades'] > 0 else 0
    wr_b = (res_b['wins'] / res_b['trades'] * 100) if res_b['trades'] > 0 else 0
    wr_c = (res_c['wins'] / res_c['trades'] * 100) if res_c['trades'] > 0 else 0
    
    ret_a = ((res_a['final_eq'] - 500.0) / 500.0) * 100
    ret_b = ((res_b['final_eq'] - 500.0) / 500.0) * 100
    ret_c = ((res_c['final_eq'] - 500.0) / 500.0) * 100
    
    print("\n=========================================================================================")
    print("                    🏆 STEP 3 & STEP 4 BACKTEST RESULTS (90 DAYS)                        ")
    print("=========================================================================================")
    print(f"指標 (Metrics)                  | 🔵 1. Standard FVG  | 🟣 2. HTF OrderBlock  | 🟢 3. HTF OB + Compound")
    print(f"-----------------------------------------------------------------------------------------")
    print(f"จำนวนออเดอร์ทั้งหมด (Total Trades) | {res_a['trades']:<18} | {res_b['trades']:<18} | {res_c['trades']:<18}")
    print(f"จำนวนไม้ที่ชนะ (Win Trades)       | {res_a['wins']:<18} | {res_b['wins']:<18} | {res_c['wins']:<18}")
    print(f"จำนวนไม้ที่แพ้ (Loss Trades)      | {res_a['losses']:<18} | {res_b['losses']:<18} | {res_c['losses']:<18}")
    print(f"อัตราการชนะ (Win Rate %)         | {wr_a:.2f}%{'':<12} | {wr_b:.2f}%{'':<12} | {wr_c:.2f}%{'':<12}")
    print(f"ผลตอบแทนสุทธิ (Net Return %)    | +{ret_a:.2f}%{'':<11} | +{ret_b:.2f}%{'':<11} | +{ret_c:.2f}%{'':<11}")
    print(f"Drawdown สูงสุด (Max Drawdown %)  | {res_a['max_dd']:.2f}%{'':<13} | {res_b['max_dd']:.2f}%{'':<13} | {res_c['max_dd']:.2f}%{'':<13}")
    print("=========================================================================================\n")

if __name__ == "__main__":
    run_ob_comparison(90)
