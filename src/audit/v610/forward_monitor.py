"""
AURA v6.10 Audit Module Core Component
========================================
Contains deterministic accounting, statistical monitoring, cryptographic ledger state,
and checkpoint verification functions for v6.10.
"""

import os
import sys
import glob
import json
import math
import hashlib
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from scipy import stats

GENESIS_HASH = "0000000000000000000000000000000000000000000000000000000000000000"

def get_file_sha256(filepath: str) -> str:
    if not os.path.exists(filepath):
        return "N/A"
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def wilson_score_interval(k: int, n: int, confidence: float = 0.95):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    z = stats.norm.ppf(1 - (1 - confidence) / 2)
    denominator = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denominator
    std_err = (z * math.sqrt((p * (1 - p) + z**2 / (4 * n)) / n)) / denominator
    lower = max(0.0, centre - std_err)
    upper = min(1.0, centre + std_err)
    return round(lower * 100, 2), round(upper * 100, 2)

def calculate_rr2_metrics(df_trades: pd.DataFrame):
    if df_trades.empty:
        return {
            "n": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
            "gross_profit": 0.0, "gross_loss": 0.0, "net_r": 0.0,
            "expectancy": 0.0, "profit_factor": 0.0, "max_dd": 0.0,
            "realized_net_r": 0.0, "realized_expectancy": 0.0
        }

    n = len(df_trades)
    wins = int((df_trades["result"] == 1).sum()) if "result" in df_trades.columns else int((df_trades["label"] == 1).sum())
    losses = n - wins
    win_rate = (wins / n) if n > 0 else 0.0

    gross_profit = wins * 2.0
    gross_loss = losses * 1.0
    net_r = gross_profit - gross_loss
    expectancy = net_r / n if n > 0 else 0.0

    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (float('inf') if gross_profit > 0 else 0.0)

    if "execution_cost_R" in df_trades.columns:
        realized_r_series = np.where((df_trades["result"].values if "result" in df_trades.columns else df_trades["label"].values) == 1, 2.0, -1.0) - df_trades["execution_cost_R"].values
        realized_net_r = float(realized_r_series.sum())
        realized_exp = realized_net_r / n if n > 0 else 0.0
    else:
        realized_r_series = np.where((df_trades["result"].values if "result" in df_trades.columns else df_trades["label"].values) == 1, 2.0, -1.0)
        realized_net_r = net_r
        realized_exp = expectancy

    cum_r = np.cumsum(realized_r_series)
    peak = np.maximum.accumulate(cum_r)
    dd = peak - cum_r
    max_dd = float(dd.max()) if len(dd) > 0 else 0.0

    return {
        "n": n,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate * 100, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "net_r": round(net_r, 2),
        "expectancy": round(expectancy, 4),
        "profit_factor": round(profit_factor, 4),
        "realized_net_r": round(realized_net_r, 2),
        "realized_expectancy": round(realized_exp, 4),
        "max_dd": round(max_dd, 2)
    }
