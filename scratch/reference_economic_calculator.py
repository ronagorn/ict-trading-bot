"""
AURA v6.5 — Independent Reference Economic Calculator & Property Tests
========================================================================
Implements an independent reference economic engine.
Verifies property-based accounting tests (Tests A-E), constructs canonical trade-level table,
calculates Theoretical vs Realized P&L, Expectancy, and Profit Factor for Train, Validation, and Holdout.
"""

import os
import sys
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import glob
import math
import hashlib
import json
import numpy as np
import pandas as pd
import xgboost as xgb

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

class ReferenceEconomicCalculator:
    """Independent Reference Economic Calculator complying with Rule 4 & Rule 9."""

    @staticmethod
    def calculate_metrics(trades_df: pd.DataFrame, rr_ratio: float = 3.0):
        if trades_df.empty:
            return {
                "n": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
                "gross_profit": 0.0, "gross_loss": 0.0, "net_r": 0.0,
                "expectancy": 0.0, "profit_factor": 0.0, "max_dd": 0.0
            }

        n = len(trades_df)
        wins = int((trades_df["label"] == 1).sum())
        losses = n - wins
        win_rate = (wins / n) if n > 0 else 0.0

        # Theoretical R
        gross_profit = wins * rr_ratio
        gross_loss = losses * 1.0
        net_r = gross_profit - gross_loss
        expectancy = net_r / n if n > 0 else 0.0

        # Profit Factor: Gross Profit / Gross Loss
        if gross_loss > 0:
            profit_factor = gross_profit / gross_loss
        else:
            profit_factor = float('inf') if gross_profit > 0 else 0.0

        # Realized R after costs (if execution_cost column exists)
        if "execution_cost" in trades_df.columns:
            realized_r_series = np.where(trades_df["label"].values == 1, rr_ratio, -1.0) - trades_df["execution_cost"].values
            realized_net_r = float(realized_r_series.sum())
            realized_exp = realized_net_r / n if n > 0 else 0.0
        else:
            realized_r_series = np.where(trades_df["label"].values == 1, rr_ratio, -1.0)
            realized_net_r = net_r
            realized_exp = expectancy

        # Max Drawdown in R
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

def run_property_based_tests():
    print("--- RUNNING RULE 10 PROPERTY-BASED ACCOUNTING TESTS ---")
    calc = ReferenceEconomicCalculator()

    # Test A: 1 win + 0 losses => +3R, PF = inf, Exp = +3R
    df_a = pd.DataFrame({"label": [1]})
    res_a = calc.calculate_metrics(df_a)
    assert res_a["net_r"] == 3.0, f"Test A Net R Failed: {res_a['net_r']}"
    assert res_a["profit_factor"] == float('inf'), f"Test A PF Failed: {res_a['profit_factor']}"
    assert res_a["expectancy"] == 3.0, f"Test A Exp Failed: {res_a['expectancy']}"
    print("✅ Test A PASSED (1 Win + 0 Losses => Net R = +3R, PF = inf, Exp = +3R)")

    # Test B: 0 wins + 1 loss => -1R, PF = 0.0, Exp = -1R
    df_b = pd.DataFrame({"label": [0]})
    res_b = calc.calculate_metrics(df_b)
    assert res_b["net_r"] == -1.0, f"Test B Net R Failed: {res_b['net_r']}"
    assert res_b["profit_factor"] == 0.0, f"Test B PF Failed: {res_b['profit_factor']}"
    assert res_b["expectancy"] == -1.0, f"Test B Exp Failed: {res_b['expectancy']}"
    print("✅ Test B PASSED (0 Wins + 1 Loss => Net R = -1R, PF = 0.0, Exp = -1R)")

    # Test C: 1 win + 1 loss => +2R, Exp = +1R, PF = 3.0
    df_c = pd.DataFrame({"label": [1, 0]})
    res_c = calc.calculate_metrics(df_c)
    assert res_c["net_r"] == 2.0, f"Test C Net R Failed: {res_c['net_r']}"
    assert res_c["expectancy"] == 1.0, f"Test C Exp Failed: {res_c['expectancy']}"
    assert res_c["profit_factor"] == 3.0, f"Test C PF Failed: {res_c['profit_factor']}"
    print("✅ Test C PASSED (1 Win + 1 Loss => Net R = +2R, Exp = +1R, PF = 3.0)")

    # Test D: 3 wins + 7 losses => +2R, Exp = +0.2R, PF = 9/7 = 1.2857
    df_d = pd.DataFrame({"label": [1, 1, 1, 0, 0, 0, 0, 0, 0, 0]})
    res_d = calc.calculate_metrics(df_d)
    assert res_d["net_r"] == 2.0, f"Test D Net R Failed: {res_d['net_r']}"
    assert res_d["expectancy"] == 0.2, f"Test D Exp Failed: {res_d['expectancy']}"
    assert round(res_d["profit_factor"], 4) == 1.2857, f"Test D PF Failed: {res_d['profit_factor']}"
    print("✅ Test D PASSED (3 Wins + 7 Losses => Net R = +2R, Exp = +0.2R, PF = 1.2857)")

    # Test E: Sign symmetry verification (Losing trade count cannot produce positive P&L when losses dominate)
    df_e = pd.DataFrame({"label": [1, 0, 0, 0, 0]}) # 1 Win (+3R), 4 Losses (-4R) => Net R = -1R
    res_e = calc.calculate_metrics(df_e)
    assert res_e["net_r"] < 0, f"Test E Sign Symmetry Failed: {res_e['net_r']}"
    assert res_e["profit_factor"] < 1.0, f"Test E PF Sign Symmetry Failed: {res_e['profit_factor']}"
    print("✅ Test E PASSED (Sign Symmetry Verified: Losses dominating economically produces Negative Net R & PF < 1.0)\n")

if __name__ == "__main__":
    run_property_based_tests()
