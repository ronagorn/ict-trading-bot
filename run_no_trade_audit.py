"""
AURA v5 — No-Trade Decision Engine Audit Runner
===============================================
Evaluates 10 Production Operational & Safety Scenarios
"""

import sys
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import os
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bot.no_trade_engine import NoTradeDecisionEngine, DecisionState
from bot.regime_engine import MarketRegime


def run_no_trade_engine_audit():
    print("==================================================================")
    print("   AURA v5 — NO-TRADE DECISION ENGINE AUDIT & SAFETY MATRIX        ")
    print("==================================================================")

    engine = NoTradeDecisionEngine()

    scenarios = [
        ("Ideal Clear Market", {"symbol": "EURUSD"}),
        ("Elevated Latency (400ms)", {"symbol": "EURUSD", "current_latency_ms": 400}),
        ("Elevated Spread (3.0 pips)", {"symbol": "EURUSD", "current_spread_pips": 3.0}),
        ("ML Model Drift (PSI=0.32)", {"symbol": "EURUSD", "model_psi_drift": 0.32}),
        ("High-Impact News Active", {"symbol": "EURUSD", "is_news_active": True}),
        ("Extreme Volatility Regime", {"symbol": "EURUSD", "regime": MarketRegime.EXTREME_VOLATILITY}),
        ("Stale Market Data (120s)", {"symbol": "EURUSD", "data_age_seconds": 120}),
        ("Losing Streak Cap (4 Losses)", {"symbol": "EURUSD", "consecutive_losses": 4}),
        ("Daily Drawdown Cap (8.5%)", {"symbol": "EURUSD", "daily_drawdown_pct": 8.5}),
        ("MT5 Connection Lost", {"symbol": "EURUSD", "mt5_connected": False}),
    ]

    print("\n=========================================================================================================")
    print("                              📊 NO-TRADE DECISION SAFETY MATRIX                                        ")
    print("=========================================================================================================")
    print(f"{'Operational Scenario':<28} | {'Decision State':<15} | {'Approved':<8} | {'RiskMult':<8} | {'Primary Reason / Gate':<35}")
    print("---------------------------------------------------------------------------------------------------------")

    for title, kwargs in scenarios:
        res = engine.evaluate_trading_conditions(**kwargs)
        reason_str = res.reasons[0] if res.reasons else "All Clear"
        if len(reason_str) > 35:
            reason_str = reason_str[:32] + "..."
        print(f"{title:<28} | {res.decision_state.value:<15} | {str(res.approved):<8} | {res.risk_multiplier:<8.2f} | {reason_str:<35}")

    print("=========================================================================================================")


if __name__ == "__main__":
    run_no_trade_engine_audit()
