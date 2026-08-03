"""
Multi-Period Backtest Engine (1 Day, 1 Month, 1 Year)
Evaluates all 12 asset strategies across multiple time horizons using optimized config presets.
"""

import json
import logging
import pandas as pd
import numpy as np
import MetaTrader5 as mt5
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("backtest_periods")

class MultiPeriodBacktester:
    def __init__(self, config_path: str = "bot/config.json"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)
        self.presets = self.config.get("optimized_strategy_presets", {})
        self.max_spread_config = self.config.get("max_spread_points", {})

    def resolve_symbol(self, symbol: str) -> str:
        """Resolves MT5 symbol name considering broker suffixes."""
        if not mt5.initialize():
            return symbol
        
        candidates = [symbol, symbol.replace("#", ""), symbol + "#", symbol + ".", symbol + "m"]
        if "GOLD" in symbol.upper() or "XAU" in symbol.upper():
            candidates.extend(["GOLD#", "XAUUSD#", "GOLD", "XAUUSD", "GOLD.a", "GOLD.i"])
        
        for cand in candidates:
            info = mt5.symbol_info(cand)
            if info is not None:
                mt5.symbol_select(cand, True)
                return cand
        return symbol

    def fetch_historical_candles(self, symbol: str, timeframe_str: str, days: int = 365) -> pd.DataFrame:
        """Fetches historical candles from MT5 for a specified timeframe and date range."""
        if not mt5.initialize():
            return pd.DataFrame()
        
        real_sym = self.resolve_symbol(symbol)
        tf_map = {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1
        }
        mt5_tf = tf_map.get(timeframe_str, mt5.TIMEFRAME_M15)
        
        end_dt = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(days=days)
        
        rates = mt5.copy_rates_range(real_sym, mt5_tf, start_dt, end_dt)
        if rates is None or len(rates) == 0:
            # Fallback to copy_rates_from_pos
            bars_count = 50000
            rates = mt5.copy_rates_from_pos(real_sym, mt5_tf, 0, bars_count)
            
        if rates is None or len(rates) == 0:
            logger.warning(f"Could not fetch candle history for {symbol} ({real_sym})")
            return pd.DataFrame()

        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
        df.set_index('time', inplace=True)
        
        # Add Spread estimations in points if missing
        info = mt5.symbol_info(real_sym)
        point_size = info.point if info and info.point > 0 else 0.00001
        
        if 'spread' in df.columns:
            df['Mean_Spread'] = df['spread'].astype(float)
        else:
            default_sp = info.spread if info else 15
            df['Mean_Spread'] = default_sp
            
        df.rename(columns={
            'open': 'Open',
            'high': 'High',
            'low': 'Low',
            'close': 'Close',
            'tick_volume': 'Volume'
        }, inplace=True)
        
        df['point_size'] = point_size
        return df

    def backtest_dataset(
        self,
        df: pd.DataFrame,
        rr_ratio: float,
        fvg_atr_mult: float,
        max_spread_filter: float,
        point_size: float = 0.00001
    ) -> Dict[str, Any]:
        """Runs vectorised ICT FVG strategy backtest on a candles DataFrame."""
        if df.empty or len(df) < 50:
            return {"total_trades": 0, "win_rate_pct": 0.0, "profit_factor": 0.0, "total_pnl_pts": 0.0, "max_drawdown_pts": 0.0}

        df = df.copy()
        
        # Calculate Indicators (ATR & EMA200)
        high_low = df['High'] - df['Low']
        high_close = (df['High'] - df['Close'].shift(1)).abs()
        low_close = (df['Low'] - df['Close'].shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = tr.rolling(window=14).mean()
        df['ema200'] = df['Close'].ewm(span=200, adjust=False).mean()

        # FVG Detection
        df['fvg_bull'] = (df['Low'] > df['High'].shift(2)) & ((df['Low'] - df['High'].shift(2)) >= df['atr'] * fvg_atr_mult)
        df['fvg_bear'] = (df['High'] < df['Low'].shift(2)) & ((df['Low'].shift(2) - df['High']) >= df['atr'] * fvg_atr_mult)

        trades = []
        in_trade = False

        for i in range(200, len(df) - 1):
            if in_trade:
                continue

            row = df.iloc[i]
            mean_sp = row.get('Mean_Spread', 15.0)

            # Spread Filter
            if mean_sp > max_spread_filter:
                continue

            entry_price = row['Close']
            atr_val = row['atr']
            if pd.isna(atr_val) or atr_val <= 0:
                continue

            # Bullish Entry Condition
            if row['fvg_bull'] and row['Close'] > row['ema200']:
                sl_dist = max(atr_val * 1.5, mean_sp * point_size * 2)
                sl = entry_price - sl_dist
                tp = entry_price + (sl_dist * rr_ratio)
                
                # Forward simulation
                in_trade = True
                for j in range(i + 1, min(i + 300, len(df))):
                    future_row = df.iloc[j]
                    # Check SL hit
                    if future_row['Low'] <= sl:
                        pnl_pts = (sl - entry_price) / point_size - mean_sp
                        trades.append({'type': 'BUY', 'pnl': pnl_pts, 'win': False})
                        in_trade = False
                        break
                    # Check TP hit
                    elif future_row['High'] >= tp:
                        pnl_pts = (tp - entry_price) / point_size - mean_sp
                        trades.append({'type': 'BUY', 'pnl': pnl_pts, 'win': True})
                        in_trade = False
                        break

            # Bearish Entry Condition
            elif row['fvg_bear'] and row['Close'] < row['ema200']:
                sl_dist = max(atr_val * 1.5, mean_sp * point_size * 2)
                sl = entry_price + sl_dist
                tp = entry_price - (sl_dist * rr_ratio)

                in_trade = True
                for j in range(i + 1, min(i + 300, len(df))):
                    future_row = df.iloc[j]
                    # Check SL hit
                    if future_row['High'] >= sl:
                        pnl_pts = (entry_price - sl) / point_size - mean_sp
                        trades.append({'type': 'SELL', 'pnl': pnl_pts, 'win': False})
                        in_trade = False
                        break
                    # Check TP hit
                    elif future_row['Low'] <= tp:
                        pnl_pts = (entry_price - tp) / point_size - mean_sp
                        trades.append({'type': 'SELL', 'pnl': pnl_pts, 'win': True})
                        in_trade = False
                        break

        if not trades:
            return {"total_trades": 0, "win_rate_pct": 0.0, "profit_factor": 0.0, "total_pnl_pts": 0.0, "max_drawdown_pts": 0.0}

        df_trades = pd.DataFrame(trades)
        total_trades = len(df_trades)
        wins = df_trades[df_trades['win'] == True]
        losses = df_trades[df_trades['win'] == False]

        win_rate = len(wins) / total_trades if total_trades > 0 else 0.0
        gross_profit = wins['pnl'].sum() if not wins.empty else 0.0
        gross_loss = abs(losses['pnl'].sum()) if not losses.empty else 1.0
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else round(gross_profit, 2)

        total_pnl_pts = df_trades['pnl'].sum()
        equity_curve = df_trades['pnl'].cumsum()
        peak = equity_curve.cummax()
        drawdown = peak - equity_curve
        max_drawdown_pts = drawdown.max() if not drawdown.empty else 0.0

        return {
            "total_trades": total_trades,
            "win_rate_pct": round(win_rate * 100, 2),
            "profit_factor": profit_factor,
            "total_pnl_pts": round(total_pnl_pts, 1),
            "max_drawdown_pts": round(max_drawdown_pts, 1)
        }

    def run_all_period_backtests(self) -> Dict[str, Dict[str, Any]]:
        """Runs 1-day, 1-month, 1-year backtests for all symbols in config."""
        symbols = self.config.get("symbols", [])
        results = {}

        for sym in symbols:
            preset = self.presets.get(sym, {
                "timeframe": "M15",
                "rr_ratio": 3.0,
                "fvg_atr_mult": 0.2
            })
            
            tf = preset.get("timeframe", "M15")
            rr = preset.get("rr_ratio", 3.0)
            fvg = preset.get("fvg_atr_mult", 0.2)
            
            # Fetch 1 Year history
            df_year = self.fetch_historical_candles(sym, tf, days=365)
            if df_year.empty:
                logger.warning(f"Skipping period backtest for {sym} (No data)")
                continue

            point_size = df_year['point_size'].iloc[0] if 'point_size' in df_year.columns else 0.00001
            
            # Max spread filter
            is_crypto = any(c in sym.upper() for c in ["BTC", "ETH", "XRP"])
            max_sp = 50000.0 if is_crypto else 350.0

            # Filter date ranges
            now = datetime.now(timezone.utc)
            dt_1day = now - timedelta(days=1)
            dt_1month = now - timedelta(days=30)
            dt_1year = now - timedelta(days=365)

            df_1d = df_year[df_year.index >= dt_1day]
            df_1m = df_year[df_year.index >= dt_1month]
            df_1y = df_year[df_year.index >= dt_1year]

            res_1d = self.backtest_dataset(df_1d, rr, fvg, max_sp, point_size)
            res_1m = self.backtest_dataset(df_1m, rr, fvg, max_sp, point_size)
            res_1y = self.backtest_dataset(df_1y, rr, fvg, max_sp, point_size)

            results[sym] = {
                "preset": preset,
                "1_day": res_1d,
                "1_month": res_1m,
                "1_year": res_1y
            }

        mt5.shutdown()
        return results

if __name__ == "__main__":
    tester = MultiPeriodBacktester()
    res = tester.run_all_period_backtests()
    print(json.dumps(res, indent=2))
