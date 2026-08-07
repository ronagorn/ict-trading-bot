"""
Unit Tests for Configuration Hierarchy & Fail-Fast Validator (AURA v5)
========================================================================
Tests:
1. Valid Configuration Parsing
2. Fail-Fast Assertion on Missing Mandatory Key
3. Fail-Fast Assertion on Out-of-Range Parameter Values
4. Fail-Fast Assertion on Empty Symbol List
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.config_validator import (
    SystemConfigValidator,
    ConfigurationValidationError
)


class TestSystemConfigValidator(unittest.TestCase):

    def setUp(self):
        self.valid_raw_cfg = {
            "risk_per_trade_percent": 1.0,
            "daily_drawdown_limit_percent": 3.0,
            "max_total_open_orders": 4,
            "max_orders_per_symbol": 2,
            "max_same_currency_exposure": 2,
            "min_rr_ratio": 1.5,
            "ml_threshold": 0.60,
            "symbols": ["EURUSD", "GBPUSD", "GOLD#"]
        }

    def test_valid_config_loading(self):
        """1. Verify valid config dictionary validates cleanly."""
        v_cfg = SystemConfigValidator.validate_dict(self.valid_raw_cfg)
        self.assertEqual(v_cfg.risk_per_trade_percent, 1.0)
        self.assertEqual(v_cfg.daily_drawdown_limit_percent, 3.0)

    def test_missing_mandatory_key_fail_fast(self):
        """2. Verify missing mandatory key triggers ConfigurationValidationError fail-fast."""
        bad_cfg = dict(self.valid_raw_cfg)
        del bad_cfg["daily_drawdown_limit_percent"]

        with self.assertRaises(ConfigurationValidationError) as ctx:
            SystemConfigValidator.validate_dict(bad_cfg)
        self.assertIn("Missing mandatory config key", str(ctx.exception))

    def test_out_of_range_parameter_fail_fast(self):
        """3. Verify out-of-range parameter triggers ConfigurationValidationError fail-fast."""
        bad_cfg = dict(self.valid_raw_cfg)
        bad_cfg["risk_per_trade_percent"] = 25.0  # Out of range (max 5.0%)

        with self.assertRaises(ConfigurationValidationError) as ctx:
            SystemConfigValidator.validate_dict(bad_cfg)
        self.assertIn("out of allowed range", str(ctx.exception))

    def test_empty_symbols_fail_fast(self):
        """4. Verify empty symbol list triggers ConfigurationValidationError fail-fast."""
        bad_cfg = dict(self.valid_raw_cfg)
        bad_cfg["symbols"] = []

        with self.assertRaises(ConfigurationValidationError) as ctx:
            SystemConfigValidator.validate_dict(bad_cfg)
        self.assertIn("symbols", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
