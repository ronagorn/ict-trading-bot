# AURA — Adversarial Research Algorithmic Trading System

> **Research-first algorithmic trading system.**  
> Primary objective: determine whether the trading hypothesis deserves to trade capital before allowing any production deployment.

---

```
╔══════════════════════════════════════╗
║       CURRENT PRODUCTION STATUS      ║
║                                      ║
║          ❌  LIVE TRADING BLOCKED    ║
║                                      ║
║      FORWARD DEMO COLLECTION ONLY    ║
║                                      ║
║    Current forward sample: N = 11    ║
║    Required for Gate D review: 200   ║
╚══════════════════════════════════════╝
```

---

## Table of Contents

1. [System Identity](#1-system-identity)
2. [Frozen Trading Hypothesis](#2-frozen-trading-hypothesis)
3. [Research Evolution](#3-research-evolution)
4. [v6.8 Adversarial Validation Results](#4-v68-adversarial-validation-results)
5. [Forward Sample Gates](#5-forward-sample-gates)
6. [System Architecture](#6-system-architecture)
7. [Repository Structure](#7-repository-structure)
8. [Module Reference](#8-module-reference)
9. [Forward-OOS Integrity](#9-forward-oos-integrity)
10. [Sequential Monitoring (v6.10)](#10-sequential-monitoring-v610)
11. [Execution Safety (v6.11)](#11-execution-safety-v611)
12. [Drift Monitoring (v6.12)](#12-drift-monitoring-v612)
13. [Telegram Observability (v6.13)](#13-telegram-observability-v613)
14. [Statistical Validation Framework](#14-statistical-validation-framework)
15. [Economic Validation](#15-economic-validation)
16. [Data Integrity Architecture](#16-data-integrity-architecture)
17. [Security Model](#17-security-model)
18. [Experiment Governance](#18-experiment-governance)
19. [Research Golden Rules](#19-research-golden-rules)
20. [Current System Status](#20-current-system-status)
21. [Operational Workflow](#21-operational-workflow)
22. [Roadmap to Production Review](#22-roadmap-to-production-review)
23. [Current Conclusion](#23-current-conclusion)
24. [Setup & Environment](#24-setup--environment)

---

## 1. System Identity

AURA is a research-grade algorithmic trading system built around **ICT (Inner Circle Trader) / Smart Money Concepts (SMC)** price-action methodology, augmented by an XGBoost machine-learning filter.

**AURA is NOT a production live-trading system.**

Its primary research objective is:

> Determine whether the ML-filtered ICT hypothesis generates positive expected value on genuinely unseen forward data before any deployment of real capital.

AURA is designed to **actively search for evidence that the strategy does not work**. A negative forward result is a valid and scientifically useful outcome.

The system maintains a strict separation between:

- **Research phase** — training, backtesting, hypothesis development (PAST)
- **Forward-OOS validation phase** — genuine unseen data collection (CURRENT)
- **Production deployment** — explicitly blocked until validation gates pass (FUTURE, not guaranteed)

---

## 2. Frozen Trading Hypothesis

The following configuration is **immutable** during Forward-OOS collection. It must not be modified based on forward results.

```
Model:                  Base XGBoost (v6.0_real_data)
Model artifact SHA-256: 900bd557402af59fd7a7e4bb6be5938a2d908213d874d0140d86847d31a6af05
Feature schema:         v6.0_real_data
Locked at git commit:   7ab805d220e62156efdbe54b07c0fb87a7e55a26

Probability Threshold:  P >= 0.60
Risk / Reward:          1:2

Asset Whitelist (Class A):
  XAUUSD  (Gold)
  BTCUSD  (Bitcoin)
  GBPUSD  (British Pound / US Dollar)
  EURUSD  (Euro / US Dollar)

Accounting:
  WIN  = +2R
  LOSS = -1R
  Theoretical break-even win rate = 33.33%
```

**Feature schema (9 features):**

```
fvg_size_pips          — Fair Value Gap size in pips
killzone_hour          — ICT Killzone session hour
trend_alignment        — Multi-timeframe trend alignment score
volume_spike_ratio     — Volume spike relative to moving average
fvg_quality_score      — Fair Value Gap quality composite
ob_quality_score       — Order Block quality composite
liquidity_quality_score — Liquidity sweep quality composite
atr_percentile         — ATR volatility percentile
trend_score            — Overall directional trend score
```

**Economic accounting:**

```
Net R         = Wins × 2 − Losses × 1
Expectancy    = Net R / Number of Trades
Profit Factor = Gross Profit / Gross Loss
```

---

## 3. Research Evolution

| Version | Purpose | Status |
|---------|---------|--------|
| v5.0–v5.3 | ICT Bot foundational build, initial ML filter, production hardening | Completed |
| v5.4–v5.8 | Reality audit, forensic PnL reconciliation, backtest integrity | Completed |
| v6.0 | Real-data model reconstruction (1,334 real trades) | Completed |
| v6.1 | Label population forensic audit | Completed |
| v6.2 | Threshold economic validation | Completed |
| v6.3 | Robustness, regime, walk-forward audit | Completed |
| v6.4 | Forensic PnL reconciliation | Completed |
| v6.5 | Final economic reality audit | Completed |
| v6.6 | Research recovery verdict | Completed |
| **v6.7** | **Frozen baseline — hypothesis locked** | **FROZEN** |
| v6.8 | Adversarial Forward-OOS Validation | Completed |
| v6.9 | Immutable Forward Telemetry | Completed |
| v6.10 | Sequential Forward-OOS Monitoring | Completed |
| v6.11 | Frozen Demo Execution & Safety Audit | Completed |
| v6.12 | Drift Detection & Health Monitoring | Completed |
| v6.13 | Sequential Evidence Engine, Telegram Observability Audit | In Progress |

---

## 4. v6.8 Adversarial Validation Results

**These are real forward-OOS observations collected after the hypothesis was locked at v6.7.**

```
Forward sample:       17 trades (as of v6.8 adversarial audit)
Wins:                 7
Losses:               10
Win rate:             41.18%
95% Wilson CI:        [21.64% – 63.99%]

Gross profit:         +14R
Gross loss:           −10R
Net R:                +4R
Expectancy:           +0.2353 R/trade
Profit Factor:        1.40

After MT5 execution costs:
Net R (cost-adj):     +3.15R
Expectancy (cost-adj): +0.1853 R/trade

Maximum Drawdown:     3R
```

**Statistical inference:**

```
One-sided t-test:
t  = 0.9578
p  = 0.1764   ← NOT statistically significant
```

> A p-value of 0.1764 means this result does NOT establish statistical significance.  
> The 95% Wilson confidence interval spans from below break-even (21.64%) to well above (63.99%).  
> This is consistent with random variation given N=17.

**Current conclusion:** `PROMISING — CONTINUE FORWARD COLLECTION`

> This conclusion has not been upgraded. N=17 is far below any validation gate.

---

## 5. Forward Sample Gates

Production cannot be considered until Gate D is passed. Each gate activates only when sufficient real observations have been collected.

### Gate A — N ≥ 30
Early signal monitoring. Statistical power insufficient for conclusions.

### Gate B — N ≥ 50
**Requires:**
- Expectancy > 0
- Profit Factor > 1.0

### Gate C — N ≥ 100
**Requires:**
- Expectancy > 0
- Profit Factor ≥ 1.20
- Positive Net R
- No catastrophic drawdown
- Cost-adjusted expectancy > 0

### Gate D — N ≥ 200
**Requires:**
- Positive expectancy (cost-adjusted)
- Profit Factor ≥ 1.20
- Stable walk-forward performance
- Stable per-asset performance
- Stable regime performance
- Execution cost stress survival
- No concentration dependency
- No unresolved data leakage
- No unresolved multiple-testing issue

**Current status:**

```
Forward sample collected:   11 / 200   (Gate D requirement)
Gate A (N=30):              NOT REACHED
Gate B (N=50):              NOT REACHED
Gate C (N=100):             NOT REACHED
Gate D (N=200):             NOT REACHED

EXECUTION MODE:             FORWARD DEMO ONLY
PRODUCTION STATUS:          BLOCKED
```

> Even after Gate D, production requires a separate security, deployment, and risk management review. Reaching N=200 does not automatically authorize live trading.

---

## 6. System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     TRADING DECISION LAYER                      │
│                                                                 │
│  MT5 Market Data (tick / M1 OHLCV)                             │
│         │                                                       │
│         ▼                                                       │
│  Feature Engineering                                            │
│  (9 ICT/SMC features: FVG, OB, Liquidity, Killzone, Trend)    │
│         │                                                       │
│         ▼                                                       │
│  XGBoost Inference  ──── Model SHA-256 verified                │
│         │                                                       │
│         ▼                                                       │
│  Probability Filter:  P >= 0.60  (reject if below)            │
│         │                                                       │
│         ▼                                                       │
│  Class A Asset Filter:  XAUUSD / BTCUSD / GBPUSD / EURUSD    │
│         │                                                       │
│         ▼                                                       │
│  Risk / RR Logic:  SL = 1R, TP = 2R                           │
│         │                                                       │
│         ▼                                                       │
│  Spread Gate:  reject if spread > threshold                    │
│         │                                                       │
│         ▼                                                       │
│  MT5 DEMO EXECUTION  (live account → HARD STOP)               │
│         │                                                       │
│         ▼                                                       │
│  Trade Lifecycle Monitoring                                     │
│         │                                                       │
│         ▼                                                       │
│  Forward-OOS Ledger  ──── SHA-256 hash chain, append-only      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                OBSERVABILITY / TELEMETRY LAYER                  │
│     (read-only — never influences trading decisions)            │
│                                                                 │
│  Sequential Monitoring  ──── alpha-spending always-valid tests  │
│  Drift Detection        ──── PSI, KS tests, feature shift      │
│  Asset Monitoring       ──── per-asset performance tracking     │
│  Regime Monitoring      ──── bull/bear/ranging classification   │
│  Concentration Monitor  ──── asset/session concentration risk   │
│  Execution Monitor      ──── spread, latency, execution drag    │
│  Probability Calibration ─── distribution shift monitoring     │
│  Checkpoint Reports     ──── pre-registered at N=20,25,30...   │
│                              │                                  │
│                              ▼                                  │
│  Telegram Observability  ──── notifications only, NOT trading   │
└─────────────────────────────────────────────────────────────────┘
```

> **Critical design rule**: Telegram is a notification output only.  
> It must never be on the trading decision path.  
> Telegram failure must never cause trading failure.

---

## 7. Repository Structure

```
ict-trading-bot/
│
├── bot/                          # Core trading bot
│   ├── main.py                   # Bot entry point, MT5 loop, Telegram listener
│   ├── strategy.py               # ICT/SMC strategy logic (BOS, CHOCH, FVG, OB)
│   ├── production_ml_engine.py   # XGBoost inference + probability filter
│   ├── ml_filter.py              # ML filter wrapper
│   ├── risk_manager.py           # Position sizing, drawdown limits
│   ├── mt5_client.py             # MT5 connection, order execution, window control
│   ├── regime_engine.py          # Market regime classification
│   ├── no_trade_engine.py        # No-trade condition filters (news, spread, session)
│   ├── tick_data_engine.py       # Real-time tick data subscription
│   ├── setup_quality_scorer.py   # Trade setup quality scoring
│   ├── challenger_engine.py      # Champion-challenger model framework
│   ├── judge_evaluator.py        # Model evaluation judge
│   ├── news_filter.py            # Economic calendar news filter
│   ├── config_validator.py       # Configuration validation / fail-fast
│   ├── logger.py                 # Logging setup
│   └── config.json               # Runtime configuration (symbols, RR, killzones)
│
├── services/                     # External service adapters
│   ├── telegram_bot.py           # Telegram bot command handler + notification emitter
│   ├── ai_analyzer.py            # Gemini AI trade analysis (observability only)
│   ├── db_client.py              # Supabase database client
│   ├── ml_optimizer.py           # ML hyperparameter optimization service
│   ├── observability_api.py      # Observability REST API adapter
│   ├── trade_analytics.py        # Trade analytics service
│   ├── judge_evaluator.py        # Service-layer judge evaluator
│   └── challenger_engine.py      # Service-layer challenger engine
│
├── backtest/                     # Backtesting engines
│   ├── purged_walk_forward.py    # Purged walk-forward validation
│   ├── monte_carlo.py            # Monte Carlo stress testing
│   ├── realistic_execution.py    # Execution cost simulation
│   └── tick_engine.py            # Tick-level backtest engine
│
├── data/                         # Market data + model artifacts
│   ├── *.parquet                 # M1 tick-aggregated data (13 instruments)
│   └── ml_models/
│       ├── production_xgboost_calibrated.pkl    # Frozen XGBoost + Platt calibration
│       ├── xgboost_trade_filter.pkl             # Trade filter model
│       └── production_model_metadata.json       # Model provenance + SHA-256
│
├── tests/                        # Test suite
│   ├── test_production_ml_engine.py
│   ├── test_risk_manager.py
│   ├── test_regime_engine.py
│   ├── test_no_trade_engine.py
│   ├── test_ml_filter.py
│   ├── test_setup_quality_scorer.py
│   ├── test_config_validator.py
│   ├── test_advanced_analytics.py
│   ├── test_champion_challenger.py
│   ├── test_monte_carlo.py
│   ├── test_observability_dashboard.py
│   ├── test_purged_walk_forward.py
│   ├── test_realistic_execution.py
│   ├── test_temporal_integrity.py
│   ├── test_telegram_interactive.py
│   └── test_suite.py
│
├── dashboard/                    # Streamlit observability dashboard
│   ├── app.py                    # Dashboard entry point
│   ├── app.js                    # Client-side dashboard logic
│   ├── index.html                # Dashboard HTML
│   ├── style.css                 # Dashboard styles
│   └── requirements.txt          # Dashboard dependencies
│
├── scratch/                      # Research artifacts, audit outputs, ledgers
│   ├── v6*_*.csv / .json / .md   # Versioned audit results and ledger files
│   └── ...
│
├── run_v6*.py                    # Research runner scripts (v6.6 – v6.13)
├── aura_control.ps1              # Windows control center (MT5 show/hide, dashboard, bot)
├── run_bot_background.ps1        # Silent bot launcher
├── run_bot_background.vbs        # No-window VBS launcher wrapper
├── requirements.txt              # Python dependencies
├── .env                          # Environment secrets (NOT committed)
├── .env.example                  # Secrets template (safe to commit)
└── .gitignore                    # Excludes secrets, caches, model binaries
```

---

## 8. Module Reference

### `bot/strategy.py`
Core ICT/SMC trading logic. Implements:
- Break of Structure (BOS)
- Change of Character (CHOCH)
- Fair Value Gap (FVG) detection
- Order Block (OB) detection
- Liquidity Sweep detection
- Multi-timeframe trend analysis
- Killzone session filtering (London 02:00–05:00, New York 08:00–12:00 NYT)

> **Rule**: The core strategy logic must not be modified without explicit justification, impact analysis, pre-written tests, and before/after comparative metrics.

### `bot/production_ml_engine.py`
XGBoost inference pipeline:
- Loads frozen model artifact (`production_xgboost_calibrated.pkl`)
- Verifies SHA-256 on every startup
- Applies Platt Sigmoid calibration
- Applies P ≥ 0.60 threshold filter
- Rejects trades below threshold

### `bot/risk_manager.py`
Execution risk control:
- Risk per trade: 1% of account balance
- Daily drawdown limit: 3%
- Maximum simultaneous open orders: 4
- Auto break-even trigger at 1R
- Same-currency exposure limit: 2 concurrent trades

### `services/telegram_bot.py`
Notification and observability adapter. Implements:
- Long-polling Telegram bot listener
- Command routing (`/start`, `/status`, `/balance`, etc.)
- Rate limiting and retry logic
- Duplicate notification protection
- Credential loading from environment only

> Telegram is observability-only. It has no authority over signal generation, order placement, or risk management.

---

## 9. Forward-OOS Integrity

### Ledger Design

The forward-OOS ledger is an **append-only, cryptographically linked record** of every trade taken under the frozen hypothesis.

Each row is protected by:

```
row_hash = SHA-256(all row fields concatenated)
cumulative_hash = SHA-256(previous_cumulative_hash + row_hash)
```

Genesis hash:
```
0000000000000000000000000000000000000000000000000000000000000000
```

### Why Forward Data is "Sacred"

> Forward observations must not be used to tune the current hypothesis.

Using forward results to select parameters creates a second hidden optimization loop — even a single parameter adjustment based on forward data contaminates the experiment.

AURA enforces this by:
1. Locking all hypothesis parameters before forward collection begins
2. Storing parameters in a signed hypothesis lock (`v67_hypothesis_lock.json`)
3. Verifying model SHA-256 on every inference
4. Protecting historical ledger rows from modification
5. Logging every forward trade with its feature schema hash

### Current Ledger State (v6.11)

```
Ledger file:         scratch/v611_forward_ledger.csv
Total trades:        11
Wins:                4
Losses:              7
Net R:               −4.97R (gross, includes MT5 execution cost per trade)
Integrity status:    LEDGER_INTEGRITY_VERIFIED ✅
Tamper detection:    ZERO MODIFICATIONS DETECTED
Final cumulative hash:
  135208c306f2c5c447494c12798e2bcf5831006384786d49089cc05adc0def77
```

> **Note**: The v6.11 ledger is the most recent validated snapshot. Active forward collection continues beyond this point.

---

## 10. Sequential Monitoring (v6.10)

### Philosophy

Sequential monitoring uses **pre-registered checkpoints** that activate only when sufficient real observations exist. No statistics are generated for hypothetical future observations.

### Pre-Registered Checkpoints

```
N =  20  (Gate A approach)
N =  25
N =  30  (Gate A)
N =  35
N =  40
N =  45
N =  50  (Gate B)
N =  60
N =  75
N = 100  (Gate C)
N = 125
N = 150
N = 175
N = 200  (Gate D)
```

### Always-Valid Sequential Inference

```
Framework:              Alpha-Spending (always-valid)
Current N:              11
Sequential p-value:     0.5274
Alpha spent so far:     0.002 / 0.05
Decision boundary:      NOT CROSSED
Status:                 CONTINUE DATA COLLECTION
```

### Monitoring Outputs (per checkpoint)

| Monitor | Purpose |
|---|---|
| Forward progress | Cumulative wins, losses, net R, expectancy, PF |
| Asset monitor | Per-asset performance breakdown |
| Session/regime monitor | Performance by London/NY session and market regime |
| Concentration monitor | Asset and session concentration risk |
| Probability calibration | P-score distribution shift vs. training |

---

## 11. Execution Safety (v6.11)

### Safety Architecture

```
Startup check sequence:
  1. Verify MT5 account mode → DEMO required
  2. Verify model SHA-256 → must match frozen hash
  3. Verify ledger integrity → hash chain validation
  4. Verify feature schema → must match training schema
  5. Check spread → reject if above symbol threshold
```

### Kill-Switch Events

| Event | Trigger | Action |
|---|---|---|
| `LIVE_ACCOUNT_DETECTED` | MT5 account is live/real | HARD STOP — no signals generated |
| `MODEL_HASH_MISMATCH` | Model binary SHA-256 differs from locked hash | STOP signal generation |
| `LEDGER_INTEGRITY_FAILURE` | Hash chain broken | HALT SYSTEM |
| `EXCESSIVE_SPREAD` | Symbol spread exceeds configured threshold | REJECT individual signal |

### Demo Mode Enforcement

```
MT5 REAL/LIVE ACCOUNT DETECTED
           ↓
      HARD STOP
(no orders, no signals,
 immediate logging,
 Telegram alert)
```

> Live trading is explicitly blocked. Demo enforcement is implemented in `run_v611_safety_execution_audit.py` and verified at every bot startup.

---

## 12. Drift Monitoring (v6.12)

### Current Telemetry Status

```
Status version:             v6.12
Current alert level:        GREEN
Operational verdict:        CONTINUE MONITORING
Production status:          STRICTLY BLOCKED 🔴
Current N:                  11
Current Net R (gross):      +1.0R
Current Expectancy:         +0.0909 R/trade
Current Profit Factor:      1.1429
Cost-adjusted Expectancy:   −0.4519 R/trade (negative after realistic MT5 costs)
Maximum Drawdown:           5.47R
```

> Cost-adjusted expectancy is currently negative. This does not disqualify forward collection but confirms production is not appropriate at N=11.

### Drift Detection Methods

| Test | Purpose |
|---|---|
| PSI (Population Stability Index) | Feature distribution shift between training and live |
| KS test | Kolmogorov-Smirnov test for probability score distribution shift |
| Spread monitoring | Live spread vs. historical spread baseline |
| Latency monitoring | MT5 execution latency tracking |
| Execution drag | Cost-per-trade tracking (slippage + spread) |

### Monitoring Outputs

All monitoring outputs are written to `scratch/v612_*.csv` and `scratch/v612_*.json`. These are research artifacts and are not committed to version control.

---

## 13. Telegram Observability (v6.13)

### Design Principle

```
AURA Event
     ↓
Notification Adapter
(services/telegram_bot.py)
     ↓
Telegram Bot API
     ↓
Monitoring Chat / Dashboard Alert
```

Telegram is a **one-way observability channel**. It does not feed back into trading logic.

> **Rule**: Telegram failure must never become a trading failure.  
> If the Telegram connection fails, the bot continues operating and logs the failure. No order is blocked or modified due to a Telegram error.

### Diagnostic Coverage (v6.13 Audit)

| Diagnostic | Status |
|---|---|
| Bot authentication | Verified ✅ |
| Chat ID validation | Verified ✅ |
| API connectivity (HTTP 200) | Verified ✅ |
| Message delivery | Active |
| Retry logic | Implemented |
| Rate limit handling | Implemented |
| Duplicate notification protection | Implemented |
| Credential isolation (env-only) | Enforced |

### Configuration

All Telegram credentials are stored in environment variables only. They must never appear in source code, logs, or reports.

```env
TELEGRAM_BOT_TOKEN=<REDACTED>
TELEGRAM_CHAT_ID=<REDACTED>
DASHBOARD_URL=<REDACTED>
```

---

## 14. Statistical Validation Framework

AURA is designed to **search for evidence that the strategy does not work**.

### Methods Used

| Method | Purpose |
|---|---|
| Forward OOS validation | Genuinely unseen data post-hypothesis-lock |
| Walk-forward validation | Purged time-series cross-validation |
| Wilson confidence interval | Win-rate confidence bounds |
| One-sided t-test | Expectancy significance testing |
| Bootstrap (block) | Non-parametric distribution of outcomes |
| Alpha-spending sequential test | Always-valid repeated testing |
| Asset generalization | Per-asset performance isolation |
| Leave-one-asset-out | Performance without each Class A asset |
| Regime analysis | Bull/bear/ranging regime breakdown |
| Threshold robustness | Performance at P=0.55, 0.60, 0.65, 0.70 |
| RR robustness | Performance at RR 1:1.5, 1:2, 1:2.5 |
| Execution cost stress | 2×, 5×, 10× cost stress scenarios |
| Adversarial degradation | Best-N trade removal |
| Concentration analysis | Asset and session concentration |
| Permutation test | Null hypothesis via trade label permutation |
| Multiple-testing control | Bonferroni / FDR correction tracking |

### What Is NOT Claimed

- Win rate alone does not validate a strategy
- Backtest performance does not equal forward performance
- Historical signal count does not equal trading opportunity
- Any single metric (win rate, accuracy, PF) alone is insufficient

---

## 15. Economic Validation

### Why Classification Accuracy Is Insufficient

A model can achieve 65% classification accuracy and still be economically useless if:
- It predicts wins for small gains and losses for large losses
- Transaction costs eliminate the edge
- The edge concentrates in one asset or session
- The edge disappears after the test period

### Primary Economic Metrics

```
Net R               = Wins × 2 − Losses × 1
Expectancy          = Net R / Number of Trades
Profit Factor       = Gross Profit / Gross Loss
Maximum Drawdown    = Largest peak-to-trough R loss
Cost-adj Expectancy = (Net R − Total Cost) / N Trades
Sharpe Ratio        = Risk-adjusted return (annualized)
Sortino Ratio       = Downside risk-adjusted return
Calmar Ratio        = Return / Max Drawdown
```

> Only cost-adjusted, multi-metric evaluation across sufficient observations justifies production consideration.

---

## 16. Data Integrity Architecture

### Hash Chain

Every forward trade is cryptographically linked:

```
row_i_hash     = SHA-256(trade_i fields)
cumulative_i   = SHA-256(cumulative_{i-1} + row_i_hash)
```

### Tamper Detection

Any modification to a historical row breaks the hash chain. The integrity verifier detects:
- Modified field values
- Deleted rows
- Inserted rows
- Reordered rows

### Distinction: Integrity vs. Validity

> A valid hash does not prove that a strategy works.

Data integrity proves that records have not been modified after recording. It does not prove:
- That the model generates positive expectancy
- That the results generalize
- That the forward sample is representative

---

## 17. Security Model

### Credential Hierarchy

```
Secrets
  ↓
Environment variables / .env file (local, not committed)
  ↓
Application (runtime only)
  ↓
Logs: credentials never logged
Reports: credentials never included
Code: credentials never hardcoded
```

### Principles

- `.env` is in `.gitignore` and must never be committed
- Use `.env.example` as a template with placeholder values
- API keys, passwords, tokens must not appear in:
  - Source code
  - Commit messages
  - Log files
  - Reports
  - README
- Model SHA-256 verification prevents model substitution attacks

### Environment Variable Reference

```env
# Supabase
SUPABASE_URL=<your-supabase-url>
SUPABASE_KEY=<your-supabase-anon-key>

# Telegram
TELEGRAM_BOT_TOKEN=<your-bot-token>
TELEGRAM_CHAT_ID=<your-chat-id>
DASHBOARD_URL=<your-dashboard-url>

# MetaTrader 5
MT5_LOGIN=<your-mt5-account-number>
MT5_PASSWORD=<your-mt5-password>
MT5_SERVER=<your-mt5-server>

# Gemini AI
GEMINI_API_KEY=<your-gemini-api-key>
```

---

## 18. Experiment Governance

### Experiment Registry

Every research experiment is recorded with:

```
hypothesis          — what was tested
dataset             — which data was used
parameters          — all parameter values
result              — actual outcome (positive or negative)
timestamp           — when the experiment ran
model version       — which model artifact
influenced_model    — whether result changed model selection
```

### Forward-OOS Governance Rule

> Forward-OOS data cannot be used to repeatedly re-test parameters until a positive result appears.

This is equivalent to test-set overfitting. Violations include:
- Changing the threshold after seeing forward results
- Changing the asset whitelist after seeing per-asset forward results
- Changing RR after seeing forward expectancy
- Rerunning the experiment with modified parameters to "fix" a bad forward result

---

## 19. Research Golden Rules

### Rule 1 — Never tune on forward data
Forward observations are read-only evidence. They are never used to select or adjust parameters.

### Rule 2 — Never modify the frozen hypothesis because of short-term losses
Losing trades are expected. A series of losses does not justify strategy modification during forward collection.

### Rule 3 — Never delete losing trades
Every executed trade, regardless of outcome, is permanently recorded in the forward ledger.

### Rule 4 — Never rewrite the forward ledger
The ledger is append-only and hash-chain protected. Historical rows are immutable.

### Rule 5 — Never report only successful experiments
Negative results, failed hypotheses, and unfavorable statistics are explicitly documented.

### Rule 6 — Never manufacture positive evidence
Every metric reported must derive from actual recorded trades under the frozen hypothesis.

### Rule 7 — Never allow Telegram to influence trading decisions
Telegram is an output channel only. Communication failure does not affect order generation.

### Rule 8 — Never enable live trading before explicit production gates
Production requires passing Gate D (N≥200) plus a separate independent risk and deployment review.

---

## 20. Current System Status

| Component | Status | Notes |
|---|---|---|
| Strategy baseline | 🔒 FROZEN | Locked at v6.7 / commit `7ab805d` |
| XGBoost model | 🔒 FROZEN | SHA-256 `900bd557...` |
| Probability threshold | 🔒 FROZEN | P ≥ 0.60 |
| Asset whitelist | 🔒 FROZEN | XAUUSD, BTCUSD, GBPUSD, EURUSD |
| Risk / Reward | 🔒 FROZEN | 1:2 |
| Forward OOS ledger | 📝 IN PROGRESS | N=11, verified hash chain |
| Forward ledger integrity | ✅ VERIFIED | Zero tamper detections |
| Execution mode | 🧪 DEMO ONLY | MT5 demo account |
| Live trading | 🚫 BLOCKED | Hard stop enforced |
| Sequential monitoring | 🟢 ACTIVE | Alpha-spending framework |
| Drift monitoring | 🟢 ACTIVE | PSI + KS tests, alert level GREEN |
| Asset monitoring | 🟢 ACTIVE | Per-asset performance tracked |
| Regime monitoring | 🟢 ACTIVE | Bull / bear / ranging |
| Concentration monitoring | 🟢 ACTIVE | Asset and session |
| Execution monitoring | 🟢 ACTIVE | Spread, latency, cost |
| Telegram observability | 🔍 AUDIT | v6.13 connectivity audit in progress |
| Production readiness | 🔴 NOT READY | Gate A not yet reached |

---

## 21. Operational Workflow

```
 1. Market data arrives (tick / M1)
       │
 2. Features generated
    (FVG, OB, Liquidity, Killzone, ATR, Trend — 9 features)
       │
 3. XGBoost inference
    (SHA-256 verified on model load)
       │
 4. P >= 0.60 check
    (reject signal if below threshold)
       │
 5. Class A asset check
    (reject if not in XAUUSD/BTCUSD/GBPUSD/EURUSD)
       │
 6. Spread gate check
    (reject if spread > symbol threshold)
       │
 7. Risk / RR validation
    (SL = 1R, TP = 2R)
       │
 8. Demo execution via MT5
    (HARD STOP if live account detected)
       │
 9. Trade lifecycle monitoring
    (entry, management, exit recorded)
       │
10. Forward ledger append
    (SHA-256 hash chain, row immutable after write)
       │
11. Telemetry generated
    (drift, concentration, probability)
       │
12. Safety checks enforced
    (spread, model hash, ledger integrity)
       │
13. Sequential checkpoint updated
    (if pre-registered N milestone reached)
       │
14. Telegram notification emitted
    (observability only — never blocks step 8)
```

---

## 22. Roadmap to Production Review

```
Current: N = 11 in Forward Demo
          │
          ▼
Telegram Connectivity Audit (v6.13)
          │
          ▼
Continue Forward Demo Collection
          │
          ▼
N = 30  →  Gate A Checkpoint
          │
          ▼
N = 50  →  Gate B — Expectancy > 0, PF > 1.0 required
          │
          ▼
N = 100 →  Gate C — Stricter validation
          │
          ▼
N = 200 →  Gate D — Full validation suite
          │
          ▼
Independent Final Risk Audit
(separate from AURA development team)
          │
          ▼
Production Architecture Review
(live-account safety, execution, risk)
          │
          ▼
Only then: consider limited production deployment
```

> Reaching N=200 does not automatically authorize live trading.  
> Production requires a separate, independent review that is distinct from the forward-OOS validation process.

---

## 23. Current Conclusion

> AURA currently has encouraging but statistically insufficient forward evidence.  
> The latest observed forward sample is partially positive under certain cost assumptions, but N=11 is far below the required validation thresholds (Gate A requires N=30, Gate D requires N=200).  
> Therefore the system remains a Forward Demo Research System and must not be deployed to live capital.

AURA is **not** described as:
- Profitable
- Validated
- Production-ready
- Proven

These descriptions are reserved for systems that have passed the full Gate D validation.

---

## 24. Setup & Environment

### Requirements

```
Python >= 3.10
Windows OS (MetaTrader 5 is Windows-only)
MetaTrader 5 terminal (XM Global or compatible broker)
```

### Installation

```bash
git clone https://github.com/ronagorn/ict-trading-bot.git
cd ict-trading-bot
pip install -r requirements.txt
```

### Environment Configuration

```bash
cp .env.example .env
# Edit .env and fill in your credentials
```

### Running the Bot

```bash
# Interactive control via AURA Control Center (recommended)
powershell -ExecutionPolicy Bypass -File aura_control.ps1

# Or directly
python -m bot.main
```

### Running Tests

```bash
python -m pytest tests/ -v
```

### Running the Dashboard

```bash
cd dashboard
streamlit run app.py
```

Or open the cloud dashboard at the URL configured in `DASHBOARD_URL`.

---

## Dependencies

| Package | Purpose |
|---|---|
| `MetaTrader5` | MT5 terminal connection and order execution |
| `smartmoneyconcepts` | ICT/SMC pattern detection |
| `xgboost >= 2.0` | ML trade probability filter |
| `scikit-learn >= 1.3` | Platt calibration, CV, metrics |
| `pandas >= 2.0` | Data processing |
| `numpy >= 1.24` | Numerical computation |
| `python-dotenv` | Environment secret loading |
| `supabase` | Remote trade logging database |
| `streamlit` | Observability dashboard |
| `requests` | Telegram API and HTTP |

---

## License

This repository is a private research project. No license is granted for production use without the explicit completion of the validation framework described in this document.

---

*Last updated: 2026-08-08 — AURA v6.13 — Forward Demo Research System*  
*Git HEAD: a2e4d7bd1bc2667f42313da0d7a1a579be6202d2*
