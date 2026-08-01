import os
import requests
from bot.logger import logger

class TelegramNotifier:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.dashboard_url = os.getenv("DASHBOARD_URL", "")
        self.api_url = f"https://api.telegram.org/bot{self.token}/"
        self.enabled = bool(self.token and self.chat_id)

    def send_message(self, text, reply_markup=None):
        if not self.enabled: return
        
        url = self.api_url + "sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML"
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
            
        try:
            requests.post(url, json=payload)
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")

    def notify_order_placed(self, symbol, trade_type, entry, sl, tp, ticket):
        msg = (
            f"🟢 <b>ICT Bot: New Order Executed</b>\n"
            f"<b>Symbol:</b> {symbol}\n"
            f"<b>Type:</b> {trade_type}\n"
            f"<b>Entry:</b> {entry}\n"
            f"<b>SL:</b> {sl}\n"
            f"<b>TP:</b> {tp}\n"
            f"<b>Ticket:</b> #{ticket}"
        )
        
        reply_markup = None
        if self.dashboard_url:
            reply_markup = {
                "inline_keyboard": [
                    [{"text": "📊 เปิดดู Dashboard", "url": self.dashboard_url}]
                ]
            }
            
        self.send_message(msg, reply_markup=reply_markup)

    def send_ai_suggestion(self, suggestion_text):
        """ส่งข้อเสนอแนะจาก AI พร้อมปุ่ม Inline Keyboard แบบจำลอง"""
        # ในระบบใช้งานจริง อาจจะใช้ไลบรารี python-telegram-bot แบบ webhook/polling เพื่อรับ callback
        # แต่ในเวอร์ชันนี้ จะส่งปุ่มไปเพื่อสาธิตให้ผู้ใช้เห็น
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "✅ อัปเดต Config", "callback_data": "update_config_yes"},
                    {"text": "❌ เพิกเฉย", "callback_data": "ignore_ai"}
                ]
            ]
        }
        msg = f"🤖 <b>Gemini AI Insight</b>\n\n{suggestion_text}"
        self.send_message(msg, reply_markup=keyboard)
