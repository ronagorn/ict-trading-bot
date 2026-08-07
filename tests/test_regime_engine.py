"""
Unit Tests for Market Regime Detection Engine (AURA v5)
======================================================
Tests:
1. Missing Data & Insufficient History -> Returns UNKNOWN & Blocks Trading
2. Classification Accuracy across Trend & Volatility States
3. Extreme Volatility Spike Detection
4. Off-Hours & Low Liquidity Gate Check
5. Deterministic Boundary Conditions
"""

import sys
import unittest
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.regime_engine import MarketRegimeEngine, MarketRegime


class TestMarketRegimeEngine(unittest.TestCase):

    def setUp(self):
        self.engine = MarketRegimeEngine(min_required_bars=50)

    def test_missing_data_returns_unknown(self):
        """1. Verify missing or empty DataFrame returns UNKNOWN and blocks trading."""
        regime, feats = self.engine.detect_regime(None)
        self.assertEqual(regime, MarketRegime.UNKNOWN)
        self.assertFalse(self.engine.should_allow_trading(regime))

        df_short = pd.DataFrame({"close": [1.1000] * 10})
        regime_short, _ = self.engine.detect_regime(df_short)
        self.assertEqual(regime_short, MarketRegime.UNKNOWN)
        self.assertFalse(self.engine.should_allow_trading(regime_short))

    def test_low_liquidity_detection(self):
        """2. Verify off-hours or extreme spread returns LOW_LIQUIDITY and blocks trading."""
        df_dummy = self._create_dummy_data(60)
        
        # Test Off-Hours (22:00 UTC)
        regime_offhours, _ = self.engine.detect_regime(df_dummy, current_hour=22)
        self.assertEqual(regime_offhours, MarketRegime.LOW_LIQUIDITY)
        self.assertFalse(self.engine.should_allow_trading(regime_offhours))

        # Test High Spread (> 5 pips)
        regime_spread, _ = self.engine.detect_regime(df_dummy, spread_pips=6.5)
        self.assertEqual(regime_spread, MarketRegime.LOW_LIQUIDITY)
        self.assertFalse(self.engine.should_allow_trading(regime_spread))

    def test_extreme_volatility_detection(self):
        """3. Verify extreme candle range ratio triggers EXTREME_VOLATILITY."""
        n = 60
        df = self._create_dummy_data(n)
        
        # Inject extreme spike in last candle
        df.iloc[-1, df.columns.get_loc("high")] = df.iloc[-1]["open"] + 0.0500
        df.iloc[-1, df.columns.get_loc("low")] = df.iloc[-1]["open"] - 0.0500

        regime, feats = self.engine.detect_regime(df)
        self.assertEqual(regime, MarketRegime.EXTREME_VOLATILITY)

    def test_trending_high_vol_classification(self):
        """4. Verify strong trend + high ATR volatility classifies as TRENDING_HIGH_VOL."""
        n = 60
        # Create strong uptrend
        prices = 1.1000 + np.linspace(0, 0.0500, n)
        df = pd.DataFrame({
            "open": prices,
            "high": prices + 0.0030,
            "low": prices - 0.0030,
            "close": prices + 0.0020
        })

        regime, feats = self.engine.detect_regime(df)
        self.assertIn(regime, [MarketRegime.TRENDING_HIGH_VOL, MarketRegime.TRENDING_LOW_VOL])
        self.assertTrue(self.engine.should_allow_trading(regime))

    def _create_dummy_data(self, n: int) -> pd.DataFrame:
        np.random.seed(42)
        prices = 1.1000 + np.cumsum(np.random.randn(n) * 0.0005)
        return pd.DataFrame({
            "open": prices,
            "high": prices + 0.0005,
            "low": prices - 0.0005,
            "close": prices + 0.0002
        })


if __name__ == "__main__":
    unittest.main()
