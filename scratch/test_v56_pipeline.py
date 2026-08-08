"""
Test AURA v5.6 Real-Market Signal Pipeline & ML Integration across 13 Parquet Datasets
"""
import os
import sys
import glob
import pandas as pd
import numpy as np
import joblib

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bot.challenger_engine import ChallengerEngine
from bot.production_ml_engine import ProductionMLEngine, AUDITED_FEATURE_COLUMNS

def test_pipeline():
    engine = ChallengerEngine(data_dir="data")
    ml_engine = ProductionMLEngine()
    model, metadata = ml_engine.load_model_and_metadata()
    
    print(f"Model loaded: {model is not None}")
    if metadata:
        print(f"Metadata: Version={metadata.model_version}, Threshold={metadata.threshold}")

    parquet_files = sorted(glob.glob("data/*.parquet"))
    
    for pf in parquet_files:
        sym = os.path.basename(pf).replace("_M1_TickAggregated.parquet", "")
        df_m1 = pd.read_parquet(pf)
        
        # Test backtest_strategy for M15, M5, M1
        for tf in ["M15", "M5"]:
            stats = engine.backtest_strategy(
                df=df_m1,
                timeframe=tf,
                rr_ratio=3.0,
                fvg_atr_mult=0.3,
                max_spread_filter=35.0,
                use_ema_filter=True,
                slippage_penalty_pts=10.0
            )
            if stats:
                print(f"{sym} [{tf}]: Trades={stats['total_trades']}, WinRate={stats['win_rate_pct']}%, PF={stats['profit_factor']}")

if __name__ == "__main__":
    test_pipeline()
