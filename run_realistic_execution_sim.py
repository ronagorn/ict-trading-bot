"""
AURA v5 — Realistic Execution Simulation Engine Runner
======================================================
Simulates Ideal, Realistic, Stress 1x, Stress 2x, and Stress 3x live execution scenarios.
"""

import sys
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from backtest.realistic_execution import RealisticExecutionEngine, EXECUTION_PROFILES
from backtest.purged_walk_forward import PurgedWalkForwardEvaluator


def generate_candle_data_for_trade(entry_price: float, direction: str, is_win: bool) -> pd.DataFrame:
    """Generate 10 M15 bars representing realistic price action."""
    bars = []
    curr_price = entry_price
    
    # Bar 0: Entry bar
    bars.append({"open": curr_price, "high": curr_price + 0.0002, "low": curr_price - 0.0002, "close": curr_price})

    # Bars 1-5: Movement towards SL or TP
    if is_win:
        target_delta = 0.0025 if direction == "BUY" else -0.0025
    else:
        target_delta = -0.0015 if direction == "BUY" else 0.0015

    step = target_delta / 5.0
    for b in range(1, 6):
        curr_price += step
        high_val = curr_price + 0.0003
        low_val = curr_price - 0.0003
        bars.append({"open": curr_price - step, "high": high_val, "low": low_val, "close": curr_price})

    return pd.DataFrame(bars)


def run_realistic_execution_simulation():
    print("==================================================================")
    print("   AURA v5 — REALISTIC LIVE EXECUTION & STRESS SIMULATION         ")
    print("==================================================================")

    np.random.seed(42)
    n_signals = 400
    base_time = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)
    
    symbols = ["EURUSD", "GBPUSD", "GOLD", "BTCUSD"]
    signals = []

    curr_time = base_time
    for i in range(n_signals):
        curr_time += timedelta(hours=int(np.random.randint(2, 8)))
        sym = str(np.random.choice(symbols))
        direction = str(np.random.choice(["BUY", "SELL"]))
        entry_p = 1.1000 if sym == "EURUSD" else 1.2500 if sym == "GBPUSD" else 2000.0 if sym == "GOLD" else 65000.0
        
        # Ground truth win prob ~52%
        is_win_baseline = bool(np.random.rand() < 0.52)

        signals.append({
            "id": i + 1,
            "symbol": sym,
            "direction": direction,
            "time": curr_time,
            "killzone_hour": curr_time.hour,
            "base_entry": entry_p,
            "is_win_baseline": is_win_baseline
        })

    print(f"Generated {len(signals)} raw trade signals across 4 symbols.")
    print("------------------------------------------------------------------")

    results_table = []

    for profile_key, profile in EXECUTION_PROFILES.items():
        engine = RealisticExecutionEngine(profile)
        executed_trades = []

        for sig in signals:
            next_bar_time = sig["time"] + timedelta(minutes=15)
            next_bar_open = sig["base_entry"]

            # 1. Simulate Order Execution
            exec_info = engine.simulate_order_execution(sig, next_bar_open, next_bar_time)
            if exec_info is None:
                continue # Rejected order

            # Generate synthetic candle price path
            target_sl = (exec_info["execution_price"] - 0.0015) if exec_info["direction"] == "BUY" else (exec_info["execution_price"] + 0.0015)
            target_tp = (exec_info["execution_price"] + 0.0027) if exec_info["direction"] == "BUY" else (exec_info["execution_price"] - 0.0027)

            df_bars = generate_candle_data_for_trade(exec_info["execution_price"], exec_info["direction"], sig["is_win_baseline"])

            # 2. Simulate Trade Lifespan
            res = engine.simulate_trade_lifespan(
                exec_info, df_bars, entry_bar_idx=0,
                target_sl=target_sl, target_tp=target_tp, risk_usd=200.0, rr_ratio=1.8
            )

            executed_trades.append(res)

        df_exec = pd.DataFrame(executed_trades) if executed_trades else pd.DataFrame()
        
        if not df_exec.empty:
            df_exec["pnl"] = df_exec["net_pnl"]
            metrics = PurgedWalkForwardEvaluator.calculate_fold_metrics(df_exec)
            worst_trade = float(df_exec["pnl"].min())
        else:
            metrics = {
                "trades": 0, "win_rate": 0.0, "profit_factor": 0.0,
                "expectancy": 0.0, "avg_r": 0.0, "net_profit": 0.0,
                "max_drawdown": 0.0, "losing_streak": 0
            }
            worst_trade = 0.0

        results_table.append({
            "scenario": profile.name,
            "trades": metrics["trades"],
            "win_rate": metrics["win_rate"],
            "profit_factor": metrics["profit_factor"],
            "expectancy": metrics["expectancy"],
            "avg_r": metrics["avg_r"],
            "net_profit": metrics["net_profit"],
            "max_dd": metrics["max_drawdown"],
            "worst_trade": round(worst_trade, 2),
            "losing_streak": metrics["losing_streak"]
        })

    # Print Comparative Stress Table
    print("\n=========================================================================================================")
    print("                              📊 COMPARATIVE EXECUTION STRESS MATRIX                                    ")
    print("=========================================================================================================")
    print(f"{'Execution Scenario':<24} | {'Trades':<6} | {'WinRate':<7} | {'PF':<5} | {'Exp($)':<7} | {'Avg R':<6} | {'NetProfit($)':<12} | {'MaxDD':<6} | {'WorstTrade':<10}")
    print("---------------------------------------------------------------------------------------------------------")
    for r in results_table:
        print(f"{r['scenario']:<24} | {r['trades']:<6} | {r['win_rate']:>5.2f}% | {r['profit_factor']:>5.2f} | ${r['expectancy']:>6.2f} | {r['avg_r']:>6.2f} | ${r['net_profit']:>11.2f} | {r['max_dd']:>5.2f}% | ${r['worst_trade']:>9.2f}")
    print("=========================================================================================================")


if __name__ == "__main__":
    run_realistic_execution_simulation()
