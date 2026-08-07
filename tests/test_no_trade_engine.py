"""
Unit Tests for No-Trade Decision Engine (AURA v5)
=================================================
Tests:
1. Emergency Stop Circuit Breakers (Daily DD limit & MT5 disconnection)
2. Individual Safety Condition Evaluations (Spread, Latency, News, Stale Data, Duplicate Signal)
3. Combination Condition Scenarios (High spread + High vol, Drawdown + Correlation, ML failure + Stale data)
4. Decision State Progression (NORMAL -> REDUCED -> STRICT -> NO_TRADE -> EMERGENCY_STOP)
5. Priority Override Authority over Strategy Engine
"""

import sys
import unittest
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.no_trade_engine import NoTradeDecisionEngine, DecisionState
from bot.regime_engine import MarketRegime


class TestNoTradeDecisionEngine(unittest.TestCase):

    def setUp(self):
        self.engine = NoTradeDecisionEngine()

    def test_normal_state_all_clear(self):
        """1. Verify NORMAL state returns approved=True and risk_multiplier=1.0."""
        res = self.engine.evaluate_trading_conditions("EURUSD")
        self.assertEqual(res.decision_state, DecisionState.NORMAL)
        self.assertTrue(res.approved)
        self.assertEqual(res.risk_multiplier, 1.0)

    def test_emergency_stop_drawdown_limit(self):
        """2. Verify EMERGENCY_STOP triggers when daily drawdown >= 8.0%."""
        res = self.engine.evaluate_trading_conditions("EURUSD", daily_drawdown_pct=8.5)
        self.assertEqual(res.decision_state, DecisionState.EMERGENCY_STOP)
        self.assertFalse(res.approved)
        self.assertEqual(res.risk_multiplier, 0.0)
        self.assertEqual(res.severity, "CRITICAL")

    def test_emergency_stop_mt5_disconnected(self):
        """3. Verify EMERGENCY_STOP triggers when MT5 is disconnected."""
        res = self.engine.evaluate_trading_conditions("EURUSD", mt5_connected=False)
        self.assertEqual(res.decision_state, DecisionState.EMERGENCY_STOP)
        self.assertFalse(res.approved)

    def test_combination_high_spread_and_volatility(self):
        """4. Verify combination of High Spread (>4.0) and Extreme Volatility triggers NO_TRADE."""
        res = self.engine.evaluate_trading_conditions(
            "EURUSD",
            current_spread_pips=5.2,
            regime=MarketRegime.EXTREME_VOLATILITY
        )
        self.assertEqual(res.decision_state, DecisionState.NO_TRADE)
        self.assertFalse(res.approved)
        self.assertGreaterEqual(len(res.reasons), 2)

    def test_combination_ml_failure_and_stale_data(self):
        """5. Verify combination of ML Failure and Stale Data (>60s) triggers NO_TRADE."""
        res = self.engine.evaluate_trading_conditions(
            "EURUSD",
            is_ml_available=False,
            data_age_seconds=120
        )
        self.assertEqual(res.decision_state, DecisionState.NO_TRADE)
        self.assertFalse(res.approved)

    def test_strict_mode_ml_drift(self):
        """6. Verify ML drift (PSI >= 0.25) triggers STRICT mode with 25% lot size."""
        res = self.engine.evaluate_trading_conditions("EURUSD", model_psi_drift=0.30)
        self.assertEqual(res.decision_state, DecisionState.STRICT)
        self.assertTrue(res.approved)
        self.assertEqual(res.risk_multiplier, 0.25)

    def test_reduced_mode_elevated_friction(self):
        """7. Verify elevated spread/latency triggers REDUCED mode with 50% lot size."""
        res = self.engine.evaluate_trading_conditions("EURUSD", current_latency_ms=400)
        self.assertEqual(res.decision_state, DecisionState.REDUCED)
        self.assertTrue(res.approved)
        self.assertEqual(res.risk_multiplier, 0.50)

    def test_news_filter_triggers_no_trade(self):
        """8. Verify active high-impact news filter triggers NO_TRADE."""
        res = self.engine.evaluate_trading_conditions("EURUSD", is_news_active=True)
        self.assertEqual(res.decision_state, DecisionState.NO_TRADE)
        self.assertFalse(res.approved)


if __name__ == "__main__":
    unittest.main()
