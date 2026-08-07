"""
Production-Grade Realistic Execution Simulation Engine (AURA v5)
================================================================
Simulates MT5 Live Execution Frictions:
1. Bid/Ask Spread (Normal, High, Extreme, News/Rollover Widening)
2. Commission & Swap Fees
3. Slippage Model (Ideal, Normal, Stress 1x, Stress 2x, Stress 3x)
4. Latency Delay (Signal -> Decision -> Execution at Next Open + Slippage)
5. Gaps & Jump Discontinuities (Price gap past SL fills at Gap Open)
6. Same-Bar TP & SL Collision Resolution (Strict Conservative Rule -> LOSS)
7. Rejected Orders / Execution Failures
"""

from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.logger import logger


@dataclass
class ExecutionProfile:
    name: str
    base_spread_pips: float
    commission_per_lot_usd: float
    swap_usd_per_night: float
    slippage_mean_pips: float
    slippage_std_pips: float
    latency_ms: int
    rejection_rate: float
    spread_widening_multiplier: float  # News / Rollover multiplier


# Predefined Production & Stress Profiles
EXECUTION_PROFILES = {
    "ideal": ExecutionProfile(
        name="Ideal Backtest",
        base_spread_pips=0.0,
        commission_per_lot_usd=0.0,
        swap_usd_per_night=0.0,
        slippage_mean_pips=0.0,
        slippage_std_pips=0.0,
        latency_ms=0,
        rejection_rate=0.0,
        spread_widening_multiplier=1.0
    ),
    "normal": ExecutionProfile(
        name="Realistic Live (Normal)",
        base_spread_pips=1.2,
        commission_per_lot_usd=7.0,
        swap_usd_per_night=1.5,
        slippage_mean_pips=0.3,
        slippage_std_pips=0.2,
        latency_ms=80,
        rejection_rate=0.005,
        spread_widening_multiplier=1.2
    ),
    "stress_1x": ExecutionProfile(
        name="Stress 1x (Volatile)",
        base_spread_pips=2.0,
        commission_per_lot_usd=7.0,
        swap_usd_per_night=2.0,
        slippage_mean_pips=0.8,
        slippage_std_pips=0.5,
        latency_ms=180,
        rejection_rate=0.02,
        spread_widening_multiplier=1.8
    ),
    "stress_2x": ExecutionProfile(
        name="Stress 2x (News Event)",
        base_spread_pips=3.5,
        commission_per_lot_usd=7.0,
        swap_usd_per_night=3.0,
        slippage_mean_pips=1.8,
        slippage_std_pips=1.2,
        latency_ms=350,
        rejection_rate=0.05,
        spread_widening_multiplier=2.5
    ),
    "stress_3x": ExecutionProfile(
        name="Stress 3x (Extreme Market)",
        base_spread_pips=6.0,
        commission_per_lot_usd=7.0,
        swap_usd_per_night=5.0,
        slippage_mean_pips=3.5,
        slippage_std_pips=2.5,
        latency_ms=750,
        rejection_rate=0.10,
        spread_widening_multiplier=4.0
    )
}


class RealisticExecutionEngine:
    """
    Simulates production order execution with full market friction & conservative collision rules.
    """

    def __init__(self, profile: ExecutionProfile):
        self.profile = profile

    @staticmethod
    def pips_to_price(pips: float, symbol: str) -> float:
        sym = symbol.upper()
        if "GOLD" in sym or "XAU" in sym:
            return pips * 0.1
        elif "BTC" in sym:
            return pips * 1.0
        elif "JPY" in sym:
            return pips * 0.01
        return pips * 0.0001

    def simulate_order_execution(
        self,
        signal_dict: Dict[str, Any],
        next_bar_open: float,
        next_bar_time: datetime
    ) -> Optional[Dict[str, Any]]:
        """
        Calculates realistic entry price including spread, slippage, and rejection risk.
        """
        # 1. Order Rejection Check
        if np.random.rand() < self.profile.rejection_rate:
            logger.debug(f"Order REJECTED by broker simulator ({self.profile.name})")
            return None

        symbol = signal_dict.get("symbol", "EURUSD")
        direction = signal_dict.get("direction", "BUY")

        # 2. Spread Widening Check (Killzone / High Volatility hours)
        killzone_hour = signal_dict.get("killzone_hour", 14)
        spread_mult = (
            self.profile.spread_widening_multiplier
            if killzone_hour in [0, 21, 22, 23] # Rollover / Thin Liquidity
            else 1.0
        )
        effective_spread_pips = self.profile.base_spread_pips * spread_mult
        spread_price = self.pips_to_price(effective_spread_pips, symbol)

        # 3. Latency & Slippage Simulation (Random Normal)
        slippage_pips = max(
            0.0,
            np.random.normal(self.profile.slippage_mean_pips, self.profile.slippage_std_pips)
        )
        slippage_price = self.pips_to_price(slippage_pips, symbol)

        # 4. Entry Price Calculation
        # BUY fills at Ask = Open + Half Spread + Slippage
        # SELL fills at Bid = Open - Half Spread - Slippage
        if direction == "BUY":
            execution_price = next_bar_open + (spread_price / 2.0) + slippage_price
        else:
            execution_price = next_bar_open - (spread_price / 2.0) - slippage_price

        # Timestamps tracking
        signal_time = pd.to_datetime(signal_dict.get("time", next_bar_time), utc=True)
        decision_time = signal_time + timedelta(milliseconds=20)
        execution_time = pd.to_datetime(next_bar_time, utc=True) + timedelta(milliseconds=self.profile.latency_ms)

        return {
            "symbol": symbol,
            "direction": direction,
            "signal_time": signal_time,
            "decision_time": decision_time,
            "execution_time": execution_time,
            "execution_price": execution_price,
            "spread_pips": effective_spread_pips,
            "slippage_pips": slippage_pips,
            "latency_ms": self.profile.latency_ms,
            "commission_usd": self.profile.commission_per_lot_usd,
            "swap_usd": self.profile.swap_usd_per_night
        }

    def simulate_trade_lifespan(
        self,
        execution_info: Dict[str, Any],
        m15_df: pd.DataFrame,
        entry_bar_idx: int,
        target_sl: float,
        target_tp: float,
        risk_usd: float = 200.0,
        rr_ratio: float = 1.8
    ) -> Dict[str, Any]:
        """
        Simulates candle-by-candle price action with:
        - Gap detection past SL/TP
        - Strict Conservative Same-Bar Collision Resolution (TP & SL in same candle -> ALWAYS LOSS)
        """
        direction = execution_info["direction"]
        entry_price = execution_info["execution_price"]
        symbol = execution_info["symbol"]
        
        # Calculate fees
        commission = execution_info["commission_usd"]
        swap = execution_info["swap_usd"]

        # Recalculate SL & TP distances relative to actual execution price
        if direction == "BUY":
            sl_dist = abs(entry_price - target_sl)
            tp_dist = sl_dist * rr_ratio
            sl_price = entry_price - sl_dist
            tp_price = entry_price + tp_dist
        else:
            sl_dist = abs(target_sl - entry_price)
            tp_dist = sl_dist * rr_ratio
            sl_price = entry_price + sl_dist
            tp_price = entry_price - tp_dist

        outcome = "OPEN"
        exit_price = entry_price
        exit_bar = entry_bar_idx
        hold_bars = 0

        for i in range(entry_bar_idx + 1, min(entry_bar_idx + 200, len(m15_df))):
            bar = m15_df.iloc[i]
            b_open = float(bar["open"])
            b_high = float(bar["high"])
            b_low = float(bar["low"])
            hold_bars += 1

            if direction == "BUY":
                sl_hit = b_low <= sl_price
                tp_hit = b_high >= tp_price

                # STRICT CONSERVATIVE RULE: Same-Bar Collision -> ALWAYS LOSS
                if sl_hit and tp_hit:
                    outcome = "LOSS"
                    exit_price = min(sl_price, b_open) # Gap handling
                    exit_bar = i
                    break
                elif sl_hit:
                    outcome = "LOSS"
                    exit_price = min(sl_price, b_open) if b_open < sl_price else sl_price
                    exit_bar = i
                    break
                elif tp_hit:
                    outcome = "WIN"
                    exit_price = max(tp_price, b_open) if b_open > tp_price else tp_price
                    exit_bar = i
                    break
            else: # SELL
                sl_hit = b_high >= sl_price
                tp_hit = b_low <= tp_price

                # STRICT CONSERVATIVE RULE: Same-Bar Collision -> ALWAYS LOSS
                if sl_hit and tp_hit:
                    outcome = "LOSS"
                    exit_price = max(sl_price, b_open) # Gap handling
                    exit_bar = i
                    break
                elif sl_hit:
                    outcome = "LOSS"
                    exit_price = max(sl_price, b_open) if b_open > sl_price else sl_price
                    exit_bar = i
                    break
                elif tp_hit:
                    outcome = "WIN"
                    exit_price = min(tp_price, b_open) if b_open < tp_price else tp_price
                    exit_bar = i
                    break

        # Calculate PnL in USD including frictions
        if outcome == "WIN":
            raw_pnl = risk_usd * rr_ratio
        elif outcome == "LOSS":
            # Account for gap slippage past SL
            gap_pips = abs(exit_price - sl_price) / self.pips_to_price(1.0, symbol)
            extra_gap_loss = (gap_pips / 10.0) * (risk_usd / 10.0)
            raw_pnl = -(risk_usd + extra_gap_loss)
        else:
            raw_pnl = 0.0

        net_pnl = raw_pnl - commission - swap

        return {
            "outcome": outcome if outcome != "OPEN" else "LOSS",
            "entry_price": round(entry_price, 5),
            "exit_price": round(exit_price, 5),
            "sl_price": round(sl_price, 5),
            "tp_price": round(tp_price, 5),
            "raw_pnl": round(raw_pnl, 2),
            "net_pnl": round(net_pnl, 2),
            "hold_bars": hold_bars,
            "profile_name": self.profile.name
        }
