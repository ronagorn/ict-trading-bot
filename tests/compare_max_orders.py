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

def compare_max_orders():
    print("🚀 Comparing Fixed Max Orders (Limit 2) vs Unlimited Open Orders (AI Unlimited)...")
    client = MT5Client()
    if not client.connect():
        print("Failed to connect to MT5.")
        return
        
    symbols = ["GOLD#", "BTCUSD#", "EURUSD#", "GBPUSD#", "USDJPY#"]
    days = 30
    bars_needed = days * 96
    
    # Run simulation for Unlimited vs Limited (2)
    for max_limit in [2, 10]:
        mode_label = f"Fixed Limit ({max_limit} Max Trades)" if max_limit == 2 else "Unlimited AI Scan (10 Max Trades)"
        print(f"\n📊 Testing: {mode_label}...")
        
        total_wins = 0
        total_losses = 0
        total_trades = 0
        total_pnl = 0.0
        
        for symbol in symbols:
            rates_m15 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, bars_needed)
            if rates_m15 is None: continue
            
            df = pd.DataFrame(rates_m15)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df.rename(columns={'tick_volume': 'volume'}, inplace=True)
            df['ema200'] = df['close'].ewm(span=200).mean()
            df['atr'] = calculate_atr(df, 14)
            
            fvg_df = smc.fvg(df)
            trades = []
            
            for i in range(200, len(df) - 30):
                c_close = df.loc[i, 'close']
                c_low = df.loc[i, 'low']
                c_high = df.loc[i, 'high']
                c_open = df.loc[i, 'open']
                ema200 = df.loc[i, 'ema200']
                atr = df.loc[i, 'atr']
                
                m15_trend = 1 if c_close > ema200 else -1
                
                recent_fvg = fvg_df.iloc[i-5:i]
                if recent_fvg.empty: continue
                
                last_fvg = recent_fvg[recent_fvg['FVG'].notna()].tail(1)
                if last_fvg.empty: continue
                
                fvg_dir = int(last_fvg['FVG'].iloc[0])
                fvg_top = last_fvg['Top'].iloc[0]
                fvg_bot = last_fvg['Bottom'].iloc[0]
                fvg_size = abs(fvg_top - fvg_bot)
                
                if fvg_size < (atr * 0.3): continue
                
                if fvg_dir == 1 and m15_trend == 1 and c_low <= fvg_top and c_high >= fvg_bot:
                    entry = fvg_top if c_open > fvg_top else c_open
                    sl = fvg_bot - (atr * 0.8)
                    risk = abs(entry - sl)
                    if risk == 0: continue
                    tp = entry + (risk * 1.5)
                    
                    for m in range(i+1, min(i+50, len(df))):
                        if df.loc[m, 'low'] <= sl:
                            trades.append('LOSS')
                            break
                        if df.loc[m, 'high'] >= tp:
                            trades.append('WIN')
                            break
                            
                elif fvg_dir == -1 and m15_trend == -1 and c_high >= fvg_bot and c_low <= fvg_top:
                    entry = fvg_bot if c_open < fvg_bot else c_open
                    sl = fvg_top + (atr * 0.8)
                    risk = abs(sl - entry)
                    if risk == 0: continue
                    tp = entry - (risk * 1.5)
                    
                    for m in range(i+1, min(i+50, len(df))):
                        if df.loc[m, 'high'] <= sl:
                            trades.append('LOSS')
                            break
                        if df.loc[m, 'low'] <= tp:
                            trades.append('WIN')
                            break
                            
            w = trades.count("WIN")
            l = trades.count("LOSS")
            total_wins += w
            total_losses += l
            total_trades += len(trades)
            total_pnl += (w * 1.5) - (l * 1.0)
            
        winrate = (total_wins / total_trades * 100) if total_trades > 0 else 0
        print(f"  Result for {mode_label}:")
        print(f"    - Total Trades: {total_trades}")
        print(f"    - Win Rate: {winrate:.2f}%")
        print(f"    - Net Return (Units of Risk): +{total_pnl:.2f} R")

    client.shutdown()

if __name__ == "__main__":
    compare_max_orders()
