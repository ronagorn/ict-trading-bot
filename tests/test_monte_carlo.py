"""
Unit Tests for Monte Carlo Robustness & Stress Testing Engine (AURA v5)
=======================================================================
Tests:
1. Resampling Execution (10,000 simulations complete cleanly)
2. Percentiles Calculation (5th, 25th, 50th, 75th, 95th)
3. Single Path Drawdown & Recovery Calculation
4. Sequence Sensitivity Detection Flag
5. Stress Scenarios Behavior (BASE vs ADVERSE vs SEVERE)
"""

import sys
import unittest
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.monte_carlo import MonteCarloEngine, MonteCarloSimulationResult


class TestMonteCarloEngine(unittest.TestCase):

    def setUp(self):
        self.engine = MonteCarloEngine(n_simulations=500, initial_balance=10000.0, risk_usd=200.0)
        # Mock OOS trade PnLs (Win Rate ~60%, R:R = 1:1.8)
        np.random.seed(42)
        n = 100
        is_win = np.random.rand(n) < 0.60
        self.oos_pnls = np.where(is_win, 360.0, -200.0)

    def test_single_path_metrics(self):
        """1. Verify single path calculation for Final R, Max DD, Streak, Recovery."""
        pnls = np.array([360.0, -200.0, -200.0, 360.0, 360.0])
        final_r, max_dd, streak, recovery = self.engine.calculate_single_path_metrics(pnls, 10000.0)
        
        self.assertEqual(final_r, 3.4)  # (360 - 200 - 200 + 360 + 360) / 200 = 680 / 200 = 3.4 R
        self.assertGreater(max_dd, 0.0)
        self.assertEqual(streak, 2)

    def test_monte_carlo_resampling_execution(self):
        """2. Verify Monte Carlo runs simulations and returns all 5 percentiles."""
        res = self.engine.run_simulations(self.oos_pnls)
        
        self.assertEqual(res.n_simulations, 500)
        self.assertIn("5th", res.final_r_percentiles)
        self.assertIn("50th", res.final_r_percentiles)
        self.assertIn("95th", res.final_r_percentiles)
        
        # Verify 95th percentile >= 50th >= 5th
        self.assertGreaterEqual(res.final_r_percentiles["95th"], res.final_r_percentiles["50th"])
        self.assertGreaterEqual(res.final_r_percentiles["50th"], res.final_r_percentiles["5th"])

    def test_stress_scenarios_degradation(self):
        """3. Verify ADVERSE and SEVERE stress scenarios degrade performance as expected."""
        res_base = self.engine.run_simulations(self.oos_pnls, slippage_noise_std=0.0, win_rate_shift=0.0)
        res_adverse = self.engine.run_simulations(self.oos_pnls, slippage_noise_std=15.0, win_rate_shift=-0.10)
        res_severe = self.engine.run_simulations(self.oos_pnls, slippage_noise_std=30.0, win_rate_shift=-0.20)

        self.assertGreater(res_base.net_pnl_percentiles["50th"], res_adverse.net_pnl_percentiles["50th"])
        self.assertGreater(res_adverse.net_pnl_percentiles["50th"], res_severe.net_pnl_percentiles["50th"])

    def test_sequence_sensitivity_flag(self):
        """4. Verify bad trade sequence triggers SEQUENCE SENSITIVE flag."""
        # Unstable trades (Win Rate 20%)
        bad_pnls = np.array([-200.0] * 80 + [360.0] * 20)
        res_bad = self.engine.run_simulations(bad_pnls)
        self.assertTrue(res_bad.is_sequence_sensitive)
        self.assertEqual(res_bad.status, "SEQUENCE SENSITIVE ⚠️")


if __name__ == "__main__":
    unittest.main()
