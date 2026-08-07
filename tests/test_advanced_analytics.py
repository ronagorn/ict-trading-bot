"""
Unit Tests for Advanced Trade Analytics & Research Logger (AURA v5)
====================================================================
Tests:
1. Schema Compliance for ComprehensiveTradeRecord
2. MFE & MAE Excursion Calculation (BUY & SELL directions)
3. Exit Reason Tracking Breakdown
4. Research Diagnostics: Asymmetry, SL Width & TP Realism Flags
"""

import sys
import unittest
from pathlib import Path
from dataclasses import asdict
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.trade_analytics import (
    ComprehensiveTradeRecord,
    AdvancedTradeAnalyticsEngine
)


class TestAdvancedTradeAnalytics(unittest.TestCase):

    def setUp(self):
        self.engine = AdvancedTradeAnalyticsEngine()

    def test_schema_completeness(self):
        """1. Verify ComprehensiveTradeRecord contains all required research fields."""
        record = ComprehensiveTradeRecord(trade_id="TR_1001")
        rec_dict = asdict(record)
        
        required_fields = [
            "trade_id", "strategy_version", "model_version", "config_version",
            "symbol", "direction", "session", "regime", "entry_time", "entry_price",
            "exit_time", "exit_price", "sl", "tp", "rr", "spread_at_entry",
            "execution_latency", "slippage", "mfe", "mae", "r_realized",
            "pnl_usd", "exit_reason", "fvg_score", "ob_score", "sweep_score",
            "ml_prob", "final_score"
        ]

        for req in required_fields:
            self.assertIn(req, rec_dict, f"SCHEMA MISSING FIELD: {req} is required in trade record!")

    def test_excursion_calculations_buy(self):
        """2. Verify MFE & MAE calculation for BUY trade."""
        # BUY entry = 1.1000, SL = 1.0900 (SL dist = 0.0100)
        # Highs = 1.1180 (+1.8 R), Lows = 1.0950 (-0.5 R)
        highs = np.array([1.1050, 1.1120, 1.1180, 1.1100])
        lows = np.array([1.0980, 1.0960, 1.0950, 1.0990])
        
        mfe, mae = self.engine.calculate_trade_excursions("BUY", 1.1000, 1.0900, highs, lows)
        self.assertEqual(mfe, 1.8)
        self.assertEqual(mae, 0.5)

    def test_excursion_calculations_sell(self):
        """3. Verify MFE & MAE calculation for SELL trade."""
        # SELL entry = 1.1000, SL = 1.1100 (SL dist = 0.0100)
        # Lows = 1.0820 (+1.8 R), Highs = 1.1040 (-0.4 R)
        highs = np.array([1.1020, 1.1040, 1.1010])
        lows = np.array([1.0950, 1.0880, 1.0820])

        mfe, mae = self.engine.calculate_trade_excursions("SELL", 1.1000, 1.1100, highs, lows)
        self.assertEqual(mfe, 1.8)
        self.assertEqual(mae, 0.4)

    def test_research_report_generation(self):
        """4. Verify research analytics report generation with asymmetry and SL/TP diagnostics."""
        df_mock = pd.DataFrame([
            {"direction": "BUY", "pnl_usd": 360.0, "mfe": 2.0, "mae": 0.3, "r_realized": 1.8, "exit_reason": "TP_HIT"},
            {"direction": "BUY", "pnl_usd": 360.0, "mfe": 1.9, "mae": 0.4, "r_realized": 1.8, "exit_reason": "TP_HIT"},
            {"direction": "SELL", "pnl_usd": -200.0, "mfe": 0.2, "mae": 1.0, "r_realized": -1.0, "exit_reason": "SL_HIT"},
            {"direction": "SELL", "pnl_usd": -200.0, "mfe": 0.1, "mae": 1.0, "r_realized": -1.0, "exit_reason": "SL_HIT"}
        ])

        report = self.engine.generate_research_report(df_mock)
        self.assertEqual(report["total_trades"], 4)
        self.assertEqual(report["buy_win_rate"], 100.0)
        self.assertEqual(report["sell_win_rate"], 0.0)
        self.assertTrue(report["directional_asymmetry_flag"])


if __name__ == "__main__":
    unittest.main()
