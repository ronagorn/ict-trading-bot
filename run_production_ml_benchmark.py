"""
AURA v5 — Production ML Benchmark & Threshold Stability Analysis
================================================================
Evaluates OOS performance of:
1. Rule-Only Baseline
2. Logistic Regression
3. Simple Decision Tree
4. Raw XGBoost Classifier
5. Calibrated XGBoost Classifier (Platt Scaling / Sigmoid CV)

Across Probability Thresholds: 0.50, 0.55, 0.60, 0.65, 0.70, 0.75
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
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import TimeSeriesSplit
import xgboost as xgb

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bot.production_ml_engine import ProductionMLEngine, AUDITED_FEATURE_COLUMNS
from backtest.purged_walk_forward import PurgedWalkForwardEvaluator


def generate_production_ml_dataset(n_samples: int = 800) -> pd.DataFrame:
    """Generate realistic trade dataset with audited features."""
    np.random.seed(2026)
    base_time = datetime(2025, 8, 1, 8, 0, tzinfo=timezone.utc)
    
    entry_times = [base_time + timedelta(hours=i*4) for i in range(n_samples)]
    fvg_size_pips = np.random.uniform(2.0, 25.0, n_samples)
    killzone_hour = [t.hour for t in entry_times]
    trend_alignment = np.random.choice([0, 1], n_samples, p=[0.4, 0.6])
    volume_spike_ratio = np.random.uniform(0.8, 3.2, n_samples)
    fvg_quality = np.random.uniform(30, 95, n_samples)
    ob_quality = np.random.uniform(30, 95, n_samples)
    liq_quality = np.random.uniform(30, 95, n_samples)
    atr_pct = np.random.uniform(10, 90, n_samples)
    trend_score = np.random.uniform(0.5, 8.5, n_samples)

    score = (
        (trend_alignment * 1.4) +
        (volume_spike_ratio * 0.6) +
        (fvg_quality / 100.0 * 1.5) +
        (ob_quality / 100.0 * 1.2) +
        np.where(np.isin(killzone_hour, [8, 9, 14, 15]), 1.0, -0.5)
    )
    p_win = 1 / (1 + np.exp(-(score - 3.8)))
    is_win = (np.random.rand(n_samples) < p_win)

    risk_usd = 200.0
    rr_ratio = 1.8
    pnl = np.where(is_win, risk_usd * rr_ratio, -risk_usd)

    return pd.DataFrame({
        "trade_id": np.arange(1, n_samples + 1),
        "entry_time": entry_times,
        "fvg_size_pips": fvg_size_pips,
        "killzone_hour": killzone_hour,
        "trend_alignment": trend_alignment,
        "volume_spike_ratio": volume_spike_ratio,
        "fvg_quality_score": fvg_quality,
        "ob_quality_score": ob_quality,
        "liquidity_quality_score": liq_quality,
        "atr_percentile": atr_pct,
        "trend_score": trend_score,
        "trade_outcome": is_win.astype(int),
        "pnl": pnl
    })


def run_production_ml_benchmark():
    print("==================================================================")
    print("   AURA v5 — PRODUCTION ML BENCHMARK & THRESHOLD STABILITY       ")
    print("==================================================================")

    df_all = generate_production_ml_dataset(n_samples=800)
    
    # Strict Temporal Split: Train (600) vs Untouched OOS Test (200)
    df_train = df_all.iloc[:600].copy()
    df_test_oos = df_all.iloc[600:].copy()

    print(f"Total Dataset: {len(df_all)} trades | Train: {len(df_train)} | OOS Test: {len(df_test_oos)}")
    print("------------------------------------------------------------------")

    X_train = df_train[AUDITED_FEATURE_COLUMNS]
    y_train = df_train["trade_outcome"]
    
    X_test = df_test_oos[AUDITED_FEATURE_COLUMNS]
    y_test = df_test_oos["trade_outcome"]

    # ----------------------------------------------------------------
    # 1. Train Baselines
    # ----------------------------------------------------------------
    # Baseline 1: Logistic Regression
    model_lr = LogisticRegression(max_iter=500, random_state=42)
    model_lr.fit(X_train, y_train)

    # Baseline 2: Simple Decision Tree
    model_dt = DecisionTreeClassifier(max_depth=4, random_state=42)
    model_dt.fit(X_train, y_train)

    # Baseline 3: Raw XGBoost
    n_pos = int(y_train.sum())
    scale_pos = float((len(y_train) - n_pos) / n_pos) if n_pos > 0 else 1.0
    model_xgb_raw = xgb.XGBClassifier(n_estimators=100, max_depth=4, scale_pos_weight=scale_pos, eval_metric="logloss", random_state=42)
    model_xgb_raw.fit(X_train, y_train)

    # Baseline 4: Production Calibrated XGBoost (Platt Scaling CV)
    tscv = TimeSeriesSplit(n_splits=4)
    model_xgb_calib = CalibratedClassifierCV(estimator=xgb.XGBClassifier(n_estimators=100, max_depth=4, scale_pos_weight=scale_pos, random_state=42), method="sigmoid", cv=tscv)
    model_xgb_calib.fit(X_train, y_train)

    models_map = {
        "Rule-Only (Score >= 60)": None,
        "Logistic Regression": model_lr,
        "Decision Tree": model_dt,
        "Raw XGBoost": model_xgb_raw,
        "Calibrated XGBoost (Prod)": model_xgb_calib
    }

    # ----------------------------------------------------------------
    # 2. Evaluate Out-of-Sample (OOS) across Thresholds
    # ----------------------------------------------------------------
    thresholds = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75]
    benchmark_results = []

    print("\n=========================================================================================================")
    print("                              📊 OUT-OF-SAMPLE (OOS) BENCHMARK MATRIX                                    ")
    print("=========================================================================================================")
    print(f"{'Model Name':<26} | {'Thresh':<6} | {'Trades':<6} | {'WinRate':<7} | {'PF':<5} | {'Exp($)':<7} | {'NetProfit($)':<12} | {'MaxDD':<6}")
    print("---------------------------------------------------------------------------------------------------------")

    for name, model in models_map.items():
        if model is None:
            # Rule-Only evaluation
            approved_mask = (df_test_oos["fvg_quality_score"] >= 60) & (df_test_oos["trend_alignment"] == 1)
            subset = df_test_oos[approved_mask]
            metrics = PurgedWalkForwardEvaluator.calculate_fold_metrics(subset)
            print(f"{name:<26} | {'N/A':<6} | {metrics['trades']:<6} | {metrics['win_rate']:>5.2f}% | {metrics['profit_factor']:>5.2f} | ${metrics['expectancy']:>6.2f} | ${metrics['net_profit']:>11.2f} | {metrics['max_drawdown']:>5.2f}%")
        else:
            probs = model.predict_proba(X_test)[:, 1]
            for th in thresholds:
                approved_indices = np.where(probs >= th)[0]
                subset = df_test_oos.iloc[approved_indices]
                metrics = PurgedWalkForwardEvaluator.calculate_fold_metrics(subset)
                print(f"{name:<26} | {th:<6.2f} | {metrics['trades']:<6} | {metrics['win_rate']:>5.2f}% | {metrics['profit_factor']:>5.2f} | ${metrics['expectancy']:>6.2f} | ${metrics['net_profit']:>11.2f} | {metrics['max_drawdown']:>5.2f}%")

    print("=========================================================================================================")


if __name__ == "__main__":
    run_production_ml_benchmark()
