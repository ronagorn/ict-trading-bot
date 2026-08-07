"""
AURA v5 — Institutional System Observability Dashboard Runner & Exporter
========================================================================
Exports live observability JSON telemetry and starts local HTTP server preview.
"""

import sys
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from services.observability_api import SystemObservabilityProvider


def run_dashboard_telemetry_export():
    print("==================================================================")
    print("   AURA v5 — INSTITUTIONAL SYSTEM OBSERVABILITY TELEMETRY         ")
    print("==================================================================")

    provider = SystemObservabilityProvider()
    snapshot = provider.get_live_observability_snapshot()

    # Save to dynamic telemetry JSON
    output_path = Path(__file__).resolve().parent / "dashboard" / "live_observability.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2)

    print(f"Exported live backend telemetry to: {output_path}")

    sh = snapshot["system_health"]
    st = snapshot["strategy_health"]
    rk = snapshot["risk_telemetry"]
    ml = snapshot["ml_telemetry"]

    print("\n------------------------------------------------------------------")
    print("   🖥️ SYSTEM & ENGINE HEALTH STATUS")
    print("------------------------------------------------------------------")
    print(f"MT5 Terminal:       {'ONLINE ✅' if sh['mt5_connected'] else 'OFFLINE ❌'} (Latency: {sh['execution_latency_ms']} ms)")
    print(f"Database Feed:      {'CONNECTED ✅' if sh['database_connected'] else 'DISCONNECTED ❌'} (Freshness: {sh['data_freshness_seconds']}s)")
    print(f"ML Model Filter:    {sh['ml_status']} (Version: {ml['model_version']})")
    print(f"Risk Engine State:  {sh['risk_engine_state']} (Drawdown: {rk['current_drawdown_pct']}%)")
    print(f"Strategy Engine:    {sh['strategy_engine_state']} (Regime: {st['current_regime']})")

    print("\n------------------------------------------------------------------")
    print("   🛡️ NO-TRADE GATE & RISK TELEMETRY")
    print("------------------------------------------------------------------")
    print(f"No-Trade Gate:      {st['no_trade_reason']}")
    print(f"Drawdown State:     {rk['drawdown_state']} (Port Heat: {rk['portfolio_heat']})")
    print(f"Feature Drift (PSI):{ml['feature_drift_psi']:.2f} -> {ml['drift_status']}")
    print("==================================================================")


if __name__ == "__main__":
    run_dashboard_telemetry_export()
