"""
AURA v5 — Institutional Setup Quality Score Bucket Analysis
============================================================
Evaluates performance across 5 Quality Score Buckets:
- Bucket 1:  0 - 20
- Bucket 2: 21 - 40
- Bucket 3: 41 - 60
- Bucket 4: 61 - 80
- Bucket 5: 81 - 100
"""

import sys
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bot.setup_quality_scorer import InstitutionalSetupQualityScorer
from backtest.purged_walk_forward import PurgedWalkForwardEvaluator


def generate_quality_scored_dataset(n_samples: int = 600) -> pd.DataFrame:
    """Generate trade history with institutional setup quality scores."""
    np.random.seed(42)
    scorer = InstitutionalSetupQualityScorer()
    
    symbols = ["EURUSD", "GBPUSD", "GOLD", "BTCUSD"]
    trades = []
    base_time = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)
    curr_time = base_time

    for i in range(n_samples):
        curr_time += timedelta(hours=int(np.random.randint(2, 6)))
        sym = str(np.random.choice(symbols))
        
        fvg_size = float(np.random.uniform(1.0, 25.0))
        atr_val = float(np.random.uniform(8.0, 15.0))
        vol_ratio = float(np.random.uniform(0.8, 3.2))
        disp_ratio = float(np.random.uniform(0.2, 0.95))
        is_htf = bool(np.random.rand() < 0.60)
        is_fresh = bool(np.random.rand() < 0.80)

        struct_type = str(np.random.choice(["BOS", "CHOCH"], p=[0.6, 0.4]))
        fvg_confluence = bool(np.random.rand() < 0.50)

        sweep_type = str(np.random.choice(["PDL", "SESSION_HL", "EQH", "SWING"]))
        rejection_pct = float(np.random.uniform(0.2, 0.95))
        in_kz = bool(np.random.rand() < 0.65)

        # Calculate Scores
        fvg_sc = scorer.score_fvg(fvg_size, atr_val, vol_ratio, disp_ratio, is_htf, is_fresh)
        ob_sc = scorer.score_order_block(struct_type, vol_ratio, disp_ratio, fvg_confluence, is_htf)
        sweep_sc = scorer.score_liquidity_sweep(sweep_type, rejection_pct, in_kz, is_htf)

        composite_sc = scorer.calculate_overall_setup_score(fvg_sc, ob_sc, sweep_sc)

        # Win probability strongly correlated with composite quality score
        p_win = 1 / (1 + np.exp(-((composite_sc - 50.0) / 15.0)))
        is_win = bool(np.random.rand() < p_win)

        risk_usd = 200.0
        rr_ratio = 1.8
        pnl = risk_usd * rr_ratio if is_win else -risk_usd

        trades.append({
            "trade_id": i + 1,
            "symbol": sym,
            "fvg_score": fvg_sc,
            "ob_score": ob_sc,
            "sweep_score": sweep_sc,
            "composite_score": composite_sc,
            "is_win": is_win,
            "pnl": pnl
        })

    return pd.DataFrame(trades)


def run_quality_bucket_backtest():
    print("==================================================================")
    print("   AURA v5 — INSTITUTIONAL SETUP QUALITY BUCKET ANALYSIS          ")
    print("==================================================================")

    df_trades = generate_quality_scored_dataset(n_samples=600)
    print(f"Generated {len(df_trades)} quality scored trade setups.")

    # Define Buckets
    bins = [0, 20, 40, 60, 80, 100]
    labels = ["0 - 20 (Poor)", "21 - 40 (Low)", "41 - 60 (Medium)", "61 - 80 (High)", "81 - 100 (Elite)"]
    df_trades["bucket"] = pd.cut(df_trades["composite_score"], bins=bins, labels=labels, include_lowest=True)

    print("\n=========================================================================================================")
    print("                               📊 SETUP QUALITY BUCKET MATRIX                                            ")
    print("=========================================================================================================")
    print(f"{'Quality Bucket':<20} | {'Trades':<6} | {'WinRate':<7} | {'PF':<5} | {'Exp($)':<7} | {'Avg R':<6} | {'NetProfit($)':<12} | {'MaxDD':<6}")
    print("---------------------------------------------------------------------------------------------------------")

    for bucket_label in labels:
        subset = df_trades[df_trades["bucket"] == bucket_label]
        if subset.empty:
            continue
        metrics = PurgedWalkForwardEvaluator.calculate_fold_metrics(subset)
        print(f"{bucket_label:<20} | {metrics['trades']:<6} | {metrics['win_rate']:>5.2f}% | {metrics['profit_factor']:>5.2f} | ${metrics['expectancy']:>6.2f} | {metrics['avg_r']:>6.2f} | ${metrics['net_profit']:>11.2f} | {metrics['max_drawdown']:>5.2f}%")

    print("=========================================================================================================")


if __name__ == "__main__":
    run_quality_bucket_backtest()
