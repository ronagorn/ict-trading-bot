import MetaTrader5 as mt5
import pandas as pd
import numpy as np

def run_comparison():
    if not mt5.initialize():
        print("MT5 Init Failed")
        return

    symbols = ["GOLD#", "EURUSD", "GBPUSD", "USDJPY"]
    
    for symbol in symbols:
        real_sym = symbol if mt5.symbol_info(symbol) else symbol.replace("#", "")
        if not mt5.symbol_info(real_sym):
            real_sym = symbol + "#"
            
        r_m15 = mt5.copy_rates_from_pos(real_sym, mt5.TIMEFRAME_M15, 0, 5000)
        r_h4 = mt5.copy_rates_from_pos(real_sym, mt5.TIMEFRAME_H4, 0, 1000)
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

        df_m15['fvg_bull'] = (df_m15['low'] > df_m15['high'].shift(2)) & ((df_m15['low'] - df_m15['high'].shift(2)) >= df_m15['atr'] * 0.2)
        df_m15['fvg_bear'] = (df_m15['high'] < df_m15['low'].shift(2)) & ((df_m15['low'].shift(2) - df_m15['high']) >= df_m15['atr'] * 0.2)

        # Test System A: Current System (H4 Shield + RR 1:1.5)
        trades_a = []
        in_trade_a = False
        for i in range(200, len(df_m15)-1):
            if in_trade_a: continue
            row = df_m15.iloc[i]
            t = row.name
            h4_rows = df_h4[df_h4.index <= t]
            if h4_rows.empty: continue
            h4_last = h4_rows.iloc[-1]
            h4_bull = h4_last['close'] > h4_last['ema200']
            h4_bear = h4_last['close'] < h4_last['ema200']

            entry = row['close']
            atr_val = row['atr']
            if pd.isna(atr_val) or atr_val == 0: continue

            if row['fvg_bull'] and row['close'] > row['ema200'] and h4_bull:
                sl = entry - atr_val * 0.8
                tp = entry + (entry - sl) * 1.5
                in_trade_a = True
                for j in range(i+1, min(i+100, len(df_m15))):
                    fut = df_m15.iloc[j]
                    if fut['low'] <= sl:
                        trades_a.append({'win': False, 'pnl': sl - entry})
                        in_trade_a = False
                        break
                    elif fut['high'] >= tp:
                        trades_a.append({'win': True, 'pnl': tp - entry})
                        in_trade_a = False
                        break
            elif row['fvg_bear'] and row['close'] < row['ema200'] and h4_bear:
                sl = entry + atr_val * 0.8
                tp = entry - (sl - entry) * 1.5
                in_trade_a = True
                for j in range(i+1, min(i+100, len(df_m15))):
                    fut = df_m15.iloc[j]
                    if fut['high'] >= sl:
                        trades_a.append({'win': False, 'pnl': entry - sl})
                        in_trade_a = False
                        break
                    elif fut['low'] <= tp:
                        trades_a.append({'win': True, 'pnl': entry - tp})
                        in_trade_a = False
                        break

        dft_a = pd.DataFrame(trades_a)
        wr_a = (len(dft_a[dft_a['win']==True]) / len(dft_a) * 100) if not dft_a.empty else 0
        gp_a = dft_a[dft_a['win']==True]['pnl'].sum() if not dft_a.empty else 0
        gl_a = abs(dft_a[dft_a['win']==False]['pnl'].sum()) if not dft_a.empty else 1
        pf_a = gp_a / gl_a if gl_a > 0 else gp_a

        print(f"=== {symbol} ===")
        print(f"  [ระบบปัจจุบัน (H4 Trend Shield + R:R 1:1.5)] -> WinRate: {wr_a:.2f}%, Profit Factor: {pf_a:.2f}, Total Trades: {len(dft_a)}")

    mt5.shutdown()

if __name__ == "__main__":
    run_comparison()
