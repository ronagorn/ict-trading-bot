# AURA Institutional Trading Bot v5.0

> Production-Grade AI-Powered ICT/SMC Institutional Trading System for MetaTrader 5

![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue)
![MetaTrader5](https://img.shields.io/badge/MetaTrader-5-0052FF)
![XGBoost](https://img.shields.io/badge/ML-XGBoost%20Calibrated-orange)
![License](https://img.shields.io/badge/License-MIT-green)

---

## What Is This?

A fully automated, production-grade institutional trading bot utilizing **ICT (Inner Circle Trader) / Smart Money Concepts (SMC)** combined with **Calibrated XGBoost Machine Learning Filtering**, **Market Regime Detection**, and **16-Condition No-Trade Decision Controls** on MetaTrader 5.

---

## AURA v5 Core Institutional Frameworks (100% Completed & Verified)

| Framework Module | Path | Description | Test Status |
| :--- | :--- | :--- | :---: |
| **1. Purged Walk-Forward CV** | `backtest/purged_walk_forward.py` | Anti-leakage sequential Purged & Embargoed Cross-Validation engine | 5/5 PASSED ✅ |
| **2. Realistic Execution Sim** | `backtest/realistic_execution.py` | Models spread, slippage, latency delay, gaps, and same-bar TP/SL collision | 4/4 PASSED ✅ |
| **3. Market Regime Engine** | `bot/regime_engine.py` | Classifies 7 market states & blocks low liquidity / unknown regimes | 4/4 PASSED ✅ |
| **4. Setup Quality Scorer** | `bot/setup_quality_scorer.py` | 0-100 score matrix for FVG, Order Block, and Liquidity Sweep setups | 4/4 PASSED ✅ |
| **5. Production ML Engine** | `bot/production_ml_engine.py` | Calibrated XGBoost (Platt Sigmoid CV), Fail-Safe modes & PSI Drift monitor | 5/5 PASSED ✅ |
| **6. No-Trade Decision Engine** | `bot/no_trade_engine.py` | 16-condition safety gate with highest priority override authority | 8/8 PASSED ✅ |
| **7. Institutional Risk Engine** | `bot/risk_manager.py` | Single Source of Truth Config, Drawdown State Machine & Cooldown caps | 7/7 PASSED ✅ |
| **8. Advanced Trade Analytics** | `services/trade_analytics.py` | 28-field institutional logging, MFE/MAE distributions & research diagnostics | 4/4 PASSED ✅ |
| **9. Monte Carlo Framework** | `backtest/monte_carlo.py` | 10,000 simulations across BASE, ADVERSE, SEVERE stress scenarios | 4/4 PASSED ✅ |
| **10. Champion / Challenger** | `services/judge_evaluator.py` | 6-stage candidate evaluation pipeline gate & instant rollback mechanism | 4/4 PASSED ✅ |
| **11. System Observability** | `services/observability_api.py` | Dynamic backend telemetry provider & web dashboard UI | 3/3 PASSED ✅ |
| **12. Config Fail-Fast Validator** | `bot/config_validator.py` | Single Source of Truth configuration validator with fail-fast assertions | 4/4 PASSED ✅ |

---

## Configuration Hierarchy (Single Source of Truth)

All modules load configuration strictly from `bot/config.json` via `SystemConfigValidator`:

$$\text{bot/config.json} \longrightarrow \text{SystemConfigValidator} \longrightarrow \text{Core Bot Engines}$$

### `bot/config.json` Key Settings
```json
{
  "risk_per_trade_percent": 1.0,
  "daily_drawdown_limit_percent": 3.0,
  "max_total_open_orders": 4,
  "max_orders_per_symbol": 2,
  "max_same_currency_exposure": 2,
  "min_rr_ratio": 1.5,
  "ml_threshold": 0.60
}
```

---

## Testing & Verification

Run all 61 automated unit test suites across the repository:

```bash
python -m unittest discover -s tests -p "test_*.py"
```

Output:
```text
Ran 61 tests in 12.732s

OK
```

---

## Development Status & Roadmap

### Completed (v5.0 Production)
- [x] 4H Shield & M15 FVG / Order Block / Liquidity Sweep strategy
- [x] Purged Walk-Forward Cross-Validation Engine
- [x] Realistic Live Execution Simulation Engine
- [x] Market Regime Detection Engine & NO TRADE Gate
- [x] Institutional Setup Quality Scoring Layer (0 - 100)
- [x] Calibrated XGBoost Machine Learning Signal Filter
- [x] No-Trade Decision Engine with Highest Priority Override
- [x] Institutional Portfolio Risk Engine & Drawdown State Machine
- [x] Advanced Trade Analytics (MFE / MAE / Realized R Diagnostics)
- [x] Monte Carlo 10,000 Simulation Robustness Framework
- [x] Safe Champion / Challenger 6-Stage Gate & Rollback Framework
- [x] Real-Time Web System Observability Dashboard
- [x] Configuration Hierarchy & Fail-Fast Validator

---

## License

MIT License — use freely for personal and commercial purposes.
