"""
Investigate Exact Discrepancy Between v6.2/v6.3 and v6.4 Holdout Results
========================================================================
Compares setup extraction, look-ahead index bounds, threshold filtering,
and setup list differences between v6.2/v6.3 scripts and v6.4 script.
"""

import os
import sys
import glob
import pandas as pd
import numpy as np
import xgboost as xgb

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bot.production_ml_engine import AUDITED_FEATURE_COLUMNS

def investigate_discrepancy():
    print("==================================================================")
    print("   AURA v6.5 - v6.2/v6.3 vs v6.4 DISCREPANCY INVESTIGATION          ")
    print("==================================================================")

    parquet_files = sorted(glob.glob("data/*.parquet"))

    # Script A: Setup extraction from run_v62 / run_v63
    setups_v62 = []
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

        for i in range(20, n - 40):
            c_close = close[i]
            c_ema = ema200[i]
            c_atr = atr[i]
            c_vol = volume[i]
            c_vma = vol_ma20[i]

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
                timestamp_dt = df_tf.index[i]
                hour_utc = timestamp_dt.hour if hasattr(timestamp_dt, 'hour') else 14
                risk = abs(entry - sl)
                rr_ratio = 3.0
                tp = entry + (risk * rr_ratio) if signal_type == "BUY" else entry - (risk * rr_ratio)
                
                trade_outcome = 0
                for j in range(i + 1, min(i + 40, n)):
                    if signal_type == "BUY":
                        if low[j] <= sl:
                            trade_outcome = 0
                            break
                        elif high[j] >= tp:
                            trade_outcome = 1
                            break
                    elif signal_type == "SELL":
                        if high[j] >= sl:
                            trade_outcome = 0
                            break
                        elif low[j] <= tp:
                            trade_outcome = 1
                            break

                fvg_pips = float(gap_size / (point_size * 10))
                vol_spike = float(c_vol / c_vma) if c_vma > 0 else 1.0

                setups_v62.append({
                    "timestamp": timestamp_dt,
                    "symbol": sym,
                    "direction": signal_type,
                    "fvg_size_pips": max(0.1, min(fvg_pips, 100.0)),
                    "killzone_hour": float(hour_utc),
                    "trend_alignment": 1.0,
                    "volume_spike_ratio": max(0.5, min(vol_spike, 10.0)),
                    "fvg_quality_score": max(10.0, min(fvg_pips * 5.0, 100.0)),
                    "ob_quality_score": 60.0,
                    "liquidity_quality_score": 65.0,
                    "atr_percentile": 50.0,
                    "trend_score": 70.0,
                    "trade_outcome": trade_outcome
                })

    df_real = pd.DataFrame(setups_v62).sort_values("timestamp").reset_index(drop=True)
    n_total = len(df_real)
    train_end_idx = int(n_total * 0.70)
    val_end_idx = int(n_total * 0.90)

    df_train = df_real.iloc[:train_end_idx].copy()
    df_val = df_real.iloc[train_end_idx:val_end_idx].copy()
    df_holdout = df_real.iloc[val_end_idx:].copy()

    X_train = df_train[AUDITED_FEATURE_COLUMNS]
    y_train = df_train["trade_outcome"]

    scale_pos_weight = float((len(y_train) - y_train.sum()) / y_train.sum())

    base_xgb = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=3,
        learning_rate=0.03,
        scale_pos_weight=scale_pos_weight,
        eval_metric="logloss",
        random_state=42
    )
    base_xgb.fit(X_train, y_train)

    df_holdout["xgb_score"] = base_xgb.predict_proba(df_holdout[AUDITED_FEATURE_COLUMNS])[:, 1]

    # Compare exact floating-point bounds: >= 0.60 vs > 0.60 vs >= 0.5999999
    h_ge_60 = df_holdout[df_holdout["xgb_score"] >= 0.60]
    h_gt_60 = df_holdout[df_holdout["xgb_score"] > 0.60]

    print(f"Total Holdout Setups: {len(df_holdout)}")
    print(f"Setups with xgb_score >= 0.60: {len(h_ge_60)} (Wins: {h_ge_60['trade_outcome'].sum()}, Losses: {len(h_ge_60) - h_ge_60['trade_outcome'].sum()})")
    print(f"Setups with xgb_score > 0.60:  {len(h_gt_60)} (Wins: {h_gt_60['trade_outcome'].sum()}, Losses: {len(h_gt_60) - h_gt_60['trade_outcome'].sum()})")

    # Check setup tie-breaker logic in v6.2 script:
    # In v6.2, if low[j] <= sl and high[j] >= tp on the SAME candle:
    # Look at line 91 in run_v62_economic_validation.py vs run_v64_forensic_pnl_audit.py!
    # In run_v62_economic_validation.py:
    # if low[j] <= sl: trade_outcome = 0; break; elif high[j] >= tp: trade_outcome = 1; break;
    # In run_v64_forensic_pnl_audit.py:
    # if low[j] <= sl and not hit_tp: hit_sl = True; break; elif high[j] >= tp and not hit_sl: hit_tp = True; break;
    # Both break on first event!

    # Why did v6.2 report N=42 (8 wins, 34 losses) while v6.4 report N=37 (9 wins, 28 losses)?
    # Let's inspect the exact setups in df_holdout with xgb_score around 0.58-0.61!
    borderline = df_holdout[(df_holdout["xgb_score"] >= 0.58) & (df_holdout["xgb_score"] <= 0.62)]
    print("\nBorderline XGBoost Scores in Holdout (0.58 - 0.62):")
    for idx, row in borderline.iterrows():
        print(f"  Setup {idx} | {row['timestamp']} | {row['symbol']} | {row['direction']} | xgb_score={row['xgb_score']:.6f} | outcome={row['trade_outcome']}")

if __name__ == "__main__":
    investigate_discrepancy()
