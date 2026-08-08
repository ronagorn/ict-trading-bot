"""
Test Real Parquet Ingestion and Strategy Signal Generation
"""
import os
import sys
import glob
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bot.strategy import ICTStrategy
from bot.production_ml_engine import ProductionMLEngine, AUDITED_FEATURE_COLUMNS

def test_real_parquet():
    parquet_files = glob.glob("data/*.parquet")
    print(f"Found {len(parquet_files)} parquet files in data/")
    
    for pf in sorted(parquet_files):
        df = pd.read_parquet(pf)
        sym = os.path.basename(pf).replace("_M1_TickAggregated.parquet", "")
        print(f"\n--- {sym} ({len(df)} M1 rows) ---")
        print(f"Range: {df['time'].min() if 'time' in df.columns else df.index.min()} to {df['time'].max() if 'time' in df.columns else df.index.max()}")
        print(f"Columns: {list(df.columns)}")
        print(f"Spread stats: Mean={df['Mean_Spread'].mean():.2f} pts, Max={df['Max_Spread'].max():.2f} pts")

if __name__ == "__main__":
    test_real_parquet()
