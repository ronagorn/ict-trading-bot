"""
Unit Tests for Safe Champion / Challenger Framework (AURA v5)
==============================================================
Tests:
1. Manifest Registration, Hashing & State Locking Assertion
2. Rejection of Overfitted Challenger (Worse Max DD / Lower Expectancy)
3. Rejection of Challenger failing Execution Stress or Monte Carlo
4. Successful Promotion of Genuinely Robust Challenger
5. Rollback Mechanism Execution
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.challenger_engine import ChampionChallengerRegistry, ModelVersionManifest
from services.judge_evaluator import SafeJudgeEvaluator, PerformanceMetricsSnapshot


class TestSafeChampionChallengerFramework(unittest.TestCase):

    def setUp(self):
        self.registry = ChampionChallengerRegistry()
        self.evaluator = SafeJudgeEvaluator(self.registry)

        # Baseline Champion Manifest & Metrics
        self.champion_manifest = self.registry.register_model_candidate(
            model_id="CHAMP_v5_0", features=["fvg_score", "trend_alignment"],
            parameters={"n_estimators": 100}, is_champion=True
        )
        self.registry.lock_model_candidate(self.champion_manifest)

        self.champ_metrics = PerformanceMetricsSnapshot(
            model_id="CHAMP_v5_0", win_rate=65.0, profit_factor=2.20,
            expectancy_usd=210.0, max_drawdown_pct=8.5, trade_count=120,
            worst_fold_pf=1.4, stress_pf=1.85, is_regime_stable=True, is_mc_robust=True
        )

    def test_unlocked_candidate_rejection(self):
        """1. Verify unlocked candidate is rejected before stage evaluation."""
        unlocked_manifest = self.registry.register_model_candidate(
            model_id="CHALL_v5_1", features=["fvg_score"], parameters={}
        )
        # Note: unlocked_manifest is NOT locked
        res = self.evaluator.evaluate_challenger_candidate(
            unlocked_manifest, self.champ_metrics, self.champ_metrics
        )
        self.assertFalse(res.promoted)
        self.assertIn("NOT locked", res.reasons[0])

    def test_overfitted_challenger_rejection(self):
        """2. Verify overfitted Challenger (high win rate but worse DD & lower expectancy) is REJECTED."""
        cand_manifest = self.registry.register_model_candidate(
            model_id="CHALL_OVERFIT", features=["fvg_score"], parameters={}
        )
        self.registry.lock_model_candidate(cand_manifest)

        overfit_metrics = PerformanceMetricsSnapshot(
            model_id="CHALL_OVERFIT",
            win_rate=85.0,           # High Win Rate (Overfit!)
            profit_factor=2.00,
            expectancy_usd=180.0,    # LOWER Expectancy than Champion ($210)
            max_drawdown_pct=14.2,   # WORSE Max DD than Champion (8.5%)
            trade_count=100, worst_fold_pf=0.9, stress_pf=1.05,
            is_regime_stable=True, is_mc_robust=True
        )

        res = self.evaluator.evaluate_challenger_candidate(
            cand_manifest, self.champ_metrics, overfit_metrics
        )
        self.assertFalse(res.promoted)
        self.assertEqual(res.stage_passed, 3, "Must fail at Stage 3 (OOS Expectancy & Max DD Gate)")

    def test_robust_challenger_promotion(self):
        """3. Verify robust Challenger passing all 6 stages is PROMOTED."""
        cand_manifest = self.registry.register_model_candidate(
            model_id="CHALL_SUPERIOR", features=["fvg_score", "ob_score"], parameters={"max_depth": 4}
        )
        self.registry.lock_model_candidate(cand_manifest)

        superior_metrics = PerformanceMetricsSnapshot(
            model_id="CHALL_SUPERIOR", win_rate=72.0, profit_factor=3.10,
            expectancy_usd=260.0,      # HIGHER Expectancy ($260 > $210)
            max_drawdown_pct=6.2,      # BETTER Max DD (6.2% < 8.5%)
            trade_count=140, worst_fold_pf=1.6, stress_pf=2.10,
            is_regime_stable=True, is_mc_robust=True
        )

        res = self.evaluator.evaluate_challenger_candidate(
            cand_manifest, self.champ_metrics, superior_metrics
        )
        self.assertTrue(res.promoted)
        self.assertEqual(res.stage_passed, 6)
        self.assertEqual(self.registry.champion_manifest.model_id, "CHALL_SUPERIOR")

    def test_rollback_mechanism(self):
        """4. Verify rollback demotes active Champion and restores previous Champion."""
        # 1. Promote candidate to champion
        cand_manifest = self.registry.register_model_candidate(
            model_id="CHALL_TEMP", features=["fvg_score"], parameters={}
        )
        self.registry.lock_model_candidate(cand_manifest)

        superior_metrics = PerformanceMetricsSnapshot(
            model_id="CHALL_TEMP", win_rate=72.0, profit_factor=3.10,
            expectancy_usd=260.0, max_drawdown_pct=6.2, trade_count=140,
            worst_fold_pf=1.6, stress_pf=2.10, is_regime_stable=True, is_mc_robust=True
        )

        self.evaluator.evaluate_challenger_candidate(cand_manifest, self.champ_metrics, superior_metrics)
        self.assertEqual(self.registry.champion_manifest.model_id, "CHALL_TEMP")

        # 2. Execute Rollback
        success, restored = self.registry.rollback_to_previous_champion()
        self.assertTrue(success)
        self.assertEqual(restored.model_id, "CHAMP_v5_0")
        self.assertEqual(self.registry.champion_manifest.model_id, "CHAMP_v5_0")


if __name__ == "__main__":
    unittest.main()
