"""
AURA v5 — Production-Grade Purged Walk-Forward Validation Runner
================================================================
Executes Marcos López de Prado's Purged Walk-Forward CV & Stability Audit
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

from backtest.purged_walk_forward import PurgedWalkForwardCV, PurgedWalkForwardEvaluator
from bot.ml_filter import MLFilterEngine, FEATURE_COLUMNS, train_xgboost_model


def generate_audit_trade_dataset(n_samples: int = 1000) -> pd.DataFrame:
    """Generate realistic chronological trade log with label_start & label_end."""
    np.random.seed(2026)
    base_time = datetime(2025, 6, 1, 0, 0, tzinfo=timezone.utc)
    
    entry_times, exit_times = [], []
    curr = base_time

    for i in range(n_samples):
        curr += timedelta(hours=int(np.random.randint(1, 6)))
        duration = timedelta(hours=int(np.random.randint(1, 12)))
        entry_times.append(curr)
        exit_times.append(curr + duration)

    fvg_size_pips = np.random.uniform(2.0, 25.0, n_samples)
    killzone_hour = [t.hour for t in entry_times]
    trend_alignment = np.random.choice([0, 1], n_samples, p=[0.38, 0.62])
    volume_spike_ratio = np.random.uniform(0.8, 3.5, n_samples)

    score = (
        (trend_alignment * 1.5) +
        (volume_spike_ratio * 0.7) +
        np.where(np.isin(killzone_hour, [8, 9, 14, 15]), 1.1, -0.6) +
        np.where((fvg_size_pips >= 4.0) & (fvg_size_pips <= 18.0), 0.9, -0.5)
    )
    p_win = 1 / (1 + np.exp(-(score - 3.8)))
    is_win = (np.random.rand(n_samples) < p_win)

    risk_usd = 200.0
    rr_ratio = 1.8
    pnl = np.where(is_win, risk_usd * rr_ratio, -risk_usd)

    return pd.DataFrame({
        "trade_id": np.arange(1, n_samples + 1),
        "entry_time": entry_times,
        "exit_time": exit_times,
        "fvg_size_pips": fvg_size_pips,
        "killzone_hour": killzone_hour,
        "trend_alignment": trend_alignment,
        "volume_spike_ratio": volume_spike_ratio,
        "trade_outcome": is_win.astype(int),
        "pnl": pnl
    })


def run_purged_walkforward_audit():
    print("==================================================================")
    print("   AURA v5 — PURGED WALK-FORWARD VALIDATION & STABILITY AUDIT     ")
    print("==================================================================")

    df_trades = generate_audit_trade_dataset(n_samples=1000)
    print(f"Loaded {len(df_trades)} chronological trades.")
    print(f"Dataset Timespan: {df_trades['entry_time'].min()} -> {df_trades['exit_time'].max()}")

    # ----------------------------------------------------------------
    # 1. Standard Naive Validation (Before Purged Walk-Forward)
    # ----------------------------------------------------------------
    baseline_metrics = PurgedWalkForwardEvaluator.calculate_fold_metrics(df_trades)

    # ----------------------------------------------------------------
    # 2. Production-Grade Purged Walk-Forward (5 Chronological Folds)
    # ----------------------------------------------------------------
    pwf = PurgedWalkForwardCV(n_splits=5, embargo_minutes=180)
    fold_results = []
    all_oos_trades = []

    print("\n------------------------------------------------------------------")
    print("   CHRONOLOGICAL FOLD EVALUATION (TRAIN -> PURGE -> EMBARGO -> TEST)")
    print("------------------------------------------------------------------")

    for fold_idx, (train_idx, test_idx) in enumerate(pwf.split(df_trades, label_start_col="entry_time", label_end_col="exit_time"), start=1):
        df_train = df_trades.iloc[train_idx].copy()
        df_test = df_trades.iloc[test_idx].copy()

        # Train XGBoost Model on Purged Train Set
        engine = MLFilterEngine()
        train_res = engine.train_xgboost_model(df_train)

        # Mock DB client to bypass cold start count check
        from unittest.mock import MagicMock
        mock_db = MagicMock()
        mock_db.enabled = True
        mock_db.get_closed_trades_for_ml.return_value = [{"id": i, "status": "WIN"} for i in range(350)]

        # Predict Out-of-Sample Test Fold
        approved_trades = []
        for _, row in df_test.iterrows():
            sig = {
                "symbol": "EURUSD",
                "fvg_size": row["fvg_size_pips"],
                "killzone_hour": row["killzone_hour"],
                "trend_alignment": row["trend_alignment"],
                "volume_spike": row["volume_spike_ratio"]
            }
            if engine.predict_signal_probability(sig, db_client=mock_db):
                approved_trades.append(row.to_dict())

        df_approved_test = pd.DataFrame(approved_trades) if approved_trades else pd.DataFrame()
        fold_metric = PurgedWalkForwardEvaluator.calculate_fold_metrics(df_approved_test)
        fold_results.append(fold_metric)

        if not df_approved_test.empty:
            all_oos_trades.append(df_approved_test)

        print(f"Fold {fold_idx} | Train: {len(df_train):<3} | Test OOS: {len(df_test):<3} | Approved: {fold_metric['trades']:<3} | WinRate: {fold_metric['win_rate']:>5.2f}% | PF: {fold_metric['profit_factor']:>4.2f} | MaxDD: {fold_metric['max_drawdown']:>5.2f}%")

    # Combine All OOS Folds
    df_all_oos = pd.concat(all_oos_trades, ignore_index=True) if all_oos_trades else pd.DataFrame()
    overall_oos_metrics = PurgedWalkForwardEvaluator.calculate_fold_metrics(df_all_oos)

    # Stability Analysis
    stability = PurgedWalkForwardEvaluator.evaluate_stability(fold_results)

    # ----------------------------------------------------------------
    # 3. Final Comparative Audit Summary Report
    # ----------------------------------------------------------------
    print("\n==================================================================")
    print("     📊 FINAL COMPARATIVE VALIDATION REPORT (BEFORE vs PURGED WF) ")
    print("==================================================================")
    print(f"Metrics                         Naive Baseline     Purged Walk-Forward (OOS)")
    print("------------------------------------------------------------------")
    print(f"Total Trades:                   {baseline_metrics['trades']:<18} {overall_oos_metrics['trades']}")
    print(f"Win Rate (%):                   {baseline_metrics['win_rate']:.2f}%             {overall_oos_metrics['win_rate']:.2f}%")
    print(f"Profit Factor:                  {baseline_metrics['profit_factor']:.2f}               {overall_oos_metrics['profit_factor']:.2f}")
    print(f"Average R:                      {baseline_metrics['avg_r']:.2f}                {overall_oos_metrics['avg_r']:.2f}")
    print(f"Net Profit ($):                 ${baseline_metrics['net_profit']:<17,.2f} ${overall_oos_metrics['net_profit']:,.2f}")
    print(f"Max Drawdown (%):               {baseline_metrics['max_drawdown']:.2f}%             {overall_oos_metrics['max_drawdown']:.2f}%")
    print(f"Sharpe Ratio:                   {baseline_metrics['sharpe']:.2f}               {overall_oos_metrics['sharpe']:.2f}")
    print(f"Sortino Ratio:                  {baseline_metrics['sortino']:.2f}               {overall_oos_metrics['sortino']:.2f}")
    print(f"Max Losing Streak:              {baseline_metrics['losing_streak']:<18} {overall_oos_metrics['losing_streak']}")
    print("------------------------------------------------------------------")
    print("                    STABILITY ANALYSIS                            ")
    print("------------------------------------------------------------------")
    print(f"Mean Win Rate across Folds:     {stability.get('mean_win_rate', 0):.2f}%")
    print(f"Median Win Rate:                {stability.get('median_win_rate', 0):.2f}%")
    print(f"Std Dev Win Rate:               {stability.get('std_win_rate', 0):.2f}%")
    print(f"Worst Fold Profit Factor:       {stability.get('worst_fold_pf', 0):.2f}")
    print(f"Best Fold Profit Factor:        {stability.get('best_fold_pf', 0):.2f}")
    print(f"System Stability Status:        {stability.get('status', 'N/A')}")
    print("==================================================================")


if __name__ == "__main__":
    run_purged_walkforward_audit()
