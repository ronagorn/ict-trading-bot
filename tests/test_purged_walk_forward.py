"""
Unit Tests for Production-Grade Purged Walk-Forward Validation Engine
=====================================================================
Tests:
1. Chronological Ordering (Strictly ascending time, no shuffle)
2. Purge Correctness (Removes overlapping label periods)
3. Embargo Correctness (Removes samples ending within embargo window)
4. No Train/Test Contamination
5. Stability Analysis & Metrics Calculation
"""

import sys
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.purged_walk_forward import PurgedWalkForwardCV, PurgedWalkForwardEvaluator


class TestPurgedWalkForwardCV(unittest.TestCase):

    def setUp(self):
        # Generate synthetic chronological trade log (150 trades)
        np.random.seed(42)
        n = 150
        base_time = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        
        entry_times, exit_times = [], []
        curr = base_time
        for i in range(n):
            curr += timedelta(hours=np.random.randint(1, 4))
            duration = timedelta(hours=np.random.randint(1, 6))
            entry_times.append(curr)
            exit_times.append(curr + duration)

        self.df_trades = pd.DataFrame({
            "entry_time": entry_times,
            "exit_time": exit_times,
            "fvg_size_pips": np.random.uniform(2, 20, n),
            "killzone_hour": [t.hour for t in entry_times],
            "trend_alignment": np.random.choice([0, 1], n),
            "volume_spike_ratio": np.random.uniform(1, 3, n),
            "pnl": np.random.choice([360.0, -200.0], n, p=[0.45, 0.55])
        })

    def test_chronological_ordering(self):
        """1. Verify splits strictly preserve chronological order with no random shuffle."""
        cv = PurgedWalkForwardCV(n_splits=3)
        for train_idx, test_idx in cv.split(self.df_trades):
            # Verify test indices come strictly after candidate train indices
            self.assertGreater(test_idx.min(), train_idx.max())

    def test_purge_correctness(self):
        """2. Verify purging removes any train sample overlapping test time window."""
        cv = PurgedWalkForwardCV(n_splits=3, purge_margin_bars=0)
        df_sorted = self.df_trades.sort_values("entry_time").reset_index(drop=True)

        for train_idx, test_idx in cv.split(df_sorted):
            test_start = pd.to_datetime(df_sorted.iloc[test_idx]["entry_time"].min(), utc=True)
            test_end = pd.to_datetime(df_sorted.iloc[test_idx]["exit_time"].max(), utc=True)

            train_df = df_sorted.iloc[train_idx]
            for _, row in train_df.iterrows():
                row_start = pd.to_datetime(row["entry_time"], utc=True)
                row_end = pd.to_datetime(row["exit_time"], utc=True)

                overlap = (row_end >= test_start) and (row_start <= test_end)
                self.assertFalse(overlap, f"PURGE FAIL: Train sample [{row_start} - {row_end}] overlaps test window [{test_start} - {test_end}]")

    def test_embargo_correctness(self):
        """3. Verify embargo removes train samples ending inside embargo window prior to test."""
        embargo_mins = 120
        cv = PurgedWalkForwardCV(n_splits=3, embargo_minutes=embargo_mins)
        df_sorted = self.df_trades.sort_values("entry_time").reset_index(drop=True)

        for train_idx, test_idx in cv.split(df_sorted):
            test_start = pd.to_datetime(df_sorted.iloc[test_idx]["entry_time"].min(), utc=True)
            embargo_cutoff = test_start - timedelta(minutes=embargo_mins)

            train_df = df_sorted.iloc[train_idx]
            for _, row in train_df.iterrows():
                row_end = pd.to_datetime(row["exit_time"], utc=True)
                is_embargo_violation = (row_end > embargo_cutoff) and (row_end < test_start)
                self.assertFalse(is_embargo_violation, f"EMBARGO FAIL: Train sample ending at {row_end} inside embargo window [{embargo_cutoff} - {test_start}]")

    def test_no_train_test_contamination(self):
        """4. Verify zero index overlap between train and test splits."""
        cv = PurgedWalkForwardCV(n_splits=4)
        for train_idx, test_idx in cv.split(self.df_trades):
            overlap_indices = set(train_idx).intersection(set(test_idx))
            self.assertEqual(len(overlap_indices), 0, "CONTAMINATION FAIL: Indices found in both train and test sets!")

    def test_evaluator_metrics_and_stability(self):
        """5. Verify fold metrics calculation and stability analysis."""
        metrics = PurgedWalkForwardEvaluator.calculate_fold_metrics(self.df_trades)
        self.assertIn("win_rate", metrics)
        self.assertIn("profit_factor", metrics)
        self.assertIn("max_drawdown", metrics)

        stability = PurgedWalkForwardEvaluator.evaluate_stability([metrics, metrics])
        self.assertIn("regime_dependency_flag", stability)


if __name__ == "__main__":
    unittest.main()
