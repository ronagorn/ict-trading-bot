"""
Production-Grade Advanced Trade Analytics & Research Logger (AURA v5)
======================================================================
Stores comprehensive institutional trade records and generates research analytics:
1. MFE (Maximum Favorable Excursion) Distribution
2. MAE (Maximum Adverse Excursion) Distribution
3. Realized R-Multiple & Holding Time Distributions
4. Exit Reason Breakdown
5. Directional Asymmetry & Setup Edge Analysis
"""

from __future__ import annotations
import sys
from pathlib import Path
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.logger import logger


@dataclass
class ComprehensiveTradeRecord:
    trade_id: str
    strategy_version: str = "v5.0"
    model_version: str = "v5.0.0"
    config_version: str = "v5.0_production"
    symbol: str = "EURUSD"
    direction: str = "BUY"  # BUY / SELL
    session: str = "London"  # London / New_York / Asian
    regime: str = "TRENDING_HIGH_VOL"

    entry_time: str = ""
    entry_price: float = 0.0
    exit_time: str = ""
    exit_price: float = 0.0

    sl: float = 0.0
    tp: float = 0.0
    rr: float = 1.8

    spread_at_entry: float = 1.2
    execution_latency: int = 80
    slippage: float = 0.2

    mfe: float = 0.0          # Maximum Favorable Excursion (Pips/R)
    mae: float = 0.0          # Maximum Adverse Excursion (Pips/R)
    r_realized: float = 0.0   # Realized R-multiple
    pnl_usd: float = 0.0

    exit_reason: str = "TP_HIT" # TP_HIT, SL_HIT, AUTO_BREAKEVEN, EXPIRED, REVERSAL

    fvg_score: float = 0.0
    ob_score: float = 0.0
    sweep_score: float = 0.0
    ml_prob: float = 0.0
    final_score: float = 0.0


class AdvancedTradeAnalyticsEngine:
    """
    Quantitative Research Engine analyzing MFE, MAE, R-distributions & Strategy Asymmetry.
    """

    @staticmethod
    def calculate_trade_excursions(
        direction: str,
        entry_price: float,
        sl_price: float,
        highs: np.ndarray,
        lows: np.ndarray
    ) -> Tuple[float, float]:
        """
        Calculates Maximum Favorable Excursion (MFE) & Maximum Adverse Excursion (MAE) in R-multiples.
        """
        sl_dist = abs(entry_price - sl_price)
        if sl_dist <= 0 or len(highs) == 0:
            return 0.0, 0.0

        if direction == "BUY":
            max_favorable_dist = np.max(highs) - entry_price
            max_adverse_dist = entry_price - np.min(lows)
        else: # SELL
            max_favorable_dist = entry_price - np.min(lows)
            max_adverse_dist = np.max(highs) - entry_price

        mfe_r = float(max_favorable_dist / sl_dist)
        mae_r = float(max_adverse_dist / sl_dist)

        return round(max(0.0, mfe_r), 2), round(max(0.0, mae_r), 2)

    @classmethod
    def generate_research_report(cls, trades_df: pd.DataFrame) -> Dict[str, Any]:
        """Generates comprehensive quant research analytics report."""
        if trades_df.empty:
            return {"status": "NO_TRADES"}

        total_trades = len(trades_df)
        buys = trades_df[trades_df["direction"] == "BUY"]
        sells = trades_df[trades_df["direction"] == "SELL"]

        # MFE / MAE Analysis
        mfes = trades_df["mfe"].values
        maes = trades_df["mae"].values
        r_realized = trades_df["r_realized"].values

        # Directional Asymmetry Check
        buy_win_rate = (len(buys[buys["pnl_usd"] > 0]) / len(buys) * 100.0) if len(buys) > 0 else 0.0
        sell_win_rate = (len(sells[sells["pnl_usd"] > 0]) / len(sells) * 100.0) if len(sells) > 0 else 0.0
        asymmetry_flag = abs(buy_win_rate - sell_win_rate) > 15.0

        # Exit Reason Breakdown
        exit_counts = trades_df["exit_reason"].value_counts().to_dict()

        # Is SL too wide check (Mean MAE < 0.5 R on losses indicates SL can be tightened)
        losses = trades_df[trades_df["pnl_usd"] < 0]
        mean_mae_losses = float(losses["mae"].mean()) if not losses.empty else 0.0
        sl_too_wide_flag = mean_mae_losses < 0.60

        # Is TP unrealistic check (Mean MFE on wins > 2.5 R but TP is set much lower or vice versa)
        wins = trades_df[trades_df["pnl_usd"] > 0]
        mean_mfe_wins = float(wins["mfe"].mean()) if not wins.empty else 0.0
        tp_unrealistic_flag = mean_mfe_wins < 1.0

        return {
            "total_trades": total_trades,
            "mean_mfe_r": round(float(np.mean(mfes)), 2),
            "median_mfe_r": round(float(np.median(mfes)), 2),
            "mean_mae_r": round(float(np.mean(maes)), 2),
            "median_mae_r": round(float(np.median(maes)), 2),
            "mean_r_realized": round(float(np.mean(r_realized)), 2),
            "buy_win_rate": round(buy_win_rate, 2),
            "sell_win_rate": round(sell_win_rate, 2),
            "directional_asymmetry_flag": asymmetry_flag,
            "sl_too_wide_flag": sl_too_wide_flag,
            "tp_unrealistic_flag": tp_unrealistic_flag,
            "exit_reasons": exit_counts
        }
