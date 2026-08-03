import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta, timezone

def run_v2_quick():
    if not mt5.initialize():
        print("MT5 Init Failed")
        return

    with open("bot/config.json", "r", encoding="utf-8") as f:
        config = json.load(f)
        
    symbols = config.get("symbols", [])
    results = {}

    for symbol in symbols:
        real_sym = symbol if mt5.symbol_info(symbol) else symbol.replace("#", "")
        if not mt5.symbol_info(real_sym):
            real_sym = symbol + "#"
            
        r_m15 = mt5.copy_rates_from_pos(real_sym, mt5.TIMEFRAME_M15, 0, 15000)
        r_h4 = mt5.copy_rates_from_pos(real_sym, mt5.TIMEFRAME_H4, 0, 1500)
        if r_m15 is None or r_h4 is None:
            continue

        df_m15 = pd.DataFrame(r_m15)
        df_m15['time'] = pd.to_datetime(df_m15['time'], unit='s', utc=True)
        df_m15.set_index('time', inplace=True)
        df_m15['ema200'] = df_m15['close'].ewm(span=200).mean()
        
        tr = pd.concat([df_m15['high']-df_m15['low'], (df_m15['high']-df_m15['close'].shift()).abs(), (df_m15['low']-df_m15['close'].shift()).abs()], axis=1).max(axis=1)
        df_m15['atr'] = tr.rolling(14).mean()

        df_h4 = pd.DataFrame(r_h4)
        df_h4['time'] = pd.to_datetime(df_h4['time'], unit='s', utc=True)
        df_h4.set_index('time', inplace=True)
        df_h4['ema200'] = df_h4['close'].ewm(span=200).mean()
        df_h4['h4_high'] = df_h4['high'].rolling(30).max()
        df_h4['h4_low'] = df_h4['low'].rolling(30).min()

        df_m15['fvg_bull'] = (df_m15['low'] > df_m15['high'].shift(2)) & ((df_m15['low'] - df_m15['high'].shift(2)) >= df_m15['atr'] * 0.2)
        df_m15['fvg_bear'] = (df_m15['high'] < df_m15['low'].shift(2)) & ((df_m15['low'].shift(2) - df_m15['high']) >= df_m15['atr'] * 0.2)

        trades = []
        in_trade = False

        for i in range(200, len(df_m15)-1):
            if in_trade: continue
            row = df_m15.iloc[i]
            t = row.name
            
            h4_rows = df_h4[df_h4.index <= t]
            if h4_rows.empty: continue
            h4_last = h4_rows.iloc[-1]
            h4_bull = h4_last['close'] > h4_last['ema200']
            h4_bear = h4_last['close'] < h4_last['ema200']

            h4_h = h4_last['h4_high']
            h4_l = h4_last['h4_low']
            h4_rng = h4_h - h4_l
            if pd.isna(h4_rng) or h4_rng <= 0: continue
            eq = h4_l + (h4_rng * 0.5)

            is_discount = row['close'] < eq
            is_premium = row['close'] > eq

            entry = row['close']
            atr_val = row['atr']
            if pd.isna(atr_val) or atr_val == 0: continue

            if row['fvg_bull'] and row['close'] > row['ema200'] and h4_bull and is_discount:
                sl = entry - atr_val * 0.8
                tp = entry + (entry - sl) * 2.0
                in_trade = True
                for j in range(i+1, min(i+100, len(df_m15))):
                    fut = df_m15.iloc[j]
                    if fut['low'] <= sl:
                        trades.append({'time': fut.name, 'win': False, 'pnl': sl - entry})
                        in_trade = False
                        break
                    elif fut['high'] >= tp:
                        trades.append({'time': fut.name, 'win': True, 'pnl': tp - entry})
                        in_trade = False
                        break
            elif row['fvg_bear'] and row['close'] < row['ema200'] and h4_bear and is_premium:
                sl = entry + atr_val * 0.8
                tp = entry - (sl - entry) * 2.0
                in_trade = True
                for j in range(i+1, min(i+100, len(df_m15))):
                    fut = df_m15.iloc[j]
                    if fut['high'] >= sl:
                        trades.append({'time': fut.name, 'win': False, 'pnl': entry - sl})
                        in_trade = False
                        break
                    elif fut['low'] <= tp:
                        trades.append({'time': fut.name, 'win': True, 'pnl': entry - tp})
                        in_trade = False
                        break

        if not trades:
            continue

        dft = pd.DataFrame(trades)
        dft.set_index('time', inplace=True)
        now = datetime.now(timezone.utc)
        
        def calc_res(sub):
            if sub.empty: return {"trades": 0, "wr": 0.0, "pf": 0.0}
            w = sub[sub['win']==True]
            l = sub[sub['win']==False]
            wr = len(w)/len(sub)*100
            gp = w['pnl'].sum() if not w.empty else 0
            gl = abs(l['pnl'].sum()) if not l.empty else 1
            return {"trades": len(sub), "wr": round(wr, 2), "pf": round(gp/gl, 2)}

        results[symbol] = {
            "1_day": calc_res(dft[dft.index >= (now - timedelta(days=1))]),
            "1_month": calc_res(dft[dft.index >= (now - timedelta(days=30))]),
            "1_year": calc_res(dft[dft.index >= (now - timedelta(days=365))])
        }

    mt5.shutdown()
    with open("v2_results.json", "w", encoding="utf-8") as out:
        json.dump(results, out, indent=2)
    print("V2 Backtest Complete!")

if __name__ == "__main__":
    run_v2_quick()
