"""
Unit Tests for Machine Learning Trade Filter (bot/ml_filter.py)
=============================================================
ทดสอบการทำงานของ ML Filter:
1. Feature Engineering & Security Check (No Data Leakage)
2. XGBoost Model Training (TimeSeriesSplit)
3. Cold Start Logic (< 300 trades -> True)
4. Inference Threshold Logic (prob >= 0.60 -> True, else False)
5. Robust Exception Fallback
"""

import sys
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.ml_filter import (
    MLFilterEngine,
    fetch_training_data,
    train_xgboost_model,
    predict_signal_probability,
    FEATURE_COLUMNS,
    FORBIDDEN_LEAKAGE_COLUMNS
)


class TestMLFilter(unittest.TestCase):

    def setUp(self):
        self.engine = MLFilterEngine()

    def test_security_leakage_assertion(self):
        """ทดสอบว่าห้ามมี future data คอลัมน์ใดอยู่ใน FEATURE_COLUMNS"""
        for col in FORBIDDEN_LEAKAGE_COLUMNS:
            self.assertNotIn(col, FEATURE_COLUMNS, f"Leakage violation: {col} is in FEATURE_COLUMNS")

    @patch("bot.ml_filter.SupabaseClient")
    def test_cold_start_bypass(self, mock_supabase_class):
        """ทดสอบ Cold Start: ถ้าประวัติเทรดปิดแล้วน้อยกว่า 300 จะต้อง return True เสมอ"""
        mock_db = MagicMock()
        mock_db.enabled = True
        # จำลองส่งข้อมูลกลับมา 50 เทรด (< 300)
        mock_db.get_closed_trades_for_ml.return_value = [{"id": i, "status": "WIN"} for i in range(50)]

        signal_dict = {
            "symbol": "GOLD#",
            "fvg_size": 2.0,
            "volume_spike": 1.6,
            "trend_alignment": 1,
            "killzone_hour": 14
        }

        approved = predict_signal_probability(signal_dict, db_client=mock_db)
        self.assertTrue(approved, "Cold start should bypass ML and return True")

    def test_training_pipeline_with_dummy_data(self):
        """ทดสอบการสร้างโมเดลด้วย TimeSeriesSplit และ dataset จำลอง"""
        # สร้าง dummy dataframe
        np.random.seed(42)
        n = 100
        df_dummy = pd.DataFrame({
            "fvg_size_pips": np.random.uniform(2.0, 15.0, n),
            "killzone_hour": np.random.choice([8, 9, 14, 15], n),
            "trend_alignment": np.random.choice([0, 1], n, p=[0.3, 0.7]),
            "volume_spike_ratio": np.random.uniform(1.0, 3.5, n),
            "trade_outcome": np.random.choice([0, 1], n, p=[0.6, 0.4])  # 40% win rate baseline
        })

        res = train_xgboost_model(df_dummy)
        self.assertTrue(res.get("success"), f"Training failed: {res}")
        self.assertIn("mean_accuracy", res)

    @patch("bot.ml_filter.MLFilterEngine.load_model")
    @patch("bot.ml_filter.SupabaseClient")
    def test_inference_threshold_logic(self, mock_supabase_class, mock_load_model):
        """ทดสอบ Inference: prob >= 0.60 คืน True, ถ้าต่ำกว่าคืน False"""
        mock_db = MagicMock()
        mock_db.enabled = True
        # จำลองเทรดใน DB >= 300 เพื่อข้าม cold start
        mock_db.get_closed_trades_for_ml.return_value = [{"id": i, "status": "WIN"} for i in range(350)]

        # Mock XGBoost model ที่คืนค่า predict_proba
        mock_model = MagicMock()
        
        # กรณีที่ 1: Probability = 0.75 (>= 0.60) -> ควรได้ True
        mock_model.predict_proba.return_value = np.array([[0.25, 0.75]])
        mock_load_model.return_value = mock_model

        signal_dict = {"symbol": "GOLD#", "fvg_size": 3.0, "volume_spike": 2.0}
        approved = predict_signal_probability(signal_dict, db_client=mock_db)
        self.assertTrue(approved, "Probability 0.75 should be approved (True)")

        # กรณีที่ 2: Probability = 0.45 (< 0.60) -> ควรได้ False
        mock_model.predict_proba.return_value = np.array([[0.55, 0.45]])
        approved_low = predict_signal_probability(signal_dict, db_client=mock_db)
        self.assertFalse(approved_low, "Probability 0.45 should be rejected (False)")

    @patch("bot.ml_filter.SupabaseClient")
    def test_robust_exception_fallback(self, mock_supabase_class):
        """ทดสอบ Supabase หรือ Model Error จะต้อง fallback เป็น True (Approve) อย่างปลอดภัย"""
        mock_db = MagicMock()
        mock_db.enabled = True
        # ทำให้เกิด exception ตอนดึงข้อมูล
        mock_db.get_closed_trades_for_ml.side_effect = Exception("Supabase connection lost")

        signal_dict = {"symbol": "EURUSD", "fvg_size": 1.5}
        approved = predict_signal_probability(signal_dict, db_client=mock_db)
        self.assertTrue(approved, "Exception in DB/Model should fallback to True (Approve)")


if __name__ == "__main__":
    unittest.main()
