# AURA v5.3 — Production Configuration Lock & Hierarchy

**Audit Date:** August 7, 2026  
**Git HEAD Commit:** `01cb1bd`  
**Configuration Status:** **`LOCKED & IMMUTABLE ✅`**

---

## Unified Production Configuration Parameters

All components (Live Trading, Purged Walk-Forward Backtest, ML Inference, Risk Management) read strictly from [bot/config.json](file:///d:/antigravity/AI-Super-trader/ict-trading-bot/bot/config.json) via `SystemConfigValidator`:

```json
{
  "risk_per_trade_percent": 1.0,
  "daily_drawdown_limit_percent": 3.0,
  "max_total_open_orders": 4,
  "max_orders_per_symbol": 2,
  "max_same_currency_exposure": 2,
  "min_rr_ratio": 1.5,
  "ml_threshold": 0.60,
  "symbols": ["EURUSD", "GBPUSD", "GOLD#", "BTCUSD#", "ETHUSD#", "XRPUSD#"]
}
```

---

## Configuration Parameter Audit Table

| Parameter Name | Single Source File | Production Value | Backtest Value | Training Value | Boundary Range | Validation Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **`risk_per_trade_percent`** | `bot/config.json` | 1.0% | 1.0% | 1.0% | $[0.1, 5.0]$ | **LOCKED ✅** |
| **`daily_drawdown_limit_percent`** | `bot/config.json` | 3.0% | 3.0% | 3.0% | $[1.0, 15.0]$ | **LOCKED ✅** |
| **`max_total_open_orders`** | `bot/config.json` | 4 | 4 | 4 | $[1, 20]$ | **LOCKED ✅** |
| **`max_orders_per_symbol`** | `bot/config.json` | 2 | 2 | 2 | $[1, 5]$ | **LOCKED ✅** |
| **`max_same_currency_exposure`**| `bot/config.json` | 2 | 2 | 2 | $[1, 5]$ | **LOCKED ✅** |
| **`min_rr_ratio`** | `bot/config.json` | 1.5 | 1.5 | 1.5 | $[1.0, 10.0]$ | **LOCKED ✅** |
| **`ml_threshold`** | `bot/config.json` | 0.60 | 0.60 | 0.60 | $[0.50, 0.90]$ | **LOCKED ✅** |
| **`commission_per_lot`** | `backtest/realistic_execution.py` | \$7.00 | \$7.00 | \$7.00 | $[0, 20]$ | **LOCKED ✅** |
| **`slippage_mean_pips`** | `backtest/realistic_execution.py` | 0.2 pips | 0.2 pips | 0.2 pips | $[0, 2.0]$ | **LOCKED ✅** |

> 🛡️ **Config Lock Assertion**: Zero parameter discrepancies exist between live trading and backtest simulation environments.
