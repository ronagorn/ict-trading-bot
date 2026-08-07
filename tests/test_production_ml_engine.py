"""
Unit Tests for Production ML Filtering Engine (AURA v5)
======================================================
Tests:
1. Calibrated Model Training & Dataset Hashing
2. Fail-Safe Behavior: Model Corruption / DB Outage -> STRICT_MODE Fallback with 50% Lot Size Risk Reduction
3. Cold Start Operational Modes (RULE_ONLY mode for trades < 300)
4. Population Stability Index (PSI) Drift Calculation
5. Security Isolation Assertion against Leakage Columns
"""

import sys
import unittest
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.production_ml_engine import (
    ProductionMLEngine,
    SystemOperationalMode,
    AUDITED_FEATURE_COLUMNS,
    FORBIDDEN_LEAKAGE_COLUMNS
)


class TestProductionMLEngine(unittest.TestCase):

    def setUp(self):
        self.engine = ProductionMLEngine()

    def test_security_leakage_isolation(self):
        """1. Verify forbidden leakage columns are isolated from audited features."""
        for forbidden in FORBIDDEN_LEAKAGE_COLUMNS:
            self.assertNotIn(forbidden, AUDITED_FEATURE_COLUMNS)

    def test_cold_start_rule_only_mode(self):
        """2. Verify Cold Start (<300 trades) activates RULE_ONLY mode with 50% risk reduction."""
        signal_high_quality = {"composite_score": 75.0, "fvg_size_pips": 10.0}
        approved, prob, mode, risk_mult = self.engine.predict_trade_permission(
            signal_high_quality, threshold=0.60, total_closed_trades=100
        )
        self.assertTrue(approved)
        self.assertEqual(mode, SystemOperationalMode.RULE_ONLY)
        self.assertEqual(risk_mult, 0.50, "Cold start must apply 50% lot size risk reduction!")

        signal_low_quality = {"composite_score": 40.0, "fvg_size_pips": 2.0}
        approved_low, _, mode_low, _ = self.engine.predict_trade_permission(
            signal_low_quality, threshold=0.60, total_closed_trades=100
        )
        self.assertFalse(approved_low, "Low quality setup must be rejected during Cold Start!")

    def test_fail_safe_strict_mode(self):
        """3. Verify Fail-Safe: When model is missing/corrupt, system defaults to STRICT_MODE."""
        # Query with non-existent model path
        engine_broken = ProductionMLEngine(model_path=Path("non_existent_model.pkl"))
        
        signal_strict = {"composite_score": 80.0}
        approved, prob, mode, risk_mult = engine_broken.predict_trade_permission(
            signal_strict, threshold=0.60, total_closed_trades=400
        )
        self.assertTrue(approved)
        self.assertEqual(mode, SystemOperationalMode.STRICT_MODE)
        self.assertEqual(risk_mult, 0.50, "Fail-safe strict mode must apply 50% risk reduction!")

    def test_calibrated_training_and_hashing(self):
        """4. Verify calibrated pipeline training and dataset hash generation."""
        np.random.seed(42)
        n = 80
        df = pd.DataFrame({
            "fvg_size_pips": np.random.uniform(2, 20, n),
            "killzone_hour": np.random.choice([8, 9, 14, 15], n),
            "trend_alignment": np.random.choice([0, 1], n),
            "volume_spike_ratio": np.random.uniform(1, 3, n),
            "fvg_quality_score": np.random.uniform(40, 90, n),
            "ob_quality_score": np.random.uniform(40, 90, n),
            "liquidity_quality_score": np.random.uniform(40, 90, n),
            "atr_percentile": np.random.uniform(20, 80, n),
            "trend_score": np.random.uniform(1, 8, n),
            "trade_outcome": np.random.choice([0, 1], n)
        })

        res = self.engine.train_calibrated_pipeline(df)
        self.assertTrue(res["success"])
        self.assertIn("dataset_hash", res)
        self.assertGreater(len(res["dataset_hash"]), 8)

    def test_psi_drift_calculation(self):
        """5. Verify Population Stability Index (PSI) drift calculation."""
        ref = np.random.normal(0, 1, 1000)
        curr_no_drift = np.random.normal(0, 1, 1000)
        curr_with_drift = np.random.normal(1.5, 1, 1000)

        psi_low = self.engine.calculate_population_stability_index(ref, curr_no_drift)
        psi_high = self.engine.calculate_population_stability_index(ref, curr_with_drift)

        self.assertLess(psi_low, 0.10, "No-drift PSI should be < 0.10")
        self.assertGreater(psi_high, 0.25, "Significant drift PSI should be > 0.25")


if __name__ == "__main__":
    unittest.main()
