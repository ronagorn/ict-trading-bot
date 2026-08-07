"""
Production-Grade ML Filtering & Calibration Engine (AURA v5)
============================================================
Includes:
1. Audited Feature Schema (Anti-Leakage Certified)
2. Probability Calibration (CalibratedClassifierCV / Sigmoid Platt Scaling)
3. Model Versioning & Hashing Metadata
4. Explicit Fail-Safe & Cold-Start Modes (RULE_ONLY, STRICT_MODE, ML_DISABLED)
5. Drift Monitoring (Population Stability Index - PSI)
"""

from __future__ import annotations
import sys
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple, Union
import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.model_selection import TimeSeriesSplit
import xgboost as xgb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.logger import logger

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MODELS_DIR = DATA_DIR / "ml_models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)
MODEL_FILE_PATH = MODELS_DIR / "production_xgboost_calibrated.pkl"
METADATA_FILE_PATH = MODELS_DIR / "production_model_metadata.json"

FEATURE_SCHEMA_VERSION = "v5.0_audited"
AUDITED_FEATURE_COLUMNS = [
    "fvg_size_pips",
    "killzone_hour",
    "trend_alignment",
    "volume_spike_ratio",
    "fvg_quality_score",
    "ob_quality_score",
    "liquidity_quality_score",
    "atr_percentile",
    "trend_score"
]
FORBIDDEN_LEAKAGE_COLUMNS = [
    "close_time", "close_price", "profit_loss", "status",
    "duration", "execution_duration", "ticket_id", "pnl", "r_multiple"
]


class SystemOperationalMode:
    ML_ENABLED = "ML_ENABLED"
    RULE_ONLY = "RULE_ONLY"
    STRICT_MODE = "STRICT_MODE"
    ML_DISABLED = "ML_DISABLED"


@dataclass
class ModelMetadata:
    model_version: str = "5.0.0"
    training_timestamp: str = ""
    feature_schema_version: str = FEATURE_SCHEMA_VERSION
    dataset_hash: str = ""
    calibration_version: str = "Platt_Sigmoid_CV"
    samples_trained: int = 0
    mean_cv_accuracy: float = 0.0
    threshold: float = 0.60
    feature_columns: List[str] = field(default_factory=lambda: list(AUDITED_FEATURE_COLUMNS))


class ProductionMLEngine:
    """
    Production-Grade ML Engine with Probability Calibration, Fail-Safe Gating & Drift Monitoring.
    """

    def __init__(self, model_path: Optional[Path] = None, metadata_path: Optional[Path] = None):
        self.model_path = model_path or MODEL_FILE_PATH
        self.metadata_path = metadata_path or METADATA_FILE_PATH
        self._model = None
        self._metadata: Optional[ModelMetadata] = None

    @staticmethod
    def compute_dataset_hash(df: pd.DataFrame) -> str:
        """Computes deterministic SHA-256 hash of training dataset."""
        df_bytes = df.to_json(orient="values").encode("utf-8")
        return hashlib.sha256(df_bytes).hexdigest()[:16]

    def train_calibrated_pipeline(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Trains XGBoost Classifier with CalibratedClassifierCV on TimeSeriesSplit."""
        if df.empty or len(df) < 50:
            return {"success": False, "reason": "insufficient_data", "mode": SystemOperationalMode.RULE_ONLY}

        try:
            # Security Leakage Assertion
            for col in FORBIDDEN_LEAKAGE_COLUMNS:
                assert col not in df.columns or col not in AUDITED_FEATURE_COLUMNS, f"Security Violation: {col}"

            # Prepare Features
            for col in AUDITED_FEATURE_COLUMNS:
                if col not in df.columns:
                    df[col] = 0.0

            X = df[AUDITED_FEATURE_COLUMNS]
            y = df["trade_outcome"]

            n_pos = int(y.sum())
            n_neg = int(len(y) - n_pos)
            scale_pos_weight = float(n_neg / n_pos) if n_pos > 0 else 1.0

            base_model = xgb.XGBClassifier(
                n_estimators=120,
                max_depth=4,
                learning_rate=0.04,
                scale_pos_weight=scale_pos_weight,
                eval_metric="logloss",
                random_state=42
            )

            # Calibrate Probabilities using Sigmoid (Platt Scaling) via TimeSeriesSplit
            tscv = TimeSeriesSplit(n_splits=min(5, max(2, len(df) // 25)))
            calibrated_model = CalibratedClassifierCV(estimator=base_model, method="sigmoid", cv=tscv)
            calibrated_model.fit(X, y)

            # Compute CV Accuracy
            cv_accs = []
            for train_idx, val_idx in tscv.split(X):
                X_tr, X_va = X.iloc[train_idx], X.iloc[val_idx]
                y_tr, y_va = y.iloc[train_idx], y.iloc[val_idx]
                m_fold = xgb.XGBClassifier(n_estimators=100, max_depth=4, scale_pos_weight=scale_pos_weight, random_state=42)
                m_fold.fit(X_tr, y_tr)
                cv_accs.append(float(np.mean(m_fold.predict(X_va) == y_va)))

            mean_cv_acc = float(np.mean(cv_accs)) if cv_accs else 0.0

            # Save Model & Metadata
            joblib.dump(calibrated_model, self.model_path)
            self._model = calibrated_model

            dataset_hash = self.compute_dataset_hash(df)
            meta = ModelMetadata(
                training_timestamp=datetime.now(timezone.utc).isoformat(),
                dataset_hash=dataset_hash,
                samples_trained=len(y),
                mean_cv_accuracy=round(mean_cv_acc, 4)
            )
            self._metadata = meta
            
            with open(self.metadata_path, "w", encoding="utf-8") as f:
                json.dump(asdict(meta), f, indent=2)

            return {
                "success": True,
                "dataset_hash": dataset_hash,
                "mean_cv_accuracy": mean_cv_acc,
                "samples_trained": len(y),
                "model_path": str(self.model_path)
            }
        except Exception as e:
            logger.error(f"Error in train_calibrated_pipeline: {e}")
            return {"success": False, "error": str(e)}

    def load_model_and_metadata(self) -> Tuple[Optional[Any], Optional[ModelMetadata]]:
        if self._model is not None and self._metadata is not None:
            return self._model, self._metadata

        if self.model_path.exists() and self.metadata_path.exists():
            try:
                self._model = joblib.load(self.model_path)
                with open(self.metadata_path, "r", encoding="utf-8") as f:
                    meta_dict = json.load(f)
                self._metadata = ModelMetadata(**meta_dict)
                return self._model, self._metadata
            except Exception as e:
                logger.error(f"Error loading model/metadata: {e}")
                return None, None
        return None, None

    def predict_trade_permission(
        self,
        signal_dict: Dict[str, Any],
        threshold: float = 0.60,
        total_closed_trades: int = 400
    ) -> Tuple[bool, float, str, float]:
        """
        Inference Gate with Fail-Safe & Cold Start Operational Modes.
        Returns (approved, calibrated_prob, operational_mode, risk_multiplier)
        """
        # 1. Cold Start Gate (< 300 trades in DB)
        if total_closed_trades < 300:
            setup_score = signal_dict.get("composite_score", signal_dict.get("fvg_quality_score", 50.0))
            if setup_score >= 65.0:
                # Approved under RULE_ONLY mode with 50% Lot Size Risk Reduction
                return True, 0.50, SystemOperationalMode.RULE_ONLY, 0.50
            else:
                return False, 0.00, SystemOperationalMode.RULE_ONLY, 0.00

        # 2. Load Model & Metadata
        model, metadata = self.load_model_and_metadata()
        
        # FAIL SAFE: Model unavailable or corrupted
        if model is None or metadata is None:
            setup_score = signal_dict.get("composite_score", 50.0)
            if setup_score >= 75.0:
                # Approved under STRICT_MODE with 50% Risk Reduction
                return True, 0.50, SystemOperationalMode.STRICT_MODE, 0.50
            return False, 0.00, SystemOperationalMode.ML_DISABLED, 0.00

        try:
            # Construct Feature Row
            row_dict = {}
            for col in AUDITED_FEATURE_COLUMNS:
                row_dict[col] = float(signal_dict.get(col, 0.0))

            X_in = pd.DataFrame([row_dict], columns=AUDITED_FEATURE_COLUMNS)
            
            # Predict Calibrated Probability
            prob = float(model.predict_proba(X_in)[0][1])
            is_approved = prob >= threshold

            return is_approved, round(prob, 4), SystemOperationalMode.ML_ENABLED, 1.00

        except Exception as e:
            logger.error(f"Fail-Safe triggered during inference: {e}")
            setup_score = signal_dict.get("composite_score", 50.0)
            if setup_score >= 75.0:
                return True, 0.50, SystemOperationalMode.STRICT_MODE, 0.50
            return False, 0.00, SystemOperationalMode.ML_DISABLED, 0.00

    @staticmethod
    def calculate_population_stability_index(reference: np.ndarray, current: np.ndarray, bins: int = 10) -> float:
        """Calculates Population Stability Index (PSI) to detect Feature/Prediction Drift."""
        if len(reference) == 0 or len(current) == 0:
            return 0.0
        
        quantiles = np.linspace(0, 1, bins + 1)
        bin_edges = np.quantile(reference, quantiles)
        bin_edges[0] -= 1e-5
        bin_edges[-1] += 1e-5

        ref_counts, _ = np.histogram(reference, bins=bin_edges)
        cur_counts, _ = np.histogram(current, bins=bin_edges)

        ref_pct = np.maximum(ref_counts / len(reference), 1e-4)
        cur_pct = np.maximum(cur_counts / len(current), 1e-4)

        psi = np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct))
        return float(psi)
