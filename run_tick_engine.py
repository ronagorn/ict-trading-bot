"""
Multi-Symbol Runner Script for Tick Data Engine
Fetch historical tick data & dynamic spread metrics for multiple pairs.
Run directly with: python run_tick_engine.py
"""

import os
import sys
from datetime import datetime, timedelta, timezone

# Add project root directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bot.tick_data_engine import TickDataEngine, run_challenger_backtest_with_spread_penalty

# 12 Major Assets: 8 Forex Majors + Gold + Top Crypto
DEFAULT_SYMBOLS = [
    "XAUUSD", "EURUSD", "GBPUSD", "USDJPY", 
    "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "EURGBP", 
    "BTCUSD", "ETHUSD", "XRPUSD"
]

def process_symbol(symbol: str, days_back: int = 30) -> dict:
    """Downloads tick data for a single symbol and returns summary metrics."""
    print(f"\n" + "=" * 60)
    print(f"      PROCESSING PIPELINE FOR: {symbol}")
    print("=" * 60)

    engine = TickDataEngine(symbol=symbol)

    if not engine.connect_mt5():
        print(f"[ERROR] Could not connect or find symbol '{symbol}' in MT5.")
        return {}

    actual_symbol = engine.symbol
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days_back)

    print(f"Symbol: {actual_symbol} | Target Range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

    # Download & Aggregate (10 days per batch)
    m1_df = engine.download_historical_data(start_date=start_date, end_date=end_date, chunk_days=10)

    if m1_df.empty:
        print(f"[WARNING] No tick data returned for {actual_symbol}.")
        engine.disconnect_mt5()
        return {}

    # Save to dedicated Parquet file for this symbol
    clean_name = actual_symbol.replace("#", "").replace(".", "_")
    parquet_filename = f"{clean_name}_M1_TickAggregated.parquet"
    parquet_path = os.path.join("data", parquet_filename)
    
    engine.save_to_parquet(m1_df, parquet_path)
    engine.disconnect_mt5()

    # Calculate summary metrics for report
    summary = {
        "symbol": actual_symbol,
        "m1_bars": len(m1_df),
        "avg_mean_spread_pts": round(m1_df['Mean_Spread'].mean(), 2),
        "max_spread_pts": round(m1_df['Max_Spread'].max(), 2),
        "high_spread_bars": int((m1_df['Max_Spread'] > 30).sum()),
        "parquet_file": parquet_path
    }

    return summary


def main():
    print("=" * 60)
    print("   MULTI-SYMBOL HISTORICAL TICK DATA ENGINE (MT5 -> PARQUET)")
    print("=" * 60)

    symbols_to_process = DEFAULT_SYMBOLS
    results = []

    for sym in symbols_to_process:
        try:
            res = process_symbol(sym, days_back=30)
            if res:
                results.append(res)
        except Exception as e:
            print(f"[ERROR] Failed to process {sym}: {str(e)}")

    print("\n" + "=" * 70)
    print("               MULTI-SYMBOL TICK DATA PIPELINE SUMMARY")
    print("=" * 70)
    print(f"{'Symbol':<10} | {'M1 Bars':<10} | {'Avg Spread (pts)':<18} | {'Max Spread (pts)':<18} | {'Parquet Size'}")
    print("-" * 70)

    for res in results:
        file_size_mb = os.path.getsize(res['parquet_file']) / (1024 * 1024) if os.path.exists(res['parquet_file']) else 0
        print(f"{res['symbol']:<10} | {res['m1_bars']:<10,} | {res['avg_mean_spread_pts']:<18} | {res['max_spread_pts']:<18} | {file_size_mb:.2f} MB")

    print("=" * 70)
    print("\n[SUCCESS] All symbol datasets saved in 'data/' directory as Parquet files.")


if __name__ == "__main__":
    main()
