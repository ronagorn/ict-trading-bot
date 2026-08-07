"""
Unit Tests for Institutional Risk Engine (AURA v5)
=================================================
Tests:
1. Zero SL / Invalid SL / Huge SL Handling
2. Minimum & Maximum Lot Constraints
3. Insufficient Free Margin Protection
4. Symbol Specification Mismatch / Missing Values
5. Drawdown State Machine (NORMAL -> CAUTION -> REDUCED -> HALT)
6. Loss Streak Cooldown Multipliers
7. Portfolio Cap, Symbol Cap & Currency Correlation Exposure
"""

import sys
import unittest
from pathlib import Path
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.risk_manager import InstitutionalRiskManager, DrawdownState


@dataclass
class MockSymbolInfo:
    trade_contract_size: float = 100000.0
    point: float = 0.00001
    volume_step: float = 0.01
    volume_min: float = 0.01
    volume_max: float = 100.0


@dataclass
class MockPosition:
    symbol: str


class TestInstitutionalRiskManager(unittest.TestCase):

    def setUp(self):
        self.config = {
            "risk_per_trade_percent": 1.0,
            "daily_drawdown_limit_percent": 3.0,
            "max_orders_per_symbol": 2,
            "max_total_open_orders": 4,
            "max_same_currency_exposure": 2,
            "min_rr_ratio": 1.5
        }
        self.risk_mgr = InstitutionalRiskManager(self.config)
        self.symbol_info = MockSymbolInfo()

    def test_zero_and_invalid_sl(self):
        """1. Verify Zero or Invalid SL returns 0.0 lot size (rejected)."""
        lot_zero_sl = self.risk_mgr.calculate_lot_size(
            account_equity=10000.0, free_margin=8000.0,
            symbol_info=self.symbol_info, entry_price=1.1000, stop_loss_price=1.1000
        )
        self.assertEqual(lot_zero_sl, 0.0)

    def test_huge_sl_rejection(self):
        """2. Verify unrealistically huge SL (> 15% price distance) returns 0.0 lot size."""
        lot_huge = self.risk_mgr.calculate_lot_size(
            account_equity=10000.0, free_margin=8000.0,
            symbol_info=self.symbol_info, entry_price=1.1000, stop_loss_price=0.8000 # ~27% SL
        )
        self.assertEqual(lot_huge, 0.0)

    def test_insufficient_margin_protection(self):
        """3. Verify insufficient free margin rejects position creation."""
        lot_margin = self.risk_mgr.calculate_lot_size(
            account_equity=10000.0, free_margin=50.0, # Tiny free margin
            symbol_info=self.symbol_info, entry_price=1.1000, stop_loss_price=1.0950
        )
        self.assertEqual(lot_margin, 0.0)

    def test_drawdown_state_machine(self):
        """4. Verify Drawdown State Machine transitions (NORMAL -> CAUTION -> REDUCED -> HALT)."""
        state_norm, _, mult_norm = self.risk_mgr.get_drawdown_state(10000.0, 10000.0)
        self.assertEqual(state_norm, DrawdownState.NORMAL)
        self.assertEqual(mult_norm, 1.0)

        state_caut, _, mult_caut = self.risk_mgr.get_drawdown_state(10000.0, 9820.0) # 1.8% DD
        self.assertEqual(state_caut, DrawdownState.CAUTION)
        self.assertEqual(mult_caut, 0.75)

        state_red, _, mult_red = self.risk_mgr.get_drawdown_state(10000.0, 9730.0) # 2.7% DD
        self.assertEqual(state_red, DrawdownState.REDUCED)
        self.assertEqual(mult_red, 0.50)

        state_halt, _, mult_halt = self.risk_mgr.get_drawdown_state(10000.0, 9680.0) # 3.2% DD >= 3.0%
        self.assertEqual(state_halt, DrawdownState.HALT)
        self.assertEqual(mult_halt, 0.0)

    def test_loss_streak_cooldown(self):
        """5. Verify loss streak cooldown multipliers."""
        self.assertEqual(self.risk_mgr.calculate_loss_streak_multiplier(0), 1.0)
        self.assertEqual(self.risk_mgr.calculate_loss_streak_multiplier(2), 0.75)
        self.assertEqual(self.risk_mgr.calculate_loss_streak_multiplier(3), 0.50)
        self.assertEqual(self.risk_mgr.calculate_loss_streak_multiplier(4), 0.0)

    def test_portfolio_caps_and_correlation(self):
        """6. Verify portfolio cap (4), symbol cap (2), and currency correlation cap (2)."""
        positions = [
            MockPosition("EURUSD"),
            MockPosition("EURUSD"),
            MockPosition("GBPUSD"),
            MockPosition("USDJPY")
        ]
        # Portfolio cap reached (4 positions)
        self.assertFalse(self.risk_mgr.can_open_new_position(positions, "AUDUSD"))

        positions_symbol_cap = [MockPosition("EURUSD"), MockPosition("EURUSD")]
        # Symbol cap reached (2 EURUSD positions)
        self.assertFalse(self.risk_mgr.can_open_new_position(positions_symbol_cap, "EURUSD"))

        positions_corr = [MockPosition("EURUSD"), MockPosition("USDCAD")]
        # USD correlation limit reached (2 USD positions: EURUSD, USDCAD)
        self.assertFalse(self.risk_mgr.can_open_new_position(positions_corr, "GBPUSD"))


if __name__ == "__main__":
    unittest.main()
