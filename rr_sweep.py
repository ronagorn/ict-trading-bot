# -*- coding: utf-8 -*-
import sys
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import os
os.environ['PYTHONIOENCODING'] = 'utf-8'

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from collections import defaultdict

SYMBOLS = ["BTCUSD#", "ETHUSD#", "XRPUSD#"]
M15_BARS = 2000
H4_BARS = 500
STEP = 15
START_OFFSET = 200
MAX_HOLD_BARS = 200

class TickMock:
    def __init__(self, bid, ask):
        self.bid = bid
        self.ask = ask
        self.last = (bid + ask) / 2

class BacktestClient:
    def __init__(self, symbol, m15_df, h4_df, current_time):
        self.symbol = symbol
        self.m15_full = m15_df
        self.h4_full = h4_df
        self.current_time = current_time
        self.connected = True
    def get_rates(self, symbol, timeframe, num_bars):
        if timeframe == "H4" or timeframe == mt5.TIMEFRAME_H4:
            df = self.h4_full
        else:
            df = self.m15_full
        df = df[df["time"] <= self.current_time].copy()
        if df.empty: return None
        return df.tail(num_bars)
    def get_tick(self, symbol):
        df = self.m15_full[self.m15_full["time"] <= self.current_time].copy()
        if df.empty: return None
        last = df.iloc[-1]
        return TickMock(bid=float(last["close"]), ask=float(last["close"]))
    def ensure_symbol_selected(self, s): return True
    def ensure_connection(self): pass

def fetch_data(symbol):
    mt5.symbol_select(symbol, True)
    m15_rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, M15_BARS)
    m15_df = pd.DataFrame(m15_rates)
    m15_df["time"] = pd.to_datetime(m15_df["time"], unit="s")
    if "tick_volume" in m15_df.columns:
        m15_df.rename(columns={"tick_volume": "volume"}, inplace=True)
    h4_rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H4, 0, H4_BARS)
    h4_df = pd.DataFrame(h4_rates)
    h4_df["time"] = pd.to_datetime(h4_df["time"], unit="s")
    if "tick_volume" in h4_df.columns:
        h4_df.rename(columns={"tick_volume": "volume"}, inplace=True)
    return m15_df, h4_df

def simulate_trade(m15_df, entry_bar_idx, direction, entry, sl, tp):
    total_bars = len(m15_df)
    end = min(entry_bar_idx + MAX_HOLD_BARS, total_bars)
    risk = abs(entry - sl)
    reward = abs(tp - entry)
    rr = reward / risk if risk > 0 else 1.0
    for i in range(entry_bar_idx + 1, end):
        bar = m15_df.iloc[i]
        high = float(bar["high"])
        low = float(bar["low"])
        if direction == "BUY":
            if low <= sl: return {"outcome": "LOSS", "r_multiple": -1.0, "exit_bar": i, "exit_type": "SL"}
            if high >= tp: return {"outcome": "WIN", "r_multiple": rr, "exit_bar": i, "exit_type": "TP"}
        else:
            if high >= sl: return {"outcome": "LOSS", "r_multiple": -1.0, "exit_bar": i, "exit_type": "SL"}
            if low <= tp: return {"outcome": "WIN", "r_multiple": rr, "exit_bar": i, "exit_type": "TP"}
    return {"outcome": "LOSS", "r_multiple": -0.5, "exit_bar": end, "exit_type": "TIMEOUT"}

def run_backtest(base_rr, fvg_atr_mult):
    from bot.strategy import ICTStrategy
    config = {
        "risk_per_trade_percent": 1.0,
        "aura_ultimate": {
            "sniper_mode_enabled": True,
            "fvg_atr_mult": fvg_atr_mult,
            "ob_lookback": 20,
            "sniper_rr": base_rr + 1,
            "base_rr": base_rr,
            "use_4h_shield": True,
            "directional_fvg_filter": True,
        }
    }
    strategy = ICTStrategy(None, config)
    all_trades = []
    
    data_cache = {}
    for sym in SYMBOLS:
        m15_df, h4_df = fetch_data(sym)
        data_cache[sym] = (m15_df, h4_df)
    
    for sym in SYMBOLS:
        m15_df, h4_df = data_cache[sym]
        for start in range(START_OFFSET, len(m15_df) - 50, STEP):
            current_time = m15_df.iloc[start]["time"]
            client = BacktestClient(sym, m15_df, h4_df, current_time)
            strategy.mt5 = client
            try:
                trend = strategy.analyze_market_structure(sym)
            except:
                continue
            if trend == "NEUTRAL":
                continue
            try:
                setup = strategy.find_super_trader_setup(sym, trend)
            except:
                continue
            if setup is None:
                continue
            entry = setup["entry"]
            sl = setup["sl"]
            tp = setup["tp"]
            direction = setup["type"]
            risk_price = abs(entry - sl)
            if risk_price <= 0:
                continue
            if start + 1 >= len(m15_df):
                continue
            actual_entry = float(m15_df.iloc[start + 1]["open"])
            if direction == "BUY":
                sl_dist = entry - sl
                tp_dist = tp - entry
                sl = actual_entry - sl_dist
                tp = actual_entry + tp_dist
            else:
                sl_dist = sl - entry
                tp_dist = entry - tp
                sl = actual_entry + sl_dist
                tp = actual_entry - tp_dist
            result = simulate_trade(m15_df, start + 1, direction, actual_entry, sl, tp)
            if result is None:
                continue
            all_trades.append({
                "symbol": sym,
                "direction": direction,
                "result": result["outcome"],
                "exit_type": result["exit_type"],
                "r_multiple": result["r_multiple"],
            })
    
    total = len(all_trades)
    wins = sum(1 for t in all_trades if t["result"] == "WIN")
    losses = total - wins
    total_r = sum(t["r_multiple"] for t in all_trades)
    timeouts = sum(1 for t in all_trades if t["exit_type"] == "TIMEOUT")
    sl_hits = sum(1 for t in all_trades if t["exit_type"] == "SL")
    tp_hits = sum(1 for t in all_trades if t["exit_type"] == "TP")
    wr = wins / total * 100 if total else 0
    
    return {
        "total": total, "wins": wins, "losses": losses,
        "total_r": total_r, "wr": wr,
        "timeouts": timeouts, "sl_hits": sl_hits, "tp_hits": tp_hits,
    }


mt5.initialize()
print("=" * 80)
print("  RR/ATR Sweep (BTC + ETH + XRP only)")
print("=" * 80)
print(f"{'RR':>5} {'FVG_ATR':>8} {'Trades':>7} {'Wins':>5} {'WR':>6} {'R':>8} {'TO':>5} {'SL':>5} {'TP':>5}")
print("-" * 80)

for rr in [2.0, 2.5, 3.0, 3.5, 4.0, 5.0]:
    for fvg_mult in [0.25, 0.5, 1.0]:
        r = run_backtest(rr, fvg_mult)
        print(f"{rr:>5.1f} {fvg_mult:>8.2f} {r['total']:>7} {r['wins']:>5} {r['wr']:>5.1f}% {r['total_r']:>+8.2f} {r['timeouts']:>5} {r['sl_hits']:>5} {r['tp_hits']:>5}")

mt5.shutdown()
