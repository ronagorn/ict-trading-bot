import sys
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import os
os.environ['PYTHONIOENCODING'] = 'utf-8'

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime
from collections import defaultdict


# ---------------------------------------------------------------------------
#  Config
# ---------------------------------------------------------------------------
SYMBOLS = ["BTCUSD#", "ETHUSD#", "XRPUSD#"]
M15_BARS = 2000
H4_BARS = 500
STEP = 15
START_OFFSET = 200
MAX_HOLD_BARS = 200

TEST_CONFIG = {
    "risk_per_trade_percent": 1.0,
    "min_rr_ratio": 1.5,
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
    },
}

TF_MAP = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
}


# ---------------------------------------------------------------------------
#  Tick mock for strategy
# ---------------------------------------------------------------------------
class TickMock:
    def __init__(self, bid, ask):
        self.bid = bid
        self.ask = ask
        self.last = (bid + ask) / 2


# ---------------------------------------------------------------------------
#  BacktestClient — wraps pre-loaded data for strategy consumption
# ---------------------------------------------------------------------------
class BacktestClient:
    """Drop-in replacement for MT5Client during walk-forward backtest."""

    def __init__(self, symbol, m15_df, h4_df, current_time):
        self.symbol = symbol
        self.m15_full = m15_df
        self.h4_full = h4_df
        self.current_time = current_time
        self.connected = True

    def get_rates(self, symbol, timeframe, num_bars):
        if timeframe == "H4" or timeframe == mt5.TIMEFRAME_H4:
            df = self.h4_full
            tf_key = "H4"
        else:
            df = self.m15_full
            tf_key = "M15"

        df = df[df["time"] <= self.current_time].copy()
        if df.empty:
            return None
        return df.tail(num_bars)

    def get_tick(self, symbol):
        df = self.m15_full[self.m15_full["time"] <= self.current_time].copy()
        if df.empty:
            return None
        last = df.iloc[-1]
        close = float(last["close"])
        return TickMock(bid=close, ask=close)

    def ensure_symbol_selected(self, symbol):
        return True

    def ensure_connection(self):
        pass


# ---------------------------------------------------------------------------
#  Data fetching from live MT5
# ---------------------------------------------------------------------------
def fetch_data(symbol):
    """Pull M15 and H4 data from MT5."""
    print(f"  Fetching {symbol} data...", end=" ", flush=True)

    mt5.symbol_select(symbol, True)

    m15_rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, M15_BARS)
    if m15_rates is None:
        print(f"FAILED (M15): {mt5.last_error()}")
        return None, None
    m15_df = pd.DataFrame(m15_rates)
    m15_df["time"] = pd.to_datetime(m15_df["time"], unit="s")

    h4_rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H4, 0, H4_BARS)
    if h4_rates is None:
        print(f"FAILED (H4): {mt5.last_error()}")
        return None, None
    h4_df = pd.DataFrame(h4_rates)
    h4_df["time"] = pd.to_datetime(h4_df["time"], unit="s")

    print(f"OK (M15: {len(m15_df)}, H4: {len(h4_df)})")
    return m15_df, h4_df


# ---------------------------------------------------------------------------
#  Walk-forward backtest for one symbol
# ---------------------------------------------------------------------------
def backtest_symbol(symbol, m15_df, h4_df, strategy, config):
    """Run walk-forward backtest on a single symbol. Return list of trade dicts."""
    trades = []
    risk_pct = config["risk_per_trade_percent"]

    for start in range(START_OFFSET, len(m15_df) - STEP, STEP):
        current_time = m15_df.iloc[start]["time"]

        client = BacktestClient(symbol, m15_df, h4_df, current_time)
        strategy.mt5 = client

        try:
            trend = strategy.analyze_market_structure(symbol)
        except Exception:
            continue

        if trend == "NEUTRAL":
            continue

        try:
            setup = strategy.find_super_trader_setup(symbol, trend)
        except Exception:
            continue

        if setup is None:
            continue

        entry = setup["entry"]
        sl = setup["sl"]
        tp = setup["tp"]
        direction = setup["type"]
        source = setup.get("source", "Base FVG")

        if "Sniper" in source:
            mode = "Sniper"
        elif "OB+FVG" in source:
            mode = "OB+FVG"
        else:
            mode = "Base"

        risk_price = abs(entry - sl)
        if risk_price <= 0:
            continue

        # Enter at OPEN of next bar (not close of signal bar)
        if start + 1 >= len(m15_df):
            continue
        actual_entry = float(m15_df.iloc[start + 1]["open"])

        # Recalculate SL/TP relative to actual entry
        if direction == "BUY":
            sl_dist = entry - sl
            tp_dist = tp - entry
            sl = actual_entry - sl_dist
            tp = actual_entry + tp_dist
        else:
            sl_dist = sl - entry
            tp_dist = entry - tp
            sl = actual_entry + sl_dist
            tp = actual_entry - tp_dist

        entry_bar_idx = start + 1
        result = simulate_trade(m15_df, entry_bar_idx, direction, entry, sl, tp)

        if result is None:
            continue

        r_multiple = result["r_multiple"]

        trades.append({
            "entry_bar": entry_bar_idx,
            "entry_time": m15_df.iloc[entry_bar_idx]["time"],
            "direction": direction,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "is_sniper": mode == "Sniper",
            "mode": mode,
            "result": result["outcome"],
            "r_multiple": r_multiple,
            "exit_bar": result["exit_bar"],
            "hold_bars": result["exit_bar"] - entry_bar_idx,
        })

    return trades


# ---------------------------------------------------------------------------
#  Simulate trade execution bar-by-bar
# ---------------------------------------------------------------------------
def simulate_trade(m15_df, entry_bar_idx, direction, entry, sl, tp):
    """Walk forward from entry bar to check TP/SL hit."""
    total_bars = len(m15_df)
    end = min(entry_bar_idx + MAX_HOLD_BARS, total_bars)

    risk = abs(entry - sl)
    reward = abs(tp - entry)
    rr = reward / risk if risk > 0 else 1.0

    for i in range(entry_bar_idx + 1, end):
        bar = m15_df.iloc[i]
        high = float(bar["high"])
        low = float(bar["low"])

        if direction == "BUY":
            if low <= sl:
                return {"outcome": "LOSS", "r_multiple": -1.0, "exit_bar": i}
            if high >= tp:
                return {"outcome": "WIN", "r_multiple": rr, "exit_bar": i}
        else:  # SELL
            if high >= sl:
                return {"outcome": "LOSS", "r_multiple": -1.0, "exit_bar": i}
            if low <= tp:
                return {"outcome": "WIN", "r_multiple": rr, "exit_bar": i}

    # Timeout — no result (count as loss)
    return {"outcome": "LOSS", "r_multiple": -0.5, "exit_bar": end}


# ---------------------------------------------------------------------------
#  Result aggregation & printing
# ---------------------------------------------------------------------------
def aggregate_results(all_trades):
    """Aggregate trades by symbol, mode, direction."""
    stats = defaultdict(lambda: {"wins": 0, "losses": 0, "total_r": 0.0, "trades": 0})

    for t in all_trades:
        key = (t["symbol"], t["mode"], t["direction"])
        stats[key]["trades"] += 1
        stats[key]["total_r"] += t["r_multiple"]
        if t["result"] == "WIN":
            stats[key]["wins"] += 1
        else:
            stats[key]["losses"] += 1

    return stats


def print_summary(all_trades, stats, risk_pct):
    """Print formatted summary table."""
    print("\n" + "=" * 100)
    print("  AURA ULTIMATE BACKTEST RESULTS")
    print("=" * 100)

    header = f"{'Symbol':<14} {'Mode':<9} {'Dir':<6} {'Wins':>5} {'Loss':>5} {'Total':>5} {'WinRate':>9} {'Total R':>10} {'PF':>8}"
    print(header)
    print("-" * 100)

    overall_wins = 0
    overall_losses = 0
    overall_r = 0.0
    overall_trades = 0

    for symbol in SYMBOLS:
        sym_wins = 0
        sym_losses = 0
        sym_r = 0.0
        sym_trades = 0

        for mode in ["Sniper", "OB+FVG", "Base"]:
            for direction in ["BUY", "SELL"]:
                key = (symbol, mode, direction)
                if key not in stats:
                    continue
                s = stats[key]
                if s["trades"] == 0:
                    continue

                wins = s["wins"]
                losses = s["losses"]
                total = s["trades"]
                wr = (wins / total * 100) if total > 0 else 0
                pf = (sum(1 for t in all_trades if t["symbol"] == symbol and t["mode"] == mode and t["direction"] == direction and t["result"] == "WIN") /
                      max(1, sum(1 for t in all_trades if t["symbol"] == symbol and t["mode"] == mode and t["direction"] == direction and t["result"] == "LOSS")))
                total_r = s["total_r"]

                print(f"{symbol:<14} {mode:<9} {direction:<6} {wins:>5} {losses:>5} {total:>5} {wr:>8.1f}% {total_r:>+10.2f} {pf:>8.2f}")

                sym_wins += wins
                sym_losses += losses
                sym_r += total_r
                sym_trades += total

        if sym_trades > 0:
            sym_wr = sym_wins / sym_trades * 100
            sym_pf = (sym_wins / max(1, sym_losses))
            print(f"  {'SUBTOTAL':<12} {'':>9} {'':>6} {sym_wins:>5} {sym_losses:>5} {sym_trades:>5} {sym_wr:>8.1f}% {sym_r:>+10.2f} {sym_pf:>8.2f}")
            print("-" * 100)

        overall_wins += sym_wins
        overall_losses += sym_losses
        overall_r += sym_r
        overall_trades += sym_trades

    print("=" * 100)
    overall_wr = (overall_wins / overall_trades * 100) if overall_trades > 0 else 0
    overall_pf = overall_wins / max(1, overall_losses)
    roi = overall_r * risk_pct / 100
    print(f"{'OVERALL':<14} {'':>9} {'':>6} {overall_wins:>5} {overall_losses:>5} {overall_trades:>5} {overall_wr:>8.1f}% {overall_r:>+10.2f} {overall_pf:>8.2f}")
    print(f"\n  Risk per trade: {risk_pct}%")
    print(f"  Total R multiples: {overall_r:+.2f}")
    print(f"  Estimated ROI: {roi:+.2f}%")
    print(f"  Total trades evaluated: {overall_trades}")
    print("=" * 100)


# ---------------------------------------------------------------------------
#  Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 70)
    print("  AURA Ultimate Walk-Forward Backtest")
    print("  Symbols:", ", ".join(SYMBOLS))
    print("=" * 70)

    # Init MT5
    if not mt5.initialize():
        print(f"MT5 initialization failed: {mt5.last_error()}")
        return
    print(f"MT5 connected: {mt5.terminal_info().company if mt5.terminal_info() else 'Unknown'}")

    # Import strategy
    from bot.strategy import ICTStrategy

    strategy = ICTStrategy(None, TEST_CONFIG)

    # Collect all trades
    all_trades = []

    for symbol in SYMBOLS:
        print(f"\n[{symbol}]")
        m15_df, h4_df = fetch_data(symbol)
        if m15_df is None or h4_df is None:
            print(f"  Skipping {symbol} — no data")
            continue

        trades = backtest_symbol(symbol, m15_df, h4_df, strategy, TEST_CONFIG)
        for t in trades:
            t["symbol"] = symbol
        all_trades.extend(trades)

        # Per-symbol mini summary
        wins = sum(1 for t in trades if t["result"] == "WIN")
        losses = sum(1 for t in trades if t["result"] == "LOSS")
        total_r = sum(t["r_multiple"] for t in trades)
        print(f"  Result: {len(trades)} trades | {wins}W / {losses}L | Total R: {total_r:+.2f}")

    # Aggregate and print
    stats = aggregate_results(all_trades)
    print_summary(all_trades, stats, TEST_CONFIG["risk_per_trade_percent"])

    mt5.shutdown()
    print("\nMT5 shutdown complete.")


if __name__ == "__main__":
    main()
