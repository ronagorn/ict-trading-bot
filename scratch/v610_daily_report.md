# AURA v6.10 Daily Forward-OOS Report

**Report Date:** August 8, 2026  
**Git HEAD Commit:** `7ab805d220e62156efdbe54b07c0fb87a7e55a26`  
**Model Binary Path:** `data/ml_models/production_xgboost_calibrated.pkl` (SHA-256: `900bd557402af59fd7a7e4bb6be5938a2d908213d874d0140d86847d31a6af05`)  

---

## 1. Frozen Baseline Configuration

* **Model Binary**: Base XGBoost (`v6.0_real_data`)
* **Probability Threshold**: `P >= 0.60` (Frozen Immutable)
* **Class A Asset Whitelist**: `XAUUSD`, `BTCUSD`, `GBPUSD`, `EURUSD`
* **Target Risk-to-Reward**: `1:2` ($\text{Win} = +2\text{R}, \text{Loss} = -1\text{R}$)

---

## 2. Current Sample & Performance

* **Total Approved Forward Trades ($N$)**: **11 Trades**
* **Wins ($Y=1$, TP Hit)**: **4 Wins**
* **Losses ($Y=0$, SL Hit)**: **7 Losses**
* **Empirical Win Rate**: **`36.36%`** (95% Wilson CI: `[15.17%, 64.62%]`)
* **Theoretical Net Return**: **`+1.00 R`** ($\text{Expectancy} = \mathbf{+0.0909\text{ R/trade}}$)
* **Profit Factor**: **`1.1429`**
* **Realized Net Return (After Costs)**: **`+-4.97 R`** ($\text{Realized Exp} = \mathbf{+-0.4519\text{ R/trade}}$)
* **Maximum Peak-to-Trough Drawdown**: **`5.47 R`**

---

## 3. Failure Flags & Gate Status

* **Failure Flags**: `ZERO FLAGS TRIGGERED ✅`
* **Current Gate Level**: `Gate A (In-Progress ⏳)`
* **Production Status**: `STRICTLY BLOCKED 🔴`
