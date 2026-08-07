"""
Unit Tests for Institutional Setup Quality Scoring Engine (AURA v5)
====================================================================
Tests:
1. Score Bounds (0.0 to 100.0)
2. FVG Quality Scoring Logic
3. Order Block Quality Scoring Logic
4. Liquidity Sweep Quality Scoring Logic
5. Composite Quality Score & Weight Adjustability
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.setup_quality_scorer import (
    InstitutionalSetupQualityScorer,
    QualityScoringWeights
)


class TestInstitutionalSetupQualityScorer(unittest.TestCase):

    def setUp(self):
        self.scorer = InstitutionalSetupQualityScorer()

    def test_fvg_quality_score_bounds(self):
        """1. Verify FVG Quality Score strictly stays within 0.0 - 100.0."""
        score_high = self.scorer.score_fvg(
            fvg_size_pips=15.0, atr_val_pips=10.0,
            volume_spike_ratio=2.5, displacement_ratio=0.85,
            is_htf_aligned=True, is_fresh=True
        )
        self.assertGreaterEqual(score_high, 70.0)
        self.assertLessEqual(score_high, 100.0)

        score_low = self.scorer.score_fvg(
            fvg_size_pips=1.0, atr_val_pips=15.0,
            volume_spike_ratio=0.8, displacement_ratio=0.2,
            is_htf_aligned=False, is_fresh=False
        )
        self.assertLess(score_low, 50.0)
        self.assertGreaterEqual(score_low, 0.0)

    def test_ob_quality_score_choch_vs_bos(self):
        """2. Verify CHOCH structure yields higher score than BOS."""
        score_choch = self.scorer.score_order_block(
            structure_type="CHOCH", volume_spike_ratio=2.0,
            displacement_ratio=0.8, has_fvg_confluence=True, is_htf_aligned=True
        )
        score_bos = self.scorer.score_order_block(
            structure_type="BOS", volume_spike_ratio=2.0,
            displacement_ratio=0.8, has_fvg_confluence=True, is_htf_aligned=True
        )
        self.assertGreater(score_choch, score_bos)

    def test_liquidity_sweep_hierarchy(self):
        """3. Verify PDH/PDL sweeps yield higher score than minor swing sweeps."""
        score_pdl = self.scorer.score_liquidity_sweep(
            sweep_type="PDL", rejection_close_pct=0.9,
            in_killzone=True, is_htf_aligned=True
        )
        score_swing = self.scorer.score_liquidity_sweep(
            sweep_type="SWING", rejection_close_pct=0.9,
            in_killzone=True, is_htf_aligned=True
        )
        self.assertGreater(score_pdl, score_swing)

    def test_composite_setup_score(self):
        """4. Verify composite setup score averages component setup scores."""
        composite = self.scorer.calculate_overall_setup_score(
            fvg_score=80.0, ob_score=90.0, sweep_score=70.0
        )
        self.assertEqual(composite, 80.0)


if __name__ == "__main__":
    unittest.main()
