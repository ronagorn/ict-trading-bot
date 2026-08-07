"""
Production-Grade Institutional Setup Quality Scoring Engine (AURA v5)
=====================================================================
Scores ICT setups on a transparent, configurable 0-100 scale:
1. FVG Quality Score (Size/ATR, Displacement, Volume, Freshness, HTF Alignment)
2. Order Block Quality Score (BOS/CHOCH, Displacement, Volume, FVG Confluence)
3. Liquidity Sweep Quality Score (PDH/PDL, Session H/L, EQH/EQL, Sweep Depth & Rejection)
"""

from __future__ import annotations
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.logger import logger


@dataclass
class QualityScoringWeights:
    """Configurable weights for setup quality scoring (must sum to 1.0 per setup type)."""
    # FVG Weights
    fvg_size_atr_weight: float = 0.25
    fvg_volume_weight: float = 0.25
    fvg_displacement_weight: float = 0.20
    fvg_htf_align_weight: float = 0.20
    fvg_freshness_weight: float = 0.10

    # OB Weights
    ob_structure_weight: float = 0.30
    ob_volume_weight: float = 0.25
    ob_displacement_weight: float = 0.20
    ob_fvg_confluence_weight: float = 0.15
    ob_htf_align_weight: float = 0.10

    # Liquidity Sweep Weights
    sweep_type_weight: float = 0.35
    sweep_rejection_weight: float = 0.30
    sweep_session_weight: float = 0.20
    sweep_htf_align_weight: float = 0.15


class InstitutionalSetupQualityScorer:
    """
    Non-destructive Quality Scoring Layer for FVG, OB, and Liquidity Sweep setups.
    """

    def __init__(self, weights: Optional[QualityScoringWeights] = None):
        self.w = weights or QualityScoringWeights()

    def score_fvg(
        self,
        fvg_size_pips: float,
        atr_val_pips: float,
        volume_spike_ratio: float,
        displacement_ratio: float,
        is_htf_aligned: bool,
        is_fresh: bool = True
    ) -> float:
        """Calculates FVG Quality Score (0 - 100)."""
        # 1. Size / ATR Score (Ideal size between 0.5x and 2.5x ATR)
        if atr_val_pips > 0:
            size_ratio = fvg_size_pips / atr_val_pips
            size_score = min(100.0, max(0.0, (1.0 - abs(size_ratio - 1.5) / 2.0) * 100.0))
        else:
            size_score = 50.0

        # 2. Volume Imbalance Score (1.0x -> 50, 2.0x+ -> 100)
        vol_score = min(100.0, max(0.0, (volume_spike_ratio - 1.0) / 1.5 * 100.0))

        # 3. Displacement Score (Body to candle range ratio)
        disp_score = min(100.0, max(0.0, displacement_ratio * 100.0))

        # 4. HTF Alignment Score (100 if aligned, 20 if counter)
        htf_score = 100.0 if is_htf_aligned else 20.0

        # 5. Freshness Score (100 if unmitigated, 30 if partially mitigated)
        fresh_score = 100.0 if is_fresh else 30.0

        total_score = (
            size_score * self.w.fvg_size_atr_weight +
            vol_score * self.w.fvg_volume_weight +
            disp_score * self.w.fvg_displacement_weight +
            htf_score * self.w.fvg_htf_align_weight +
            fresh_score * self.w.fvg_freshness_weight
        )
        return round(float(np.clip(total_score, 0.0, 100.0)), 2)

    def score_order_block(
        self,
        structure_type: str, # "BOS" or "CHOCH"
        volume_spike_ratio: float,
        displacement_ratio: float,
        has_fvg_confluence: bool,
        is_htf_aligned: bool
    ) -> float:
        """Calculates Order Block Quality Score (0 - 100)."""
        # 1. Structure Break Score (CHOCH = 100, BOS = 75)
        struct_score = 100.0 if str(structure_type).upper() == "CHOCH" else 75.0

        # 2. Volume Spike Score
        vol_score = min(100.0, max(0.0, (volume_spike_ratio - 1.0) / 1.5 * 100.0))

        # 3. Displacement Score
        disp_score = min(100.0, max(0.0, displacement_ratio * 100.0))

        # 4. FVG Confluence Score (Order Block + FVG imbalance zone)
        confluence_score = 100.0 if has_fvg_confluence else 30.0

        # 5. HTF Alignment Score
        htf_score = 100.0 if is_htf_aligned else 20.0

        total_score = (
            struct_score * self.w.ob_structure_weight +
            vol_score * self.w.ob_volume_weight +
            disp_score * self.w.ob_displacement_weight +
            confluence_score * self.w.ob_fvg_confluence_weight +
            htf_score * self.w.ob_htf_align_weight
        )
        return round(float(np.clip(total_score, 0.0, 100.0)), 2)

    def score_liquidity_sweep(
        self,
        sweep_type: str, # "PDH_PDL", "SESSION_HL", "EQH_EQL", "SWING"
        rejection_close_pct: float, # Where price closed relative to sweep range (0-1)
        in_killzone: bool,
        is_htf_aligned: bool
    ) -> float:
        """Calculates Liquidity Sweep Quality Score (0 - 100)."""
        # 1. Sweep Hierarchy Score
        sType = str(sweep_type).upper()
        if "PDH" in sType or "PDL" in sType:
            type_score = 100.0  # Previous Day High/Low = Highest Tier
        elif "SESSION" in sType:
            type_score = 85.0   # London/NY Session High/Low
        elif "EQH" in sType or "EQL" in sType:
            type_score = 75.0   # Equal Highs/Lows
        else:
            type_score = 60.0   # Minor Swing Liquidity

        # 2. Rejection Response Score (Strong pinbar close)
        rejection_score = min(100.0, max(0.0, rejection_close_pct * 100.0))

        # 3. Session Killzone Score
        session_score = 100.0 if in_killzone else 30.0

        # 4. HTF Alignment Score
        htf_score = 100.0 if is_htf_aligned else 20.0

        total_score = (
            type_score * self.w.sweep_type_weight +
            rejection_score * self.w.sweep_rejection_weight +
            session_score * self.w.sweep_session_weight +
            htf_score * self.w.sweep_htf_align_weight
        )
        return round(float(np.clip(total_score, 0.0, 100.0)), 2)

    def calculate_overall_setup_score(
        self,
        fvg_score: float,
        ob_score: Optional[float] = None,
        sweep_score: Optional[float] = None
    ) -> float:
        """Combines component setup scores into a final Composite Quality Score (0 - 100)."""
        scores = [fvg_score]
        if ob_score is not None:
            scores.append(ob_score)
        if sweep_score is not None:
            scores.append(sweep_score)

        return round(float(np.mean(scores)), 2)
