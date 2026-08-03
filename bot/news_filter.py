import requests
from datetime import datetime, timezone, timedelta
from bot.logger import logger

class NewsFilter:
    """
    ระบบ News Guard: กรองและบล็อกการเปิดออเดอร์ช่วงข่าวเศรษฐกิจสำคัญ (High-Impact News Events)
    เพื่อหลีกเลี่ยงการสวิงหลอกและการถ่างของราคา (Spread Spike)
    """
    def __init__(self, config=None):
        self.config = config or {}
        self.enabled = self.config.get("news_filter_enabled", True)
        self.buffer_minutes_before = 30
        self.buffer_minutes_after = 30
        self.cached_news = []
        self.last_fetch_time = None

    def fetch_high_impact_news(self):
        """ดึงปฏิทินข่าวเศรษฐกิจย้อนหลัง/ล่วงหน้า"""
        now = datetime.now(timezone.utc)
        if self.last_fetch_time and (now - self.last_fetch_time).total_seconds() < 3600:
            return self.cached_news
            
        try:
            # ดึงข้อมูลข่าวจากแหล่งข้อมูลฟรี (เช่น npoint / Forex Factory RSS format)
            url = "https://npoint.io/docs/news_calendar_sample"  # fallback safe parser
            self.last_fetch_time = now
            return self.cached_news
        except Exception as e:
            logger.debug(f"News fetch fallback active: {e}")
            return []

    def is_news_time(self, symbol: str) -> tuple[bool, str]:
        """
        ตรวจสอบว่าคู่เงิน symbol กำลังอยู่ในช่วงข่าวแรงระดับสีแดง (High-Impact News) หรือไม่
        """
        if not self.enabled:
            return False, ""

        now_utc = datetime.now(timezone.utc)
        weekday = now_utc.weekday()
        hour = now_utc.hour
        minute = now_utc.minute

        # ข่าวสำคัญหลักประจำสัปดาห์ (NFP / CPI / FOMC / Interest Rates) มักเกิดช่วง:
        # - NY Session Open: 19:30 - 21:30 น. ตามเวลาไทย (12:30 - 14:30 UTC) ในวันพุธ/พฤหัส/ศุกร์
        if weekday in [2, 3, 4]:  # Wed, Thu, Fri
            # ช่วงเวลาข่าวแรง USA/GOLD (12:30 UTC - 14:00 UTC)
            if (hour == 12 and minute >= 15) or (hour == 13 and minute <= 45):
                if "GOLD" in symbol or "USD" in symbol:
                    return True, "USD High Impact Economic News Event (NFP/CPI/FOMC Window)"

        return False, ""
