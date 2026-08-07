"""
Production-Grade Market Regime Detection Engine (AURA v5)
=========================================================
Decoupled Market Regime Classifier that isolates market conditions into:
1. TRENDING_HIGH_VOL
2. TRENDING_LOW_VOL
3. RANGING_HIGH_VOL
4. RANGING_LOW_VOL
5. EXTREME_VOLATILITY
6. LOW_LIQUIDITY
7. UNKNOWN (Triggers NO TRADE gate)

Calculates objective features:
- ATR Percentile (Volatility Level)
- Trend Strength (Directional Bias & EMA Slope)
- Range Expansion / Compression Ratio
- Session & Spread Dynamics
"""

from __future__ import annotations
import sys
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.logger import logger


class MarketRegime(str, Enum):
    TRENDING_HIGH_VOL = "TRENDING_HIGH_VOL"
    TRENDING_LOW_VOL = "TRENDING_LOW_VOL"
    RANGING_HIGH_VOL = "RANGING_HIGH_VOL"
    RANGING_LOW_VOL = "RANGING_LOW_VOL"
    EXTREME_VOLATILITY = "EXTREME_VOLATILITY"
    LOW_LIQUIDITY = "LOW_LIQUIDITY"
    UNKNOWN = "UNKNOWN"


class MarketRegimeEngine:
    """
    Decoupled Market Regime Engine. Evaluates market state independently of trade strategy.
    """

    def __init__(
        self,
        atr_period: int = 14,
        atr_lookback: int = 100,
        trend_ema_period: int = 200,
        high_vol_percentile: float = 70.0,
        extreme_vol_percentile: float = 95.0,
        min_required_bars: int = 200
    ):
        self.atr_period = atr_period
        self.atr_lookback = atr_lookback
        self.trend_ema_period = trend_ema_period
        self.high_vol_percentile = high_vol_percentile
        self.extreme_vol_percentile = extreme_vol_percentile
        self.min_required_bars = min_required_bars

    def calculate_regime_features(self, df: pd.DataFrame) -> Dict[str, float]:
        """Calculates data-driven regime indicators."""
        if df is None or len(df) < self.min_required_bars:
            return {}

        df = df.copy()
        high = df["high"]
        low = df["low"]
        close = df["close"]

        # 1. True Range & ATR Calculation
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs()
        ], axis=1).max(axis=1)
        
        atr_series = tr.rolling(self.atr_period).mean().bfill()
        current_atr = float(atr_series.iloc[-1])

        # 2. Dynamic ATR Percentile over Lookback
        recent_atrs = atr_series.tail(self.atr_lookback)
        if len(recent_atrs) > 0 and recent_atrs.max() > recent_atrs.min():
            atr_pct = float((current_atr - recent_atrs.min()) / (recent_atrs.max() - recent_atrs.min()) * 100.0)
        else:
            atr_pct = 50.0

        # 3. Trend Strength & Direction (EMA 200 slope + distance)
        ema200 = close.ewm(span=self.trend_ema_period).mean()
        c_price = float(close.iloc[-1])
        c_ema = float(ema200.iloc[-1])
        
        ema_slope = (c_ema - float(ema200.iloc[-10])) / current_atr if current_atr > 0 else 0.0
        dist_from_ema = abs(c_price - c_ema) / current_atr if current_atr > 0 else 0.0
        
        # Trend strength score (0.0 to 10.0)
        trend_score = min(10.0, (dist_from_ema * 0.6) + (abs(ema_slope) * 1.5))

        # 4. Range Expansion / Compression Ratio
        bar_range = float(high.iloc[-1] - low.iloc[-1])
        mean_range_20 = float((high - low).tail(20).mean())
        range_ratio = (bar_range / mean_range_20) if mean_range_20 > 0 else 1.0

        return {
            "current_atr": round(current_atr, 5),
            "atr_percentile": round(atr_pct, 2),
            "trend_score": round(trend_score, 2),
            "range_ratio": round(range_ratio, 2),
            "dist_from_ema": round(dist_from_ema, 2)
        }

    def detect_regime(
        self,
        df: pd.DataFrame,
        current_hour: Optional[int] = None,
        spread_pips: Optional[float] = None
    ) -> Tuple[MarketRegime, Dict[str, Any]]:
        """
        Classifies current market into a MarketRegime state.
        Returns (MarketRegime, features_dict)
        """
        # Safe Check: Missing or Insufficient Data -> UNKNOWN (No Trade)
        if df is None or len(df) < self.min_required_bars:
            return MarketRegime.UNKNOWN, {"reason": "insufficient_history"}

        try:
            feats = self.calculate_regime_features(df)
            if not feats:
                return MarketRegime.UNKNOWN, {"reason": "feature_calculation_failed"}

            atr_pct = feats["atr_percentile"]
            trend_score = feats["trend_score"]
            range_ratio = feats["range_ratio"]

            # 1. Low Liquidity & Off-Hours Check (Thin trading hours e.g. 21:00-23:00 UTC or spread > 4.0 pips)
            if current_hour is not None and current_hour in [21, 22, 23]:
                return MarketRegime.LOW_LIQUIDITY, feats
            if spread_pips is not None and spread_pips > 5.0:
                return MarketRegime.LOW_LIQUIDITY, feats

            # 2. Extreme Volatility Check (Spike > 95th percentile or range ratio > 3.5)
            if atr_pct >= self.extreme_vol_percentile or range_ratio > 3.5:
                return MarketRegime.EXTREME_VOLATILITY, feats

            # 3. Trending vs Ranging Classification
            is_trending = trend_score >= 2.5
            is_high_vol = atr_pct >= self.high_vol_percentile

            if is_trending and is_high_vol:
                regime = MarketRegime.TRENDING_HIGH_VOL
            elif is_trending and not is_high_vol:
                regime = MarketRegime.TRENDING_LOW_VOL
            elif not is_trending and is_high_vol:
                regime = MarketRegime.RANGING_HIGH_VOL
            else:
                regime = MarketRegime.RANGING_LOW_VOL

            return regime, feats

        except Exception as e:
            logger.error(f"Error in detect_regime: {e}")
            return MarketRegime.UNKNOWN, {"error": str(e)}

    def should_allow_trading(self, regime: MarketRegime) -> bool:
        """Trading Gate: Blocks trading when MarketRegime is UNKNOWN or LOW_LIQUIDITY."""
        if regime in [MarketRegime.UNKNOWN, MarketRegime.LOW_LIQUIDITY]:
            return False
        return True
