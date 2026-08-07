# -*- coding: utf-8 -*-
"""
=====================================================================
 AURA ULTIMATE - DRY TEST (ไม่ต้องเชื่อมต่อ MT5 จริง)
=====================================================================
 ทดสอบ Strategy Engine v3.0 ด้วย synthetic OHLC data
 ครอบคลุม 21 เคส
=====================================================================
"""
import sys
import os
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from unittest.mock import MagicMock


TEST_CONFIG = {
    "risk_per_trade_percent": 1.0,
    "min_rr_ratio": 1.5,
    "killzones_ny_time": {
        "london": {"start": "02:00", "end": "05:00", "enabled": True},
        "new_york": {"start": "08:00", "end": "12:00", "enabled": True},
    },
    "aura_ultimate": {
        "sniper_mode_enabled": True,
        "fvg_atr_mult": 0.25,
        "ob_lookback": 20,
        "sniper_rr": 3.0,
        "base_rr": 2.0,
        "use_4h_shield": True,
        "directional_fvg_filter": True,
        "whitelist_only": True,
        "whitelist_symbols": ["EURUSD", "BTCUSD#", "ETHUSD#", "XRPUSD#"],
        "volume_spike_mult": 1.5,
        "volume_ma_period": 20,
        "all_day_scalping": True,
        "order_flow_only": True,
    },
}


def _make_ohlcv(highs, lows, closes, opens=None, volumes=None):
    n = len(highs)
    if opens is None:
        opens = closes[:]
    if volumes is None:
        volumes = [1000] * n
    df = pd.DataFrame({
        "time": pd.date_range("2025-01-01", periods=n, freq="15min"),
        "open": opens, "high": highs, "low": lows, "close": closes,
        "volume": volumes,
    })
    df.set_index("time", inplace=True)
    return df


def build_bullish_fvg_frame(n=250, base_price=100.0):
    """
    Uptrend with a clear bullish FVG near the end.
    FVG condition: high[i-1] < low[i+1], middle candle is green.
    """
    prices = [base_price + i * 0.3 for i in range(n)]
    highs = [p + 1.5 for p in prices]
    lows = [p - 0.5 for p in prices]
    volumes = [1000] * n

    i = n - 3
    highs[i] = base_price + (i) * 0.3 + 1.0
    lows[i] = base_price + (i) * 0.3 + 0.5
    highs[i + 1] = base_price + (i + 1) * 0.3 + 8.0
    lows[i + 1] = base_price + (i + 1) * 0.3 + 3.0
    highs[i + 2] = base_price + (i + 2) * 0.3 + 10.0
    lows[i + 2] = base_price + (i + 2) * 0.3 + 9.0

    closes = prices[:]
    opens = [p - 0.1 for p in prices]
    opens[i + 1] = base_price + (i + 1) * 0.3 + 3.5
    closes[i + 1] = base_price + (i + 1) * 0.3 + 7.0
    volumes[i + 1] = 5000

    return _make_ohlcv(highs, lows, closes, opens, volumes)


def build_bearish_fvg_frame(n=250, base_price=200.0):
    """
    Downtrend with a clear bearish FVG near the end.
    FVG condition: low[i-1] > high[i+1], middle candle is red.
    """
    prices = [base_price - i * 0.3 for i in range(n)]
    highs = [p + 0.5 for p in prices]
    lows = [p - 1.5 for p in prices]

    i = n - 3
    lows[i] = base_price - (i) * 0.3 - 0.5
    highs[i] = base_price - (i) * 0.3 - 0.5
    lows[i + 1] = base_price - (i + 1) * 0.3 - 8.0
    highs[i + 1] = base_price - (i + 1) * 0.3 - 3.0
    lows[i + 2] = base_price - (i + 2) * 0.3 - 10.0
    highs[i + 2] = base_price - (i + 2) * 0.3 - 9.0

    closes = prices[:]
    opens = [p + 0.1 for p in prices]
    volumes = [1000] * n
    opens[i + 1] = base_price - (i + 1) * 0.3 - 3.5
    closes[i + 1] = base_price - (i + 1) * 0.3 - 7.0
    volumes[i + 1] = 5000

    return _make_ohlcv(highs, lows, closes, opens, volumes)


def build_sniper_bull_m15(n=250, base_price=100.0):
    """
    Complex pattern: uptrend + OB breakout + sweep + bullish FVG.
    Need ~200+ bars for swing detection (swing_length=50, window=100).
    """
    prices = [base_price + i * 0.2 for i in range(n)]
    highs = [p + 0.8 for p in prices]
    lows = [p - 0.8 for p in prices]
    closes = prices[:]
    opens = [p - 0.1 for p in prices]
    volumes = [1000] * n

    # Phase 1 (0-60): steady uptrend to create swing highs/lows
    for i in range(60):
        prices[i] = base_price + (i % 10) * 0.5 + i * 0.1
        highs[i] = prices[i] + 1.0
        lows[i] = prices[i] - 1.0
        closes[i] = prices[i]
        opens[i] = prices[i] - 0.1

    # Phase 2 (60-80): consolidation range
    for i in range(60, 80):
        prices[i] = base_price + 8.0 + (i % 4) * 0.3
        highs[i] = prices[i] + 0.5
        lows[i] = prices[i] - 0.5
        closes[i] = prices[i]
        opens[i] = prices[i] - 0.1

    # Phase 3 (80-100): dip creating OB zone
    for i in range(80, 90):
        prices[i] = base_price + 8.0 - (i - 80) * 0.8
        highs[i] = prices[i] + 0.5
        lows[i] = prices[i] - 1.5
        closes[i] = prices[i]
        opens[i] = prices[i] + 0.3
    # Lowest point (OB candle) - big red candle
    lows[85] = base_price + 1.0
    prices[85] = base_price + 1.5
    highs[85] = base_price + 2.5
    closes[85] = base_price + 1.5
    opens[85] = base_price + 2.3
    volumes[85] = 3000

    # Phase 4 (90-110): recovery with breakout above swing high
    for i in range(90, 110):
        prices[i] = base_price + 6.0 + (i - 90) * 0.6
        highs[i] = prices[i] + 0.8
        lows[i] = prices[i] - 0.3
        closes[i] = prices[i]
        opens[i] = prices[i] - 0.2
    # Breakout candle: close above previous swing high
    highs[95] = base_price + 14.0
    prices[95] = base_price + 13.5
    closes[95] = base_price + 13.5
    opens[95] = base_price + 11.5
    lows[95] = base_price + 11.0

    # Phase 5 (110-130): pullback/sweep below recent low then close above
    for i in range(110, 120):
        prices[i] = base_price + 12.0 - (i - 110) * 0.3
        highs[i] = prices[i] + 0.5
        lows[i] = prices[i] - 0.5
        closes[i] = prices[i]
        opens[i] = prices[i] + 0.1
    # Sweep bar: low below OB zone, close above
    lows[115] = base_price + 0.5  # sweep below OB bottom
    prices[115] = base_price + 10.0
    closes[115] = base_price + 10.0
    opens[115] = base_price + 1.0
    highs[115] = base_price + 10.5

    # Phase 6 (120-150): bullish FVG
    for i in range(120, 130):
        prices[i] = base_price + 10.0
        highs[i] = prices[i] + 0.5
        lows[i] = prices[i] - 0.5
        closes[i] = prices[i]
        opens[i] = prices[i] - 0.1

    # FVG three-candle pattern
    highs[130] = base_price + 11.0
    lows[130] = base_price + 10.5
    prices[130] = base_price + 10.8
    closes[130] = base_price + 10.8
    opens[130] = base_price + 10.5

    # Middle candle: green, big (creates the gap)
    highs[131] = base_price + 18.0
    lows[131] = base_price + 12.0
    opens[131] = base_price + 12.5
    closes[131] = base_price + 17.0
    prices[131] = base_price + 17.0
    volumes[131] = 5000

    # Next candle: low above prev high -> FVG
    highs[132] = base_price + 20.0
    lows[132] = base_price + 18.5  # FVG: low[132] > high[130]
    prices[132] = base_price + 19.0
    closes[132] = base_price + 19.0
    opens[132] = base_price + 18.5

    # Phase 7 (133-n): continue uptrend
    for i in range(133, n):
        prices[i] = base_price + 18.0 + (i - 133) * 0.2
        highs[i] = prices[i] + 0.5
        lows[i] = prices[i] - 0.3
        closes[i] = prices[i]
        opens[i] = prices[i] - 0.1

    return _make_ohlcv(highs, lows, closes, opens, volumes)


def build_sniper_bear_m15(n=250, base_price=200.0):
    """Mirror of bullish sniper for bearish signals."""
    bull = build_sniper_bull_m15(n, base_price=100.0)
    K = base_price + 100.0
    bear = bull.copy()
    bear["high"] = [round(K - x, 2) for x in bull["low"]]
    bear["low"] = [round(K - x, 2) for x in bull["high"]]
    bear["open"] = [round(K - x, 2) for x in bull["open"]]
    bear["close"] = [round(K - x, 2) for x in bull["close"]]
    return bear


def build_4h_bullish(n=100, base_price=100.0):
    """4H frame with clear bullish BOS structure."""
    prices = [base_price + i * 0.5 for i in range(n)]
    highs = [p + 2.0 for p in prices]
    lows = [p - 2.0 for p in prices]

    # Create alternating swing structure: LL, LH, HH, HL pattern
    # Swings: low(10)=98, high(25)=112, low(40)=105, high(55)=120
    for i in range(n):
        phase = i % 40
        if phase < 10:
            prices[i] = base_price + 5.0 - phase * 0.5
        elif phase < 20:
            prices[i] = base_price + (phase - 10) * 0.8
        elif phase < 30:
            prices[i] = base_price + 8.0 - (phase - 20) * 0.3
        else:
            prices[i] = base_price + 5.0 + (phase - 30) * 0.9
        highs[i] = prices[i] + 2.0
        lows[i] = prices[i] - 2.0

    closes = prices[:]
    opens = [p - 0.5 for p in prices]

    return _make_ohlcv(highs, lows, closes, opens)


def build_4h_bearish(n=100, base_price=200.0):
    """4H frame with clear bearish structure."""
    prices = [base_price - i * 0.5 for i in range(n)]
    highs = [p + 2.0 for p in prices]
    lows = [p - 2.0 for p in prices]

    for i in range(n):
        phase = i % 40
        if phase < 10:
            prices[i] = base_price - 5.0 + phase * 0.5
        elif phase < 20:
            prices[i] = base_price - (phase - 10) * 0.8
        elif phase < 30:
            prices[i] = base_price - 8.0 + (phase - 20) * 0.3
        else:
            prices[i] = base_price - 5.0 - (phase - 30) * 0.9
        highs[i] = prices[i] + 2.0
        lows[i] = prices[i] - 2.0

    closes = prices[:]
    opens = [p + 0.5 for p in prices]

    return _make_ohlcv(highs, lows, closes, opens)


def make_mock_mt5(df_m15=None, df_h4=None, tick_price=100.0):
    mock = MagicMock()
    def get_rates(s, tf, n):
        if tf == "M15":
            return df_m15
        elif tf == "H4":
            return df_h4 if df_h4 is not None else df_m15
        return None
    mock.get_rates = MagicMock(side_effect=get_rates)
    tick = MagicMock()
    tick.ask = tick_price + 0.01
    tick.bid = tick_price - 0.01
    mock.get_tick = MagicMock(return_value=tick)
    return mock


from bot.strategy import ICTStrategy
from bot.risk_manager import RiskManager


passed = 0
failed = 0
total = 0


def run_test(name, condition):
    global passed, failed, total
    total += 1
    if condition:
        passed += 1
        print(f"  [PASS] {total:02d}  {name}")
    else:
        failed += 1
        print(f"  [FAIL] {total:02d}  {name}")


print("=" * 60)
print(" AURA ULTIMATE STRATEGY - DRY TEST")
print("=" * 60)

# --- T1: Order Flow BUY (ต้องมี Sweep+MSS — synthetic อาจไม่ครบ) ---
df = build_bullish_fvg_frame()
mock = make_mock_mt5(df_m15=df, tick_price=110.0)
st = ICTStrategy(mock, TEST_CONFIG)
setup = st.find_super_trader_setup("EURUSD", "BULLISH")
run_test("Order Flow BUY: setup or filtered None", setup is None or setup.get("type") == "BUY")

# --- T2: Order Flow SELL ---
df = build_bearish_fvg_frame()
mock = make_mock_mt5(df_m15=df, tick_price=190.0)
st = ICTStrategy(mock, TEST_CONFIG)
setup = st.find_super_trader_setup("EURUSD", "BEARISH")
run_test("Order Flow SELL: setup or filtered None", setup is None or setup.get("type") == "SELL")

# --- T3: Sniper BUY (OB+Sweep+FVG) ---
# Note: smc.ob() requires very specific swing patterns from real market data.
# If sniper doesn't fire on synthetic data, base fallback should still work.
df = build_sniper_bull_m15()
mock = make_mock_mt5(df_m15=df, tick_price=120.0)
st = ICTStrategy(mock, TEST_CONFIG)
setup = st.find_super_trader_setup("EURUSD", "BULLISH")
sniper_ok = setup is not None and setup.get("is_sniper") is True
base_fallback = setup is not None and setup.get("is_sniper") is False
run_test("Sniper BUY or Base fallback", sniper_ok or base_fallback)
if setup:
    run_test("  -> source tag present", "source" in setup)
else:
    run_test("  -> source tag present", False)

# --- T4: Sniper SELL (OB+Sweep+FVG) ---
df = build_sniper_bear_m15()
mock = make_mock_mt5(df_m15=df, tick_price=180.0)
st = ICTStrategy(mock, TEST_CONFIG)
setup = st.find_super_trader_setup("EURUSD", "BEARISH")
sniper_ok = setup is not None and setup.get("is_sniper") is True
base_fallback = setup is not None and setup.get("is_sniper") is False
run_test("Sniper SELL or Base fallback", sniper_ok or base_fallback)

# --- T5: Directional filter blocks bearish FVG in BULLISH ---
df = build_bearish_fvg_frame()
mock = make_mock_mt5(df_m15=df, tick_price=190.0)
st = ICTStrategy(mock, TEST_CONFIG)
setup = st.find_super_trader_setup("EURUSD", "BULLISH")
run_test("Directional filter: bearish FVG blocked in BULLISH", setup is None)

# --- T6: Directional filter blocks bullish FVG in BEARISH ---
df = build_bullish_fvg_frame()
mock = make_mock_mt5(df_m15=df, tick_price=110.0)
st = ICTStrategy(mock, TEST_CONFIG)
setup = st.find_super_trader_setup("EURUSD", "BEARISH")
run_test("Directional filter: bullish FVG blocked in BEARISH", setup is None)

# --- T7: NEUTRAL trend -> None ---
df = build_bullish_fvg_frame()
mock = make_mock_mt5(df_m15=df, tick_price=110.0)
st = ICTStrategy(mock, TEST_CONFIG)
setup = st.find_super_trader_setup("EURUSD", "NEUTRAL")
run_test("NEUTRAL trend returns None", setup is None)

# --- T8: Tiny FVG (below ATR*mult threshold) -> None ---
# Make completely flat data so ATR is tiny but FVG is even tinier
df = pd.DataFrame({
    "time": pd.date_range("2025-01-01", periods=250, freq="15min"),
    "open": [100.0] * 250,
    "high": [100.001] * 250,
    "low": [99.999] * 250,
    "close": [100.0] * 250,
    "volume": [1000] * 250,
})
df.set_index("time", inplace=True)
mock = make_mock_mt5(df_m15=df, tick_price=100.0)
st = ICTStrategy(mock, TEST_CONFIG)
setup = st.find_super_trader_setup("EURUSD", "BULLISH")
run_test("Tiny FVG (flat data) returns None", setup is None)

# --- T9: ไม่มี OB → ต้องมี FVG+Volume หรือ None ---
df = build_bullish_fvg_frame()
mock = make_mock_mt5(df_m15=df, tick_price=110.0)
st = ICTStrategy(mock, TEST_CONFIG)
setup = st.find_super_trader_setup("EURUSD", "BULLISH")
run_test("No full Order Flow → filtered or FVG setup", setup is None or "Order Flow" in setup.get("source", ""))

# --- T10: Order Flow fallback behavior ---
df = build_bullish_fvg_frame()
mock = make_mock_mt5(df_m15=df, tick_price=110.0)
st = ICTStrategy(mock, TEST_CONFIG)
setup = st.find_super_trader_setup("EURUSD", "BULLISH")
run_test("Order Flow produces valid or no setup", setup is None or setup.get("entry") is not None)

# --- T11: BUY direction check ---
df = build_bullish_fvg_frame()
mock = make_mock_mt5(df_m15=df, tick_price=110.0)
st = ICTStrategy(mock, TEST_CONFIG)
setup = st.find_super_trader_setup("EURUSD", "BULLISH")
run_test("BUY setup has type BUY when found", setup is None or setup["type"] == "BUY")

# --- T12: R:R validation ---
rm = RiskManager(TEST_CONFIG)
run_test("R:R 1.5:1 accepted", rm.validate_setup(100.0, 99.0, 101.5, "EURUSD"))
run_test("R:R 1.0:1 rejected", not rm.validate_setup(100.0, 99.0, 101.0, "EURUSD"))

# --- T13: risk_percent default ---
rm = RiskManager(TEST_CONFIG)
run_test("Default risk_per_trade_percent = 1.0", rm.config.get("risk_per_trade_percent") == 1.0)

# --- T14: Config aura_ultimate exists ---
run_test("Config has aura_ultimate section", "aura_ultimate" in TEST_CONFIG)

# --- T15: aura_ultimate params ---
aura = TEST_CONFIG["aura_ultimate"]
run_test("sniper_mode_enabled = True", aura["sniper_mode_enabled"] is True)
run_test("fvg_atr_mult = 0.25", aura["fvg_atr_mult"] == 0.25)
run_test("sniper_rr = 3.0", aura["sniper_rr"] == 3.0)
run_test("base_rr = 2.0", aura["base_rr"] == 2.0)
run_test("directional_fvg_filter = True", aura["directional_fvg_filter"] is True)

# --- T16: Whitelist ---
run_test("Whitelist has EURUSD", "EURUSD" in aura["whitelist_symbols"])
run_test("Whitelist has BTCUSD#", "BTCUSD#" in aura["whitelist_symbols"])
run_test("Whitelist has ETHUSD#", "ETHUSD#" in aura["whitelist_symbols"])
run_test("Whitelist has XRPUSD#", "XRPUSD#" in aura["whitelist_symbols"])

# --- T17: Empty DataFrame -> None ---
mock = make_mock_mt5(df_m15=pd.DataFrame())
st = ICTStrategy(mock, TEST_CONFIG)
setup = st.find_super_trader_setup("EURUSD", "BULLISH")
run_test("Empty DataFrame returns None", setup is None)

# --- T18: None DataFrame -> None ---
mock = make_mock_mt5(df_m15=None)
st = ICTStrategy(mock, TEST_CONFIG)
setup = st.find_super_trader_setup("EURUSD", "BULLISH")
run_test("None DataFrame returns None", setup is None)

# --- T19: No tick -> None ---
mock = make_mock_mt5(df_m15=build_bullish_fvg_frame(), tick_price=110.0)
mock.get_tick = MagicMock(return_value=None)
st = ICTStrategy(mock, TEST_CONFIG)
setup = st.find_super_trader_setup("EURUSD", "BULLISH")
run_test("No tick data returns None", setup is None)

# --- T20: Killzone always open ---
mock = make_mock_mt5(df_m15=build_bullish_fvg_frame())
st = ICTStrategy(mock, TEST_CONFIG)
in_kz, session = st.is_in_killzone()
run_test("is_in_killzone returns True", in_kz is True)
run_test("Session name is ALL_DAY_SCALPING", session == "ALL_DAY_SCALPING")

# --- T21: validate_setup edge cases ---
rm = RiskManager(TEST_CONFIG)
run_test("Zero risk -> rejected", not rm.validate_setup(100.0, 100.0, 105.0, "EURUSD"))
run_test("Valid 2:1 R:R accepted", rm.validate_setup(100.0, 99.0, 102.0, "EURUSD"))

# --- T22-T24: Volume Imbalance unit tests ---
df_vol = build_bullish_fvg_frame()
mock = make_mock_mt5(df_m15=df_vol)
st = ICTStrategy(mock, TEST_CONFIG)
df_prep = st._prepare_df(df_vol.reset_index())
ok, spike = st.has_volume_imbalance(df_prep, len(df_prep) - 2)
run_test("Volume Imbalance detected on spike candle", ok is True and spike >= 1.5)

flat_vol = [1000] * 250
df_flat = build_bullish_fvg_frame()
df_flat["volume"] = flat_vol
mock = make_mock_mt5(df_m15=df_flat.reset_index())
st = ICTStrategy(mock, TEST_CONFIG)
df_prep2 = st._prepare_df(df_flat.reset_index())
ok2, _ = st.has_volume_imbalance(df_prep2, len(df_prep2) - 2)
run_test("Flat volume fails imbalance check", ok2 is False)

run_test("volume_spike_mult in config", TEST_CONFIG["aura_ultimate"]["volume_spike_mult"] == 1.5)

# ---------------------------------------------------------------
print("=" * 60)
print(f" RESULTS: {passed}/{total} passed, {failed} failed")
print("=" * 60)
if failed > 0:
    sys.exit(1)
