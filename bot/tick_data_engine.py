"""
Tick Data Engine for MT5 Historical Backtesting (ICT Strategy & Spread Analysis)
Author: Lead Quantitative Data Engineer
Project: AI-Super-trader / ICT-Trading-Bot
"""

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Union
import pandas as pd
import numpy as np
import MetaTrader5 as mt5
import pytz

try:
    from bot.logger import logger
except ImportError:
    import logging
    logger = logging.getLogger("TickDataEngine")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class TickDataEngine:
    """
    High-performance Historical Tick Data Fetcher, Aggregator, and Storage Engine
    optimized for MetaTrader 5 (MT5).
    
    Converts raw Ask/Bid tick streams into dynamic M1 candles containing:
    OHLC (Bid), Volume (Tick Count), Max_Spread, Min_Spread, and Mean_Spread.
    """

    def __init__(self, symbol: str = "XAUUSD", server_tz: str = "UTC"):
        self.symbol = symbol
        self.server_tz = pytz.timezone(server_tz)
        self.connected = False
        self.point_size = 0.01  # Default for XAUUSD (0.01), auto-updated upon MT5 connection

    def connect_mt5(self, path: Optional[str] = None, login: Optional[int] = None,
                    password: Optional[str] = None, server: Optional[str] = None) -> bool:
        """
        Connects gracefully to MT5 terminal and retrieves symbol metadata.
        """
        if mt5.terminal_info() is not None:
            self.connected = True
        else:
            if path and os.path.exists(path):
                self.connected = mt5.initialize(path=path, login=login, password=password, server=server)
            else:
                self.connected = mt5.initialize()

        if not self.connected:
            err = mt5.last_error()
            logger.error(f"[MT5 Connection Error] Failed to initialize MT5: {err}")
            return False

        # Select symbol in Market Watch (with auto-fallback for broker suffixes like #, .m, m)
        clean_sym = self.symbol.split('#')[0].split('.m')[0]
        candidates = [self.symbol, clean_sym, f"{clean_sym}#", f"{clean_sym}.m", f"{clean_sym}m", f"{clean_sym}_m"]
        if clean_sym in ["XAUUSD", "GOLD"]:
            candidates.extend(["GOLD#", "GOLD", "XAUUSD#", "XAUUSD", "XAUUSD.m", "XAUUSDm", "GOLD.m", "GOLDm"])

        selected_symbol = None
        
        for sym in candidates:
            if mt5.symbol_select(sym, True):
                selected_symbol = sym
                break

        if not selected_symbol:
            logger.error(f"[MT5 Error] Failed to select symbol '{self.symbol}' (tested candidates: {candidates}) in Market Watch.")
            return False

        self.symbol = selected_symbol
        sym_info = mt5.symbol_info(self.symbol)
        if sym_info:
            self.point_size = sym_info.point if sym_info.point > 0 else 0.01
            logger.info(f"Connected to MT5. Symbol: {self.symbol} | Point: {self.point_size} | Digits: {sym_info.digits}")
        else:
            logger.warning(f"Could not retrieve symbol_info for {self.symbol}. Using fallback point_size={self.point_size}")

        return True

    def disconnect_mt5(self):
        """Safely shuts down the MT5 connection."""
        mt5.shutdown()
        self.connected = False
        logger.info("MT5 connection shutdown completed.")

    def aggregate_ticks_to_m1(self, ticks_array: np.ndarray) -> pd.DataFrame:
        """
        Converts raw tick array (from copy_ticks_range) to M1 aggregated DataFrame.
        Extracts OHLC (Bid), Volume (Tick count), and Spread metrics (in Points).
        """
        if ticks_array is None or len(ticks_array) == 0:
            return pd.DataFrame()

        # Convert numpy record array to Pandas DataFrame
        df_ticks = pd.DataFrame(ticks_array)
        
        # Calculate Spread in Points: (Ask - Bid) / Point Size
        # E.g., for XAUUSD (Point=0.01): Ask=2000.50, Bid=2000.20 -> Spread = 0.30 / 0.01 = 30 points
        df_ticks['spread_points'] = (df_ticks['ask'] - df_ticks['bid']) / self.point_size

        # Convert millisecond timestamp to timezone-aware UTC Datetime Index
        df_ticks['timestamp'] = pd.to_datetime(df_ticks['time_msc'], unit='ms', utc=True)
        df_ticks.set_index('timestamp', inplace=True)

        # Resample ticks into 1-minute (M1) bars
        resampler = df_ticks.resample('1min')

        m1_df = pd.DataFrame({
            'Open': resampler['bid'].first(),
            'High': resampler['bid'].max(),
            'Low': resampler['bid'].min(),
            'Close': resampler['bid'].last(),
            'Volume': resampler['bid'].count(),  # Tick volume count
            'Max_Spread': resampler['spread_points'].max(),
            'Min_Spread': resampler['spread_points'].min(),
            'Mean_Spread': resampler['spread_points'].mean().round(2)
        })

        # Drop minutes with zero tick activity (e.g. market closure / weekend gaps)
        m1_df.dropna(subset=['Open', 'Close'], inplace=True)

        return m1_df

    def fetch_and_aggregate_batch(self, date_from: datetime, date_to: datetime,
                                  max_retries: int = 3) -> pd.DataFrame:
        """
        Fetches ticks for a single batch range and immediately aggregates them into M1 bars.
        Includes retry logic for MT5 API stability.
        """
        if not self.connected:
            if not self.connect_mt5():
                raise ConnectionError("MT5 connection could not be established.")

        logger.info(f"Fetching ticks from {date_from.strftime('%Y-%m-%d %H:%M')} to {date_to.strftime('%Y-%m-%d %H:%M')}...")

        ticks = None
        for attempt in range(1, max_retries + 1):
            ticks = mt5.copy_ticks_range(self.symbol, date_from, date_to, mt5.COPY_TICKS_ALL)
            if ticks is not None and len(ticks) > 0:
                break
            logger.warning(f"Attempt {attempt}/{max_retries} returned no ticks. Retrying in 2 seconds...")
            time.sleep(2)

        if ticks is None or len(ticks) == 0:
            logger.warning(f"No tick data retrieved for range {date_from} -> {date_to}")
            return pd.DataFrame()

        logger.info(f"Fetched {len(ticks):,} raw ticks. Aggregating to M1...")
        m1_chunk = self.aggregate_ticks_to_m1(ticks)
        
        # Explicit memory cleanup of raw tick array
        del ticks
        
        return m1_chunk

    def download_historical_data(self, start_date: datetime, end_date: datetime,
                                 chunk_days: int = 15) -> pd.DataFrame:
        """
        Processes multi-month/year requests by batching chunk-by-chunk.
        Prevents RAM crash by aggregating each chunk immediately.
        """
        if not self.connected:
            if not self.connect_mt5():
                raise ConnectionError("MT5 connection is required.")

        m1_chunks = []
        current_start = start_date

        total_days = (end_date - start_date).days
        logger.info(f"Starting historical tick pipeline for {self.symbol} ({total_days} total days, {chunk_days}-day batch size)...")

        while current_start < end_date:
            current_end = min(current_start + timedelta(days=chunk_days), end_date)
            
            chunk_m1 = self.fetch_and_aggregate_batch(current_start, current_end)
            if not chunk_m1.empty:
                m1_chunks.append(chunk_m1)

            current_start = current_end

        if not m1_chunks:
            logger.error("Pipeline finished with zero aggregated bars.")
            return pd.DataFrame()

        # Combine all aggregated M1 chunks into one clean DataFrame
        full_m1_df = pd.concat(m1_chunks)
        
        # Deduplicate overlap boundaries
        full_m1_df = full_m1_df[~full_m1_df.index.duplicated(keep='first')].sort_index()

        logger.info(f"Pipeline finished! Total aggregated M1 bars: {len(full_m1_df):,}")
        return full_m1_df

    def save_to_parquet(self, df: pd.DataFrame, output_filepath: str) -> bool:
        """
        Saves the aggregated DataFrame into Apache Parquet format.
        """
        try:
            os.makedirs(os.path.dirname(os.path.abspath(output_filepath)), exist_ok=True)
            df.to_parquet(output_filepath, engine='pyarrow', compression='snappy')
            file_size_mb = os.path.getsize(output_filepath) / (1024 * 1024)
            logger.info(f"Saved M1 DataFrame to Parquet: '{output_filepath}' ({file_size_mb:.2f} MB)")
            return True
        except Exception as e:
            logger.error(f"Failed to save Parquet file '{output_filepath}': {str(e)}")
            return False


# =====================================================================
# BACKTESTER INTEGRATION DEMONSTRATION
# =====================================================================

def run_challenger_backtest_with_spread_penalty(
    parquet_filepath: str,
    max_spread_threshold: float = 30.0,
    slippage_penalty_points: float = 10.0,
    point_size: float = 0.01
):
    """
    Challenger Backtester Bot Integration Function.
    
    Reads the stored Parquet M1 dataset and applies dynamic spread penalty:
    "If Max_Spread > 30 points, simulate a Slippage penalty of 10 points on the SL".
    """
    if not os.path.exists(parquet_filepath):
        logger.error(f"File not found: {parquet_filepath}")
        return

    logger.info(f"Loading Parquet dataset from: {parquet_filepath}")
    df = pd.read_parquet(parquet_filepath)
    print("\n--- Aggregated M1 Tick-Data Sample ---")
    print(df.head(10))
    print("--------------------------------------\n")

    # Simulation Statistics
    total_bars = len(df)
    high_spread_count = 0
    total_slippage_points = 0.0

    # Vectorized / Iterative scan for High Spread Events during ICT setups
    high_spread_mask = df['Max_Spread'] > max_spread_threshold
    high_spread_bars = df[high_spread_mask]
    high_spread_count = len(high_spread_bars)
    total_slippage_points = high_spread_count * slippage_penalty_points

    print("=" * 60)
    print("      CHALLENGER BACKTESTER: DYNAMIC SPREAD & SLIPPAGE REPORT")
    print("=" * 60)
    print(f"Total M1 Bars Tested                       : {total_bars:,}")
    print(f"Spread Threshold                           : > {max_spread_threshold} points")
    print(f"High-Spread Minutes Detected (News/Illiquid): {high_spread_count:,} bars ({high_spread_count / max(total_bars, 1) * 100:.2f}%)")
    print(f"Slippage Penalty Applied per Trigger       : {slippage_penalty_points} points")
    print(f"Total Accumulated Slippage Loss            : {total_slippage_points:,.1f} points")
    print(f"Impact per 1.0 Lot Position (XAUUSD)        : ${total_slippage_points * point_size * 100:,.2f}")
    print("=" * 60)


if __name__ == "__main__":
    # Quick Test Execution Example
    print("Tick Data Engine Module loaded successfully.")
    
    # Example usage (Uncomment below to run real download if MT5 Terminal is running):
    """
    engine = TickDataEngine(symbol="XAUUSD")
    if engine.connect_mt5():
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 15, tzinfo=timezone.utc)
        
        m1_data = engine.download_historical_data(start_date=start, end_date=end, chunk_days=7)
        parquet_file = "data/XAUUSD_M1_TickAggregated_2024.parquet"
        engine.save_to_parquet(m1_data, parquet_file)
        engine.disconnect_mt5()
        
        # Run Backtest simulation
        run_challenger_backtest_with_spread_penalty(parquet_file, max_spread_threshold=30.0, slippage_penalty_points=10.0)
    """
