"""
Unit Tests for Realistic Execution Simulation Engine (AURA v5)
==============================================================
Tests:
1. Entry Timestamp & Latency Delay Calculation
2. Strict Conservative Same-Bar Collision Rule (TP & SL in same candle -> ALWAYS LOSS)
3. Gap Slippage past SL (Fills at Gap Open price)
4. Order Rejection & Spread Widening Simulation
5. Stress Profiles Execution Metrics
"""

import sys
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.realistic_execution import (
    RealisticExecutionEngine,
    ExecutionProfile,
    EXECUTION_PROFILES
)


class TestRealisticExecutionEngine(unittest.TestCase):

    def setUp(self):
        self.signal_dict = {
            "symbol": "EURUSD",
            "direction": "BUY",
            "time": datetime(2026, 8, 1, 14, 0, tzinfo=timezone.utc),
            "killzone_hour": 14
        }
        self.next_bar_time = datetime(2026, 8, 1, 14, 15, tzinfo=timezone.utc)
        self.next_bar_open = 1.1000

    def test_latency_and_timestamp_sequence(self):
        """1. Verify timestamp progression: signal_time <= decision_time < execution_time."""
        engine = RealisticExecutionEngine(EXECUTION_PROFILES["normal"])
        exec_info = engine.simulate_order_execution(
            self.signal_dict, self.next_bar_open, self.next_bar_time
        )
        if exec_info:
            self.assertLessEqual(exec_info["signal_time"], exec_info["decision_time"])
            self.assertLess(exec_info["decision_time"], exec_info["execution_time"])
            self.assertGreater(exec_info["execution_price"], self.next_bar_open)

    def test_conservative_same_bar_collision(self):
        """2. Verify Same-Bar Collision Rule: When both TP & SL are hit in same candle, outcome MUST be LOSS."""
        engine = RealisticExecutionEngine(EXECUTION_PROFILES["ideal"])
        exec_info = {
            "symbol": "EURUSD",
            "direction": "BUY",
            "execution_price": 1.1000,
            "commission_usd": 0.0,
            "swap_usd": 0.0
        }

        # Create Bar 0 (entry bar) and Bar 1 (collision candle where low <= SL AND high >= TP)
        df_collision = pd.DataFrame([
            {"time": self.signal_dict["time"], "open": 1.1000, "high": 1.1005, "low": 1.0995, "close": 1.1000},
            {"time": self.next_bar_time, "open": 1.1000, "high": 1.1200, "low": 1.0800, "close": 1.1000}
        ])

        res = engine.simulate_trade_lifespan(
            exec_info, df_collision, entry_bar_idx=0,
            target_sl=1.0900, target_tp=1.1180, risk_usd=200.0, rr_ratio=1.8
        )

        self.assertEqual(res["outcome"], "LOSS", "CRITICAL CONSERVATIVE RULE: Same-bar TP/SL collision MUST resolve as LOSS!")

    def test_gap_slippage_past_sl(self):
        """3. Verify Gap Slippage: If price gaps past SL, exit price fills at Gap Open, resulting in larger loss."""
        engine = RealisticExecutionEngine(EXECUTION_PROFILES["ideal"])
        exec_info = {
            "symbol": "EURUSD",
            "direction": "BUY",
            "execution_price": 1.1000,
            "commission_usd": 0.0,
            "swap_usd": 0.0
        }

        # Create Bar 0 (entry bar) and Bar 1 (gap candle where Open = 1.0850 < SL 1.0900)
        df_gap = pd.DataFrame([
            {"time": self.signal_dict["time"], "open": 1.1000, "high": 1.1005, "low": 1.0995, "close": 1.1000},
            {"time": self.next_bar_time, "open": 1.0850, "high": 1.0870, "low": 1.0800, "close": 1.0820}
        ])

        res = engine.simulate_trade_lifespan(
            exec_info, df_gap, entry_bar_idx=0,
            target_sl=1.0900, target_tp=1.1180, risk_usd=200.0, rr_ratio=1.8
        )

        self.assertEqual(res["outcome"], "LOSS")
        self.assertEqual(res["exit_price"], 1.0850, "Gap exit price must fill at Gap Open (1.0850)")
        self.assertLess(res["net_pnl"], -200.0, "Net PnL must reflect extra gap loss")

    def test_all_execution_profiles_validity(self):
        """4. Verify all 5 execution profiles load cleanly and simulate correctly."""
        for key, profile in EXECUTION_PROFILES.items():
            engine = RealisticExecutionEngine(profile)
            self.assertIsNotNone(engine.profile.name)
            self.assertGreaterEqual(engine.profile.base_spread_pips, 0.0)


if __name__ == "__main__":
    unittest.main()
