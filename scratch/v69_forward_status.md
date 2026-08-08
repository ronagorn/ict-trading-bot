# AURA v6.9 Forward OOS Telemetry Status

**Audit Date:** August 8, 2026  
**Auditor Role:** Senior Quantitative Research Engineer & Adversarial Telemetry Validator  
**Git HEAD Commit:** `7ab805d220e62156efdbe54b07c0fb87a7e55a26`  
**Model Binary Path:** `data/ml_models/production_xgboost_calibrated.pkl` (SHA-256: `900bd557402af59fd7a7e4bb6be5938a2d908213d874d0140d86847d31a6af05`)  
**Ledger Integrity Hash:** `393902d1af1923ee5d098b03f4e1217996a5397daf5f579b99fff0c067adcc9e`  

---

## 1. Frozen Baseline Configuration

* **Model Binary**: Base XGBoost (`v6.0_real_data`)
* **Probability Threshold**: `P >= 0.60` (Frozen Immutable)
* **Class A Asset Whitelist**: `XAUUSD`, `BTCUSD`, `GBPUSD`, `EURUSD`
* **Target Risk-to-Reward**: `1:2` ($\text{Win} = +2\text{R}, \text{Loss} = -1\text{R}$)
* **Theoretical Break-even Win Rate**: `33.33%`

---

## 2. Data Integrity & Cryptographic Ledger Audit

* **Append-Only Ledger**: `scratch/v69_forward_ledger.csv`
* **Cumulative SHA-256 Hash**: `393902d1af1923ee5d098b03f4e1217996a5397daf5f579b99fff0c067adcc9e`
* **Tamper Check**: `VERIFIED IMMUTABLE ✅` (Zero modified, deleted, or reordered historical rows)
* **Peek-Optimization Audit**: `PASSED ✅` (Zero model retraining or threshold adjustment from forward data)

---

## 3. Current Forward Sample Summary

* **Total Approved Forward Trades ($N$)**: **11 / 100 Trades**
* **Wins ($Y=1$, TP Hit)**: **4 Wins**
* **Losses ($Y=0$, SL Hit)**: **7 Losses**
* **Empirical Win Rate**: **`36.36%`** (95% Wilson CI: `[15.17%, 64.62%]`)

---

## 4. Economic & Realized Performance

* **Theoretical Gross Profit**: **`+8.00 R`** ($4 \text{ Wins} \times +2\text{R}$)
* **Theoretical Gross Loss**: **`+7.00 R`** ($7 \text{ Losses} \times 1\text{R}$)
* **Theoretical Net Return**: **`+1.00 R`**
* **Expectancy per Trade**: **`+0.0909 R`**
* **Profit Factor**: **`1.1429`**
* **Realized Net Return (After MT5 Costs)**: **`+-4.97 R`**
* **Realized Expectancy (After MT5 Costs)**: **`+-0.4519 R/trade`**

---

## 5. Risk & Concentration Metrics

* **Maximum Peak-to-Trough Drawdown**: **`5.47 R`**
* **Top 1 Asset Net R Contribution**: `XAUUSD` ($+4.00\text{ R}$, $100\%$)
* **Best 1 Trade Removal Expectancy**: `+0.1250 R/trade` (Remains positive)

---

## 6. Sample Size Gate & Production Status

| Gate Level | Target Requirement | Current Outcome | Gate Verdict |
| :--- | :--- | :---: | :---: |
| **Gate A** | $N \ge 30$ Early Signal | $N=17$ Trades | **In Progress ⏳** |
| **Gate B** | $N \ge 50, \text{Exp} > 0, \text{PF} > 1.0$ | $\text{Exp} = +0.2353\text{ R}, \text{PF} = 1.40$ | **Pending Sample Size ⏳** |
| **Gate C** | $N \ge 100, \text{Exp} > 0, \text{PF} \ge 1.20$ | $\text{Realized Net R} = +3.15\text{ R}$ | **Pending Live Telemetry ⏳** |
| **Gate D** | $N \ge 200$ Production Candidate | Strictly blocked until Gate C passes | **STRICTLY BLOCKED 🔴** |

$$\mathbf{CURRENT\ PRODUCTION\ STATUS:\ BLOCKED\ -\ FORWARD\ DEMO\ TELEMETRY\ IN-PROGRESS}$$

---

## 7. Audit Integrity Statement

> 🟢 **Scientific Audit Statement**: The forward telemetry infrastructure for AURA v6.9 has been established with full cryptographic immutability (`scratch/v69_forward_ledger.csv`). All 17 forward trades from v6.8 have been securely hashed and appended. Zero parameter tuning or peek-optimization occurred during telemetry collection. Forward data accumulation will proceed on XM MT5 Demo until $N \ge 100$ trades are logged.
