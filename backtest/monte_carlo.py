"""
Production-Grade Monte Carlo Robustness & Stress Testing Engine (AURA v5)
========================================================================
Implements 10,000 Monte Carlo simulations on locked OOS trade results:
1. Trade Sequence Resampling (Bootstrapping trade ordering)
2. Market Friction Noise Injection (Slippage & Spread Variations)
3. Stress Scenarios: BASE, ADVERSE, SEVERE
4. Sequence Sensitivity Detection (Lucky sequence flag)
5. Percentiles Evaluation: 5th, 25th, 50th (Median), 75th, 95th
"""

from __future__ import annotations
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.logger import logger


@dataclass
class MonteCarloSimulationResult:
    n_simulations: int
    final_r_percentiles: Dict[str, float]
    net_pnl_percentiles: Dict[str, float]
    max_dd_percentiles: Dict[str, float]
    losing_streak_percentiles: Dict[str, float]
    recovery_trades_percentiles: Dict[str, float]
    is_sequence_sensitive: bool
    status: str


class MonteCarloEngine:
    """
    Monte Carlo Robustness & Uncertainty Engine.
    """

    def __init__(self, n_simulations: int = 10000, initial_balance: float = 10000.0, risk_usd: float = 200.0):
        self.n_simulations = max(100, n_simulations)
        self.initial_balance = initial_balance
        self.risk_usd = risk_usd

    @staticmethod
    def calculate_single_path_metrics(
        pnls: np.ndarray,
        initial_balance: float
    ) -> Tuple[float, float, int, int]:
        """
        Calculates Final R, Max Drawdown %, Max Losing Streak, and Recovery Time for 1 simulation path.
        """
        total_pnl = float(np.sum(pnls))
        final_r = float(total_pnl / 200.0)

        equity_curve = initial_balance + np.cumsum(pnls)
        peaks = np.maximum.accumulate(equity_curve)
        drawdowns = (peaks - equity_curve) / peaks * 100.0
        max_dd = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

        # Losing streak
        losing_streak, current_streak = 0, 0
        for pnl in pnls:
            if pnl < 0:
                current_streak += 1
                if current_streak > losing_streak:
                    losing_streak = current_streak
            else:
                current_streak = 0

        # Recovery time (max trades spent in drawdown)
        in_dd_count, max_recovery_trades = 0, 0
        for eq, peak in zip(equity_curve, peaks):
            if eq < peak:
                in_dd_count += 1
                if in_dd_count > max_recovery_trades:
                    max_recovery_trades = in_dd_count
            else:
                in_dd_count = 0

        return final_r, max_dd, losing_streak, max_recovery_trades

    def run_simulations(
        self,
        oos_pnls: np.ndarray,
        slippage_noise_std: float = 15.0,
        win_rate_shift: float = 0.0
    ) -> MonteCarloSimulationResult:
        """
        Executes N Monte Carlo simulations by resampling trades with noise injection.
        """
        if len(oos_pnls) == 0:
            raise ValueError("OOS trade PnLs cannot be empty.")

        n_trades = len(oos_pnls)
        final_rs, max_dds, streaks, recoveries, net_pnls = [], [], [], [], []

        np.random.seed(42)

        for _ in range(self.n_simulations):
            # 1. Resample trade sequence with replacement
            sampled_indices = np.random.choice(n_trades, size=n_trades, replace=True)
            sampled_pnls = oos_pnls[sampled_indices].copy()

            # 2. Apply Win Rate Shift if specified (Adverse / Severe stress)
            if win_rate_shift != 0.0:
                # Flip some win trades to loss
                wins_mask = sampled_pnls > 0
                flip_count = int(np.sum(wins_mask) * abs(win_rate_shift))
                if flip_count > 0:
                    win_indices = np.where(wins_mask)[0]
                    flip_indices = np.random.choice(win_indices, size=min(flip_count, len(win_indices)), replace=False)
                    sampled_pnls[flip_indices] = -self.risk_usd

            # 3. Inject Slippage & Friction Noise
            if slippage_noise_std > 0:
                noise = np.random.normal(0, slippage_noise_std, size=n_trades)
                sampled_pnls -= np.abs(noise)

            # 4. Calculate Single Path Metrics
            final_r, max_dd, streak, recovery = self.calculate_single_path_metrics(
                sampled_pnls, self.initial_balance
            )

            final_rs.append(final_r)
            net_pnls.append(float(np.sum(sampled_pnls)))
            max_dds.append(max_dd)
            streaks.append(streak)
            recoveries.append(recovery)

        # Calculate Percentiles (5th, 25th, 50th/Median, 75th, 95th)
        percentile_keys = ["5th", "25th", "50th", "75th", "95th"]
        pct_values = [5, 25, 50, 75, 95]

        final_r_pcts = {k: round(float(np.percentile(final_rs, p)), 2) for k, p in zip(percentile_keys, pct_values)}
        net_pnl_pcts = {k: round(float(np.percentile(net_pnls, p)), 2) for k, p in zip(percentile_keys, pct_values)}
        max_dd_pcts = {k: round(float(np.percentile(max_dds, p)), 2) for k, p in zip(percentile_keys, pct_values)}
        streak_pcts = {k: round(float(np.percentile(streaks, p)), 2) for k, p in zip(percentile_keys, pct_values)}
        recovery_pcts = {k: round(float(np.percentile(recoveries, p)), 2) for k, p in zip(percentile_keys, pct_values)}

        # Failure Condition: SEQUENCE SENSITIVE Flag
        # Flagged if 5th percentile Max DD > 30% or 5th percentile Final R < 0
        is_sequence_sensitive = (max_dd_pcts["95th"] > 30.0) or (final_r_pcts["5th"] < 0.0)
        status = "SEQUENCE SENSITIVE ⚠️" if is_sequence_sensitive else "MONTE CARLO ROBUST ✅"

        return MonteCarloSimulationResult(
            n_simulations=self.n_simulations,
            final_r_percentiles=final_r_pcts,
            net_pnl_percentiles=net_pnl_pcts,
            max_dd_percentiles=max_dd_pcts,
            losing_streak_percentiles=streak_pcts,
            recovery_trades_percentiles=recovery_pcts,
            is_sequence_sensitive=is_sequence_sensitive,
            status=status
        )
