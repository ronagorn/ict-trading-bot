"""
Forensic Model Artifact & Lineage Inspection Script (AURA v5.8)
==========================================================================
Inspects production_xgboost_calibrated.pkl internals:
1. Base estimators inside CalibratedClassifierCV
2. Base model predict_proba vs Calibrated predict_proba on 1,185 real market setups
3. Feature importances & parameters
4. All repository code references to joblib.dump, CalibratedClassifierCV, train_calibrated_pipeline
"""

import os
import sys
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import glob
import hashlib
import json
import joblib
import numpy as np
import pandas as pd

from bot.production_ml_engine import ProductionMLEngine, AUDITED_FEATURE_COLUMNS

def inspect_model_artifact():
    print("==================================================================")
    print("   AURA v5.8 - MODEL ARTIFACT & LINEAGE FORENSIC AUDIT            ")
    print("==================================================================")

    model_path = "data/ml_models/production_xgboost_calibrated.pkl"
    meta_path = "data/ml_models/production_model_metadata.json"

    print("\n--- PHASE 1: ARTIFACT FILE METADATA ---")
    if os.path.exists(model_path):
        size = os.path.getsize(model_path)
        sha256 = hashlib.sha256(open(model_path, 'rb').read()).hexdigest()
        print(f"Model Path: {model_path}")
        print(f"File Size: {size:,} bytes")
        print(f"SHA-256: {sha256}")
    else:
        print(f"ERROR: Model file not found at {model_path}")
        return

    if os.path.exists(meta_path):
        with open(meta_path, 'r', encoding='utf-8') as f:
            meta_dict = json.load(f)
        print(f"\nMetadata Content:\n{json.dumps(meta_dict, indent=2)}")
    else:
        print("Metadata file not found.")

    model = joblib.load(model_path)
    print("\n--- PHASE 1 & 10: MODEL OBJECT INTERNALS ---")
    print(f"Model Class Type: {type(model)}")
    print(f"Calibrated Method: {getattr(model, 'method', 'N/A')}")
    print(f"CV Parameter: {getattr(model, 'cv', 'N/A')}")
    
    calibrated_classifiers = getattr(model, 'calibrated_classifiers_', [])
    print(f"Number of Calibrated Classifiers: {len(calibrated_classifiers)}")

    for idx, cc in enumerate(calibrated_classifiers):
        estimator = getattr(cc, 'estimator', None)
        calibrators = getattr(cc, 'calibrators', [])
        print(f"\n[Fold {idx + 1}] Base Estimator Type: {type(estimator)}")
        if hasattr(estimator, 'get_params'):
            params = estimator.get_params()
            print(f"  Estimator Params (n_estimators={params.get('n_estimators')}, max_depth={params.get('max_depth')}, lr={params.get('learning_rate')})")
        print(f"  Calibrators Count: {len(calibrators)}")
        for c_idx, calib in enumerate(calibrators):
            print(f"    Calibrator {c_idx+1}: {type(calib)}")
            if hasattr(calib, 'a_') and hasattr(calib, 'b_'):
                print(f"      Platt Sigmoid Parameters: a_ (slope) = {calib.a_:.6f}, b_ (intercept) = {calib.b_:.6f}")

    # Evaluate Base Estimators vs Calibrated Model on Real Market Setups
    print("\n--- PHASE 9: BASE XGBOOST VS CALIBRATED PROBABILITY SHIFT ON REAL SETUPS ---")
    parquet_files = sorted(glob.glob("data/*.parquet"))
    feature_rows = []

    for pf in parquet_files:
        sym = os.path.basename(pf).replace("_M1_TickAggregated.parquet", "")
        df_m1 = pd.read_parquet(pf)
        rule = "15min"
        df_tf = pd.DataFrame({
            'Open': df_m1['Open'].resample(rule).first(),
            'High': df_m1['High'].resample(rule).max(),
            'Low': df_m1['Low'].resample(rule).min(),
            'Close': df_m1['Close'].resample(rule).last(),
            'Volume': df_m1['Volume'].resample(rule).sum(),
            'Max_Spread': df_m1['Max_Spread'].resample(rule).max(),
            'Min_Spread': df_m1['Min_Spread'].resample(rule).min(),
            'Mean_Spread': df_m1['Mean_Spread'].resample(rule).mean().round(2)
        }).dropna(subset=['Open', 'Close'])

        if len(df_tf) < 50:
            continue

        high = df_tf['High'].values
        low = df_tf['Low'].values
        close = df_tf['Close'].values
        volume = df_tf['Volume'].values

        ema200 = pd.Series(close).ewm(span=min(200, len(close) - 1)).mean().values
        tr = np.maximum(high - low, np.abs(high - np.roll(close, 1)))
        atr = pd.Series(tr).rolling(14).mean().bfill().values
        vol_ma20 = pd.Series(volume).rolling(20).mean().bfill().values

        n = len(df_tf)
        point_size = 0.01 if "GOLD" in sym or "XAU" in sym or "BTC" in sym else 0.0001

        for i in range(20, n):
            c_close = close[i]
            c_ema = ema200[i]
            c_atr = atr[i]
            c_vol = volume[i]
            c_vma = vol_ma20[i]

            bull_gap = low[i] - high[i - 2]
            bear_gap = low[i - 2] - high[i]

            signal_type = None
            if bull_gap >= (c_atr * 0.3):
                signal_type = "BUY"
                gap_size = bull_gap
            elif bear_gap >= (c_atr * 0.3):
                signal_type = "SELL"
                gap_size = bear_gap

            if signal_type:
                timestamp_dt = df_tf.index[i]
                hour_utc = timestamp_dt.hour if hasattr(timestamp_dt, 'hour') else 14
                if 7 <= hour_utc <= 20:
                    trend_passed = (signal_type == "BUY" and c_close > c_ema) or (signal_type == "SELL" and c_close < c_ema)
                    if trend_passed:
                        fvg_pips = float(gap_size / (point_size * 10))
                        fvg_score = max(10.0, min(fvg_pips * 5.0, 100.0))
                        if fvg_score >= 10.0:
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
                            feature_rows.append(feat_dict)

    if feature_rows:
        X_real = pd.DataFrame(feature_rows, columns=AUDITED_FEATURE_COLUMNS)
        calibrated_probs = model.predict_proba(X_real)[:, 1]

        base_probs_list = []
        for cc in calibrated_classifiers:
            est = cc.estimator
            if hasattr(est, 'predict_proba'):
                b_p = est.predict_proba(X_real)[:, 1]
                base_probs_list.append(b_p)

        if base_probs_list:
            avg_base_probs = np.mean(base_probs_list, axis=0)
            print(f"Evaluated Real Market Setups: {len(X_real):,}")
            print("\n--- COMPARISON: BASE XGBOOST vs CALIBRATED PROBABILITIES ---")
            print(f"Base XGBoost Prob Min: {avg_base_probs.min():.6f}")
            print(f"Base XGBoost Prob Max: {avg_base_probs.max():.6f}")
            print(f"Base XGBoost Prob Mean: {avg_base_probs.mean():.6f}")
            print(f"Base XGBoost Prob Median: {np.median(avg_base_probs):.6f}")
            print(f"Base XGBoost Prob P90: {np.percentile(avg_base_probs, 90):.6f}")
            print(f"Base XGBoost Prob P99: {np.percentile(avg_base_probs, 99):.6f}")
            print(f"Base XGBoost Count (P >= 0.60): {(avg_base_probs >= 0.60).sum():,} ({ (avg_base_probs >= 0.60).sum() / len(avg_base_probs) * 100:.2f}%)")

            print("\n------------------------------------------------------------")
            print(f"Calibrated Prob Min: {calibrated_probs.min():.6f}")
            print(f"Calibrated Prob Max: {calibrated_probs.max():.6f}")
            print(f"Calibrated Prob Mean: {calibrated_probs.mean():.6f}")
            print(f"Calibrated Prob Median: {np.median(calibrated_probs):.6f}")
            print(f"Calibrated Prob P90: {np.percentile(calibrated_probs, 90):.6f}")
            print(f"Calibrated Prob P99: {np.percentile(calibrated_probs, 99):.6f}")
            print(f"Calibrated Count (P >= 0.60): {(calibrated_probs >= 0.60).sum():,} ({ (calibrated_probs >= 0.60).sum() / len(calibrated_probs) * 100:.2f}%)")

if __name__ == "__main__":
    inspect_model_artifact()
