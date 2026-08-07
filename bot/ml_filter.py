"""
Machine Learning Trade Filter Module (XGBoost)
==============================================
Module นี้รับหน้าที่กรองสัญญาณเทรด (Signal) จาก AURA ICT Strategy 
โดยใช้โมเดล XGBoost ทำนายความน่าจะเป็นที่จะชนะ (Win Probability) 
เพื่อให้ Win Rate สูงกว่า 60%
"""
from __future__ import annotations
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sklearn.model_selection import TimeSeriesSplit
import xgboost as xgb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bot.logger import logger
from services.db_client import SupabaseClient

load_dotenv()
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MODELS_DIR = DATA_DIR / "ml_models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)
MODEL_FILE_PATH = MODELS_DIR / "xgboost_trade_filter.pkl"

MIN_TRADES_COLD_START = 300
PROBABILITY_THRESHOLD = 0.60
FEATURE_COLUMNS = ["fvg_size_pips", "killzone_hour", "trend_alignment", "volume_spike_ratio"]
FORBIDDEN_LEAKAGE_COLUMNS = ["close_time", "close_price", "profit_loss", "status", "duration", "execution_duration", "ticket_id"]

class MLFilterEngine:
    def __init__(self, model_path: Optional[Path] = None):
        self.model_path = model_path or MODEL_FILE_PATH
        self._model = None

    def _to_pips(self, fvg_size_val: float, symbol: str) -> float:
        if pd.isna(fvg_size_val) or fvg_size_val <= 0: return 0.0
        sym = str(symbol).upper()
        if "GOLD" in sym or "XAU" in sym: return float(fvg_size_val) * 10.0
        elif "BTC" in sym: return float(fvg_size_val)
        elif len(sym) >= 6:
            if fvg_size_val < 0.1: return float(fvg_size_val) * 10000.0
            return float(fvg_size_val)
        return float(fvg_size_val)

    def fetch_training_data(self, db_client: Optional[SupabaseClient] = None) -> pd.DataFrame:
        db = db_client or SupabaseClient()
        if not db.enabled:
            logger.warning("Supabase client not enabled.")
            return pd.DataFrame()
        try:
            rows = db.get_closed_trades_for_ml(limit=3000)
            if not rows: return pd.DataFrame()
            df = pd.DataFrame(rows)
            if df.empty: return pd.DataFrame()
            if "status" in df.columns:
                df = df[df["status"].isin(["WIN", "LOSS"])].copy()
            if df.empty: return pd.DataFrame()
            raw_fvg = df.get("fvg_size", pd.Series([0.0] * len(df)))
            symbols = df.get("symbol", pd.Series(["EURUSD"] * len(df)))
            df["fvg_size_pips"] = [self._to_pips(f, s) for f, s in zip(raw_fvg, symbols)]
            if "entry_time" in df.columns:
                entry_dt = pd.to_datetime(df["entry_time"], utc=True, errors="coerce")
                df["killzone_hour"] = entry_dt.dt.hour.fillna(8).astype(int)
            else:
                df["killzone_hour"] = 8
            if "trend_alignment" in df.columns:
                df["trend_alignment"] = pd.to_numeric(df["trend_alignment"], errors="coerce").fillna(1).astype(int)
            elif "trend_strength" in df.columns:
                ts = pd.to_numeric(df["trend_strength"], errors="coerce").fillna(0)
                df["trend_alignment"] = (ts > 0.5).astype(int)
            else:
                df["trend_alignment"] = 1
            if "volume_spike_multiplier" in df.columns:
                df["volume_spike_ratio"] = pd.to_numeric(df["volume_spike_multiplier"], errors="coerce").fillna(1.0)
            else:
                df["volume_spike_ratio"] = 1.0
            df["trade_outcome"] = (df["status"].str.upper() == "WIN").astype(int)
            for col in FORBIDDEN_LEAKAGE_COLUMNS:
                assert col not in FEATURE_COLUMNS, f"Security Violation: {col}"
            req_cols = FEATURE_COLUMNS + ["trade_outcome"]
            for col in req_cols:
                if col not in df.columns:
                    if col == "trade_outcome": return pd.DataFrame()
                    df[col] = 0.0
            return df[req_cols].dropna().copy()
        except Exception as e:
            logger.error(f"Error in fetch_training_data: {e}")
            return pd.DataFrame()

    def train_xgboost_model(self, df: pd.DataFrame) -> Dict[str, Any]:
        if df.empty or len(df) < 30:
            return {"success": False, "reason": "insufficient_data"}
        try:
            X = df[FEATURE_COLUMNS]
            y = df["trade_outcome"]
            n_pos = int(y.sum())
            n_neg = int(len(y) - n_pos)
            scale_pos_weight = float(n_neg / n_pos) if n_pos > 0 else 1.0
            tscv = TimeSeriesSplit(n_splits=min(5, max(2, len(df) // 20)))
            accuracies, best_score = [], -1.0
            for train_idx, val_idx in tscv.split(X):
                X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
                y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]
                model = xgb.XGBClassifier(n_estimators=100, max_depth=4, learning_rate=0.05, scale_pos_weight=scale_pos_weight, eval_metric="logloss", random_state=42)
                model.fit(X_train, y_train)
                acc = float(np.mean(model.predict(X_val) == y_val))
                accuracies.append(acc)
                if acc >= best_score: best_score = acc
            mean_acc = float(np.mean(accuracies)) if accuracies else 0.0
            final_model = xgb.XGBClassifier(n_estimators=150, max_depth=4, learning_rate=0.05, scale_pos_weight=scale_pos_weight, eval_metric="logloss", random_state=42)
            final_model.fit(X, y)
            joblib.dump(final_model, self.model_path)
            self._model = final_model
            return {"success": True, "mean_accuracy": mean_acc, "best_cv_accuracy": best_score, "samples_trained": len(y), "model_path": str(self.model_path)}
        except Exception as e:
            logger.error(f"Train error: {e}")
            return {"success": False, "error": str(e)}

    def load_model(self) -> Optional[xgb.XGBClassifier]:
        if self._model is not None: return self._model
        if self.model_path.exists():
            try:
                self._model = joblib.load(self.model_path)
                return self._model
            except Exception:
                return None
        return None

    def predict_signal_probability(self, signal_dict: Dict[str, Any], db_client: Optional[SupabaseClient] = None) -> bool:
        db = db_client or SupabaseClient()
        try:
            trades = db.get_closed_trades_for_ml(limit=400) if db.enabled else []
            total_count = len(trades)
        except Exception:
            total_count = 0
        if total_count < MIN_TRADES_COLD_START:
            return True
        model = self.load_model()
        if model is None: return True
        try:
            sym = signal_dict.get("symbol", "EURUSD")
            fvg = self._to_pips(signal_dict.get("fvg_size", 0.0), sym)
            kz = signal_dict.get("killzone_hour", datetime.now(timezone.utc).hour)
            trend_align = int(signal_dict.get("trend_alignment", 1))
            vol_spike = float(signal_dict.get("volume_spike", signal_dict.get("volume_spike_ratio", 1.5)))
            X_in = pd.DataFrame([[fvg, int(kz), trend_align, vol_spike]], columns=FEATURE_COLUMNS)
            prob = float(model.predict_proba(X_in)[0][1])
            return prob >= PROBABILITY_THRESHOLD
        except Exception as e:
            logger.error(f"Inference error: {e}")
            return True

_engine = MLFilterEngine()
def fetch_training_data(db = None, db_client = None): return _engine.fetch_training_data(db_client or db)
def train_xgboost_model(df): return _engine.train_xgboost_model(df)
def predict_signal_probability(signal_dict, db = None, db_client = None): return _engine.predict_signal_probability(signal_dict, db_client or db)
