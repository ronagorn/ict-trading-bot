"""
The Challenger Optimization Engine
Searches and backtests a massive space of ICT parameters (M1, M5, M15, R:R 1:1.5 to 1:10)
using historical Tick Parquet datasets.
"""

import os
import glob
import pandas as pd
import numpy as np
from datetime import datetime
from typing import List, Dict, Any

try:
    from bot.logger import logger
except ImportError:
    import logging
    logger = logging.getLogger("ChallengerEngine")
    logging.basicConfig(level=logging.INFO)


class ChallengerEngine:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir

    def load_parquet_data(self, symbol: str) -> pd.DataFrame:
        """Loads tick-aggregated Parquet dataset for a symbol."""
        clean_name = symbol.replace("#", "").replace(".", "_")
        pattern = os.path.join(self.data_dir, f"*{clean_name}*.parquet")
        matches = glob.glob(pattern)
        if not matches:
            logger.warning(f"No parquet dataset found for {symbol} matching pattern '{pattern}'")
            return pd.DataFrame()

        filepath = matches[0]
        logger.info(f"Loading Parquet file for Challenger: {filepath}")
        df = pd.read_parquet(filepath)
        return df

    def resample_m1_to_timeframe(self, df_m1: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        """Resamples M1 aggregated data to M5 or M15 while maintaining Spread metrics."""
        if timeframe.upper() == "M1" or df_m1.empty:
            return df_m1.copy()

        rule = "5min" if timeframe.upper() == "M5" else "15min"

        resampled = pd.DataFrame({
            'Open': df_m1['Open'].resample(rule).first(),
            'High': df_m1['High'].resample(rule).max(),
            'Low': df_m1['Low'].resample(rule).min(),
            'Close': df_m1['Close'].resample(rule).last(),
            'Volume': df_m1['Volume'].resample(rule).sum(),
            'Max_Spread': df_m1['Max_Spread'].resample(rule).max(),
            'Min_Spread': df_m1['Min_Spread'].resample(rule).min(),
            'Mean_Spread': df_m1['Mean_Spread'].resample(rule).mean().round(2)
        })

        resampled.dropna(subset=['Open', 'Close'], inplace=True)
        return resampled

    def backtest_strategy(
        self,
        df: pd.DataFrame,
        timeframe: str,
        rr_ratio: float,
        fvg_atr_mult: float = 0.3,
        max_spread_filter: float = 35.0,
        use_ema_filter: bool = True,
        slippage_penalty_pts: float = 10.0,
        point_size: float = 0.01
    ) -> Dict[str, Any]:
        """
        Ultra-fast vectorized / event-driven backtest for a specific parameter combination.
        """
        if df.empty or len(df) < 50:
            return {}

        df_tf = self.resample_m1_to_timeframe(df, timeframe)
        if len(df_tf) < 50:
            return {}

        # Indicators
        high = df_tf['High'].values
        low = df_tf['Low'].values
        close = df_tf['Close'].values
        open_p = df_tf['Open'].values
        max_spread = df_tf['Max_Spread'].values

        # EMA 200
        ema200 = pd.Series(close).ewm(span=min(200, len(close) - 1)).mean().values

        # ATR 14
        tr = np.maximum(high - low, np.abs(high - np.roll(close, 1)))
        atr = pd.Series(tr).rolling(14).mean().bfill().values

        # Trade Tracking
        trades = []
        in_trade = False
        trade_type = None
        entry_price = 0.0
        sl_price = 0.0
        tp_price = 0.0
        entry_idx = 0

        n = len(df_tf)
        for i in range(2, n):
            # Check open trade execution
            if in_trade:
                curr_high = high[i]
                curr_low = low[i]

                if trade_type == "BUY":
                    if curr_low <= sl_price:
                        # Stop Loss Hit (with slippage penalty if spread was high)
                        actual_sl = sl_price
                        if max_spread[i] > max_spread_filter:
                            actual_sl -= (slippage_penalty_pts * point_size)
                        pnl_points = (actual_sl - entry_price) / point_size
                        trades.append({"type": "BUY", "pnl": pnl_points, "win": False, "hold_bars": i - entry_idx})
                        in_trade = False
                    elif curr_high >= tp_price:
                        # Take Profit Hit
                        pnl_points = (tp_price - entry_price) / point_size
                        trades.append({"type": "BUY", "pnl": pnl_points, "win": True, "hold_bars": i - entry_idx})
                        in_trade = False

                elif trade_type == "SELL":
                    if curr_high >= sl_price:
                        # Stop Loss Hit
                        actual_sl = sl_price
                        if max_spread[i] > max_spread_filter:
                            actual_sl += (slippage_penalty_pts * point_size)
                        pnl_points = (entry_price - actual_sl) / point_size
                        trades.append({"type": "SELL", "pnl": pnl_points, "win": False, "hold_bars": i - entry_idx})
                        in_trade = False
                    elif curr_low <= tp_price:
                        # Take Profit Hit
                        pnl_points = (entry_price - tp_price) / point_size
                        trades.append({"type": "SELL", "pnl": pnl_points, "win": True, "hold_bars": i - entry_idx})
                        in_trade = False

                continue

            # FVG Pattern Scanning (3-Bar Pattern: Bar i-2, Bar i-1, Bar i)
            if max_spread[i] > max_spread_filter and max_spread_filter > 0:
                continue  # Skip entry if current spread is too wide

            c_close = close[i]
            c_ema = ema200[i]
            c_atr = atr[i]

            # Bullish FVG: Low[i] > High[i-2]
            bullish_fvg_gap = low[i] - high[i - 2]
            if bullish_fvg_gap >= (c_atr * fvg_atr_mult):
                if not use_ema_filter or c_close > c_ema:
                    in_trade = True
                    trade_type = "BUY"
                    entry_price = close[i]
                    sl_price = low[i - 2] - (c_atr * 0.5)
                    risk = abs(entry_price - sl_price)
                    if risk > 0:
                        tp_price = entry_price + (risk * rr_ratio)
                        entry_idx = i
                    else:
                        in_trade = False
                    continue

            # Bearish FVG: High[i] < Low[i-2]
            bearish_fvg_gap = low[i - 2] - high[i]
            if bearish_fvg_gap >= (c_atr * fvg_atr_mult):
                if not use_ema_filter or c_close < c_ema:
                    in_trade = True
                    trade_type = "SELL"
                    entry_price = close[i]
                    sl_price = high[i - 2] + (c_atr * 0.5)
                    risk = abs(sl_price - entry_price)
                    if risk > 0:
                        tp_price = entry_price - (risk * rr_ratio)
                        entry_idx = i
                    else:
                        in_trade = False
                    continue

        if not trades:
            return {}

        # Statistical Metrics Calculation
        df_trades = pd.DataFrame(trades)
        total_trades = len(df_trades)
        wins = df_trades[df_trades['win'] == True]
        losses = df_trades[df_trades['win'] == False]
        win_rate = len(wins) / total_trades if total_trades > 0 else 0.0

        total_pnl_pts = df_trades['pnl'].sum()
        gross_profit = wins['pnl'].sum() if not wins.empty else 0.0
        gross_loss = abs(losses['pnl'].sum()) if not losses.empty else 1.0
        profit_factor = round(gross_profit / max(gross_loss, 0.001), 2)

        # Drawdown calculation
        equity_curve = df_trades['pnl'].cumsum()
        peak = equity_curve.cummax()
        drawdown = peak - equity_curve
        max_drawdown_pts = drawdown.max() if not drawdown.empty else 0.0

        avg_win_pts = wins['pnl'].mean() if not wins.empty else 0.0
        avg_loss_pts = abs(losses['pnl'].mean()) if not losses.empty else 1.0
        expectancy_pts = (win_rate * avg_win_pts) - ((1 - win_rate) * avg_loss_pts)

        # Composite Performance Score (CPS)
        cps = round(expectancy_pts * profit_factor * (win_rate * 100) / max(max_drawdown_pts, 1.0), 2)

        return {
            "timeframe": timeframe,
            "rr_ratio": rr_ratio,
            "fvg_atr_mult": fvg_atr_mult,
            "max_spread_filter": max_spread_filter,
            "use_ema_filter": use_ema_filter,
            "total_trades": total_trades,
            "win_rate_pct": round(win_rate * 100, 2),
            "profit_factor": profit_factor,
            "total_pnl_points": round(total_pnl_pts, 1),
            "max_drawdown_points": round(max_drawdown_pts, 1),
            "expectancy_points": round(expectancy_pts, 2),
            "cps_score": cps
        }

    def run_grid_search(self, symbol: str) -> List[Dict[str, Any]]:
        """Runs hyper-parameter grid search across all combinations."""
        df_m1 = self.load_parquet_data(symbol)
        if df_m1.empty:
            return []

        timeframes = ["M1", "M5", "M15"]
        rr_ratios = [1.5, 2.0, 3.0, 5.0, 8.0, 10.0]
        fvg_atr_mults = [0.2, 0.3, 0.5]
        
        # Adapt spread filters based on asset type (Crypto spreads are naturally larger in point values)
        is_crypto = any(c in symbol.upper() for c in ["BTC", "ETH", "XRP"])
        max_spread_filters = [3000.0, 5000.0, 10000.0] if is_crypto else [25.0, 35.0, 50.0]
        ema_filters = [True, False]

        candidates = []
        total_combos = len(timeframes) * len(rr_ratios) * len(fvg_atr_mults) * len(max_spread_filters) * len(ema_filters)
        logger.info(f"Grid Search Grid Size for {symbol}: {total_combos} parameter combinations...")

        for tf in timeframes:
            for rr in rr_ratios:
                for fvg in fvg_atr_mults:
                    for sp in max_spread_filters:
                        for ema in ema_filters:
                            res = self.backtest_strategy(
                                df=df_m1,
                                timeframe=tf,
                                rr_ratio=rr,
                                fvg_atr_mult=fvg,
                                max_spread_filter=sp,
                                use_ema_filter=ema
                            )
                            if res and res.get("total_trades", 0) >= 10:
                                # Avoid high-frequency M1 spread trap for Forex (where trade count is high and profit factor < 0.5)
                                if res["timeframe"] == "M1" and res["profit_factor"] < 0.5 and res["total_trades"] > 200:
                                    continue
                                candidates.append(res)

        # Sort candidates by Composite Performance Score (CPS)
        candidates.sort(key=lambda x: x["cps_score"], reverse=True)
        logger.info(f"Grid Search finished. Found {len(candidates)} valid candidate strategies for {symbol}.")
        return candidates
