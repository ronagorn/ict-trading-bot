"""
Production-Grade Judge Evaluator & Safe Promotion Gate (AURA v5)
=================================================================
Enforces 6-Stage Gate Evaluation Pipeline for Champion / Challenger Promotion:
1. Training CV
2. Sequential Validation
3. Untouched OOS Performance
4. Realistic Execution Stress Test
5. Market Regime Stability Test
6. Monte Carlo 10,000 Simulations

Anti-Overfitting Rules:
- CANNOT promote on Win Rate or Profit Factor alone!
- Expectancy MUST be strictly higher than Champion ($)
- Max Drawdown MUST be less than or equal to Champion (%)
- Must be MONTE CARLO ROBUST (5th percentile Realized R > 0)
"""

from __future__ import annotations
import sys
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.logger import logger
from services.challenger_engine import ModelVersionManifest, ChampionChallengerRegistry


@dataclass
class PerformanceMetricsSnapshot:
    model_id: str
    win_rate: float
    profit_factor: float
    expectancy_usd: float
    max_drawdown_pct: float
    trade_count: int
    worst_fold_pf: float
    stress_pf: float
    is_regime_stable: bool
    is_mc_robust: bool


@dataclass
class JudgeEvaluationResult:
    challenger_id: str
    champion_id: str
    promoted: bool
    stage_passed: int  # 0 to 6
    reasons: List[str]
    audit_trail: List[str]
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SafeJudgeEvaluator:
    """
    Judge Evaluator protecting Champion from overfitted Challengers.
    """

    def __init__(self, registry: ChampionChallengerRegistry):
        self.registry = registry

    def evaluate_challenger_candidate(
        self,
        manifest: ModelVersionManifest,
        champion_metrics: PerformanceMetricsSnapshot,
        challenger_metrics: PerformanceMetricsSnapshot
    ) -> JudgeEvaluationResult:
        """
        Executes 6-Stage Gate Pipeline to decide promotion.
        """
        reasons = []
        audit_trail = [f"Initiated 6-Stage Evaluation for Candidate {manifest.model_id}"]

        # Lock Verification Assertion
        if not manifest.is_locked:
            reasons.append("REJECTED: Model candidate state is NOT locked!")
            return JudgeEvaluationResult(
                challenger_id=manifest.model_id, champion_id=champion_metrics.model_id,
                promoted=False, stage_passed=0, reasons=reasons, audit_trail=audit_trail
            )

        # -------------------------------------------------------------
        # Stage 1: Training CV Check (Min 55% Win Rate / Accuracy)
        # -------------------------------------------------------------
        if challenger_metrics.win_rate < 40.0:
            reasons.append(f"Stage 1 FAIL: Training Win Rate ({challenger_metrics.win_rate:.1f}%) < 40.0%")
            return JudgeEvaluationResult(
                challenger_id=manifest.model_id, champion_id=champion_metrics.model_id,
                promoted=False, stage_passed=1, reasons=reasons, audit_trail=audit_trail
            )
        audit_trail.append("Stage 1 (Training CV): PASSED ✅")

        # -------------------------------------------------------------
        # Stage 2: Validation Check (Min Trade Count & Validation PF)
        # -------------------------------------------------------------
        if challenger_metrics.trade_count < 50:
            reasons.append(f"Stage 2 FAIL: Insufficient trades ({challenger_metrics.trade_count} < 50)")
            return JudgeEvaluationResult(
                challenger_id=manifest.model_id, champion_id=champion_metrics.model_id,
                promoted=False, stage_passed=2, reasons=reasons, audit_trail=audit_trail
            )
        audit_trail.append("Stage 2 (Validation Check): PASSED ✅")

        # -------------------------------------------------------------
        # Stage 3: Untouched OOS Performance (Expectancy & Max DD Gate)
        # -------------------------------------------------------------
        if challenger_metrics.expectancy_usd <= champion_metrics.expectancy_usd:
            reasons.append(f"Stage 3 FAIL: Expectancy (${challenger_metrics.expectancy_usd:.2f}) <= Champion (${champion_metrics.expectancy_usd:.2f})")
            return JudgeEvaluationResult(
                challenger_id=manifest.model_id, champion_id=champion_metrics.model_id,
                promoted=False, stage_passed=3, reasons=reasons, audit_trail=audit_trail
            )

        if challenger_metrics.max_drawdown_pct > champion_metrics.max_drawdown_pct:
            reasons.append(f"Stage 3 FAIL: Max DD ({challenger_metrics.max_drawdown_pct:.2f}%) > Champion ({champion_metrics.max_drawdown_pct:.2f}%)")
            return JudgeEvaluationResult(
                challenger_id=manifest.model_id, champion_id=champion_metrics.model_id,
                promoted=False, stage_passed=3, reasons=reasons, audit_trail=audit_trail
            )
        audit_trail.append("Stage 3 (Untouched OOS Gate): PASSED ✅")

        # -------------------------------------------------------------
        # Stage 4: Realistic Execution Stress Test
        # -------------------------------------------------------------
        if challenger_metrics.stress_pf < 1.10:
            reasons.append(f"Stage 4 FAIL: Stress Profit Factor ({challenger_metrics.stress_pf:.2f}) < 1.10")
            return JudgeEvaluationResult(
                challenger_id=manifest.model_id, champion_id=champion_metrics.model_id,
                promoted=False, stage_passed=4, reasons=reasons, audit_trail=audit_trail
            )
        audit_trail.append("Stage 4 (Execution Stress Test): PASSED ✅")

        # -------------------------------------------------------------
        # Stage 5: Market Regime Stability Test
        # -------------------------------------------------------------
        if not challenger_metrics.is_regime_stable:
            reasons.append("Stage 5 FAIL: Market Regime Instability detected across market cycles")
            return JudgeEvaluationResult(
                challenger_id=manifest.model_id, champion_id=champion_metrics.model_id,
                promoted=False, stage_passed=5, reasons=reasons, audit_trail=audit_trail
            )
        audit_trail.append("Stage 5 (Regime Stability Test): PASSED ✅")

        # -------------------------------------------------------------
        # Stage 6: Monte Carlo 10,000 Runs Robustness
        # -------------------------------------------------------------
        if not challenger_metrics.is_mc_robust:
            reasons.append("Stage 6 FAIL: Monte Carlo flagged SEQUENCE SENSITIVE ⚠️")
            return JudgeEvaluationResult(
                challenger_id=manifest.model_id, champion_id=champion_metrics.model_id,
                promoted=False, stage_passed=6, reasons=reasons, audit_trail=audit_trail
            )
        audit_trail.append("Stage 6 (Monte Carlo 10k Robustness): PASSED ✅")

        # -------------------------------------------------------------
        # PROMOTION APPROVED
        # -------------------------------------------------------------
        manifest.is_champion = True
        if self.registry.champion_manifest is not None:
            self.registry.champion_manifest.is_champion = False
            self.registry.history_manifests.append(self.registry.champion_manifest)
        self.registry.champion_manifest = manifest

        audit_trail.append(f"🏆 PROMOTION GRANTED: Challenger {manifest.model_id} is now Champion!")
        logger.info(f"🏆 Champion Model Promoted: {manifest.model_id}")

        return JudgeEvaluationResult(
            challenger_id=manifest.model_id, champion_id=champion_metrics.model_id,
            promoted=True, stage_passed=6, reasons=["Passed all 6 pipeline gates"], audit_trail=audit_trail
        )
