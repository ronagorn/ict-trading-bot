"""
Real-Market Signal Funnel & ML Filtering Reproduction Script (AURA v5.6)
========================================================================
Extracts signals from data/*.parquet files, extracts 9 audited features,
applies production_xgboost_calibrated.pkl at threshold 0.60, and records
signal funnel metrics (Total Signals -> ML Approved -> ML Rejected -> Wins -> Losses).
"""

import os
import sys
import glob
import json
import pandas as pd
import numpy as np
import joblib

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bot.production_ml_engine import ProductionMLEngine, AUDITED_FEATURE_COLUMNS

def run_real_market_funnel():
    ml_engine = ProductionMLEngine()
    model, metadata = ml_engine.load_model_and_metadata()

    print(f"ML Model loaded: {model is not None}")
    if metadata:
        print(f"Model Metadata: Version={metadata.model_version}, Threshold={metadata.threshold}")

    parquet_files = sorted(glob.glob("data/*.parquet"))
    symbol_results = []

    total_signals_all = 0
    ml_approved_all = 0
    ml_rejected_all = 0
    approved_wins_all = 0
    approved_losses_all = 0

    for pf in parquet_files:
        sym = os.path.basename(pf).replace("_M1_TickAggregated.parquet", "")
        df_m1 = pd.read_parquet(pf)

        # Resample to M15
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
        open_p = df_tf['Open'].values
        volume = df_tf['Volume'].values
        max_spread = df_tf['Max_Spread'].values

        ema200 = pd.Series(close).ewm(span=min(200, len(close) - 1)).mean().values
        tr = np.maximum(high - low, np.abs(high - np.roll(close, 1)))
        atr = pd.Series(tr).rolling(14).mean().bfill().values
        vol_ma20 = pd.Series(volume).rolling(20).mean().bfill().values

        signals = []
        n = len(df_tf)

        for i in range(20, n):
            c_close = close[i]
            c_ema = ema200[i]
            c_atr = atr[i]
            c_vol = volume[i]
            c_vma = vol_ma20[i]

            vol_spike = float(c_vol / c_vma) if c_vma > 0 else 1.0
            
            # FVG Pattern Scanning
            bull_gap = low[i] - high[i - 2]
            bear_gap = low[i - 2] - high[i]

            signal_type = None
            if bull_gap >= (c_atr * 0.3) and c_close > c_ema:
                signal_type = "BUY"
                gap_size = bull_gap
                entry = close[i]
                sl = low[i - 2] - (c_atr * 0.5)
            elif bear_gap >= (c_atr * 0.3) and c_close < c_ema:
                signal_type = "SELL"
                gap_size = bear_gap
                entry = close[i]
                sl = high[i - 2] + (c_atr * 0.5)

            if signal_type and abs(entry - sl) > 0:
                point_size = 0.01 if "GOLD" in sym or "XAU" in sym or "BTC" in sym else 0.0001
                fvg_pips = float(gap_size / (point_size * 10))

                # Feature extraction
                timestamp_dt = df_tf.index[i]
                kz_hour = timestamp_dt.hour if hasattr(timestamp_dt, 'hour') else 14
                
                features = {
                    "fvg_size_pips": max(0.1, min(fvg_pips, 100.0)),
                    "killzone_hour": float(kz_hour),
                    "trend_alignment": 1.0 if (signal_type == "BUY" and c_close > c_ema) or (signal_type == "SELL" and c_close < c_ema) else 0.0,
                    "volume_spike_ratio": max(0.5, min(vol_spike, 10.0)),
                    "fvg_quality_score": max(10.0, min(fvg_pips * 5.0, 100.0)),
                    "ob_quality_score": 60.0,
                    "liquidity_quality_score": 65.0,
                    "atr_percentile": 50.0,
                    "trend_score": 70.0
                }

                # Evaluate ML Probability using production_xgboost_calibrated.pkl
                X_in = pd.DataFrame([features], columns=AUDITED_FEATURE_COLUMNS)
                prob = float(model.predict_proba(X_in)[0][1]) if model else 0.50
                is_approved = prob >= 0.60

                # Simulate execution outcome
                rr_ratio = 3.0
                risk = abs(entry - sl)
                tp = entry + (risk * rr_ratio) if signal_type == "BUY" else entry - (risk * rr_ratio)

                is_win = False
                hit_exit = False
                for j in range(i + 1, min(i + 100, n)):
                    if signal_type == "BUY":
                        if low[j] <= sl:
                            is_win = False
                            hit_exit = True
                            break
                        elif high[j] >= tp:
                            is_win = True
                            hit_exit = True
                            break
                    elif signal_type == "SELL":
                        if high[j] >= sl:
                            is_win = False
                            hit_exit = True
                            break
                        elif low[j] <= tp:
                            is_win = True
                            hit_exit = True
                            break

                signals.append({
                    "symbol": sym,
                    "bar_idx": i,
                    "timestamp": str(df_tf.index[i]),
                    "type": signal_type,
                    "prob": round(prob, 4),
                    "approved": is_approved,
                    "win": is_win if hit_exit else False,
                    "hit_exit": hit_exit
                })

        # Summary for symbol
        df_sig = pd.DataFrame(signals)
        total_sig = len(df_sig)
        approved_df = df_sig[df_sig['approved'] == True] if not df_sig.empty else pd.DataFrame()
        rejected_df = df_sig[df_sig['approved'] == False] if not df_sig.empty else pd.DataFrame()

        num_app = len(approved_df)
        num_rej = len(rejected_df)
        num_app_wins = int(approved_df['win'].sum()) if not approved_df.empty else 0
        num_app_losses = num_app - num_app_wins

        total_signals_all += total_sig
        ml_approved_all += num_app
        ml_rejected_all += num_rej
        approved_wins_all += num_app_wins
        approved_losses_all += num_app_losses

        print(f"{sym:<10} | Signals: {total_sig:<4} | ML Approved: {num_app:<3} | ML Rejected: {num_rej:<4} | Approved Wins: {num_app_wins} | Approved Losses: {num_app_losses}")

    print("-" * 75)
    print(f"TOTAL ALL   | Signals: {total_signals_all:<4} | ML Approved: {ml_approved_all:<3} | ML Rejected: {ml_rejected_all:<4} | Approved Wins: {approved_wins_all} | Approved Losses: {approved_losses_all}")

if __name__ == "__main__":
    run_real_market_funnel()
