"""
AURA v5 — Champion / Challenger Safe Evaluation & Audit Runner
================================================================
Evaluates Champion vs 3 Challenger Candidates across 6 Pipeline Stages:
1. Overfitted Challenger Candidate
2. Fragile Execution Challenger Candidate
3. Robust Superior Challenger Candidate
"""

import sys
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import os
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from services.challenger_engine import ChampionChallengerRegistry
from services.judge_evaluator import SafeJudgeEvaluator, PerformanceMetricsSnapshot


def run_champion_challenger_audit():
    print("==================================================================")
    print("   AURA v5 — SAFE CHAMPION / CHALLENGER PROMOTION AUDIT           ")
    print("==================================================================")

    registry = ChampionChallengerRegistry()
    evaluator = SafeJudgeEvaluator(registry)

    # 1. Register Active Champion
    champ_manifest = registry.register_model_candidate(
        model_id="CHAMPION_v5_0", features=["fvg_score", "trend_alignment"],
        parameters={"n_estimators": 100}, is_champion=True
    )
    registry.lock_model_candidate(champ_manifest)

    champ_metrics = PerformanceMetricsSnapshot(
        model_id="CHAMPION_v5_0", win_rate=65.0, profit_factor=2.20,
        expectancy_usd=210.0, max_drawdown_pct=8.5, trade_count=120,
        worst_fold_pf=1.4, stress_pf=1.85, is_regime_stable=True, is_mc_robust=True
    )

    print(f"Active Champion: {champ_manifest.model_id} | Expectancy: ${champ_metrics.expectancy_usd:.2f} | Max DD: {champ_metrics.max_drawdown_pct:.1f}%")
    print("------------------------------------------------------------------")

    # 2. Define 3 Challenger Candidates
    candidates = [
        ("Candidate A (Overfit)", "CHALLENGER_A_OVERFIT", PerformanceMetricsSnapshot(
            model_id="CHALLENGER_A_OVERFIT", win_rate=90.0, profit_factor=2.10,
            expectancy_usd=160.0, max_drawdown_pct=16.5, trade_count=100,
            worst_fold_pf=0.8, stress_pf=1.05, is_regime_stable=True, is_mc_robust=True
        )),
        ("Candidate B (Fragile)", "CHALLENGER_B_FRAGILE", PerformanceMetricsSnapshot(
            model_id="CHALLENGER_B_FRAGILE", win_rate=70.0, profit_factor=2.40,
            expectancy_usd=230.0, max_drawdown_pct=7.5, trade_count=110,
            worst_fold_pf=1.2, stress_pf=0.95, is_regime_stable=True, is_mc_robust=True # Fails Stress
        )),
        ("Candidate C (Superior)", "CHALLENGER_C_SUPERIOR", PerformanceMetricsSnapshot(
            model_id="CHALLENGER_C_SUPERIOR", win_rate=73.5, profit_factor=3.25,
            expectancy_usd=270.0, max_drawdown_pct=5.8, trade_count=150,
            worst_fold_pf=1.75, stress_pf=2.20, is_regime_stable=True, is_mc_robust=True # Passes All 6
        ))
    ]

    print("\n=========================================================================================================")
    print("                              📊 6-STAGE PIPELINE EVALUATION MATRIX                                     ")
    print("=========================================================================================================")
    print(f"{'Challenger Model':<24} | {'Exp ($)':<8} | {'Max DD (%)':<10} | {'Passed':<7} | {'Promoted':<9} | {'Audit Verdict / Failure Reason':<32}")
    print("---------------------------------------------------------------------------------------------------------")

    for title, model_id, c_metrics in candidates:
        manifest = registry.register_model_candidate(
            model_id=model_id, features=["fvg_score", "ob_score"], parameters={"max_depth": 4}
        )
        registry.lock_model_candidate(manifest)

        res = evaluator.evaluate_challenger_candidate(manifest, champ_metrics, c_metrics)
        verdict = res.reasons[0] if res.reasons else "All Passed"
        if len(verdict) > 32:
            verdict = verdict[:29] + "..."

        print(f"{model_id:<24} | ${c_metrics.expectancy_usd:>6.2f} | {c_metrics.max_drawdown_pct:>9.2f}% | {res.stage_passed}/6    | {str(res.promoted):<9} | {verdict:<32}")

    # 3. Test Rollback Demonstration
    print("\n------------------------------------------------------------------")
    print("   ⏪ DEMONSTRATING INSTANT ROLLBACK MECHANISM")
    print("------------------------------------------------------------------")
    print(f"Current Champion before rollback: {registry.champion_manifest.model_id}")
    success, restored = registry.rollback_to_previous_champion()
    print(f"Rollback Execution Status: {'SUCCESS ✅' if success else 'FAILED ❌'}")
    print(f"Restored Active Champion:  {registry.champion_manifest.model_id}")
    print("==================================================================")


if __name__ == "__main__":
    run_champion_challenger_audit()
