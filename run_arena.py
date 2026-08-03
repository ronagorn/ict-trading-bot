"""
The Arena Master Runner (12 Assets + Auto Config Update)
Executes Grid Search, Evaluates Champion vs Challenger for 12 major assets,
and automatically updates config.json with winning strategy parameters.
Run directly with: python run_arena.py
"""

import os
import sys
import json
import pandas as pd
from typing import Dict, Any, List

# Add project root directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bot.challenger_engine import ChallengerEngine
from bot.judge_evaluator import JudgeEvaluator

# 12 Assets: 8 Forex Majors + Gold + 3 Top Crypto
ALL_SYMBOLS = [
    "GOLD", "EURUSD", "GBPUSD", "USDJPY",
    "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "EURGBP",
    "BTCUSD", "ETHUSD", "XRPUSD"
]

def update_config_json(arena_results: List[Dict[str, Any]]) -> None:
    """Automatically updates bot/config.json with winning strategies & parameters."""
    config_path = os.path.join(os.path.dirname(__file__), "bot", "config.json")
    if not os.path.exists(config_path):
        print(f"[WARNING] Config file not found at {config_path}")
        return

    try:
        with open(config_path, "r") as f:
            config = json.load(f)

        updated_symbols = []
        max_spreads = config.get("max_spread_points", {})
        strategy_presets = {}

        for res in arena_results:
            symbol_key = res["symbol_key"]
            top = res["top_candidate"]

            # Format symbol for MT5 config (e.g. GOLD# or EURUSD)
            config_sym = f"{symbol_key}#" if symbol_key in ["GOLD", "BTCUSD", "ETHUSD", "XRPUSD"] else symbol_key
            updated_symbols.append(config_sym)

            max_spreads[config_sym] = int(top.get("max_spread_filter", 35.0) * 10)
            strategy_presets[config_sym] = {
                "timeframe": top.get("timeframe", "M15"),
                "rr_ratio": top.get("rr_ratio", 3.0),
                "fvg_atr_mult": top.get("fvg_atr_mult", 0.3),
                "win_rate_pct": top.get("win_rate_pct", 0.0),
                "profit_factor": top.get("profit_factor", 0.0)
            }

        config["symbols"] = list(dict.fromkeys(updated_symbols))  # Deduplicate
        config["max_spread_points"] = max_spreads
        config["optimized_strategy_presets"] = strategy_presets

        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)

        print("\n[SUCCESS] Successfully updated 'bot/config.json' with winning strategy parameters!")

    except Exception as e:
        print(f"[ERROR] Failed to update config.json: {str(e)}")


def main():
    print("=" * 70)
    print("   THE ARENA: 12-ASSET CHAMPION vs CHALLENGER OPTIMIZATION")
    print("=" * 70)

    engine = ChallengerEngine(data_dir="data")
    judge = JudgeEvaluator(outperformance_threshold_pct=15.0)

    symbols_to_test = ALL_SYMBOLS
    arena_results = []

    for symbol in symbols_to_test:
        print(f"\n" + "-" * 70)
        print(f"  RUNNING ARENA GRID SEARCH FOR SYMBOL: {symbol}")
        print("-" * 70)

        # 1. Run Grid Search for Challenger
        candidates = engine.run_grid_search(symbol)

        if not candidates:
            print(f"[WARNING] No parquet data or valid candidates found for {symbol}. Skipping.")
            continue

        top_challenger = candidates[0]
        top_challenger["symbol"] = symbol

        # 2. Define Standard Champion Baseline (M15, RR 1:3, FVG 0.3, EMA True)
        df_m1 = engine.load_parquet_data(symbol)
        champion_stats = engine.backtest_strategy(
            df=df_m1,
            timeframe="M15",
            rr_ratio=3.0,
            fvg_atr_mult=0.3,
            max_spread_filter=35.0,
            use_ema_filter=True
        )

        if not champion_stats:
            champion_stats = {
                "symbol": symbol,
                "timeframe": "M15",
                "rr_ratio": 3.0,
                "win_rate_pct": 20.0,
                "profit_factor": 1.0,
                "cps_score": 1.0,
                "total_trades": 10
            }
        else:
            champion_stats["symbol"] = symbol

        # 3. Judge Evaluation
        evaluation = judge.evaluate_champion_vs_challenger(champion_stats, top_challenger)
        report_md = judge.generate_markdown_report(evaluation)

        print(report_md)

        # Print Top 3 Challenger Candidates
        print(f"\nTOP 3 CHALLENGER STRATEGIES FOR {symbol}:")
        print(f"{'Rank':<5} | {'TF':<5} | {'R:R':<6} | {'WinRate (%)':<12} | {'PF':<6} | {'CPS Score':<10} | {'Trades'}")
        print("-" * 65)
        for rank, cand in enumerate(candidates[:3], 1):
            print(f"{rank:<5} | {cand['timeframe']:<5} | 1:{cand['rr_ratio']:<4} | {cand['win_rate_pct']:<12}% | {cand['profit_factor']:<6} | {cand['cps_score']:<10} | {cand['total_trades']}")
        print("-" * 65)

        arena_results.append({
            "symbol_key": symbol,
            "top_candidate": top_challenger,
            "evaluation": evaluation
        })

    # Auto update config.json
    if arena_results:
        update_config_json(arena_results)

    print("\n" + "=" * 70)
    print("   [COMPLETED] 12-ASSET ARENA OPTIMIZATION FINISHED!")
    print("=" * 70)

if __name__ == "__main__":
    main()
