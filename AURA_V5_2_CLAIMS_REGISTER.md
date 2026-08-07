# AURA v5.2 — Claims Register & Forensics Audit

**Audit Scope:** Verification of all claims in `AURA_V5_AUDIT_REPORT.md` & `AURA_V5_ADVERSARIAL_AUDIT.md` against actual code.

---

## Claims Forensic Register

| Claim # | Claim Summary | Source Document | Expected Implementation | Actual Code Implementation | Empirical Evidence | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| **C-01** | **65/65 Unit Tests Pass** | `AURA_V5_AUDIT_REPORT.md` | 65 unit tests across repository pass 100%. | `pytest` / `unittest` discovers 65 tests in `tests/`. | `Ran 65 tests in 12.475s ... OK` | **VERIFIED ✅** |
| **C-02** | **Session Sweep Zero Leakage** | `AURA_V5_AUDIT_REPORT.md` | Dynamic calculation using historical bars prior to candle $T$. | `bot/strategy.py` uses `recent.loc[:idx].iloc[:-1]`. | `tests/test_temporal_integrity.py` 5/5 PASSED. | **VERIFIED ✅** |
| **C-03** | **Calibrated XGBoost Filter** | `AURA_V5_AUDIT_REPORT.md` | Probability calibration via `CalibratedClassifierCV`. | `bot/production_ml_engine.py` uses `method="sigmoid"` on `TimeSeriesSplit`. | `tests/test_production_ml_engine.py` PASSED. | **VERIFIED ✅** |
| **C-04** | **Fail-Safe Fallback Modes** | `AURA_V5_AUDIT_REPORT.md` | Cold start / Model failure triggers `STRICT_MODE` with 50% Lot. | `predict_trade_permission()` in `bot/production_ml_engine.py`. | Returns `risk_multiplier = 0.50` on failure. | **VERIFIED ✅** |
| **C-05** | **ML OOS Win Rate 71.43%** | `AURA_V5_ADVERSARIAL_AUDIT.md` | 40 wins out of 56 approved trades ($N=56$). | `run_production_ml_benchmark.py` OOS execution. | $40 / 56 = 71.43\%$, $95\%\text{ CI} = [58.46\%, 81.67\%]$. | **VERIFIED ✅** |
| **C-06** | **Single Source of Truth Config** | `AURA_V5_AUDIT_REPORT.md` | `bot/config.json` is sole config source with fail-fast assertions. | `bot/config_validator.py` enforces ranges. | `tests/test_config_validator.py` PASSED. | **VERIFIED ✅** |
| **C-07** | **Daily Drawdown Limit 3.0%** | `AURA_V5_AUDIT_REPORT.md` | Unified drawdown limit across all modules. | `bot/config.json` sets `3.0%`; `bot/risk_manager.py` enforces `3.0%`. | `run_config_consistency_audit.py` PASSED. | **VERIFIED ✅** |
| **C-08** | **Supabase Query Order** | `AURA_V5_2_REALITY_AUDIT.md` | Training data sorted by `entry_time ASC` prior to `TimeSeriesSplit`. | `services/db_client.py` line 89 uses `order("entry_time", desc=True)`. | Descending order requires `.iloc[::-1]` re-sorting! | **PARTIALLY VERIFIED ⚠️** |
| **C-09** | **Severe Monte Carlo 95th DD**| `AURA_V5_ADVERSARIAL_AUDIT.md` | 95th Percentile Max DD reaches 34.39% under Severe Stress. | `run_monte_carlo_framework.py` 10k simulations. | Flagged as `SEQUENCE SENSITIVE ⚠️`. | **VERIFIED ✅** |
| **C-10** | **Same-Bar TP/SL Collision** | `AURA_V5_AUDIT_REPORT.md` | Strict conservative resolution (always LOSS). | `backtest/realistic_execution.py` line 142. | Same-bar collision returns `loss_per_trade`. | **VERIFIED ✅** |
