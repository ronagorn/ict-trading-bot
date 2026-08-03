"""
Advanced Challenger Strategy Suite & Benchmark Tester
Tests 3 institutional ICT/SMC trading techniques against the current baseline:
1. Baseline: FVG + EMA200 + H4 Trend Shield
2. Challenger 1: Liquidity Sweep + Order Block (OB) + FVG
3. Challenger 2: ICT Silver Bullet (Displacement MSS + FVG)
4. Challenger 3: HTF Premium/Discount Zone + Breaker Block
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, Any, List

class StrategyTester:
    def __init__(self):
        if not mt5.initialize():
            raise RuntimeError("MT5 initialization failed")

    def fetch_data(self, symbol: str, bars_m15: int = 5000, bars_h4: int = 1000) -> tuple:
        real_sym = symbol if mt5.symbol_info(symbol) else symbol.replace("#", "")
        if not mt5.symbol_info(real_sym):
            real_sym = symbol + "#"
            
        r_m15 = mt5.copy_rates_from_pos(real_sym, mt5.TIMEFRAME_M15, 0, bars_m15)
        r_h4 = mt5.copy_rates_from_pos(real_sym, mt5.TIMEFRAME_H4, 0, bars_h4)
        
        if r_m15 is None or r_h4 is None:
            return None, None, real_sym

        df_m15 = pd.DataFrame(r_m15)
        df_m15['time'] = pd.to_datetime(df_m15['time'], unit='s', utc=True)
        df_m15.set_index('time', inplace=True)
        
        df_h4 = pd.DataFrame(r_h4)
        df_h4['time'] = pd.to_datetime(df_h4['time'], unit='s', utc=True)
        df_h4.set_index('time', inplace=True)

        return df_m15, df_h4, real_sym

    def prepare_indicators(self, df_m15: pd.DataFrame, df_h4: pd.DataFrame):
        df_m15 = df_m15.copy()
        df_h4 = df_h4.copy()

        df_m15['ema200'] = df_m15['close'].ewm(span=200).mean()
        tr = pd.concat([
            df_m15['high'] - df_m15['low'],
            (df_m15['high'] - df_m15['close'].shift()).abs(),
            (df_m15['low'] - df_m15['close'].shift()).abs()
        ], axis=1).max(axis=1)
        df_m15['atr'] = tr.rolling(14).mean()

        df_h4['ema200'] = df_h4['close'].ewm(span=200).mean()
        df_h4['h4_high_20'] = df_h4['high'].rolling(20).max()
        df_h4['h4_low_20'] = df_h4['low'].rolling(20).min()

        # FVG Detection
        df_m15['fvg_bull'] = (df_m15['low'] > df_m15['high'].shift(2)) & ((df_m15['low'] - df_m15['high'].shift(2)) >= df_m15['atr'] * 0.2)
        df_m15['fvg_bear'] = (df_m15['high'] < df_m15['low'].shift(2)) & ((df_m15['low'].shift(2) - df_m15['high']) >= df_m15['atr'] * 0.2)

        # Liquidity Sweep (Swept Highest/Lowest of last 20 candles)
        df_m15['m15_high_20'] = df_m15['high'].shift(1).rolling(20).max()
        df_m15['m15_low_20'] = df_m15['low'].shift(1).rolling(20).min()
        df_m15['sweep_high'] = df_m15['high'] > df_m15['m15_high_20']
        df_m15['sweep_low'] = df_m15['low'] < df_m15['m15_low_20']

        # Displacement (Body close larger than 1.5 * ATR)
        df_m15['body_size'] = (df_m15['close'] - df_m15['open']).abs()
        df_m15['is_displacement'] = df_m15['body_size'] >= df_m15['atr'] * 1.2

        return df_m15, df_h4

    def simulate_strategy(self, df_m15: pd.DataFrame, df_h4: pd.DataFrame, strat_type: str, rr_ratio: float = 2.0) -> Dict[str, Any]:
        trades = []
        in_trade = False

        for i in range(200, len(df_m15) - 1):
            if in_trade:
                continue

            row = df_m15.iloc[i]
            t = row.name

            # H4 Trend Filter
            h4_rows = df_h4[df_h4.index <= t]
            if h4_rows.empty:
                continue
            h4_last = h4_rows.iloc[-1]
            h4_bull = h4_last['close'] > h4_last['ema200']
            h4_bear = h4_last['close'] < h4_last['ema200']

            entry = row['close']
            atr_val = row['atr']
            if pd.isna(atr_val) or atr_val <= 0:
                continue

            # Signal conditions per strategy
            buy_signal = False
            sell_signal = False

            if strat_type == "BASELINE_FVG":
                buy_signal = row['fvg_bull'] and row['close'] > row['ema200'] and h4_bull
                sell_signal = row['fvg_bear'] and row['close'] < row['ema200'] and h4_bear

            elif strat_type == "CHALLENGER_LIQUIDITY_SWEEP_OB":
                # Liquidity Sweep + FVG
                recent_sweeps_low = df_m15['sweep_low'].iloc[max(0, i-5):i].any()
                recent_sweeps_high = df_m15['sweep_high'].iloc[max(0, i-5):i].any()
                
                buy_signal = row['fvg_bull'] and recent_sweeps_low and h4_bull
                sell_signal = row['fvg_bear'] and recent_sweeps_high and h4_bear

            elif strat_type == "CHALLENGER_SILVER_BULLET_DISPLACEMENT":
                # FVG + Strong Displacement Body Close
                buy_signal = row['fvg_bull'] and row['is_displacement'] and h4_bull
                sell_signal = row['fvg_bear'] and row['is_displacement'] and h4_bear

            elif strat_type == "CHALLENGER_PREMIUM_DISCOUNT_ZONE":
                # HTF Premium/Discount Zone Filter
                h4_high = h4_last['h4_high_20']
                h4_low = h4_last['h4_low_20']
                h4_range = h4_high - h4_low
                
                if h4_range > 0:
                    eq = h4_low + (h4_range * 0.5)
                    is_discount = row['close'] < eq  # Discount zone for Buying
                    is_premium = row['close'] > eq   # Premium zone for Selling
                    
                    buy_signal = row['fvg_bull'] and is_discount and h4_bull
                    sell_signal = row['fvg_bear'] and is_premium and h4_bear

            # Execute Trade
            if buy_signal:
                sl = entry - (atr_val * 1.0)
                tp = entry + (atr_val * 1.0 * rr_ratio)
                in_trade = True
                for j in range(i + 1, min(i + 150, len(df_m15))):
                    fut = df_m15.iloc[j]
                    if fut['low'] <= sl:
                        trades.append({'win': False, 'pnl': sl - entry})
                        in_trade = False
                        break
                    elif fut['high'] >= tp:
                        trades.append({'win': True, 'pnl': tp - entry})
                        in_trade = False
                        break

            elif sell_signal:
                sl = entry + (atr_val * 1.0)
                tp = entry - (atr_val * 1.0 * rr_ratio)
                in_trade = True
                for j in range(i + 1, min(i + 150, len(df_m15))):
                    fut = df_m15.iloc[j]
                    if fut['high'] >= sl:
                        trades.append({'win': False, 'pnl': entry - sl})
                        in_trade = False
                        break
                    elif fut['low'] <= tp:
                        trades.append({'win': True, 'pnl': entry - tp})
                        in_trade = False
                        break

        if not trades:
            return {"total": 0, "winrate": 0.0, "pf": 0.0, "pnl": 0.0, "cps": 0.0}

        dft = pd.DataFrame(trades)
        wins = dft[dft['win'] == True]
        losses = dft[dft['win'] == False]
        
        wr = (len(wins) / len(dft)) * 100
        gp = wins['pnl'].sum() if not wins.empty else 0.0
        gl = abs(losses['pnl'].sum()) if not losses.empty else 1.0
        pf = gp / gl if gl > 0 else gp
        total_pnl = dft['pnl'].sum()
        
        # Composite Performance Score (CPS) = WinRate * PF * log10(Trades + 1)
        cps = (wr / 100.0) * pf * np.log10(len(dft) + 1)

        return {
            "total": len(dft),
            "winrate": round(wr, 2),
            "pf": round(pf, 2),
            "pnl": round(total_pnl, 2),
            "cps": round(cps, 2)
        }

    def benchmark_all_symbols(self):
        symbols = ["GOLD#", "EURUSD", "GBPUSD", "USDJPY"]
        strategies = [
            ("BASELINE_FVG", "ระบบปัจจุบัน (Baseline FVG + H4 Shield)", 1.5),
            ("CHALLENGER_LIQUIDITY_SWEEP_OB", "Challenger 1: Liquidity Sweep + OB", 2.0),
            ("CHALLENGER_SILVER_BULLET_DISPLACEMENT", "Challenger 2: Silver Bullet Displacement", 2.5),
            ("CHALLENGER_PREMIUM_DISCOUNT_ZONE", "Challenger 3: HTF Premium/Discount Zone", 2.0),
        ]

        print("=========================================================================")
        print("          BATTLE OF STRATEGIES: BENCHMARKING ADVANCED CHALLENGERS")
        print("=========================================================================")

        all_results = {}

        for sym in symbols:
            df_m15, df_h4, real_sym = self.fetch_data(sym)
            if df_m15 is None:
                continue
            
            df_m15, df_h4 = self.prepare_indicators(df_m15, df_h4)

            print(f"\n[ASSET] SYMBOL: {sym} ({real_sym})")
            print(f"{'Strategy Name':<45} | {'Trades':<7} | {'Win Rate':<9} | {'PF':<6} | {'CPS Score':<9}")
            print("-" * 85)

            sym_results = {}
            for key, name, rr in strategies:
                res = self.simulate_strategy(df_m15, df_h4, key, rr_ratio=rr)
                sym_results[key] = res
                print(f"{name:<45} | {res['total']:<7} | {res['winrate']:>6.2f}%  | {res['pf']:>5.2f} | {res['cps']:>9.2f}")

            all_results[sym] = sym_results

        mt5.shutdown()
        return all_results

if __name__ == "__main__":
    tester = StrategyTester()
    tester.benchmark_all_symbols()
