import os
import google.generativeai as genai
from bot.logger import logger

class AIAnalyzer:
    def __init__(self, db_client, telegram_bot):
        self.db = db_client
        self.tg = telegram_bot
        
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel('gemini-1.5-flash')
            self.enabled = True
        else:
            logger.warning("Gemini API key not found. AI Analyzer disabled.")
            self.enabled = False

    def analyze_daily_performance(self):
        """ดึงข้อมูลไม้ที่เสียมาวิเคราะห์ตอนจบวัน"""
        if not self.enabled: return
        
        logger.info("Starting AI Analysis on recent losing trades...")
        losing_trades = self.db.get_recent_losing_trades(limit=20)
        
        if not losing_trades or len(losing_trades) < 5:
            logger.info("Not enough losing trades to perform AI analysis.")
            return
            
        # สร้าง Prompt ให้ Gemini
        prompt = (
            "You are an expert ICT (Inner Circle Trader) algorithmic trading analyst. "
            "Here is the data of recent losing trades from our automated system. "
            "Identify any patterns regarding which session (London or NY) or which pairs are failing most often. "
            "Give a concise insight and a recommendation on whether we should pause trading during a specific killzone. "
            "Respond in Thai language.\n\n"
            "Data:\n"
        )
        for t in losing_trades:
            prompt += f"- Symbol: {t.get('symbol')}, Session: {t.get('session')}, FVG Size: {t.get('fvg_size')}, P/L: {t.get('profit_loss')}\n"
            
        try:
            response = self.model.generate_content(prompt)
            insight = response.text
            logger.info(f"AI Insight Generated: {insight}")
            
            # ส่งแจ้งเตือนผ่าน Telegram
            self.tg.send_ai_suggestion(insight)
        except Exception as e:
            logger.error(f"Error during AI analysis: {e}")
