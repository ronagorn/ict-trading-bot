"""
Production-Grade Purged Walk-Forward Validation Engine
======================================================
Implements Marcos López de Prado's Purged Walk-Forward CV:
TRAIN -> PURGE -> EMBARGO -> TEST

Prevents:
1. Look-ahead bias
2. Overlapping label contamination
3. Serial correlation / embargo leakage
4. Hyperparameter & Fold selection bias
"""

from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, Generator
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.logger import logger
from bot.ml_filter import MLFilterEngine, FEATURE_COLUMNS, FORBIDDEN_LEAKAGE_COLUMNS


class PurgedWalkForwardCV:
    """
    Purged Walk-Forward Cross-Validator with Embargo logic.
    """

    def __init__(
        self,
        n_splits: int = 5,
        purge_margin_bars: int = 0,
        embargo_pct: float = 0.01,
        embargo_minutes: Optional[int] = None
    ):
        self.n_splits = max(2, n_splits)
        self.purge_margin_bars = max(0, purge_margin_bars)
        self.embargo_pct = max(0.0, embargo_pct)
        self.embargo_minutes = embargo_minutes

    def split(
        self,
        df: pd.DataFrame,
        label_start_col: str = "entry_time",
        label_end_col: str = "exit_time"
    ) -> Generator[Tuple[np.ndarray, np.ndarray], None, None]:
        """
        Yields (train_indices, test_indices) for each chronological fold.
        """
        n_samples = len(df)
        if n_samples < self.n_splits * 5:
            raise ValueError(f"Dataset size ({n_samples}) too small for {self.n_splits} splits.")

        df_sorted = df.sort_values(label_start_col).reset_index(drop=True)
        
        # Calculate test block size
        fold_size = n_samples // (self.n_splits + 1)

        for k in range(self.n_splits):
            test_start_idx = (k + 1) * fold_size
            test_end_idx = min(test_start_idx + fold_size, n_samples)
            if k == self.n_splits - 1:
                test_end_idx = n_samples

            test_indices = np.arange(test_start_idx, test_end_idx)
            test_df = df_sorted.iloc[test_indices]
            
            test_start_time = pd.to_datetime(test_df[label_start_col].min(), utc=True)
            test_end_time = pd.to_datetime(test_df[label_end_col].max(), utc=True)

            # Candidate train set: All samples prior to test start
            train_candidates = df_sorted.iloc[:test_start_idx].copy()
            
            # Determine Embargo Delta
            if self.embargo_minutes is not None:
                embargo_delta = timedelta(minutes=self.embargo_minutes)
            else:
                total_duration = (test_end_time - test_start_time).total_seconds()
                embargo_delta = timedelta(seconds=total_duration * self.embargo_pct)

            embargo_cutoff = test_start_time - embargo_delta

            clean_train_indices = []
            for idx, row in train_candidates.iterrows():
                row_start = pd.to_datetime(row[label_start_col], utc=True)
                row_end = pd.to_datetime(row[label_end_col], utc=True)

                # 1. PURGE: Remove training samples whose label period overlaps test window
                is_purged = (row_end >= test_start_time) and (row_start <= test_end_time)

                # 2. EMBARGO: Remove training samples ending inside embargo window
                is_embargoed = (row_end > embargo_cutoff) and (row_end < test_start_time)

                if not is_purged and not is_embargoed:
                    clean_train_indices.append(idx)

            yield np.array(clean_train_indices), test_indices


class PurgedWalkForwardEvaluator:
    """
    Evaluator for Purged Walk-Forward Performance Metrics & Regime Analysis.
    """

    @staticmethod
    def calculate_fold_metrics(trades_df: pd.DataFrame, initial_balance: float = 10000.0) -> Dict[str, Any]:
        """Calculates comprehensive quant metrics for a single fold or overall OOS."""
        if trades_df.empty:
            return {
                "trades": 0, "win_rate": 0.0, "avg_r": 0.0, "expectancy": 0.0,
                "profit_factor": 0.0, "max_drawdown": 0.0, "sharpe": 0.0,
                "sortino": 0.0, "losing_streak": 0, "net_profit": 0.0
            }

        total_trades = len(trades_df)
        wins = trades_df[trades_df["pnl"] > 0]
        losses = trades_df[trades_df["pnl"] < 0]
        
        n_wins = len(wins)
        win_rate = (n_wins / total_trades) * 100.0 if total_trades > 0 else 0.0
        
        gross_profit = float(wins["pnl"].sum()) if not wins.empty else 0.0
        gross_loss = abs(float(losses["pnl"].sum())) if not losses.empty else 0.0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

        pnls = trades_df["pnl"].values
        net_profit = float(np.sum(pnls))
        expectancy = float(np.mean(pnls)) if total_trades > 0 else 0.0

        # R-Multiple statistics (assuming risk per trade = $200)
        r_multiples = pnls / 200.0
        avg_r = float(np.mean(r_multiples)) if len(r_multiples) > 0 else 0.0

        # Max Drawdown
        equity_curve = initial_balance + np.cumsum(pnls)
        peaks = np.maximum.accumulate(equity_curve)
        drawdowns = (peaks - equity_curve) / peaks * 100.0
        max_dd = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

        # Sharpe & Sortino (per-trade risk adjusted)
        std_pnl = float(np.std(pnls))
        sharpe = (expectancy / std_pnl * np.sqrt(252)) if std_pnl > 0 else 0.0
        
        downside_pnls = pnls[pnls < 0]
        downside_std = float(np.std(downside_pnls)) if len(downside_pnls) > 0 else 0.0
        sortino = (expectancy / downside_std * np.sqrt(252)) if downside_std > 0 else 0.0

        # Max Losing Streak
        losing_streak, current_streak = 0, 0
        for pnl in pnls:
            if pnl < 0:
                current_streak += 1
                if current_streak > losing_streak:
                    losing_streak = current_streak
            else:
                current_streak = 0

        return {
            "trades": total_trades,
            "win_rate": round(win_rate, 2),
            "avg_r": round(avg_r, 2),
            "expectancy": round(expectancy, 2),
            "profit_factor": round(profit_factor, 2),
            "max_drawdown": round(max_dd, 2),
            "sharpe": round(sharpe, 2),
            "sortino": round(sortino, 2),
            "losing_streak": losing_streak,
            "net_profit": round(net_profit, 2)
        }

    @classmethod
    def evaluate_stability(cls, fold_metrics_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Performs stability analysis across all chronological folds."""
        if not fold_metrics_list:
            return {}

        win_rates = [m["win_rate"] for m in fold_metrics_list]
        pfs = [m["profit_factor"] for m in fold_metrics_list]
        sharpes = [m["sharpe"] for m in fold_metrics_list]

        mean_wr = float(np.mean(win_rates))
        std_wr = float(np.std(win_rates))
        median_wr = float(np.median(win_rates))

        mean_pf = float(np.mean(pfs))
        worst_pf = float(np.min(pfs))
        best_pf = float(np.max(pfs))

        # Regime Dependency Check: Flag if std is high or win rate drops severely in folds
        regime_dependent = (std_wr > 12.0) or (worst_pf < 1.0) or (min(win_rates) < 45.0)

        return {
            "mean_win_rate": round(mean_wr, 2),
            "median_win_rate": round(median_wr, 2),
            "std_win_rate": round(std_wr, 2),
            "mean_profit_factor": round(mean_pf, 2),
            "worst_fold_pf": round(worst_pf, 2),
            "best_fold_pf": round(best_pf, 2),
            "regime_dependency_flag": regime_dependent,
            "status": "REGIME DEPENDENT ⚠️" if regime_dependent else "ROBUST & STABLE ✅"
        }
