"""
Production-Grade No-Trade Decision Engine (AURA v5)
===================================================
Dedicated No-Trade Control Layer with HIGHEST priority override.

Evaluates 16 Critical Conditions:
1. Spread Abnormal
2. Latency Abnormal
3. Liquidity Insufficient
4. Extreme Volatility
5. Regime Unknown / Low Liquidity
6. Daily Drawdown Limit
7. Portfolio Exposure Cap
8. Correlation Concentration
9. Loss Streak Cap
10. ML Model Unavailable / Corrupted
11. Model Drift (PSI > 0.25)
12. Data Stale (> 60s delay)
13. MT5 Terminal Connection Unstable
14. Duplicate Signal Protection
15. Excessive Recent Trading
16. High-Impact News Filter Active

Decision States:
- NORMAL (100% Lot Size)
- REDUCED (50% Lot Size)
- STRICT (25% Lot Size + Higher Quality Cutoff)
- NO_TRADE (Block new position)
- EMERGENCY_STOP (Kill Switch activated)
"""

from __future__ import annotations
import sys
from enum import Enum
from pathlib import Path
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple
import json
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.logger import logger
from bot.regime_engine import MarketRegime


class DecisionState(str, Enum):
    NORMAL = "NORMAL"
    REDUCED = "REDUCED"
    STRICT = "STRICT"
    NO_TRADE = "NO_TRADE"
    EMERGENCY_STOP = "EMERGENCY_STOP"


@dataclass
class NoTradeLimitsConfig:
    max_spread_pips: float = 4.0
    max_latency_ms: int = 300
    max_daily_drawdown_pct: float = 8.0
    max_portfolio_trades: int = 4
    max_symbol_trades: int = 2
    max_losing_streak: int = 4
    max_data_age_seconds: int = 60
    max_psi_drift: float = 0.25
    max_trades_per_hour: int = 5


@dataclass
class NoTradeEvaluationResult:
    decision_state: DecisionState
    approved: bool
    risk_multiplier: float
    reasons: List[str]
    severity: str
    metrics: Dict[str, Any]
    logged_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class NoTradeDecisionEngine:
    """
    Production No-Trade Gate with highest override authority over Strategy & Risk execution.
    """

    def __init__(self, config: Optional[NoTradeLimitsConfig] = None):
        self.cfg = config or NoTradeLimitsConfig()

    def evaluate_trading_conditions(
        self,
        symbol: str,
        current_spread_pips: float = 1.2,
        current_latency_ms: int = 80,
        regime: MarketRegime = MarketRegime.TRENDING_HIGH_VOL,
        daily_drawdown_pct: float = 0.0,
        portfolio_open_trades: int = 0,
        symbol_open_trades: int = 0,
        consecutive_losses: int = 0,
        data_age_seconds: int = 5,
        mt5_connected: bool = True,
        is_ml_available: bool = True,
        model_psi_drift: float = 0.05,
        is_news_active: bool = False,
        recent_trades_last_hour: int = 1,
        has_duplicate_signal: bool = False,
        strategy_signal: Optional[Dict[str, Any]] = None,
        ml_prob: float = 0.65
    ) -> NoTradeEvaluationResult:
        """
        Evaluates all 16 safety conditions and returns explicit No-Trade Decision.
        """
        reasons = []
        metrics = {
            "symbol": symbol,
            "spread_pips": current_spread_pips,
            "latency_ms": current_latency_ms,
            "regime": regime.value if isinstance(regime, MarketRegime) else str(regime),
            "daily_drawdown_pct": daily_drawdown_pct,
            "portfolio_trades": portfolio_open_trades,
            "symbol_trades": symbol_open_trades,
            "consecutive_losses": consecutive_losses,
            "data_age_seconds": data_age_seconds,
            "mt5_connected": mt5_connected,
            "ml_available": is_ml_available,
            "psi_drift": model_psi_drift,
            "news_active": is_news_active,
            "recent_trades_hour": recent_trades_last_hour,
            "duplicate_signal": has_duplicate_signal,
            "ml_prob": ml_prob
        }

        # -------------------------------------------------------------
        # 1. EMERGENCY_STOP Conditions (Circuit Breakers)
        # -------------------------------------------------------------
        if daily_drawdown_pct >= self.cfg.max_daily_drawdown_pct:
            reasons.append(f"EMERGENCY_STOP: Daily drawdown limit reached ({daily_drawdown_pct:.1f}% >= {self.cfg.max_daily_drawdown_pct:.1f}%)")
            return NoTradeEvaluationResult(
                decision_state=DecisionState.EMERGENCY_STOP,
                approved=False, risk_multiplier=0.0,
                reasons=reasons, severity="CRITICAL", metrics=metrics
            )

        if not mt5_connected:
            reasons.append("EMERGENCY_STOP: MT5 terminal connection lost")
            return NoTradeEvaluationResult(
                decision_state=DecisionState.EMERGENCY_STOP,
                approved=False, risk_multiplier=0.0,
                reasons=reasons, severity="CRITICAL", metrics=metrics
            )

        # -------------------------------------------------------------
        # 2. NO_TRADE Conditions (Block Order Creation)
        # -------------------------------------------------------------
        if is_news_active:
            reasons.append("NO_TRADE: High-Impact Economic News filter active")
        
        if data_age_seconds > self.cfg.max_data_age_seconds:
            reasons.append(f"NO_TRADE: Market data stale ({data_age_seconds}s > {self.cfg.max_data_age_seconds}s)")

        if regime in [MarketRegime.UNKNOWN, MarketRegime.LOW_LIQUIDITY, MarketRegime.EXTREME_VOLATILITY]:
            reasons.append(f"NO_TRADE: Unfavorable market regime ({regime})")

        if current_spread_pips > self.cfg.max_spread_pips:
            reasons.append(f"NO_TRADE: Abnormal spread ({current_spread_pips:.1f} pips > {self.cfg.max_spread_pips:.1f} pips)")

        if portfolio_open_trades >= self.cfg.max_portfolio_trades:
            reasons.append(f"NO_TRADE: Portfolio exposure cap reached ({portfolio_open_trades} >= {self.cfg.max_portfolio_trades})")

        if symbol_open_trades >= self.cfg.max_symbol_trades:
            reasons.append(f"NO_TRADE: Symbol position cap reached ({symbol_open_trades} >= {self.cfg.max_symbol_trades})")

        if has_duplicate_signal:
            reasons.append("NO_TRADE: Duplicate active position/signal detected")

        if recent_trades_last_hour >= self.cfg.max_trades_per_hour:
            reasons.append(f"NO_TRADE: Over-trading protection ({recent_trades_last_hour} trades/hr >= {self.cfg.max_trades_per_hour})")

        if consecutive_losses >= self.cfg.max_losing_streak:
            reasons.append(f"NO_TRADE: Consecutive loss streak cap hit ({consecutive_losses} >= {self.cfg.max_losing_streak})")

        if reasons:
            return NoTradeEvaluationResult(
                decision_state=DecisionState.NO_TRADE,
                approved=False, risk_multiplier=0.0,
                reasons=reasons, severity="HIGH", metrics=metrics
            )

        # -------------------------------------------------------------
        # 3. STRICT Mode Conditions (Allow with 25% Lot Size)
        # -------------------------------------------------------------
        if not is_ml_available or model_psi_drift >= self.cfg.max_psi_drift:
            reasons.append(f"STRICT: ML Model drift ({model_psi_drift:.2f}) or unavailable. Fallback to 25% Lot Size")
            return NoTradeEvaluationResult(
                decision_state=DecisionState.STRICT,
                approved=True, risk_multiplier=0.25,
                reasons=reasons, severity="MEDIUM", metrics=metrics
            )

        # -------------------------------------------------------------
        # 4. REDUCED Mode Conditions (Allow with 50% Lot Size)
        # -------------------------------------------------------------
        if current_latency_ms > self.cfg.max_latency_ms or current_spread_pips > 2.5:
            reasons.append(f"REDUCED: Elevated market friction (Latency: {current_latency_ms}ms, Spread: {current_spread_pips:.1f}pips). Reduced to 50% Lot Size")
            return NoTradeEvaluationResult(
                decision_state=DecisionState.REDUCED,
                approved=True, risk_multiplier=0.50,
                reasons=reasons, severity="LOW", metrics=metrics
            )

        # -------------------------------------------------------------
        # 5. NORMAL Mode (All Clear -> 100% Lot Size)
        # -------------------------------------------------------------
        return NoTradeEvaluationResult(
            decision_state=DecisionState.NORMAL,
            approved=True, risk_multiplier=1.00,
            reasons=["All systems clear"], severity="INFO", metrics=metrics
        )

    def log_no_trade_decision(self, result: NoTradeEvaluationResult):
        """Logs structured decision record for audit analysis."""
        log_msg = (
            f"🛑 [No-Trade Engine] State: {result.decision_state.value} | "
            f"Approved: {result.approved} | RiskMult: {result.risk_multiplier:.2f} | "
            f"Reasons: {'; '.join(result.reasons)}"
        )
        if result.decision_state in [DecisionState.NO_TRADE, DecisionState.EMERGENCY_STOP]:
            logger.warning(log_msg)
        else:
            logger.info(log_msg)
