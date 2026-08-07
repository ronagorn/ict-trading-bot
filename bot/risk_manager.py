"""
Production-Grade Institutional Risk Engine (AURA v5)
====================================================
Single Source of Truth Config & Portfolio Risk Control Layer.

Enforces:
1. Single Source of Truth Configuration (bot/config.json)
2. Drawdown State Machine (NORMAL -> CAUTION -> REDUCED -> HALT)
3. Loss Streak Cooldown & Risk Reduction
4. Robust Position Sizing (Free Margin, Spec Validation, Lot Limits)
5. Multi-Layer Safety Gate (Strategy -> ML -> NoTrade -> Risk -> Broker)
"""

from __future__ import annotations
import math
import sys
from pathlib import Path
from enum import Enum
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.logger import logger


class DrawdownState(str, Enum):
    NORMAL = "NORMAL"      # DD < 1.5% -> 100% Risk
    CAUTION = "CAUTION"    # DD 1.5% - 2.5% -> 75% Risk
    REDUCED = "REDUCED"    # DD 2.5% - 3.0% -> 50% Risk
    HALT = "HALT"          # DD >= 3.0% -> 0% Risk (Halt Trading)


class InstitutionalRiskManager:
    """
    Institutional Risk Engine enforcing single source of truth configuration.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def get_drawdown_state(self, initial_balance: float, current_equity: float) -> Tuple[DrawdownState, float, float]:
        """
        Calculates Drawdown State and Risk Scaling Multiplier.
        Returns (DrawdownState, drawdown_percent, risk_multiplier)
        """
        limit_pct = float(self.config.get("daily_drawdown_limit_percent", 3.0))

        if current_equity >= initial_balance or initial_balance <= 0:
            return DrawdownState.NORMAL, 0.0, 1.0

        dd_pct = ((initial_balance - current_equity) / initial_balance) * 100.0

        if dd_pct >= limit_pct:
            return DrawdownState.HALT, dd_pct, 0.0
        elif dd_pct >= (limit_pct * 0.83): # e.g. >= 2.5%
            return DrawdownState.REDUCED, dd_pct, 0.50
        elif dd_pct >= (limit_pct * 0.50): # e.g. >= 1.5%
            return DrawdownState.CAUTION, dd_pct, 0.75
        else:
            return DrawdownState.NORMAL, dd_pct, 1.0

    def calculate_loss_streak_multiplier(self, consecutive_losses: int) -> float:
        """Applies risk reduction based on consecutive losing streak."""
        if consecutive_losses >= 4:
            return 0.0  # Cooldown Halt
        elif consecutive_losses == 3:
            return 0.50 # 50% Risk
        elif consecutive_losses == 2:
            return 0.75 # 75% Risk
        return 1.0

    def calculate_lot_size(
        self,
        account_equity: float,
        free_margin: float,
        symbol_info: Any,
        entry_price: float,
        stop_loss_price: float,
        risk_percent: Optional[float] = None,
        consecutive_losses: int = 0,
        initial_balance: Optional[float] = None
    ) -> float:
        """
        Robust Position Sizing calculation with broker spec validation & risk caps.
        """
        # 1. Invalid Input Checks
        if account_equity <= 0 or free_margin <= 0 or entry_price <= 0 or stop_loss_price <= 0:
            logger.warning("Position Sizing Rejected: Invalid equity, margin, or prices")
            return 0.0

        sl_distance = abs(entry_price - stop_loss_price)
        if sl_distance <= 0:
            logger.warning("Position Sizing Rejected: SL Distance is 0")
            return 0.0

        # Reject unrealistically huge SLs (> 15% price distance)
        if (sl_distance / entry_price) > 0.15:
            logger.warning(f"Position Sizing Rejected: SL Distance unrealistically wide ({sl_distance:.4f})")
            return 0.0

        # 2. Single Source of Truth Risk Percent
        base_risk_pct = float(risk_percent if risk_percent is not None else self.config.get("risk_per_trade_percent", 1.0))
        
        # 3. Apply Drawdown State & Loss Streak Multipliers
        init_bal = initial_balance or account_equity
        dd_state, dd_pct, dd_multiplier = self.get_drawdown_state(init_bal, account_equity)
        
        if dd_state == DrawdownState.HALT:
            logger.warning(f"Position Sizing Rejected: Drawdown State is HALT ({dd_pct:.2f}%)")
            return 0.0

        streak_multiplier = self.calculate_loss_streak_multiplier(consecutive_losses)
        if streak_multiplier == 0.0:
            logger.warning(f"Position Sizing Rejected: Cooldown active ({consecutive_losses} consecutive losses)")
            return 0.0

        effective_risk_pct = base_risk_pct * dd_multiplier * streak_multiplier
        risk_amount = account_equity * (effective_risk_pct / 100.0)

        # 4. Symbol Specification & Tick Value Calculation
        try:
            contract_size = getattr(symbol_info, "trade_contract_size", 100000.0)
            point = getattr(symbol_info, "point", 0.00001)
            vol_step = getattr(symbol_info, "volume_step", 0.01)
            min_vol = getattr(symbol_info, "volume_min", 0.01)
            max_vol = getattr(symbol_info, "volume_max", 100.0)
        except Exception as e:
            logger.error(f"Error accessing symbol specifications: {e}")
            return 0.0

        tick_value = contract_size * point
        if tick_value <= 0 or point <= 0:
            logger.warning("Position Sizing Rejected: Invalid tick value or point size")
            return 0.0

        loss_per_lot = (sl_distance / point) * tick_value
        if loss_per_lot <= 0:
            return 0.0

        raw_lot = risk_amount / loss_per_lot

        # 5. Round to Broker Volume Step
        steps = math.floor(raw_lot / vol_step)
        lot_size = steps * vol_step

        # 6. Apply Min/Max Volume Caps
        if lot_size < min_vol:
            # Check if minimum lot size exceeds max risk amount
            min_lot_loss = min_vol * loss_per_lot
            if min_lot_loss > (risk_amount * 1.5):
                logger.warning(f"Position Sizing Rejected: Minimum lot size loss (${min_lot_loss:.2f}) exceeds risk cap")
                return 0.0
            lot_size = min_vol

        lot_size = min(lot_size, max_vol)
        lot_size = round(lot_size, 2)

        # 7. Insufficient Free Margin Check
        estimated_margin = (lot_size * contract_size * entry_price) / 100.0  # Approx 1:100 leverage
        if estimated_margin > (free_margin * 0.8):
            logger.warning(f"Position Sizing Rejected: Required margin (${estimated_margin:.2f}) exceeds 80% free margin (${free_margin:.2f})")
            return 0.0

        return lot_size

    def validate_setup(self, entry: float, sl: float, tp: float, symbol: str) -> bool:
        """Validates Risk/Reward Ratio against Single Source of Truth min_rr_ratio."""
        min_rr = float(self.config.get("min_rr_ratio", 1.5))
        risk = abs(entry - sl)
        reward = abs(tp - entry)

        if risk <= 0 or reward <= 0:
            logger.warning(f"Invalid setup for {symbol}: Zero risk or reward")
            return False

        rr_ratio = reward / risk
        if rr_ratio < (min_rr - 0.05):
            logger.info(f"Setup rejected for {symbol}: R:R ratio {rr_ratio:.2f} < minimum {min_rr}")
            return False

        return True

    def check_correlation_exposure(self, open_positions: List[Any], new_symbol: str) -> bool:
        """Currency Correlation Exposure Filter."""
        if not open_positions:
            return True

        max_same_curr = int(self.config.get("max_same_currency_exposure", 2))

        def get_currencies(sym: str) -> List[str]:
            s = str(sym).replace("#", "").upper()
            if "GOLD" in s or "XAU" in s: return ["USD"]
            if "BTC" in s: return ["BTC"]
            if len(s) == 6: return [s[:3], s[3:]]
            return [s]

        new_curs = get_currencies(new_symbol)
        for cur in new_curs:
            same_count = sum(1 for pos in open_positions if cur in get_currencies(getattr(pos, "symbol", "")))
            if same_count >= max_same_curr:
                logger.warning(f"Correlation limit reached for {cur}: {same_count} active orders")
                return False

        return True

    def can_open_new_position(self, open_positions: List[Any], target_symbol: str) -> bool:
        """Portfolio & Symbol Exposure Caps Validation."""
        if not open_positions:
            return True

        max_total = int(self.config.get("max_total_open_orders", 4))
        if len(open_positions) >= max_total:
            logger.debug(f"Portfolio open orders limit reached: {len(open_positions)}/{max_total}")
            return False

        max_per_symbol = int(self.config.get("max_orders_per_symbol", 2))
        symbol_count = sum(1 for pos in open_positions if getattr(pos, "symbol", "") == target_symbol)
        if symbol_count >= max_per_symbol:
            logger.debug(f"Max open orders limit reached for {target_symbol}: {symbol_count}/{max_per_symbol}")
            return False

        if not self.check_correlation_exposure(open_positions, target_symbol):
            return False

        return True


# Backward Compatibility Alias
RiskManager = InstitutionalRiskManager
