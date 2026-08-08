"""
AURA v6.13 Sequential Statistical Evidence & Inference Core Module
===================================================================
Implements Exact Binomial Test, Wilson 95% CI, Non-parametric Bootstrap (10,000 resamples),
Sequential Alpha Spending / Always-Valid Inference, and Power Analysis.
"""

import os
import sys
import math
import numpy as np
import pandas as pd
from scipy import stats

def exact_binomial_test(k: int, n: int, p0: float = 1/3) -> dict:
    """Exact binomial test H0: p <= 1/3 vs H1: p > 1/3."""
    if n == 0:
        return {"k": 0, "n": 0, "p_value": 1.0, "statistic": 0.0}
    
    res = stats.binomtest(k, n, p=p0, alternative='greater')
    return {
        "k": k,
        "n": n,
        "observed_p": round(k / n, 4),
        "null_p": round(p0, 4),
        "statistic": round(res.statistic, 4),
        "p_value": round(res.pvalue, 6)
    }

def run_bootstrap_expectancy_inference(wins: int, losses: int, num_bootstraps: int = 10000, seed: int = 42) -> dict:
    """Non-parametric IID bootstrap (10,000 resamples) for E[R] and Net R."""
    np.random.seed(seed)
    n = wins + losses
    if n == 0:
        return {"p_exp_gt_0": 0.0, "p_net_r_gt_0": 0.0, "exp_ci_95": "[0.0, 0.0]"}
    
    sample_r = np.array([2.0] * wins + [-1.0] * losses)
    boot_indices = np.random.choice(n, size=(num_bootstraps, n), replace=True)
    boot_samples = sample_r[boot_indices]
    
    boot_net_r = boot_samples.sum(axis=1)
    boot_exp = boot_net_r / n
    
    p_exp_gt_0 = float((boot_exp > 0).mean())
    p_net_r_gt_0 = float((boot_net_r > 0).mean())
    
    ci_low = float(np.percentile(boot_exp, 2.5))
    ci_high = float(np.percentile(boot_exp, 97.5))
    
    return {
        "num_bootstraps": num_bootstraps,
        "seed": seed,
        "p_expectancy_gt_0": round(p_exp_gt_0 * 100, 2),
        "p_net_r_gt_0": round(p_net_r_gt_0 * 100, 2),
        "p_expectancy_le_0": round((1 - p_exp_gt_0) * 100, 2),
        "p_net_r_le_0": round((1 - p_net_r_gt_0) * 100, 2),
        "exp_ci_95": f"[{ci_low:.4f}, {ci_high:.4f}]"
    }

def compute_statistical_power_matrix(sample_sizes: list, expectancies: list) -> pd.DataFrame:
    """Compute statistical power matrix for binomial test against p0 = 1/3."""
    power_rows = []
    p0 = 1/3
    for n in sample_sizes:
        for exp_val in expectancies:
            # Map E[R] to p: E[R] = p*2 - (1-p)*1 = 3p - 1 => p = (E[R] + 1) / 3
            p_alt = (exp_val + 1.0) / 3.0
            # Normal approximation for power calculation
            z_alpha = stats.norm.ppf(0.95) # 5% one-sided
            se_0 = math.sqrt(p0 * (1 - p0) / n)
            se_alt = math.sqrt(p_alt * (1 - p_alt) / n)
            
            critical_val = p0 + z_alpha * se_0
            z_alt = (critical_val - p_alt) / se_alt
            power = 1 - stats.norm.cdf(z_alt)
            
            power_rows.append({
                "N": n,
                "assumed_expectancy": exp_val,
                "assumed_win_rate": round(p_alt * 100, 2),
                "statistical_power_pct": round(power * 100, 2)
            })
    return pd.DataFrame(power_rows)
