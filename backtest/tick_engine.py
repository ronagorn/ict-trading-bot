"""
Tick Data Backtesting Engine
============================
Backtest ระดับ Tick ด้วย MetaTrader5.copy_ticks_range
จำลอง Dynamic Spread + Slippage แบบตลาดจริง (ไม่ใช้ M1 OHLC อย่างเดียว)

Usage:
    python -m backtest.tick_engine --symbol XAUUSD --days 7
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import MetaTrader5 as mt5
import numpy as np
import pandas as pd
import pytz

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.logger import logger
from bot.strategy import ICTStrategy


NY_TZ = pytz.timezone("America/New_York")


@dataclass
class TickTradeResult:
    symbol: str
    direction: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    sl: float
    tp: float
    outcome: str  # WIN / LOSS / BREAKEVEN
    spread_points: float
    slippage_points: float
    source: str
    pnl_r: float


@dataclass
class TickBacktestReport:
    symbol: str
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    total_r: float = 0.0
    profit_factor: float = 0.0
    avg_spread_pts: float = 0.0
    avg_slippage_pts: float = 0.0
    trades: List[TickTradeResult] = field(default_factory=list)


class TickBacktestEngine:
    """
    Tick-level backtester with realistic execution costs.

    Dynamic Spread:
      - ใช้ spread จริงจาก tick (ask - bid) / point
    Slippage Penalty (Killzone / Volatile):
      - spread > threshold → เพิ่ม slippage 15-25 points (XAUUSD default)
    """

    DEFAULT_SPREAD_SLIPPAGE = {
        "XAUUSD": {"base_slippage": 10, "volatile_slippage": 20, "spread_threshold": 25},
        "GOLD#": {"base_slippage": 10, "volatile_slippage": 20, "spread_threshold": 25},
        "GOLD": {"base_slippage": 10, "volatile_slippage": 20, "spread_threshold": 25},
        "EURUSD": {"base_slippage": 1, "volatile_slippage": 3, "spread_threshold": 3},
        "BTCUSD#": {"base_slippage": 50, "volatile_slippage": 150, "spread_threshold": 80},
        "DEFAULT": {"base_slippage": 5, "volatile_slippage": 15, "spread_threshold": 20},
    }

    def __init__(self, config: dict, symbol: str):
        self.config = config
        self.symbol = symbol
        self.point_size = 0.00001
        self.connected = False
        self._slippage_cfg = self._resolve_slippage_cfg(symbol)

    def _resolve_slippage_cfg(self, symbol: str) -> dict:
        clean = symbol.replace("#", "").upper()
        for key in (symbol, clean, clean.split(".")[0]):
            if key in self.DEFAULT_SPREAD_SLIPPAGE:
                return self.DEFAULT_SPREAD_SLIPPAGE[key]
        return self.DEFAULT_SPREAD_SLIPPAGE["DEFAULT"]

    def connect(self) -> bool:
        if mt5.terminal_info() is not None:
            self.connected = True
        else:
            self.connected = mt5.initialize()

        if not self.connected:
            logger.error(f"MT5 init failed: {mt5.last_error()}")
            return False

        candidates = [
            self.symbol,
            self.symbol.replace("#", ""),
            f"{self.symbol.replace('#', '')}#",
            "GOLD#" if "XAU" in self.symbol.upper() or "GOLD" in self.symbol.upper() else None,
        ]
        selected = None
        for sym in filter(None, candidates):
            if mt5.symbol_select(sym, True):
                selected = sym
                break

        if not selected:
            logger.error(f"Cannot select symbol {self.symbol}")
            return False

        self.symbol = selected
        info = mt5.symbol_info(self.symbol)
        if info and info.point > 0:
            self.point_size = info.point
        logger.info(f"TickBacktest connected: {self.symbol} point={self.point_size}")
        return True

    def disconnect(self):
        mt5.shutdown()
        self.connected = False

    def fetch_ticks(self, date_from: datetime, date_to: datetime) -> pd.DataFrame:
        """ดึง raw tick จาก MT5"""
        ticks = mt5.copy_ticks_range(self.symbol, date_from, date_to, mt5.COPY_TICKS_ALL)
        if ticks is None or len(ticks) == 0:
            return pd.DataFrame()

        df = pd.DataFrame(ticks)
        df["time"] = pd.to_datetime(df["time_msc"], unit="ms", utc=True)
        df["spread_pts"] = (df["ask"] - df["bid"]) / self.point_size
        df.sort_values("time", inplace=True)
        df.reset_index(drop=True, inplace=True)
        return df

    def _in_killzone(self, ts: pd.Timestamp) -> Tuple[bool, str]:
        kz = self.config.get("killzones_ny_time", {})
        ny_time = ts.tz_convert(NY_TZ).time()
        for name, cfg in kz.items():
            if not cfg.get("enabled", True):
                continue
            start = datetime.strptime(cfg["start"], "%H:%M").time()
            end = datetime.strptime(cfg["end"], "%H:%M").time()
            if start <= end:
                ok = start <= ny_time <= end
            else:
                ok = ny_time >= start or ny_time <= end
            if ok:
                return True, name.upper()
        return False, "OFF"

    def _calc_slippage(self, spread_pts: float, in_killzone: bool) -> float:
        cfg = self._slippage_cfg
        slip = cfg["base_slippage"]
        if spread_pts > cfg["spread_threshold"]:
            slip = cfg["volatile_slippage"]
        if in_killzone and spread_pts > cfg["spread_threshold"] * 0.8:
            slip = max(slip, cfg["volatile_slippage"])
        return float(slip)

    def _apply_entry_slippage(
        self, direction: str, bid: float, ask: float, spread_pts: float, in_kz: bool
    ) -> Tuple[float, float]:
        """คืน (entry_price, slippage_points)"""
        slip_pts = self._calc_slippage(spread_pts, in_kz)
        slip_price = slip_pts * self.point_size

        if direction == "BUY":
            return ask + slip_price, slip_pts
        return bid - slip_price, slip_pts

    def _apply_sl_slippage(self, direction: str, sl: float, slip_pts: float) -> float:
        """SL ถูกเลื่อนไปในทิศที่แย่ลงเมื่อ volatile"""
        slip_price = slip_pts * self.point_size * 0.5
        if direction == "BUY":
            return sl - slip_price
        return sl + slip_price

    def aggregate_m15_from_ticks(self, ticks_df: pd.DataFrame) -> pd.DataFrame:
        """สร้าง M15 OHLCV จาก tick สำหรับ strategy scan"""
        if ticks_df.empty:
            return pd.DataFrame()

        df = ticks_df.set_index("time")
        resampled = df.resample("15min").agg({
            "bid": ["first", "max", "min", "last"],
            "ask": "last",
            "spread_pts": "mean",
        })
        resampled.columns = ["open", "high", "low", "close", "ask_last", "mean_spread"]
        resampled.dropna(subset=["open", "close"], inplace=True)
        resampled["volume"] = df.resample("15min")["bid"].count()
        resampled["tick_volume"] = resampled["volume"]
        resampled.reset_index(inplace=True)
        resampled.rename(columns={"time": "time"}, inplace=True)
        return resampled

    def simulate_trade_on_ticks(
        self,
        ticks_df: pd.DataFrame,
        entry_time: datetime,
        direction: str,
        entry: float,
        sl: float,
        tp: float,
        max_hold_minutes: int = 480,
    ) -> Optional[TickTradeResult]:
        """จำลองการถือ position tick-by-tick"""
        future = ticks_df[ticks_df["time"] >= entry_time].copy()
        if future.empty:
            return None

        deadline = entry_time + timedelta(minutes=max_hold_minutes)
        future = future[future["time"] <= deadline]
        if future.empty:
            return None

        first = future.iloc[0]
        spread_pts = float(first["spread_pts"])
        in_kz, _ = self._in_killzone(first["time"])
        fill_entry, slip_pts = self._apply_entry_slippage(
            direction, first["bid"], first["ask"], spread_pts, in_kz
        )
        adj_sl = self._apply_sl_slippage(direction, sl, slip_pts)

        exit_time = future.iloc[-1]["time"]
        exit_price = float(future.iloc[-1]["bid" if direction == "BUY" else "ask"])
        outcome = "BREAKEVEN"
        risk = abs(fill_entry - adj_sl)
        if risk <= 0:
            return None

        for _, row in future.iterrows():
            bid, ask = float(row["bid"]), float(row["ask"])
            ts = row["time"]

            if direction == "BUY":
                if bid <= adj_sl:
                    outcome = "LOSS"
                    exit_price = adj_sl
                    exit_time = ts
                    break
                if bid >= tp:
                    outcome = "WIN"
                    exit_price = tp
                    exit_time = ts
                    break
            else:
                if ask >= adj_sl:
                    outcome = "LOSS"
                    exit_price = adj_sl
                    exit_time = ts
                    break
                if ask <= tp:
                    outcome = "WIN"
                    exit_price = tp
                    exit_time = ts
                    break

        if outcome == "WIN":
            pnl_r = abs(tp - fill_entry) / risk if direction == "BUY" else abs(fill_entry - tp) / risk
        elif outcome == "LOSS":
            pnl_r = -1.0
        else:
            pnl_r = 0.0

        return TickTradeResult(
            symbol=self.symbol,
            direction=direction,
            entry_time=entry_time,
            exit_time=exit_time,
            entry_price=fill_entry,
            exit_price=exit_price,
            sl=adj_sl,
            tp=tp,
            outcome=outcome,
            spread_points=spread_pts,
            slippage_points=slip_pts,
            source="tick_sim",
            pnl_r=round(pnl_r, 3),
        )

    def run_walk_forward(
        self,
        ticks_df: pd.DataFrame,
        m15_df: pd.DataFrame,
        h4_df: pd.DataFrame,
        step_bars: int = 4,
        warmup: int = 100,
    ) -> TickBacktestReport:
        """Walk-forward backtest ด้วย strategy v4 + tick execution"""
        report = TickBacktestReport(symbol=self.symbol)
        strategy = ICTStrategy(None, self.config)

        class TickClient:
            def __init__(self, m15, h4, t, point_size):
                self.m15 = m15
                self.h4 = h4
                self.t = t
                self.point_size = point_size

            def get_rates(self, symbol, tf, n):
                src = self.h4 if tf == "H4" else self.m15
                sub = src[src["time"] <= self.t]
                return sub.tail(n) if not sub.empty else None

            def get_tick(self, symbol):
                class T:
                    pass
                row = self.m15[self.m15["time"] <= self.t].tail(1)
                if row.empty:
                    return None
                c = float(row.iloc[0]["close"])
                t = T()
                t.bid = c
                t.ask = c + self.point_size * 2
                return t

        for i in range(warmup, len(m15_df) - step_bars, step_bars):
            bar_time = m15_df.iloc[i]["time"]
            client = TickClient(m15_df, h4_df, bar_time, self.point_size)
            strategy.mt5 = client

            try:
                trend = strategy.analyze_market_structure(self.symbol)
            except Exception:
                continue
            if trend == "NEUTRAL":
                continue

            setup = strategy.find_super_trader_setup(
                self.symbol, trend,
                df_m15=client.get_rates(self.symbol, "M15", 250),
            )
            if setup is None:
                continue

            entry_time = m15_df.iloc[i + 1]["time"]
            result = self.simulate_trade_on_ticks(
                ticks_df,
                entry_time,
                setup["type"],
                setup["entry"],
                setup["sl"],
                setup["tp"],
            )
            if result is None:
                continue

            result.source = setup.get("source", "Order Flow")
            report.trades.append(result)

        self._finalize_report(report)
        return report

    @staticmethod
    def _finalize_report(report: TickBacktestReport):
        report.total_trades = len(report.trades)
        if report.total_trades == 0:
            return

        report.wins = sum(1 for t in report.trades if t.outcome == "WIN")
        report.losses = sum(1 for t in report.trades if t.outcome == "LOSS")
        report.win_rate = round(report.wins / report.total_trades * 100, 2)
        report.total_r = round(sum(t.pnl_r for t in report.trades), 2)

        gross_win = sum(t.pnl_r for t in report.trades if t.pnl_r > 0)
        gross_loss = abs(sum(t.pnl_r for t in report.trades if t.pnl_r < 0))
        report.profit_factor = round(gross_win / gross_loss, 2) if gross_loss > 0 else gross_win
        report.avg_spread_pts = round(
            sum(t.spread_points for t in report.trades) / report.total_trades, 2
        )
        report.avg_slippage_pts = round(
            sum(t.slippage_points for t in report.trades) / report.total_trades, 2
        )

    def fetch_h4(self, date_from: datetime, date_to: datetime) -> pd.DataFrame:
        rates = mt5.copy_rates_range(self.symbol, mt5.TIMEFRAME_H4, date_from, date_to)
        if rates is None:
            return pd.DataFrame()
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        return df

    def run(self, days_back: int = 14) -> TickBacktestReport:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days_back)

        ticks = self.fetch_ticks(start, end)
        if ticks.empty:
            logger.error("No tick data — check MT5 connection and symbol history")
            return TickBacktestReport(symbol=self.symbol)

        m15 = self.aggregate_m15_from_ticks(ticks)
        h4 = self.fetch_h4(start, end)
        if m15.empty:
            return TickBacktestReport(symbol=self.symbol)

        logger.info(f"Tick backtest {self.symbol}: {len(ticks):,} ticks, {len(m15)} M15 bars")
        return self.run_walk_forward(ticks, m15, h4)


def load_config() -> dict:
    cfg_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "bot", "config.json",
    )
    with open(cfg_path, "r", encoding="utf-8") as f:
        return json.load(f)


def print_report(report: TickBacktestReport):
    print("\n" + "=" * 70)
    print(f"  TICK BACKTEST REPORT — {report.symbol}")
    print("=" * 70)
    print(f"  Total Trades     : {report.total_trades}")
    print(f"  Wins / Losses    : {report.wins} / {report.losses}")
    print(f"  Win Rate         : {report.win_rate}%")
    print(f"  Total R          : {report.total_r:+.2f}")
    print(f"  Profit Factor    : {report.profit_factor}")
    print(f"  Avg Spread (pts) : {report.avg_spread_pts}")
    print(f"  Avg Slippage(pts): {report.avg_slippage_pts}")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="AURA Tick Backtesting Engine")
    parser.add_argument("--symbol", default="GOLD#", help="MT5 symbol (e.g. GOLD#, XAUUSD)")
    parser.add_argument("--days", type=int, default=14, help="Days of tick history")
    args = parser.parse_args()

    config = load_config()
    engine = TickBacktestEngine(config, args.symbol)

    if not engine.connect():
        sys.exit(1)

    try:
        report = engine.run(days_back=args.days)
        print_report(report)
    finally:
        engine.disconnect()


if __name__ == "__main__":
    main()
