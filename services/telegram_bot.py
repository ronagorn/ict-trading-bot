import os
import time
import threading
import requests
from bot.logger import logger

class TelegramNotifier:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = str(os.getenv("TELEGRAM_CHAT_ID", "")).strip()
        self.dashboard_url = os.getenv("DASHBOARD_URL", "")
        self.api_url = f"https://api.telegram.org/bot{self.token}/"
        self.enabled = bool(self.token and self.chat_id)

        self._is_paused = False
        self._running = False
        self._polling_thread = None
        self._callbacks = {
            'status': None,
            'balance': None,
            'positions': None,
            'ai_summary': None
        }

    def is_paused(self) -> bool:
        return self._is_paused

    def pause_trading(self):
        self._is_paused = True
        logger.info("Trading paused via Telegram command.")

    def resume_trading(self):
        self._is_paused = False
        logger.info("Trading resumed via Telegram command.")

    def set_callback(self, event_name: str, func):
        """ตั้งค่า Callback functions จาก main.py (เช่น status, balance, positions, ai_summary)"""
        self._callbacks[event_name] = func

    def send_message(self, text, reply_markup=None, chat_id=None):
        if not self.token:
            return
        
        target_chat = chat_id or self.chat_id
        if not target_chat:
            return
        
        url = self.api_url + "sendMessage"
        payload = {
            "chat_id": target_chat,
            "text": text,
            "parse_mode": "HTML"
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
            
        try:
            requests.post(url, json=payload, timeout=10)
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
        """ส่งข้อเสนอแนะจาก AI พร้อมปุ่ม Inline Keyboard"""
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

    def send_ml_config_suggestion(self, suggestion_text):
        """ส่งคำแนะนำจาก ML Optimizer พร้อมปุ่มอนุมัติ/ปฏิเสธ"""
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "✅ อนุมัติ ML Config", "callback_data": "ml_config_approve"},
                    {"text": "❌ ปฏิเสธ", "callback_data": "ml_config_reject"},
                ]
            ]
        }
        self.send_message(suggestion_text, reply_markup=keyboard)

    def set_ml_approval_callback(self, on_approve, on_reject):
        """ตั้ง callback สำหรับ ML config approval"""
        self._callbacks["ml_approve"] = on_approve
        self._callbacks["ml_reject"] = on_reject

    # ----------------------------------------------------
    # TELEGRAM COMMAND LISTENER & INTENT HANDLER ENGINE
    # ----------------------------------------------------

    def start_polling(self):
        """เริ่มทำงาน Background Thread ในการรับคำสั่งจาก Telegram"""
        if not self.enabled:
            logger.warning("Telegram Bot is disabled (missing token or chat_id). Polling not started.")
            return

        if self._running:
            return

        self._running = True
        self._polling_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._polling_thread.start()
        logger.info("Telegram Command Listener started (Long Polling active).")

    def stop_polling(self):
        """หยุดงาน Background Thread"""
        self._running = False

    def _poll_loop(self):
        offset = 0
        while self._running:
            try:
                url = f"{self.api_url}getUpdates"
                params = {"offset": offset, "timeout": 15}
                response = requests.get(url, params=params, timeout=20)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("ok"):
                        for update in data.get("result", []):
                            offset = update["update_id"] + 1
                            self._process_update(update)
                time.sleep(1)
            except Exception as e:
                logger.debug(f"Telegram polling exception: {e}")
                time.sleep(5)

    def _process_update(self, update: dict):
        """ตรวจสอบ Security และแยกแยะประเภทข้อความ/Callback"""
        # 1. จัดการข้อความพิมพ์เข้ามา (Messages)
        if "message" in update:
            message = update["message"]
            chat_id = str(message.get("chat", {}).get("id", ""))
            
            # Security Check: ตรวจสอบ Chat ID (หากตั้งค่าไว้)
            if self.chat_id and chat_id != self.chat_id:
                self.send_message(
                    "⚠️ <b>Access Denied</b>\nคุณไม่มีสิทธิ์ควบคุมสั่งงานระบบนี้",
                    chat_id=chat_id
                )
                return

            self._handle_message(message, chat_id)

        # 2. จัดการการกดปุ่ม Inline Keyboard (Callback Queries)
        elif "callback_query" in update:
            cb = update["callback_query"]
            chat_id = str(cb.get("message", {}).get("chat", {}).get("id", ""))
            
            if self.chat_id and chat_id != self.chat_id:
                return

            cb_id = cb.get("id")
            data = cb.get("data", "")
            
            # ส่ง answerCallbackQuery เพื่อให้ Telegram ปิดสถานะ Loading ของปุ่ม
            try:
                requests.post(f"{self.api_url}answerCallbackQuery", json={"callback_query_id": cb_id})
            except Exception:
                pass

            self._handle_callback_data(data, chat_id)

    def _get_main_keyboard(self):
        """สร้างปุ่ม เมนูคำสั่งด่วน (Inline Keyboard)"""
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "🟢 สถานะบอท", "callback_data": "cmd_status"},
                    {"text": "💰 ยอดเงิน/พอร์ต", "callback_data": "cmd_balance"}
                ],
                [
                    {"text": "📊 ออเดอร์ปัจจุบัน", "callback_data": "cmd_positions"},
                    {"text": "🤖 AI สรุปผล", "callback_data": "cmd_ai"}
                ],
                [
                    {"text": "⏸️ หยุดเทรด", "callback_data": "cmd_pause"},
                    {"text": "▶️ เริ่มเทรดต่อ", "callback_data": "cmd_resume"}
                ],
                [
                    {"text": "❓ เมนูคำสั่งทั้งหมด", "callback_data": "cmd_help"}
                ]
            ]
        }
        if self.dashboard_url:
            keyboard["inline_keyboard"].append([{"text": "🌐 เปิดดู Dashboard", "url": self.dashboard_url}])
        return keyboard

    def _handle_message(self, message: dict, chat_id: str):
        raw_text = message.get("text", "").strip()
        if not raw_text:
            return

        text = raw_text.lower()

        # 1. คำสั่งช่วยเหลือ / เริ่มต้น
        if any(k == text or k in text for k in ["/start", "/help", "คำสั่ง", "สั่งอะไรได้บ้าง", "ทำอะไรได้บ้าง", "เมนู", "help", "start"]):
            self._send_help_menu(chat_id)

        # 2. ถามสถานะการทำงาน
        elif any(k in text for k in ["/status", "ยังรันอยู่ไหม", "รันอยู่ไหม", "รันอยู่เปล่า", "เปิดอยู่ไหม", "ทำงานไหม", "ทำงานอยู่", "ทำงาน", "สถานะ"]):
            self._execute_status_cmd(chat_id)

        # 3. ถามยอดเงิน / พอร์ต
        elif any(k in text for k in ["/balance", "/equity", "เงินเหลือเท่าไหร่", "พอร์ต", "ยอดเงิน", "ยอดเงินเหลือ", "balance", "equity"]):
            self._execute_balance_cmd(chat_id)

        # 4. ถามออเดอร์ active
        elif any(k in text for k in ["/positions", "/orders", "มีออเดอร์อะไรบ้าง", "มีออเดอร์ไหม", "เปิดกี่ไม้", "ออเดอร์", "position"]):
            self._execute_positions_cmd(chat_id)

        # 5. สั่งหยุดเทรดชั่วคราว
        elif any(k in text for k in ["/pause", "หยุดเทรด", "พักก่อน", "หยุดระบบ", "pause"]):
            self.pause_trading()
            msg = (
                "⏸️ <b>สั่งหยุดเทรดชั่วคราวเรียบร้อยแล้ว</b>\n\n"
                "บอทจะไม่เปิดออเดอร์ใหม่จนกว่าจะสั่ง /resume หรือกดปุ่มเริ่มเทรดต่อครับ"
            )
            self.send_message(msg, reply_markup=self._get_main_keyboard(), chat_id=chat_id)

        # 6. สั่งเริ่มเทรดต่อ
        elif any(k in text for k in ["/resume", "เริ่มเทรดต่อ", "เปิดระบบ", "ทำงานต่อ", "resume"]):
            self.resume_trading()
            msg = (
                "▶️ <b>เปิดระบบการเทรดต่อเรียบร้อยแล้ว</b>\n\n"
                "บอทพร้อมสแกนกราฟและเปิดออเดอร์ตามสัญญาณปกติครับ"
            )
            self.send_message(msg, reply_markup=self._get_main_keyboard(), chat_id=chat_id)

        # 7. สั่งดึง AI สรุปผล
        elif any(k in text for k in ["/ai", "/summary", "สรุปภาพรวม", "วิเคราะห์", "ai"]):
            self._execute_ai_summary_cmd(chat_id)

        # 8. คำทักทาย
        elif any(k in text for k in ["สวัสดี", "หวัดดี", "ดีครับ", "ดีค่ะ", "hi", "hello", "hey", "ทักทาย"]):
            msg = (
                "👋 <b>สวัสดีครับ! ยินดีต้อนรับสู่ AURA Super Trader Bot</b>\n\n"
                "สอบถามสถานะบอทภาษาไทยได้เลยครับ เช่น:\n"
                "• <i>'ยังรันอยู่ไหม'</i>\n"
                "• <i>'เงินเหลือเท่าไหร่'</i>\n"
                "• <i>'มีออเดอร์อะไรบ้าง'</i>\n\n"
                "หรือเลือกกดปุ่มคำสั่งด่วนด้านล่างนี้ได้ทันทีครับ 👇"
            )
            self.send_message(msg, reply_markup=self._get_main_keyboard(), chat_id=chat_id)

        # 9. ข้อความอื่นๆ ที่ไม่ตรงกับคีย์เวิร์ด
        else:
            msg = (
                f"🤖 <b>ได้รับข้อความ:</b> '{raw_text}'\n\n"
                "💡 <i>พิมพ์ถามคำถามทั่วไปได้ เช่น:</i>\n"
                "• <b>'ยังรันอยู่ไหม'</b> (เช็คสถานะการทำงาน)\n"
                "• <b>'เงินเหลือเท่าไหร่'</b> (เช็คยอดเงินและพอร์ต)\n"
                "• <b>'มีออเดอร์อะไรบ้าง'</b> (เช็คออเดอร์ที่เปิดอยู่)\n"
                "• <b>'หยุดเทรด'</b> / <b>'เริ่มเทรดต่อ'</b>\n\n"
                "หรือใช้ Slash Commands:\n"
                "/status | /balance | /positions | /pause | /resume | /ai | /help"
            )
            self.send_message(msg, reply_markup=self._get_main_keyboard(), chat_id=chat_id)

    def _handle_callback_data(self, data: str, chat_id: str):
        """ประมวลผลเมื่อผู้ใช้กดปุ่ม Inline Keyboard"""
        if data == "cmd_status":
            self._execute_status_cmd(chat_id)
        elif data == "cmd_balance":
            self._execute_balance_cmd(chat_id)
        elif data == "cmd_positions":
            self._execute_positions_cmd(chat_id)
        elif data == "cmd_pause":
            self.pause_trading()
            self.send_message("⏸️ <b>สั่งหยุดเทรดชั่วคราวเรียบร้อยแล้ว</b>", reply_markup=self._get_main_keyboard(), chat_id=chat_id)
        elif data == "cmd_resume":
            self.resume_trading()
            self.send_message("▶️ <b>เปิดระบบการเทรดต่อเรียบร้อยแล้ว</b>", reply_markup=self._get_main_keyboard(), chat_id=chat_id)
        elif data == "cmd_ai":
            self._execute_ai_summary_cmd(chat_id)
        elif data == "cmd_help":
            self._send_help_menu(chat_id)
        elif data == "ml_config_approve":
            if self._callbacks.get("ml_approve"):
                try:
                    self._callbacks["ml_approve"]()
                    self.send_message(
                        "✅ <b>อนุมัติ ML Config แล้ว</b>\nกำลังอัปเดต config.json...",
                        chat_id=chat_id,
                    )
                except Exception as e:
                    self.send_message(f"⚠️ ML apply error: {e}", chat_id=chat_id)
            else:
                self.send_message(
                    "⚠️ ML approval handler ยังไม่ได้เชื่อมต่อ — รัน: python -m services.ml_optimizer --apply",
                    chat_id=chat_id,
                )
        elif data == "ml_config_reject":
            if self._callbacks.get("ml_reject"):
                try:
                    self._callbacks["ml_reject"]()
                except Exception:
                    pass
            self.send_message("❌ <b>ปฏิเสธคำแนะนำ ML</b> — config ไม่มีการเปลี่ยนแปลง", chat_id=chat_id)
        elif data == "update_config_yes":
            self.send_message("ℹ️ ใช้ ML Optimizer สำหรับการอัปเดต config อัตโนมัติ", chat_id=chat_id)
        elif data == "ignore_ai":
            self.send_message("👌 เพิกเฉยคำแนะนำแล้ว", chat_id=chat_id)

    def _send_help_menu(self, chat_id: str):
        msg = (
            "📋 <b>คำสั่งสั่งการผ่าน Telegram (AURA Control Panel)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "💬 <b>พิมพ์ถามภาษาไทยธรรมชาติ:</b>\n"
            "• <i>'ยังรันอยู่ไหม'</i> — เช็คสถานะการรันของบอท\n"
            "• <i>'เงินเหลือเท่าไหร่'</i> — เช็ค Balance / Equity ใน MT5\n"
            "• <i>'มีออเดอร์อะไรบ้าง'</i> — เช็คไม้ที่เปิดอยู่ขณะนี้\n"
            "• <i>'หยุดเทรด'</i> — สั่งหยุดเปิดออเดอร์ชั่วคราว\n"
            "• <i>'เริ่มเทรดต่อ'</i> — สั่งเปิดระบบสแกนเทรดต่อ\n"
            "• <i>'สรุปภาพรวม'</i> — ดึงรายงานจาก Gemini AI\n\n"
            "⌨️ <b>Slash Commands:</b>\n"
            "/status — ดูสถานะการทำงานบอท\n"
            "/balance — เช็คยอดเงินพอร์ต MT5\n"
            "/positions — รายการออเดอร์ Active\n"
            "/pause — หยุดเทรดชั่วคราว (Pause)\n"
            "/resume — เริ่มเทรดต่อ (Resume)\n"
            "/ai — สรุปรายงาน Gemini AI\n"
            "/help — ดูรายการคำสั่งนี้\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "กดปุ่มลัดด้านล่างเพื่อสั่งงานได้ทันที:"
        )
        self.send_message(msg, reply_markup=self._get_main_keyboard(), chat_id=chat_id)

    def _execute_status_cmd(self, chat_id: str):
        status_mode = "⏸️ <b>PAUSED (หยุดเทรดชั่วคราว)</b>" if self._is_paused else "🟢 <b>ACTIVE (กำลังสแกนตลาด)</b>"
        
        extra_info = ""
        if self._callbacks['status']:
            try:
                extra_info = self._callbacks['status']()
            except Exception as e:
                extra_info = f"\n⚠️ Error fetching status details: {e}"

        msg = (
            "🚀 <b>AURA Super Trader System Status</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>สถานะระบบ:</b> {status_mode}\n"
            f"{extra_info}\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.send_message(msg, reply_markup=self._get_main_keyboard(), chat_id=chat_id)

    def _execute_balance_cmd(self, chat_id: str):
        balance_info = "ไม่มีข้อมูลการเชื่อมต่อ MT5"
        if self._callbacks['balance']:
            try:
                balance_info = self._callbacks['balance']()
            except Exception as e:
                balance_info = f"⚠️ Error reading balance: {e}"

        msg = (
            "💰 <b>MT5 Account Balance & Portfolio</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{balance_info}\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.send_message(msg, reply_markup=self._get_main_keyboard(), chat_id=chat_id)

    def _execute_positions_cmd(self, chat_id: str):
        pos_info = "ไม่มีข้อมูลออเดอร์"
        if self._callbacks['positions']:
            try:
                pos_info = self._callbacks['positions']()
            except Exception as e:
                pos_info = f"⚠️ Error reading positions: {e}"

        msg = (
            "📊 <b>Active Open Orders</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{pos_info}\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.send_message(msg, reply_markup=self._get_main_keyboard(), chat_id=chat_id)

    def _execute_ai_summary_cmd(self, chat_id: str):
        self.send_message("⏳ <i>กำลังวิเคราะห์ข้อมูลประวัติการเทรดด้วย Gemini AI...</i>", chat_id=chat_id)
        
        summary = "ยังไม่ได้เปิดใช้งาน AI หรือไม่มีข้อมูลบันทึก"
        if self._callbacks['ai_summary']:
            try:
                summary = self._callbacks['ai_summary']()
            except Exception as e:
                summary = f"⚠️ Error generating AI summary: {e}"

        msg = (
            "🤖 <b>Gemini AI Performance Insight</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{summary}\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.send_message(msg, reply_markup=self._get_main_keyboard(), chat_id=chat_id)

