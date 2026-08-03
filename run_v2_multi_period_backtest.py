"""
ICT Strategy V2 Multi-Period Backtester (1 Day, 1 Month, 1 Year)
Runs comprehensive backtest for ICTStrategy V2 across all 12 assets.
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta, timezone

class V2MultiPeriodBacktester:
    def __init__(self, config_path: str = "bot/config.json"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)
        self.symbols = self.config.get("symbols", [])
        if not mt5.initialize():
            raise RuntimeError("MT5 initialization failed")

    def resolve_symbol(self, symbol: str) -> str:
        candidates = [symbol, symbol.replace("#", ""), symbol + "#"]
        if "GOLD" in symbol.upper() or "XAU" in symbol.upper():
            candidates.extend(["GOLD#", "XAUUSD#", "GOLD", "XAUUSD"])
        for cand in candidates:
            if mt5.symbol_info(cand) is not None:
                return cand
        return symbol

    def backtest_v2_symbol(self, symbol: str) -> dict:
        real_sym = self.resolve_symbol(symbol)
        
        # Determine timeframe
        preset = self.config.get("optimized_strategy_presets", {}).get(symbol, {})
        tf_str = preset.get("timeframe", "M15")
        
        tf_map = {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30
        }
        mt5_tf = tf_map.get(tf_str, mt5.TIMEFRAME_M15)

        # Fetch M15/M5 bars (50,000 bars ~ 1 Year for M15) and H4 bars
        rates = mt5.copy_rates_from_pos(real_sym, mt5_tf, 0, 45000)
        rates_h4 = mt5.copy_rates_from_pos(real_sym, mt5.TIMEFRAME_H4, 0, 3000)

        if rates is None or len(rates) == 0 or rates_h4 is None or len(rates_h4) == 0:
            return None

        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
        df.set_index('time', inplace=True)
        df['ema200'] = df['close'].ewm(span=200).mean()

        tr = pd.concat([
            df['high'] - df['low'],
            (df['high'] - df['close'].shift()).abs(),
            (df['low'] - df['close'].shift()).abs()
        ], axis=1).max(axis=1)
        df['atr'] = tr.rolling(14).mean()

        # FVG Detection
        df['fvg_bull'] = (df['low'] > df['high'].shift(2)) & ((df['low'] - df['high'].shift(2)) >= df['atr'] * 0.2)
        df['fvg_bear'] = (df['high'] < df['low'].shift(2)) & ((df['low'].shift(2) - df['high']) >= df['atr'] * 0.2)

        # H4 Indicators
        df_h4 = pd.DataFrame(rates_h4)
        df_h4['time'] = pd.to_datetime(df_h4['time'], unit='s', utc=True)
        df_h4.set_index('time', inplace=True)
        df_h4['ema200'] = df_h4['close'].ewm(span=200).mean()
        df_h4['h4_high_30'] = df_h4['high'].rolling(30).max()
        df_h4['h4_low_30'] = df_h4['low'].rolling(30).min()

        # Point size & spread
        info = mt5.symbol_info(real_sym)
        point_size = info.point if info and info.point > 0 else 0.00001
        default_sp = info.spread if info else 15
        
        is_crypto = any(c in symbol.upper() for c in ["BTC", "ETH", "XRP"])
        max_sp = 50000.0 if is_crypto else 350.0

        rr_ratio = 2.0

        # Simulate Strategy over all bars
        all_trades = []
        in_trade = False

        for i in range(200, len(df) - 1):
            if in_trade:
                continue

            row = df.iloc[i]
            t = row.name

            # HTF H4 Confluence
            h4_rows = df_h4[df_h4.index <= t]
            if h4_rows.empty:
                continue
            h4_last = h4_rows.iloc[-1]
            
            h4_bull = h4_last['close'] > h4_last['ema200']
            h4_bear = h4_last['close'] < h4_last['ema200']

            h4_high = h4_last['h4_high_30']
            h4_low = h4_last['h4_low_30']
            h4_range = h4_high - h4_low
            
            if pd.isna(h4_range) or h4_range <= 0:
                continue
                
            eq = h4_low + (h4_range * 0.5)
            is_discount = row['close'] < eq
            is_premium = row['close'] > eq

            entry = row['close']
            atr_val = row['atr']
            if pd.isna(atr_val) or atr_val <= 0:
                continue

            fvg_size = abs(df['high'].iloc[i-2] - row['low']) if row['fvg_bull'] else abs(df['low'].iloc[i-2] - row['high'])
            if fvg_size < atr_val * 0.2:
                continue

            buy_signal = row['fvg_bull'] and row['close'] > row['ema200'] and h4_bull and is_discount
            sell_signal = row['fvg_bear'] and row['close'] < row['ema200'] and h4_bear and is_premium

            if buy_signal:
                sl = entry - (atr_val * 0.8)
                tp = entry + (entry - sl) * rr_ratio
                in_trade = True
                for j in range(i + 1, min(i + 150, len(df))):
                    fut = df.iloc[j]
                    if fut['low'] <= sl:
                        pnl_pts = (sl - entry) / point_size - default_sp
                        all_trades.append({'time': fut.name, 'win': False, 'pnl': pnl_pts})
                        in_trade = False
                        break
                    elif fut['high'] >= tp:
                        pnl_pts = (tp - entry) / point_size - default_sp
                        all_trades.append({'time': fut.name, 'win': True, 'pnl': pnl_pts})
                        in_trade = False
                        break

            elif sell_signal:
                sl = entry + (atr_val * 0.8)
                tp = entry - (sl - entry) * rr_ratio
                in_trade = True
                for j in range(i + 1, min(i + 150, len(df))):
                    fut = df.iloc[j]
                    if fut['high'] >= sl:
                        pnl_pts = (entry - sl) / point_size - default_sp
                        all_trades.append({'time': fut.name, 'win': False, 'pnl': pnl_pts})
                        in_trade = False
                        break
                    elif fut['low'] <= tp:
                        pnl_pts = (entry - tp) / point_size - default_sp
                        all_trades.append({'time': fut.name, 'win': True, 'pnl': pnl_pts})
                        in_trade = False
                        break

        if not all_trades:
            empty_res = {"total": 0, "winrate": 0.0, "pf": 0.0, "pnl_pts": 0.0, "max_dd_pts": 0.0}
            return {"1_day": empty_res, "1_month": empty_res, "1_year": empty_res}

        df_trades = pd.DataFrame(all_trades)
        df_trades.set_index('time', inplace=True)
        
        now = datetime.now(timezone.utc)
        dt_1d = now - timedelta(days=1)
        dt_1m = now - timedelta(days=30)
        dt_1y = now - timedelta(days=365)

        def eval_period(sub_df):
            if sub_df.empty:
                return {"total": 0, "winrate": 0.0, "pf": 0.0, "pnl_pts": 0.0, "max_dd_pts": 0.0}
            wins = sub_df[sub_df['win'] == True]
            losses = sub_df[sub_df['win'] == False]
            wr = len(wins) / len(sub_df) * 100
            gp = wins['pnl'].sum() if not wins.empty else 0.0
            gl = abs(losses['pnl'].sum()) if not losses.empty else 1.0
            pf = gp / gl if gl > 0 else gp
            total_pnl = sub_df['pnl'].sum()
            eq = sub_df['pnl'].cumsum()
            dd = eq.cummax() - eq
            max_dd = dd.max() if not dd.empty else 0.0
            
            return {
                "total": len(sub_df),
                "winrate": round(wr, 2),
                "pf": round(pf, 2),
                "pnl_pts": round(total_pnl, 1),
                "max_dd_pts": round(max_dd, 1)
            }

        return {
            "timeframe": tf_str,
            "1_day": eval_period(df_trades[df_trades.index >= dt_1d]),
            "1_month": eval_period(df_trades[df_trades.index >= dt_1m]),
            "1_year": eval_period(df_trades[df_trades.index >= dt_1y])
        }

    def run_all(self):
        results = {}
        for sym in self.symbols:
            res = self.backtest_v2_symbol(sym)
            if res:
                results[sym] = res
        mt5.shutdown()
        return results

if __name__ == "__main__":
    tester = V2MultiPeriodBacktester()
    res = tester.run_all()
    print(json.dumps(res, indent=2))
