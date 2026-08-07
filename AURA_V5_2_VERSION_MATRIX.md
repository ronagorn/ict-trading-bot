# AURA v5.2 — Git Reproducibility & Version Matrix

**Audit Timestamp:** August 7, 2026  
**HEAD Commit SHA:** `99cc306305a415ff68f1c8413b63bf2ee62ad2a8`  
**Parent Commit SHA:** `a46deff6f8c48c1aced777b4d493fb4d0bcde9d5`  
**Audit Purpose:** Precise file-level Git SHA and dependency tracking for live and backtest components.

---

## Component Versioning & Git SHA Matrix

| System Component | Core Source File | Git SHA (Current HEAD) | Active Version Tag | Used by Backtest | Used by Live Bot | Alignment Status |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| **Strategy Engine** | `bot/strategy.py` | `99cc306` | `v5.0_production` | Yes | Yes | **ALIGNED ✅** |
| **Legacy ML Filter** | `bot/ml_filter.py` | `99cc306` | `v5.0_legacy` | Yes | Partial | **MISMATCH (Refactored) ⚠️** |
| **Production ML Engine**| `bot/production_ml_engine.py` | `99cc306` | `v5.0.0_calibrated` | Yes | Yes | **ALIGNED ✅** |
| **No-Trade Engine** | `bot/no_trade_engine.py` | `99cc306` | `v5.0_override` | Yes | Yes | **ALIGNED ✅** |
| **Risk Manager** | `bot/risk_manager.py` | `99cc306` | `v5.0_institutional` | Yes | Yes | **ALIGNED ✅** |
| **Config Validator** | `bot/config_validator.py` | `99cc306` | `v5.0_schema` | Yes | Yes | **ALIGNED ✅** |
| **Observability Provider**| `services/observability_api.py` | `99cc306` | `v5.0_telemetry` | No | Yes | **ALIGNED ✅** |
| **Trade Analytics** | `services/trade_analytics.py` | `99cc306` | `v5.0_logger` | Yes | Yes | **ALIGNED ✅** |
| **Purged Walk-Forward** | `backtest/purged_walk_forward.py` | `99cc306` | `v5.0_cv` | Yes | No | **ALIGNED ✅** |
| **Realistic Execution** | `backtest/realistic_execution.py` | `99cc306` | `v5.0_sim` | Yes | No | **ALIGNED ✅** |
| **Monte Carlo Engine** | `backtest/monte_carlo.py` | `99cc306` | `v5.0_10k` | Yes | No | **ALIGNED ✅** |
| **Judge Evaluator** | `services/judge_evaluator.py` | `99cc306` | `v5.0_gate` | Yes | No | **ALIGNED ✅** |
| **Challenger Registry** | `services/challenger_engine.py` | `99cc306` | `v5.0_manifest` | Yes | No | **ALIGNED ✅** |
| **System Config** | `bot/config.json` | `99cc306` | `v5.0_single_truth` | Yes | Yes | **ALIGNED ✅** |
| **ML Model Artifact** | `data/ml_models/production_xgboost_calibrated.pkl` | `99cc306` | `v5.0.0` | Yes | Yes | **ALIGNED ✅** |
| **ML Metadata Manifest**| `data/ml_models/production_model_metadata.json` | `99cc306` | `v5.0.0` | Yes | Yes | **ALIGNED ✅** |
