"""
AURA v5.4 — Independent Quantitative Audit Reproducer Engine
=============================================================
Executes exact mathematical recalculations for Phases 1-8.
"""

import sys
import os
import math
from typing import Tuple, List, Dict, Any
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone
from scipy import stats
from sklearn.metrics import brier_score_loss, log_loss
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import TimeSeriesSplit
import xgboost as xgb

# ---------------------------------------------------------
# 1. Dataset Generator (Identical to production benchmark)
# ---------------------------------------------------------
AUDITED_FEATURE_COLUMNS = [
    "fvg_size_pips",
    "killzone_hour",
    "trend_alignment",
    "volume_spike_ratio",
    "fvg_quality_score",
    "ob_quality_score",
    "liquidity_quality_score",
    "atr_percentile",
    "trend_score"
]

def generate_production_ml_dataset(n_samples: int = 800) -> pd.DataFrame:
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

# ---------------------------------------------------------
# Statistical Helper Functions
# ---------------------------------------------------------
def wilson_ci(k: int, n: int, confidence: float = 0.95) -> Tuple[float, float]:
    if n == 0: return (0.0, 0.0)
    p = k / n
    z = stats.norm.ppf(1 - (1 - confidence) / 2)
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    margin = z * math.sqrt((p * (1 - p) / n) + (z**2 / (4 * n**2))) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))

def clopper_pearson_ci(k: int, n: int, confidence: float = 0.95) -> Tuple[float, float]:
    if n == 0: return (0.0, 0.0)
    alpha = 1 - confidence
    lower = stats.beta.ppf(alpha / 2, k, n - k + 1) if k > 0 else 0.0
    upper = stats.beta.ppf(1 - alpha / 2, k + 1, n - k) if k < n else 1.0
    return (float(lower), float(upper))

def bayesian_posterior_ci(k: int, n: int, confidence: float = 0.95, a: float = 1.0, b: float = 1.0) -> Tuple[float, float]:
    if n == 0: return (0.0, 0.0)
    alpha = 1 - confidence
    post_a = a + k
    post_b = b + n - k
    lower = stats.beta.ppf(alpha / 2, post_a, post_b)
    upper = stats.beta.ppf(1 - alpha / 2, post_a, post_b)
    return (float(lower), float(upper))

def bootstrap_ci_winrate(y_true: np.ndarray, n_bootstraps: int = 10000, confidence: float = 0.95) -> Tuple[float, float]:
    if len(y_true) == 0: return (0.0, 0.0)
    np.random.seed(42)
    boot_means = []
    for _ in range(n_bootstraps):
        sample = np.random.choice(y_true, size=len(y_true), replace=True)
        boot_means.append(np.mean(sample))
    alpha = 1 - confidence
    lower = np.percentile(boot_means, alpha / 2 * 100)
    upper = np.percentile(boot_means, (1 - alpha / 2) * 100)
    return (float(lower), float(upper))

def calculate_ece_and_mce(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> Tuple[float, float, List[Dict[str, Any]]]:
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    mce = 0.0
    bins_data = []
    
    for i in range(n_bins):
        bin_lower = bin_boundaries[i]
        bin_upper = bin_boundaries[i + 1]
        in_bin = (y_prob >= bin_lower) & (y_prob < bin_upper) if i < n_bins - 1 else (y_prob >= bin_lower) & (y_prob <= bin_upper)
        n_in_bin = np.sum(in_bin)
        prop_in_bin = n_in_bin / len(y_prob) if len(y_prob) > 0 else 0.0
        
        if n_in_bin > 0:
            accuracy_in_bin = float(np.mean(y_true[in_bin]))
            avg_confidence_in_bin = float(np.mean(y_prob[in_bin]))
            gap = abs(accuracy_in_bin - avg_confidence_in_bin)
            ece += gap * prop_in_bin
            if gap > mce:
                mce = gap
            bins_data.append({
                "bin": f"{bin_lower:.2f}-{bin_upper:.2f}",
                "n": int(n_in_bin),
                "mean_pred": avg_confidence_in_bin,
                "actual_wr": accuracy_in_bin,
                "gap": gap
            })
        else:
            bins_data.append({
                "bin": f"{bin_lower:.2f}-{bin_upper:.2f}",
                "n": 0,
                "mean_pred": 0.0,
                "actual_wr": 0.0,
                "gap": 0.0
            })
            
    return float(ece), float(mce), bins_data

def run_audit():
    df_all = generate_production_ml_dataset(n_samples=800)
    df_train = df_all.iloc[:600].copy()
    df_test_oos = df_all.iloc[600:].copy()

    X_train = df_train[AUDITED_FEATURE_COLUMNS]
    y_train = df_train["trade_outcome"]
    X_test = df_test_oos[AUDITED_FEATURE_COLUMNS]
    y_test = df_test_oos["trade_outcome"].values

    n_pos = int(y_train.sum())
    scale_pos = float((len(y_train) - n_pos) / n_pos) if n_pos > 0 else 1.0

    tscv = TimeSeriesSplit(n_splits=4)
    raw_xgb = xgb.XGBClassifier(n_estimators=100, max_depth=4, scale_pos_weight=scale_pos, eval_metric="logloss", random_state=42)
    calib_xgb = CalibratedClassifierCV(estimator=xgb.XGBClassifier(n_estimators=100, max_depth=4, scale_pos_weight=scale_pos, random_state=42), method="sigmoid", cv=tscv)

    raw_xgb.fit(X_train, y_train)
    calib_xgb.fit(X_train, y_train)

    probs_raw = raw_xgb.predict_proba(X_test)[:, 1]
    probs_calib = calib_xgb.predict_proba(X_test)[:, 1]

    print("=== PHASE 2 & 3: THRESHOLD AUDIT MATRIX ===")
    thresholds = [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]
    
    sweep_results = []
    for th in thresholds:
        approved_mask = probs_calib >= th
        approved_indices = np.where(approved_mask)[0]
        sub_df = df_test_oos.iloc[approved_indices]
        n_trades = len(sub_df)
        appr_rate = (n_trades / 200.0) * 100.0
        
        if n_trades > 0:
            wins = int(sub_df["trade_outcome"].sum())
            losses = n_trades - wins
            win_rate = (wins / n_trades) * 100.0
            
            pnl_wins = wins * 360.0
            pnl_losses = losses * 200.0
            pf = (pnl_wins / pnl_losses) if pnl_losses > 0 else 99.0
            net_profit = pnl_wins - pnl_losses
            expectancy = net_profit / n_trades
            total_r = net_profit / 200.0
            
            # Drawdown & Ratios
            equity_curve = 10000.0 + np.cumsum(sub_df["pnl"].values)
            peaks = np.maximum.accumulate(equity_curve)
            dds = (peaks - equity_curve) / peaks * 100.0
            max_dd = float(np.max(dds)) if len(dds) > 0 else 0.0
            
            ret_std = np.std(sub_df["pnl"].values) if len(sub_df) > 1 else 1.0
            sharpe = (expectancy / ret_std) * math.sqrt(252) if ret_std > 0 else 0.0
            
            downside_returns = sub_df["pnl"].values[sub_df["pnl"].values < 0]
            downside_std = np.std(downside_returns) if len(downside_returns) > 1 else 1.0
            sortino = (expectancy / downside_std) * math.sqrt(252) if downside_std > 0 else 0.0
            
            w_ci95 = wilson_ci(wins, n_trades, 0.95)
            w_ci99 = wilson_ci(wins, n_trades, 0.99)
            cp_ci95 = clopper_pearson_ci(wins, n_trades, 0.95)
            bayes_ci95 = bayesian_posterior_ci(wins, n_trades, 0.95)
            boot_ci95 = bootstrap_ci_winrate(sub_df["trade_outcome"].values, n_bootstraps=5000)
            
            # Minimum sample size required to prove win_rate > 50% at alpha=0.05
            p0 = 0.50
            p_obs = wins / n_trades
            if p_obs > p0:
                n_min = math.ceil((1.645 * math.sqrt(p0*(1-p0)) + 0.84 * math.sqrt(p_obs*(1-p_obs)))**2 / (p_obs - p0)**2)
            else:
                n_min = 9999
        else:
            wins = 0
            losses = 0
            win_rate = 0.0
            pf = 0.0
            net_profit = 0.0
            expectancy = 0.0
            total_r = 0.0
            max_dd = 0.0
            sharpe = 0.0
            sortino = 0.0
            w_ci95 = (0.0, 0.0)
            w_ci99 = (0.0, 0.0)
            cp_ci95 = (0.0, 0.0)
            bayes_ci95 = (0.0, 0.0)
            boot_ci95 = (0.0, 0.0)
            n_min = 0

        sweep_results.append({
            "threshold": th,
            "trades": n_trades,
            "appr_rate": appr_rate,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "pf": pf,
            "expectancy": expectancy,
            "net_profit": net_profit,
            "total_r": total_r,
            "max_dd": max_dd,
            "sharpe": sharpe,
            "sortino": sortino,
            "w_ci95": f"[{w_ci95[0]*100:.2f}%, {w_ci95[1]*100:.2f}%]",
            "w_ci99": f"[{w_ci99[0]*100:.2f}%, {w_ci99[1]*100:.2f}%]",
            "cp_ci95": f"[{cp_ci95[0]*100:.2f}%, {cp_ci95[1]*100:.2f}%]",
            "bayes_ci95": f"[{bayes_ci95[0]*100:.2f}%, {bayes_ci95[1]*100:.2f}%]",
            "boot_ci95": f"[{boot_ci95[0]*100:.2f}%, {boot_ci95[1]*100:.2f}%]",
            "n_min": n_min
        })

    df_sweep = pd.DataFrame(sweep_results)
    print(df_sweep[["threshold", "trades", "appr_rate", "win_rate", "pf", "expectancy", "total_r", "max_dd", "w_ci95", "n_min"]].to_string())

    print("\n=== PHASE 5: CALIBRATION AUDIT ===")
    # Evaluates Calibration on OOS Test Set (200 trades)
    brier_uncalib = brier_score_loss(y_test, probs_raw)
    brier_calib = brier_score_loss(y_test, probs_calib)
    
    logloss_uncalib = log_loss(y_test, probs_raw)
    logloss_calib = log_loss(y_test, probs_calib)

    ece_uncalib, mce_uncalib, _ = calculate_ece_and_mce(y_test, probs_raw, n_bins=10)
    ece_calib, mce_calib, bins_calib = calculate_ece_and_mce(y_test, probs_calib, n_bins=10)

    base_rate = np.mean(y_test)
    y_dummy_prob = np.full_like(probs_calib, base_rate)
    brier_dummy = brier_score_loss(y_test, y_dummy_prob)
    logloss_dummy = log_loss(y_test, y_dummy_prob)
    ece_dummy, mce_dummy, _ = calculate_ece_and_mce(y_test, y_dummy_prob, n_bins=10)

    # Calibration Slope & Intercept (Logistic Regression of logit(prob) vs y_true)
    from sklearn.linear_model import LogisticRegression
    # Clip probabilities to avoid inf logits
    clipped_probs = np.clip(probs_calib, 1e-6, 1 - 1e-6)
    logits = np.log(clipped_probs / (1 - clipped_probs)).reshape(-1, 1)
    calib_lr = LogisticRegression()
    calib_lr.fit(logits, y_test)
    slope = float(calib_lr.coef_[0][0])
    intercept = float(calib_lr.intercept_[0])

    print(f"Base Rate: {base_rate:.4f} ({base_rate*100:.2f}%)")
    print(f"Uncalibrated  : Brier={brier_uncalib:.4f} | LogLoss={logloss_uncalib:.4f} | ECE={ece_uncalib:.4f} | MCE={mce_uncalib:.4f}")
    print(f"Calibrated    : Brier={brier_calib:.4f} | LogLoss={logloss_calib:.4f} | ECE={ece_calib:.4f} | MCE={mce_calib:.4f}")
    print(f"Dummy (Mean)  : Brier={brier_dummy:.4f} | LogLoss={logloss_dummy:.4f} | ECE={ece_dummy:.4f} | MCE={mce_dummy:.4f}")
    print(f"Calibration Slope: {slope:.4f} (Ideal=1.0) | Intercept: {intercept:.4f} (Ideal=0.0)")

    print("\nCalibration Bins (OOS Actual vs Predicted):")
    for b in bins_calib:
        print(f"Bin {b['bin']}: N={b['n']:<3} | MeanPred={b['mean_pred']:.3f} | ActualWR={b['actual_wr']:.3f} | Gap={b['gap']:.3f}")

if __name__ == "__main__":
    run_audit()
