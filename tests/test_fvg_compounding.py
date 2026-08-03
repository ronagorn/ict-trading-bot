import sys
import os

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from smartmoneyconcepts import smc
from bot.mt5_client import MT5Client

def calculate_atr(df, period=14):
    high = df['high']
    low = df['low']
    close = df['close']
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean().bfill()

def test_fvg_compounding(days=90):
    client = MT5Client()
    if not client.connect():
        print("❌ Failed to connect to MT5.")
        return
        
    symbols = ["GOLD#", "BTCUSD#", "EURUSD#", "GBPUSD#", "USDJPY#"]
    bars_needed = days * 96
    
    # Capital $1,000 Total ($200 per symbol)
    initial_total_capital = 1000.0
    
    trades = 0
    wins = 0
    losses = 0
    
    # Capital tracking
    eq_fixed = 1000.0
    eq_compound = 1000.0
    
    peak_fixed = eq_fixed
    peak_compound = eq_compound
    max_dd_fixed = 0.0
    max_dd_compound = 0.0
    
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
        
        # Per symbol starting equity $200
        sym_eq_fixed = 200.0
        sym_eq_compound = 200.0
        
        for date_val, group in grouped:
            for i in group.index:
                if i < 200 or i >= len(df) - 30: continue
                c_close = df.loc[i, 'close']
                c_open = df.loc[i, 'open']
                c_high = df.loc[i, 'high']
                c_low = df.loc[i, 'low']
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
                fvg_size = abs(fvg_top - fvg_bot)
                
                if fvg_size < (atr * 0.25): continue
                
                setup = None
                if trend == 1 and fvg_dir == 1 and c_close > ema200:
                    if c_low <= fvg_top and c_high >= fvg_bot:
                        entry = fvg_top if c_open > fvg_top else c_open
                        sl = fvg_bot - (atr * 0.8)
                        risk = abs(entry - sl)
                        tp = entry + (risk * 2.0)
                        setup = ("BUY", entry, sl, tp)
                elif trend == -1 and fvg_dir == -1 and c_close < ema200:
                    if c_high >= fvg_bot and c_low <= fvg_top:
                        entry = fvg_bot if c_open < fvg_bot else c_open
                        sl = fvg_top + (atr * 0.8)
                        risk = abs(entry - sl)
                        tp = entry - (risk * 2.0)
                        setup = ("SELL", entry, sl, tp)
                        
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
                            
                    trades += 1
                    if won:
                        wins += 1
                        # Fixed: +$4.0 (+2% of initial $200)
                        sym_eq_fixed += 4.0
                        # Compound: +2.0% of current equity
                        sym_eq_compound += (sym_eq_compound * 0.02)
                    elif lost:
                        losses += 1
                        # Fixed: -$2.0 (-1% of initial $200)
                        sym_eq_fixed -= 2.0
                        # Compound: -1.0% of current equity
                        sym_eq_compound -= (sym_eq_compound * 0.01)

        eq_fixed += (sym_eq_fixed - 200.0)
        eq_compound += (sym_eq_compound - 200.0)

    mt5.shutdown()
    
    wr = (wins / trades * 100) if trades > 0 else 0
    ret_fixed = ((eq_fixed - initial_total_capital) / initial_total_capital) * 100
    ret_compound = ((eq_compound - initial_total_capital) / initial_total_capital) * 100
    
    print("\n=========================================================================")
    print(f"🚀 COMPOUND INTEREST SIMULATION ON CURRENT FVG STRATEGY ({days} DAYS)")
    print("=========================================================================")
    print(f"💰 เงินทุนตั้งต้น (Initial Capital):  $1,000 (35,000 บาท)")
    print(f"📊 จำนวนไม้ทั้งหมด (Total Trades):     {trades:,} ไม้ (Win Rate: {wr:.1f}%)")
    print(f"-------------------------------------------------------------------------")
    print(f"🔴 แบบไม่ทบต้น (Fixed Risk $10/ไม้):  ${eq_fixed:,.2f}  (กำไรสุทธิ +{ret_fixed:,.1f}%)")
    print(f"🟢 แบบทบต้น (Compounding 1%/ไม้):     ${eq_compound:,.2f}  (กำไรสุทธิ +{ret_compound:,.1f}%)")
    print("=========================================================================\n")

if __name__ == "__main__":
    test_fvg_compounding(90)
