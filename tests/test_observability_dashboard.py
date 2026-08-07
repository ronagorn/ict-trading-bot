"""
Unit Tests for System Observability Provider & Dashboard Backend (AURA v5)
========================================================================
Tests:
1. Observability Payload Section Completeness (System Health, Strategy Health, Performance, Breakdown, ML, Risk)
2. Live Metrics Aggregation from Backend Config & Engines
3. Structure Compliance for Dashboard Frontend Consume
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.observability_api import SystemObservabilityProvider


class TestSystemObservabilityProvider(unittest.TestCase):

    def setUp(self):
        self.provider = SystemObservabilityProvider()

    def test_live_snapshot_sections(self):
        """1. Verify all 6 core telemetry sections are present in snapshot."""
        snapshot = self.provider.get_live_observability_snapshot()

        sections = [
            "timestamp", "system_health", "strategy_health",
            "performance", "breakdown", "ml_telemetry", "risk_telemetry"
        ]
        for sec in sections:
            self.assertIn(sec, snapshot, f"OBSERVABILITY PAYLOAD MISSING SECTION: {sec}")

    def test_system_health_fields(self):
        """2. Verify system health telemetry fields."""
        sh = self.provider.get_live_observability_snapshot()["system_health"]
        self.assertTrue(sh["mt5_connected"])
        self.assertTrue(sh["database_connected"])
        self.assertIn("execution_latency_ms", sh)

    def test_risk_telemetry_fields(self):
        """3. Verify risk telemetry fields and drawdown state."""
        rk = self.provider.get_live_observability_snapshot()["risk_telemetry"]
        self.assertEqual(rk["drawdown_state"], "NORMAL")
        self.assertIn("current_drawdown_pct", rk)


if __name__ == "__main__":
    unittest.main()
