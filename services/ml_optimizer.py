"""
Machine Learning Parameter Optimizer
=====================================
ใช้ scikit-learn วิเคราะห์ประวัติเทรดจาก Supabase
หา threshold ที่ให้ Win Rate > 65% แล้วส่งคำแนะนำผ่าน Telegram
รอการอนุมัติจากมนุษย์ก่อนอัปเดต config.json

Usage:
    python -m services.ml_optimizer
    python -m services.ml_optimizer --dry-run
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.logger import logger
from services.db_client import SupabaseClient
from services.telegram_bot import TelegramNotifier

load_dotenv()

CONFIG_PATH = Path(__file__).resolve().parent.parent / "bot" / "config.json"
RECOMMENDATIONS_DIR = Path(__file__).resolve().parent.parent / "data" / "ml_recommendations"
PENDING_APPROVAL_FILE = RECOMMENDATIONS_DIR / "pending_approval.json"
TARGET_ACCURACY = 0.65


class MLOptimizer:
    """ML-based parameter tuning with human-in-the-loop approval."""

    FEATURE_COLUMNS = [
        "fvg_size",
        "killzone_hour",
        "volume_spike_multiplier",
        "trend_strength",
    ]

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or CONFIG_PATH
        self.db = SupabaseClient()
        self.telegram = TelegramNotifier()
        self.config = self._load_config()
        RECOMMENDATIONS_DIR.mkdir(parents=True, exist_ok=True)

    def _load_config(self) -> dict:
        with open(self.config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def fetch_training_data(self, min_trades: int = 30) -> pd.DataFrame:
        """ดึงประวัติเทรดที่ปิดแล้วจาก Supabase"""
        rows = self.db.get_closed_trades_for_ml(limit=2000)
        if not rows:
            logger.warning("No closed trades in Supabase for ML training.")
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df = self._engineer_features(df)

        closed = df[df["status"].isin(["WIN", "LOSS"])].copy()
        if len(closed) < min_trades:
            logger.warning(f"Only {len(closed)} closed trades — need at least {min_trades}")
            return pd.DataFrame()

        closed["target"] = (closed["status"] == "WIN").astype(int)
        return closed

    def _engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """สร้าง feature matrix จาก trade log"""
        df = df.copy()

        # Killzone hour จาก entry_time
        if "entry_time" in df.columns:
            df["entry_dt"] = pd.to_datetime(df["entry_time"], utc=True, errors="coerce")
            df["killzone_hour"] = df["entry_dt"].dt.hour
        else:
            df["killzone_hour"] = 8

        # fvg_size
        df["fvg_size"] = pd.to_numeric(df.get("fvg_size", 0), errors="coerce").fillna(0)

        # volume_spike_multiplier — จาก DB หรือประมาณจาก fvg_size
        if "volume_spike_multiplier" in df.columns:
            df["volume_spike_multiplier"] = pd.to_numeric(
                df["volume_spike_multiplier"], errors="coerce"
            ).fillna(1.5)
        else:
            median_fvg = df["fvg_size"].median() if df["fvg_size"].median() > 0 else 1.0
            df["volume_spike_multiplier"] = (df["fvg_size"] / median_fvg).clip(0.5, 5.0)

        # trend_strength
        if "trend_strength" in df.columns:
            df["trend_strength"] = pd.to_numeric(
                df["trend_strength"], errors="coerce"
            ).fillna(1.0)
        else:
            df["trend_strength"] = 1.0

        return df

    def train_model(
        self, df: pd.DataFrame
    ) -> Tuple[Any, float, Dict[str, float]]:
        """Train RandomForest + GradientBoosting ensemble, return best model"""
        X = df[self.FEATURE_COLUMNS].values
        y = df["target"].values

        if len(np.unique(y)) < 2:
            raise ValueError("Need both WIN and LOSS samples for training")

        # Temporal sequential split (75% train, 25% test) to prevent future data leakage
        split_idx = int(len(X) * 0.75)
        X_train, X_test = X[:split_idx], X[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]

        models = {
            "RandomForest": RandomForestClassifier(
                n_estimators=200, max_depth=6, random_state=42, class_weight="balanced"
            ),
            "GradientBoosting": GradientBoostingClassifier(
                n_estimators=150, max_depth=4, random_state=42
            ),
        }

        best_model = None
        best_acc = 0.0
        best_name = ""

        for name, model in models.items():
            model.fit(X_train, y_train)
            preds = model.predict(X_test)
            acc = accuracy_score(y_test, preds)
            logger.info(f"{name} accuracy: {acc:.3f}")
            if acc > best_acc:
                best_acc = acc
                best_model = model
                best_name = name

        importances = {}
        if hasattr(best_model, "feature_importances_"):
            for col, imp in zip(self.FEATURE_COLUMNS, best_model.feature_importances_):
                importances[col] = round(float(imp), 4)

        logger.info(f"Best model: {best_name} ({best_acc:.3f})")
        logger.debug(classification_report(y_test, best_model.predict(X_test)))

        return best_model, best_acc, importances

    def find_optimal_thresholds(self, df: pd.DataFrame, model) -> Dict[str, Any]:
        """
        Grid search บน feature ranges เพื่อหา threshold ที่ Win Rate สูงสุด
        """
        wins = df[df["target"] == 1]
        best = {
            "expected_win_rate": 0.0,
            "expected_accuracy": 0.0,
            "sample_count": 0,
            "thresholds": {},
            "suggestions": [],
        }

        fvg_sizes = df["fvg_size"]
        fvg_min_candidates = [
            float(fvg_sizes.quantile(q)) for q in (0.1, 0.25, 0.35, 0.5) if fvg_sizes.max() > 0
        ]
        fvg_max_candidates = [
            float(fvg_sizes.quantile(q)) for q in (0.5, 0.65, 0.75, 0.9) if fvg_sizes.max() > 0
        ]
        vol_candidates = [1.2, 1.5, 1.8, 2.0, 2.5]
        hour_ranges = [(7, 12), (8, 12), (13, 17), (2, 5), (8, 17)]

        for fvg_lo in fvg_min_candidates or [0]:
            for fvg_hi in fvg_max_candidates or [999999]:
                if fvg_lo >= fvg_hi:
                    continue
                for vol_min in vol_candidates:
                    for h_start, h_end in hour_ranges:
                        mask = (
                            (df["fvg_size"] >= fvg_lo)
                            & (df["fvg_size"] <= fvg_hi)
                            & (df["volume_spike_multiplier"] >= vol_min)
                            & (df["killzone_hour"] >= h_start)
                            & (df["killzone_hour"] <= h_end)
                        )
                        subset = df[mask]
                        if len(subset) < 10:
                            continue

                        wr = subset["target"].mean()
                        if wr > best["expected_win_rate"]:
                            X_sub = subset[self.FEATURE_COLUMNS].values
                            preds = model.predict(X_sub)
                            acc = accuracy_score(subset["target"], preds)

                            session = "NY" if h_start >= 7 else "London" if h_start <= 5 else "Mixed"
                            best = {
                                "expected_win_rate": round(float(wr), 4),
                                "expected_accuracy": round(float(acc), 4),
                                "sample_count": int(len(subset)),
                                "thresholds": {
                                    "fvg_size_min": round(fvg_lo, 5),
                                    "fvg_size_max": round(fvg_hi, 5),
                                    "volume_spike_mult_min": vol_min,
                                    "killzone_hour_start": h_start,
                                    "killzone_hour_end": h_end,
                                    "trend_strength_min": round(
                                        float(subset["trend_strength"].quantile(0.25)), 3
                                    ),
                                },
                                "suggestions": [
                                    f"รับเฉพาะ FVG ขนาด {fvg_lo:.2f}–{fvg_hi:.2f} points",
                                    f"Volume Spike ขั้นต่ำ {vol_min}x ของ MA20",
                                    f"เทรดเฉพาะช่วง {h_start}:00–{h_end}:00 UTC ({session} session)",
                                    f"Win Rate คาดการณ์: {wr*100:.1f}% จาก {len(subset)} ไม้",
                                ],
                            }

        return best

    def build_recommendation_report(
        self, model_acc: float, importances: dict, thresholds: dict
    ) -> dict:
        """สร้าง JSON report สำหรับ config.json"""
        aura = self.config.get("aura_ultimate", {})
        ts = datetime.now(timezone.utc).isoformat()

        report = {
            "generated_at": ts,
            "model_accuracy": round(model_acc, 4),
            "target_accuracy": TARGET_ACCURACY,
            "meets_target": model_acc >= TARGET_ACCURACY,
            "feature_importances": importances,
            "optimal_thresholds": thresholds.get("thresholds", {}),
            "expected_win_rate": thresholds.get("expected_win_rate", 0),
            "expected_accuracy": thresholds.get("expected_accuracy", 0),
            "sample_count": thresholds.get("sample_count", 0),
            "suggestions_th": thresholds.get("suggestions", []),
            "proposed_config_changes": {
                "aura_ultimate": {
                    "fvg_atr_mult": self._suggest_fvg_atr_mult(thresholds),
                    "volume_spike_mult": thresholds.get("thresholds", {}).get(
                        "volume_spike_mult_min", aura.get("volume_spike_mult", 1.5)
                    ),
                    "volume_ma_period": aura.get("volume_ma_period", 20),
                    "preferred_killzone_hours": {
                        "start": thresholds.get("thresholds", {}).get("killzone_hour_start", 8),
                        "end": thresholds.get("thresholds", {}).get("killzone_hour_end", 12),
                    },
                }
            },
            "approval_status": "PENDING",
            "approval_required": True,
        }

        out_file = RECOMMENDATIONS_DIR / f"ml_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        with open(PENDING_APPROVAL_FILE, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        logger.info(f"ML recommendation saved: {out_file}")
        return report

    @staticmethod
    def _suggest_fvg_atr_mult(thresholds: dict) -> float:
        th = thresholds.get("thresholds", {})
        fvg_min = th.get("fvg_size_min", 0)
        fvg_max = th.get("fvg_size_max", 0)
        if fvg_min > 0 and fvg_max > fvg_min:
            return round(min(0.8, max(0.2, (fvg_min + fvg_max) / 2 / 10)), 2)
        return 0.5

    def send_telegram_approval_request(self, report: dict):
        """ส่งคำแนะนำ ML ไป Telegram พร้อมปุ่ม Approve/Reject"""
        suggestions = report.get("suggestions_th", [])
        body = "\n".join(f"• {s}" for s in suggestions)
        msg = (
            f"🧠 <b>ML Parameter Optimizer — คำแนะนำใหม่</b>\n\n"
            f"📊 Model Accuracy: <b>{report.get('model_accuracy', 0)*100:.1f}%</b>\n"
            f"🎯 Expected Win Rate: <b>{report.get('expected_win_rate', 0)*100:.1f}%</b>\n"
            f"📁 Sample Size: {report.get('sample_count', 0)} trades\n\n"
            f"<b>ข้อเสนอแนะ:</b>\n{body}\n\n"
            f"⚠️ กดอนุมัติเพื่ออัปเดต config.json หรือเพิกเฉย"
        )
        self.telegram.send_ml_config_suggestion(msg)

    def apply_approved_config(self) -> bool:
        """อัปเดต config.json หลังได้รับการอนุมัติ"""
        if not PENDING_APPROVAL_FILE.exists():
            logger.warning("No pending ML approval file.")
            return False

        with open(PENDING_APPROVAL_FILE, "r", encoding="utf-8") as f:
            report = json.load(f)

        if report.get("approval_status") != "APPROVED":
            logger.warning("Report not approved yet.")
            return False

        changes = report.get("proposed_config_changes", {}).get("aura_ultimate", {})
        config = self._load_config()
        aura = config.setdefault("aura_ultimate", {})

        for key, val in changes.items():
            if key == "preferred_killzone_hours":
                kz = config.setdefault("killzones_ny_time", {})
                ny = kz.setdefault("new_york", {})
                ny["start"] = f"{val['start']:02d}:00"
                ny["end"] = f"{val['end']:02d}:00"
            else:
                aura[key] = val

        aura["ml_last_updated"] = datetime.now(timezone.utc).isoformat()
        aura["ml_model_accuracy"] = report.get("model_accuracy")

        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        report["approval_status"] = "APPLIED"
        with open(PENDING_APPROVAL_FILE, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        logger.info("config.json updated from ML recommendation.")
        self.telegram.send_message("✅ <b>ML Optimizer:</b> อัปเดต config.json เรียบร้อยแล้ว")
        return True

    def mark_approved(self):
        if PENDING_APPROVAL_FILE.exists():
            with open(PENDING_APPROVAL_FILE, "r", encoding="utf-8") as f:
                report = json.load(f)
            report["approval_status"] = "APPROVED"
            with open(PENDING_APPROVAL_FILE, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)

    def mark_rejected(self):
        if PENDING_APPROVAL_FILE.exists():
            with open(PENDING_APPROVAL_FILE, "r", encoding="utf-8") as f:
                report = json.load(f)
            report["approval_status"] = "REJECTED"
            with open(PENDING_APPROVAL_FILE, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
        self.telegram.send_message("❌ <b>ML Optimizer:</b> คำแนะนำถูกปฏิเสธ — ไม่มีการเปลี่ยน config")

    def run(self, dry_run: bool = False, send_telegram: bool = True) -> Optional[dict]:
        """Pipeline หลัก: fetch → train → threshold → report → Telegram"""
        df = self.fetch_training_data()
        if df.empty:
            logger.error("Insufficient training data.")
            return None

        model, acc, importances = self.train_model(df)
        thresholds = self.find_optimal_thresholds(df, model)
        report = self.build_recommendation_report(acc, importances, thresholds)

        if acc < TARGET_ACCURACY:
            logger.warning(
                f"Model accuracy {acc:.3f} below target {TARGET_ACCURACY}. "
                "Report generated but flagged."
            )
            report["meets_target"] = False

        if send_telegram and not dry_run:
            self.send_telegram_approval_request(report)
        elif dry_run:
            logger.info("Dry run — Telegram notification skipped.")

        return report


def main():
    import argparse

    parser = argparse.ArgumentParser(description="AURA ML Parameter Optimizer")
    parser.add_argument("--dry-run", action="store_true", help="Skip Telegram notification")
    parser.add_argument("--apply", action="store_true", help="Apply approved config")
    args = parser.parse_args()

    optimizer = MLOptimizer()

    if args.apply:
        ok = optimizer.apply_approved_config()
        sys.exit(0 if ok else 1)

    report = optimizer.run(dry_run=args.dry_run)
    if report:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
