import os
import sys
import unittest

# เพิ่ม root dir ใน sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.telegram_bot import TelegramNotifier

class TestTelegramInteractiveCommands(unittest.TestCase):

    def setUp(self):
        self.tg = TelegramNotifier()
        # Mock chat_id สำหรับทดสอบ
        self.tg.chat_id = "12345678"
        self.sent_messages = []
        
        # Override send_message เพื่อเก็บประวัติข้อความแทนการส่งจริงไปยัง Telegram API
        def mock_send_message(text, reply_markup=None, chat_id=None):
            self.sent_messages.append({
                "text": text,
                "reply_markup": reply_markup,
                "chat_id": chat_id
            })
        
        self.tg.send_message = mock_send_message

    def test_status_intent_matching(self):
        """ทดสอบข้อความถามสถานะภาษาไทย เช่น 'ยังรันอยู่ไหม', 'สถานะ'"""
        self.tg._handle_message({"text": "ยังรันอยู่ไหม"}, "12345678")
        self.assertTrue(len(self.sent_messages) > 0)
        self.assertIn("AURA Super Trader System Status", self.sent_messages[-1]["text"])

    def test_balance_intent_matching(self):
        """ทดสอบข้อความถามยอดเงิน เช่น 'เงินเหลือเท่าไหร่'"""
        self.tg.set_callback("balance", lambda: "Balance: $10,000.00")
        self.tg._handle_message({"text": "เงินเหลือเท่าไหร่"}, "12345678")
        self.assertTrue(len(self.sent_messages) > 0)
        self.assertIn("Balance: $10,000.00", self.sent_messages[-1]["text"])

    def test_positions_intent_matching(self):
        """ทดสอบข้อความถามออเดอร์ เช่น 'มีออเดอร์อะไรบ้าง'"""
        self.tg.set_callback("positions", lambda: "GOLD# BUY Lot 0.1")
        self.tg._handle_message({"text": "มีออเดอร์อะไรบ้าง"}, "12345678")
        self.assertTrue(len(self.sent_messages) > 0)
        self.assertIn("GOLD# BUY Lot 0.1", self.sent_messages[-1]["text"])

    def test_pause_and_resume_commands(self):
        """ทดสอบคำสั่ง 'หยุดเทรด' และ 'เริ่มเทรดต่อ'"""
        self.assertFalse(self.tg.is_paused())

        # สั่งหยุดเทรด
        self.tg._handle_message({"text": "หยุดเทรด"}, "12345678")
        self.assertTrue(self.tg.is_paused())
        self.assertIn("สั่งหยุดเทรดชั่วคราวเรียบร้อยแล้ว", self.sent_messages[-1]["text"])

        # สั่งเริ่มเทรดต่อ
        self.tg._handle_message({"text": "เริ่มเทรดต่อ"}, "12345678")
        self.assertFalse(self.tg.is_paused())
        self.assertIn("เปิดระบบการเทรดต่อเรียบร้อยแล้ว", self.sent_messages[-1]["text"])

    def test_security_chat_id_check(self):
        """ทดสอบกรณีคนอื่นแอบทักทายสั่งการเข้ามา (Chat ID ไม่ตรง)"""
        self.sent_messages.clear()
        
        # ปรับปรุง update เป็น chat_id แปลกปลอม
        unauthorized_update = {
            "message": {
                "chat": {"id": 999999999},
                "text": "หยุดเทรด"
            }
        }
        self.tg._process_update(unauthorized_update)
        
        # ต้องปฏิเสธสิทธิ์ และต้องไม่สั่ง pause บอท
        self.assertFalse(self.tg.is_paused())
        self.assertTrue(len(self.sent_messages) > 0)
        self.assertIn("Access Denied", self.sent_messages[-1]["text"])

if __name__ == "__main__":
    unittest.main()
