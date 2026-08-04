# AURA Trading Bot v3.0

> AI-Powered ICT/SMC Trading Bot for MetaTrader 5 — 4H Shield + M15 FVG Sniper Entry

![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue)
![MetaTrader5](https://img.shields.io/badge/MetaTrader-5-0052FF)
![License](https://img.shields.io/badge/License-MIT-green)

---

## What Is This?

A fully automated trading bot that uses **ICT (Inner Circle Trader) / SMC (Smart Money Concepts)** strategies on MetaTrader 5. It runs on Windows, connects to your XM Global MT5 terminal, and trades 24/7 with multi-layer risk management.

**Core Strategy:** 4H Trend Shield (BOS/CHOCH detection) → M15 FVG Entry (Fair Value Gap) → Sniper Confluence (OB + Sweep + FVG)

---

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    AURA TRADING BOT                     │
├──────────┬──────────┬──────────┬──────────┬─────────────┤
│  MT5     │ Strategy │   Risk   │ Telegram │  Services   │
│  Client  │  Engine  │ Manager  │   Bot    │  Layer      │
├──────────┼──────────┼──────────┼──────────┼─────────────┤
│ Connect  │ 4H BOS/  │ Lot calc │ Thai NLP │ Supabase    │
│ Fetch    │ CHOCH    │ R:R      │ Commands │ AI Gemini   │
│ Orders   │ OB det.  │ Correl.  │ Alerts   │ Trade Log   │
│ Spread   │ Sweep    │ Drawdown │ Pa/Resu  │ Analysis    │
│ Hide UI  │ FVG      │ Breakevn │ Keyboard │             │
└──────────┴──────────┴──────────┴──────────┴─────────────┘
```

### Strategy Engine (v3.0 AURA Ultimate)

```
Entry Priority:
  1. Sniper Setup   = OrderBlock + LiquiditySweep + FVG (3-confluence, 3.5R)
  2. Base FVG Setup = FVG only with 4H directional filter (2.5R)

4H Shield (Trend Gate):
  - Detects BOS (Break of Structure) / CHOCH (Change of Character)
  - BULLISH → only BUY entries allowed
  - BEARISH → only SELL entries allowed
  - NEUTRAL → no trades

M15 Entry Logic:
  - Detects Fair Value Gaps (FVG) using smartmoneyconcepts library
  - FVG must be minimum 0.5x ATR in size
  - Entry at FVG zone, SL below FVG, TP at 2.5R
```

### Risk Management (6 Layers)

| Layer | Rule | Default |
|-------|------|---------|
| 1 | Max open orders per symbol | 2 |
| 2 | Max total open orders | 4 |
| 3 | Currency correlation filter | Max 2 per group |
| 4 | Daily drawdown circuit breaker | 3% |
| 5 | Max trades per day | 30 |
| 6 | Position sizing | 1% risk per trade |

---

## Quick Start (5 Minutes)

### Prerequisites

- **Windows 10/11** (MT5 Python package is Windows-only)
- **Python 3.11+**
- **XM Global MT5 Terminal** installed ([Download](https://www.xmglobal.com/metatrader-5))
- **MT5 Account** (Demo or Real)

### 1. Clone & Install

```bash
git clone https://github.com/ronagorn/ict-trading-bot.git
cd ict-trading-bot
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in your credentials:

```bash
copy .env.example .env
```

Edit `.env`:
```env
MT5_LOGIN=your_mt5_account_number
MT5_PASSWORD=your_mt5_password
MT5_SERVER=XMGlobal-MT5 5

# Optional (for alerts)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Optional (for trade logging)
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
```

### 3. Configure Trading Pairs

Edit `bot/config.json` — `aura_ultimate.whitelist_symbols`:

```json
{
  "aura_ultimate": {
    "whitelist_symbols": ["EURUSD", "BTCUSD#", "ETHUSD#", "XRPUSD#"],
    "base_rr": 2.5,
    "sniper_rr": 3.5,
    "fvg_atr_mult": 0.5
  }
}
```

> **Note:** Crypto pairs on XM use `#` suffix (e.g., `BTCUSD#`, `ETHUSD#`)

### 4. Run

```bash
# Foreground (see logs)
python -m bot.main

# Background (Windows)
run_bot_background.vbs

# Or use batch file
run_bot.bat
```

---

## Project Structure

```
├── bot/                        # Core trading engine
│   ├── main.py                 # Entry point — main event loop
│   ├── strategy.py             # ICT/SMC strategy (FVG, OB, Sweep, BOS/CHOCH)
│   ├── mt5_client.py           # MT5 connection, orders, data fetch
│   ├── risk_manager.py         # Position sizing, drawdown, correlation
│   ├── news_filter.py          # Economic news time guard
│   ├── logger.py               # Rotating file + console logging
│   ├── config.json             # Trading configuration
│   ├── challenger_engine.py    # Strategy optimization grid search
│   ├── judge_evaluator.py      # Champion vs Challenger evaluator
│   ├── tick_data_engine.py     # Historical tick data aggregator
│   └── backtest_real.py        # Portfolio-level backtest
│
├── services/                   # External integrations
│   ├── telegram_bot.py         # Telegram bot (Thai NLP, commands, alerts)
│   ├── db_client.py            # Supabase trade logging
│   └── ai_analyzer.py          # Gemini AI trade analysis
│
├── dashboard/                  # Streamlit web dashboard
│   └── app.py                  # Glassmorphism dark theme UI
│
├── tests/                      # Test suites
│   ├── test_suite.py           # Core system diagnostic (4 tests)
│   ├── test_telegram_interactive.py  # Telegram command tests (5 tests)
│   └── test_aura_ultimate_strategy.py # Strategy dry tests (21 cases)
│
├── run_aura_backtest.py        # Walk-forward backtest runner
├── rr_sweep.py                 # R:R parameter optimizer
├── requirements.txt            # Python dependencies
├── .env.example                # Environment template
└── render.yaml                 # Render.com deployment config
```

---

## Backtesting

### Walk-Forward Backtest

Tests the strategy on real MT5 historical data with simulated execution:

```bash
python run_aura_backtest.py
```

Output example:
```
Symbol         Mode      Dir     Wins  Loss Total   WinRate    Total R       PF
─────────────────────────────────────────────────────────────────────────────
BTCUSD#        Base      SELL      18    35    53     34.0%      -1.07     0.51
ETHUSD#        Base      BUY       19    41    60     31.7%      -4.08     0.46
XRPUSD#        Base      SELL      18    37    55     32.7%      -2.87     0.49
─────────────────────────────────────────────────────────────────────────────
OVERALL                            55   113   168     32.7%      -8.02     0.49
```

### Parameter Optimization (R:R Sweep)

Finds optimal Risk:Reward ratio and FVG ATR multiplier:

```bash
python rr_sweep.py
```

Best parameters found (Aug 2026):
| RR | FVG_ATR | Trades | Win Rate | Total R |
|----|---------|--------|----------|---------|
| 2.0 | 0.50 | 179 | 40.2% | **+41.00** |
| 2.5 | 0.50 | 179 | 34.1% | **+39.00** |
| 3.0 | 0.50 | 185 | 25.4% | +9.00 |

---

## Configuration Reference

### `bot/config.json` — Key Settings

```json
{
  "risk_per_trade_percent": 1.0,
  "max_orders_per_symbol": 2,
  "max_total_open_orders": 4,
  "max_trades_per_day": 30,
  "daily_drawdown_limit_percent": 3.0,

  "aura_ultimate": {
    "sniper_mode_enabled": true,
    "use_4h_shield": true,
    "directional_fvg_filter": true,
    "whitelist_only": true,
    "whitelist_symbols": ["EURUSD", "BTCUSD#", "ETHUSD#", "XRPUSD#"],

    "base_rr": 2.5,
    "sniper_rr": 3.5,
    "fvg_atr_mult": 0.5,
    "ob_lookback": 20
  }
}
```

### Symbol Whitelist

| Symbol | Broker Name | Notes |
|--------|-------------|-------|
| EURUSD | EURUSD | Forex major |
| BTCUSD# | BTCUSD# | Crypto (XM suffix #) |
| ETHUSD# | ETHUSD# | Crypto (XM suffix #) |
| XRPUSD# | XRPUSD# | Crypto (XM suffix #) |
| GOLD# | GOLD# | Gold (XM suffix #) |

---

## Telegram Bot Commands

The bot responds to Thai natural language:

| Command | Thai Example | Description |
|---------|-------------|-------------|
| /status | "ยังรันอยู่ไหม" | Check if bot is running |
| /balance | "เงินเหลือเท่าไหร่" | Show account balance |
| /positions | "มีออเดอร์อะไรบ้าง" | List open positions |
| /pause | "หยุดเทรดก่อน" | Pause trading |
| /resume | "เทรดต่อ" | Resume trading |
| /ai | "วิเคราะห์ให้หน่อย" | AI analysis of recent trades |

---

## Deployment

### Local Windows (Recommended)

```bash
# Run in background (hidden from taskbar)
run_bot_background.vbs

# Or with console visible
python -m bot.main
```

### Render.com (Cloud)

> ⚠️ Requires MetaAPI bridge (not yet implemented) since MT5 is Windows-only.

```bash
# render.yaml is pre-configured as Background Worker
# Dashboard runs as separate Web Service
```

### Autostart on Windows Boot

```powershell
# Run in PowerShell as Admin
.\setup_autostart.ps1
```

---

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test suite
python -m pytest tests/test_suite.py -v

# Run strategy dry tests (no MT5 needed)
python -m pytest tests/test_aura_ultimate_strategy.py -v
```

---

## Known Limitations

1. **Windows Only** — MetaTrader5 Python package only works on Windows
2. **XM Broker Specific** — Crypto symbols use `#` suffix (e.g., `BTCUSD#`)
3. **Single Account** — Runs one MT5 account at a time
4. **News Filter Stub** — Economic calendar integration is placeholder only
5. **Auto-Breakeven** — Implemented but not yet wired into main loop

---

## Development Roadmap

### Completed
- [x] 4H Shield (BOS/CHOCH trend detection)
- [x] M15 FVG entry with directional filter
- [x] Sniper confluence (OB + Sweep + FVG)
- [x] Multi-layer risk management
- [x] Telegram bot with Thai NLP
- [x] Walk-forward backtest engine
- [x] R:R parameter optimizer
- [x] MT5 window hide/unhide
- [x] Single-instance guard

### In Progress
- [ ] Auto-Breakeven integration into main loop
- [ ] News filter with real economic calendar API
- [ ] Fix strategy SELL TP default value consistency

### Planned
- [ ] MetaAPI cloud bridge (Linux deployment)
- [ ] Trailing stop loss system
- [ ] Multi-timeframe FVG confluence (M5 + M15 + H1)
- [ ] Machine learning signal scoring
- [ ] Web dashboard real-time monitoring
- [ ] Docker containerization

---

## Performance Notes

Backtested on real MT5 M15 data (Aug 2026, 2000 bars):

| Config | Win Rate | Total R | Profit Factor |
|--------|----------|---------|---------------|
| RR 2.0, FVG 0.5 | 40.2% | +41.00 | 1.35 |
| RR 2.5, FVG 0.5 | 34.1% | +39.00 | 1.12 |
| RR 3.0, FVG 0.5 | 25.4% | +9.00 | 0.85 |

> ⚠️ Past performance does not guarantee future results. Always use demo accounts first.

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11+ |
| Broker API | MetaTrader5 (Windows) |
| Strategy | ICT/SMC (smartmoneyconcepts) |
| Database | Supabase (PostgreSQL) |
| AI | Google Gemini 1.5 Flash |
| Alerts | Telegram Bot API |
| Dashboard | Streamlit |
| Testing | pytest |

---

## License

MIT License — use freely for personal and commercial purposes.

---

## Disclaimer

This software is for **educational purposes only**. Trading financial instruments carries significant risk. The authors are not responsible for any financial losses incurred from using this software. Always test thoroughly on demo accounts before live trading.
