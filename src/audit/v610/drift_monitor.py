"""
AURA v6.12 Drift Monitoring & Health Operations Core Module
=============================================================
Implements Feature Drift (PSI/KS), Model Probability Shift, Signal Frequency Collapse/Explosion,
Execution Quality Degradation, and Alert Router (GREEN/YELLOW/ORANGE/RED).
"""

import os
import sys
import json
import numpy as np
import pandas as pd
from scipy import stats

def calculate_psi(expected: np.ndarray, actual: np.ndarray, num_buckets: int = 10) -> float:
    """Calculate Population Stability Index (PSI) between reference and current distribution."""
    if len(expected) == 0 or len(actual) == 0:
        return 0.0
    
    quantiles = np.linspace(0, 100, num_buckets + 1)
    buckets = np.percentile(expected, quantiles)
    buckets[0] = -np.inf
    buckets[-1] = np.inf
    
    expected_counts, _ = np.histogram(expected, bins=buckets)
    actual_counts, _ = np.histogram(actual, bins=buckets)
    
    expected_pct = np.where(expected_counts == 0, 0.0001, expected_counts) / len(expected)
    actual_pct = np.where(actual_counts == 0, 0.0001, actual_counts) / len(actual)
    
    psi_val = np.sum((actual_pct - expected_pct) * np.log(actual_pct / expected_pct))
    return float(psi_val)

def classify_drift_level(psi: float) -> str:
    if psi < 0.10:
        return "NO_DRIFT"
    elif psi < 0.20:
        return "MILD_DRIFT"
    elif psi < 0.25:
        return "MODERATE_DRIFT"
    else:
        return "SEVERE_DRIFT"

def evaluate_alert_level(integrity_ok: bool, severe_drift: bool, exec_degraded: bool, dd_high: bool) -> str:
    if not integrity_ok:
        return "RED"
    elif severe_drift or exec_degraded:
        return "ORANGE"
    elif dd_high:
        return "YELLOW"
    else:
        return "GREEN"
