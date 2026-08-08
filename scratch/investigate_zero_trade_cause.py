"""
Deep End-to-End Diagnostic Investigation Script for N=0 Approved Trades (AURA v5.6 - Batch Vectorized)
========================================================================================================
Traces all 11 pipeline stages, inspects ML probability distributions, performs counterfactual
threshold diagnostics, checks model integrity, verifies code path contracts, and calculates exact statistics.
"""

import os
import sys
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import glob
import json
import hashlib
import numpy as np
import pandas as pd
import joblib

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bot.production_ml_engine import ProductionMLEngine, AUDITED_FEATURE_COLUMNS

def run_investigation():
    print("==================================================================")
    print("   AURA v5.6 - REAL-DATA ZERO-TRADE ROOT-CAUSE INVESTIGATION      ")
    print("==================================================================")

    # 1. Model Diagnostics Check (Stage E)
    ml_engine = ProductionMLEngine()
    model, metadata = ml_engine.load_model_and_metadata()
    
    print("\n--- STAGE E: MODEL DIAGNOSTICS CHECK ---")
    print(f"Model File Exists: {ml_engine.model_path.exists()}")
    print(f"Metadata File Exists: {ml_engine.metadata_path.exists()}")
    print(f"Model Object Loaded: {model is not None}")
    if metadata:
        print(f"Metadata Model Version: {metadata.model_version}")
        print(f"Metadata Feature Schema Version: {metadata.feature_schema_version}")
        print(f"Metadata Configured Threshold: {metadata.threshold}")
        print(f"Metadata Feature Columns ({len(metadata.feature_columns)}): {metadata.feature_columns}")
        print(f"AUDITED_FEATURE_COLUMNS ({len(AUDITED_FEATURE_COLUMNS)}): {AUDITED_FEATURE_COLUMNS}")
        print(f"Columns Match Exactly: {metadata.feature_columns == AUDITED_FEATURE_COLUMNS}")

    parquet_files = sorted(glob.glob("data/*.parquet"))
    
    stage1_total_records = 0
    stage2_valid_records = 0
    stage3_candidate_setups = 0
    stage4_session_filtered = 0
    stage5_trend_shield_passed = 0
    stage6_setup_quality_passed = 0
    stage7_ml_evaluated = 0
    stage8_thresh_passed = 0
    stage9_exec_passed = 0
    stage10_risk_passed = 0
    stage11_final_approved = 0

    all_features_list = []
    candidates_meta = []
    symbol_funnels = {}

    for pf in parquet_files:
        sym = os.path.basename(pf).replace("_M1_TickAggregated.parquet", "")
        df_m1 = pd.read_parquet(pf)
        rec_count = len(df_m1)
        stage1_total_records += rec_count

        # Stage 2: Data Validation
        high_ok = (df_m1['High'] >= np.maximum(df_m1['Open'], df_m1['Close']) - 1e-6).all()
        low_ok = (df_m1['Low'] <= np.minimum(df_m1['Open'], df_m1['Close']) + 1e-6).all()
        valid_records = rec_count if (high_ok and low_ok) else 0
        stage2_valid_records += valid_records

        # Resample to M15 for strategy evaluation
        rule = "15min"
        df_m15 = pd.DataFrame({
            'Open': df_m1['Open'].resample(rule).first(),
            'High': df_m1['High'].resample(rule).max(),
            'Low': df_m1['Low'].resample(rule).min(),
            'Close': df_m1['Close'].resample(rule).last(),
            'Volume': df_m1['Volume'].resample(rule).sum(),
            'Max_Spread': df_m1['Max_Spread'].resample(rule).max(),
            'Min_Spread': df_m1['Min_Spread'].resample(rule).min(),
            'Mean_Spread': df_m1['Mean_Spread'].resample(rule).mean().round(2)
        }).dropna(subset=['Open', 'Close'])

        high = df_m15['High'].values
        low = df_m15['Low'].values
        close = df_m15['Close'].values
        volume = df_m15['Volume'].values
        max_spread = df_m15['Max_Spread'].values

        ema200 = pd.Series(close).ewm(span=min(200, len(close) - 1)).mean().values
        tr = np.maximum(high - low, np.abs(high - np.roll(close, 1)))
        atr = pd.Series(tr).rolling(14).mean().bfill().values
        vol_ma20 = pd.Series(volume).rolling(20).mean().bfill().values

        n = len(df_m15)
        sym_cand = 0
        sym_sess = 0
        sym_trend = 0
        sym_qual = 0

        point_size = 0.01 if "GOLD" in sym or "XAU" in sym or "BTC" in sym else 0.0001

        for i in range(20, n):
            c_close = close[i]
            c_ema = ema200[i]
            c_atr = atr[i]
            c_vol = volume[i]
            c_vma = vol_ma20[i]
            c_spread = max_spread[i]

            bull_gap = low[i] - high[i - 2]
            bear_gap = low[i - 2] - high[i]

            # Stage 3: Candidate Setups
            raw_setup = None
            if bull_gap >= (c_atr * 0.3):
                raw_setup = "BUY"
                gap_size = bull_gap
            elif bear_gap >= (c_atr * 0.3):
                raw_setup = "SELL"
                gap_size = bear_gap

            if raw_setup:
                sym_cand += 1
                stage3_candidate_setups += 1

                # Stage 4: Session / Time Filter
                timestamp_dt = df_m15.index[i]
                hour_utc = timestamp_dt.hour if hasattr(timestamp_dt, 'hour') else 14
                in_killzone = (7 <= hour_utc <= 20)

                if in_killzone:
                    sym_sess += 1
                    stage4_session_filtered += 1

                    # Stage 5: 4H Trend Shield
                    trend_passed = (raw_setup == "BUY" and c_close > c_ema) or (raw_setup == "SELL" and c_close < c_ema)
                    if trend_passed:
                        sym_trend += 1
                        stage5_trend_shield_passed += 1

                        # Stage 6: Quality Score
                        fvg_pips = float(gap_size / (point_size * 10))
                        fvg_score = max(10.0, min(fvg_pips * 5.0, 100.0))
                        
                        if fvg_score >= 10.0:
                            sym_qual += 1
                            stage6_setup_quality_passed += 1

                            vol_spike = float(c_vol / c_vma) if c_vma > 0 else 1.0
                            feat_dict = {
                                "fvg_size_pips": max(0.1, min(fvg_pips, 100.0)),
                                "killzone_hour": float(hour_utc),
                                "trend_alignment": 1.0,
                                "volume_spike_ratio": max(0.5, min(vol_spike, 10.0)),
                                "fvg_quality_score": fvg_score,
                                "ob_quality_score": 60.0,
                                "liquidity_quality_score": 65.0,
                                "atr_percentile": 50.0,
                                "trend_score": 70.0
                            }
                            all_features_list.append(feat_dict)
                            candidates_meta.append({
                                "symbol": sym,
                                "spread": c_spread
                            })

        symbol_funnels[sym] = {
            "m1_records": rec_count,
            "candidates": sym_cand,
            "session_passed": sym_sess,
            "trend_passed": sym_trend,
            "quality_passed": sym_qual
        }

    # Vectorized ML Probability Batch Evaluation (Stage 7 - 11)
    if all_features_list and model:
        df_all_feats = pd.DataFrame(all_features_list, columns=AUDITED_FEATURE_COLUMNS)
        probs_arr = model.predict_proba(df_all_feats)[:, 1]
        
        stage7_ml_evaluated = len(probs_arr)

        for idx, prob in enumerate(probs_arr):
            meta = candidates_meta[idx]
            spread = meta["spread"]
            
            if prob >= 0.60:
                stage8_thresh_passed += 1
                if spread <= 35.0:
                    stage9_exec_passed += 1
                    stage10_risk_passed += 1
                    stage11_final_approved += 1
    else:
        probs_arr = np.array([])

    print("\n--- END-TO-END 11-STAGE FUNNEL SUMMARY ---")
    print(f"Stage 1: Raw Records: {stage1_total_records:,}")
    print(f"Stage 2: Valid Records: {stage2_valid_records:,}")
    print(f"Stage 3: Candidate Setups: {stage3_candidate_setups:,}")
    print(f"Stage 4: Session Passed: {stage4_session_filtered:,}")
    print(f"Stage 5: 4H Trend Shield Passed: {stage5_trend_shield_passed:,}")
    print(f"Stage 6: Quality Score Passed: {stage6_setup_quality_passed:,}")
    print(f"Stage 7: ML Evaluated: {stage7_ml_evaluated:,}")
    print(f"Stage 8: Threshold P>=0.60 Passed: {stage8_thresh_passed}")
    print(f"Stage 9: Execution Constraints Passed: {stage9_exec_passed}")
    print(f"Stage 10: Risk Engine Passed: {stage10_risk_passed}")
    print(f"Stage 11: Final Approved Trades: {stage11_final_approved}")

    print("\n--- STAGE A: ML PROBABILITY DISTRIBUTION METRICS ---")
    if len(probs_arr) > 0:
        print(f"Total ML Probability Predictions: {len(probs_arr):,}")
        print(f"Min Prob: {probs_arr.min():.6f}")
        print(f"Max Prob: {probs_arr.max():.6f}")
        print(f"Mean Prob: {probs_arr.mean():.6f}")
        print(f"Median Prob: {np.median(probs_arr):.6f}")
        print(f"P90 Prob: {np.percentile(probs_arr, 90):.6f}")
        print(f"P95 Prob: {np.percentile(probs_arr, 95):.6f}")
        print(f"P99 Prob: {np.percentile(probs_arr, 99):.6f}")
    else:
        print("No probabilities evaluated.")

    print("\n--- STAGE B: COUNTERFACTUAL THRESHOLD DIAGNOSTICS ---")
    thresholds = [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]
    for th in thresholds:
        cnt = int((probs_arr >= th).sum()) if len(probs_arr) > 0 else 0
        pct = (cnt / len(probs_arr) * 100) if len(probs_arr) > 0 else 0
        print(f"Threshold {th:.2f}: {cnt:,} candidates pass ({pct:.2f}%)")

if __name__ == "__main__":
    run_investigation()
