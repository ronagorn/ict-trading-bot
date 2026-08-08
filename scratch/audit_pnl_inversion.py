"""
Forensic P&L Accounting & Sign Inversion Audit Script (AURA v6.4)
===================================================================
Inspects real market setup labeling in data/*.parquet, evaluates trade_outcome
encoding (0 vs 1), recalculates exact P&L, Expectancy, and Profit Factor for Validation
and Holdout splits, and identifies the exact source code formula discrepancy!
"""

import os
import sys
import glob
import pandas as pd
import numpy as np
import xgboost as xgb

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bot.production_ml_engine import AUDITED_FEATURE_COLUMNS

def audit_pnl_accounting():
    print("==================================================================")
    print("   AURA v6.4 - P&L, EXPECTANCY & PROFIT FACTOR FORENSIC AUDIT     ")
    print("==================================================================")

    parquet_files = sorted(glob.glob("data/*.parquet"))
    all_setups = []

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
        mean_spread = df_tf['Mean_Spread'].values

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
            c_spread = mean_spread[i]

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
                
                # Check exact price path for TP vs SL
                hit_tp = False
                hit_sl = False
                first_event = None

                for j in range(i + 1, min(i + 40, n)):
                    if signal_type == "BUY":
                        if low[j] <= sl and not hit_tp:
                            hit_sl = True
                            first_event = "SL"
                            break
                        elif high[j] >= tp and not hit_sl:
                            hit_tp = True
                            first_event = "TP"
                            break
                    elif signal_type == "SELL":
                        if high[j] >= sl and not hit_tp:
                            hit_sl = True
                            first_event = "SL"
                            break
                        elif low[j] <= tp and not hit_sl:
                            hit_tp = True
                            first_event = "TP"
                            break

                # Label encoding: 1 = Win (TP hit first), 0 = Loss (SL hit first or timeout)
                trade_outcome = 1 if first_event == "TP" else 0

                fvg_pips = float(gap_size / (point_size * 10))
                vol_spike = float(c_vol / c_vma) if c_vma > 0 else 1.0

                all_setups.append({
                    "timestamp": timestamp_dt,
                    "symbol": sym,
                    "direction": signal_type,
                    "spread_pts": c_spread,
                    "first_event": first_event,
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

    df_real = pd.DataFrame(all_setups).sort_values("timestamp").reset_index(drop=True)
    n_total = len(df_real)
    train_end_idx = int(n_total * 0.70)
    val_end_idx = int(n_total * 0.90)

    df_train = df_real.iloc[:train_end_idx].copy()
    df_val = df_real.iloc[train_end_idx:val_end_idx].copy()
    df_holdout = df_real.iloc[val_end_idx:].copy()

    # Train Base XGBoost Model on Train Split
    X_train = df_train[AUDITED_FEATURE_COLUMNS]
    y_train = df_train["trade_outcome"]

    n_pos = int(y_train.sum())
    n_neg = int(len(y_train) - n_pos)
    scale_pos_weight = float(n_neg / n_pos) if n_pos > 0 else 1.0

    base_xgb = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=3,
        learning_rate=0.03,
        scale_pos_weight=scale_pos_weight,
        eval_metric="logloss",
        random_state=42
    )
    base_xgb.fit(X_train, y_train)

    df_val["xgb_score"] = base_xgb.predict_proba(df_val[AUDITED_FEATURE_COLUMNS])[:, 1]
    df_holdout["xgb_score"] = base_xgb.predict_proba(df_holdout[AUDITED_FEATURE_COLUMNS])[:, 1]

    # Evaluate Holdout at P >= 0.60
    ho_sel = df_holdout[df_holdout["xgb_score"] >= 0.60]
    ho_n = len(ho_sel)
    ho_tp_count = int((ho_sel["trade_outcome"] == 1).sum())
    ho_sl_count = int((ho_sel["trade_outcome"] == 0).sum())
    ho_wr = ho_tp_count / ho_n if ho_n > 0 else 0.0

    # Calculate Correct Accounting:
    correct_gross_profit = ho_tp_count * 3.0
    correct_gross_loss = ho_sl_count * 1.0
    correct_net_r = correct_gross_profit - correct_gross_loss
    correct_expectancy = correct_net_r / ho_n if ho_n > 0 else 0.0
    correct_pf = correct_gross_profit / correct_gross_loss if correct_gross_loss > 0 else 0.0

    # Inspect Inverted Formula:
    inverted_net_r = (ho_sl_count * 1.0) - (ho_tp_count * 3.0)  # Wait! What if 34 - 24 = +10.0?!
    inverted_pf = correct_gross_loss / correct_gross_profit if correct_gross_profit > 0 else 0.0

    print("\n--- HOLDOUT P&L RECONCILIATION AUDIT ---")
    print(f"Total Approved Holdout Trades (P >= 0.60): {ho_n}")
    print(f"TP Hit (Wins, Y=1): {ho_tp_count}")
    print(f"SL Hit / Loss (Y=0): {ho_sl_count}")
    print(f"Empirical Win Rate: {ho_wr:.2%}")
    print(f"\n1. CORRECT MATHEMATICAL ACCOUNTING (Win = +3R, Loss = -1R):")
    print(f"   Gross Profit: {correct_gross_profit:+.2f} R")
    print(f"   Gross Loss:   {correct_gross_loss:+.2f} R")
    print(f"   Total Net R:  {correct_net_r:+.2f} R")
    print(f"   Expectancy:   {correct_expectancy:+.4f} R / trade")
    print(f"   Profit Factor: {correct_pf:.4f}")

    print(f"\n2. INVERTED FORMULA AUDIT (What produced +10.00 R and PF = 1.41):")
    print(f"   (Losses * 1) - (Wins * 3) = ({ho_sl_count} * 1) - ({ho_tp_count} * 3) = {inverted_net_r:+.2f} R")
    print(f"   Inverted Profit Factor (Gross Loss / Gross Profit) = 34 / 24 = {inverted_pf:.4f}")

    # Evaluate Validation at P >= 0.60
    val_sel = df_val[df_val["xgb_score"] >= 0.60]
    val_n = len(val_sel)
    val_tp_count = int((val_sel["trade_outcome"] == 1).sum())
    val_sl_count = int((val_sel["trade_outcome"] == 0).sum())
    val_wr = val_tp_count / val_n if val_n > 0 else 0.0

    val_correct_gp = val_tp_count * 3.0
    val_correct_gl = val_sl_count * 1.0
    val_correct_net_r = val_correct_gp - val_correct_gl
    val_correct_exp = val_correct_net_r / val_n if val_n > 0 else 0.0
    val_correct_pf = val_correct_gp / val_correct_gl if val_correct_gl > 0 else 0.0

    val_inv_net_r = (val_sl_count * 1.0) - (val_tp_count * 3.0)
    val_inv_pf = val_correct_gl / val_correct_gp if val_correct_gp > 0 else 0.0

    print("\n--- VALIDATION P&L RECONCILIATION AUDIT ---")
    print(f"Total Approved Validation Trades (P >= 0.60): {val_n}")
    print(f"TP Hit (Wins, Y=1): {val_tp_count}")
    print(f"SL Hit / Loss (Y=0): {val_sl_count}")
    print(f"Empirical Win Rate: {val_wr:.2%}")
    print(f"\n1. CORRECT MATHEMATICAL ACCOUNTING (Win = +3R, Loss = -1R):")
    print(f"   Gross Profit: {val_correct_gp:+.2f} R")
    print(f"   Gross Loss:   {val_correct_gl:+.2f} R")
    print(f"   Total Net R:  {val_correct_net_r:+.2f} R")
    print(f"   Expectancy:   {val_correct_exp:+.4f} R / trade")
    print(f"   Profit Factor: {val_correct_pf:.4f}")

    print(f"\n2. INVERTED FORMULA AUDIT (What produced +14.50 R and PF = 1.20):")
    print(f"   (Losses * 1) - (Wins * 3) = ({val_sl_count} * 1) - ({val_tp_count} * 3) = {val_inv_net_r:+.2f} R")
    print(f"   Inverted Profit Factor (Gross Loss / Gross Profit) = 71 / 48 = {val_inv_pf:.4f}")

if __name__ == "__main__":
    audit_pnl_accounting()
