import pandas as pd
from smartmoneyconcepts import smc
from bot.logger import logger
from datetime import datetime
import pytz

class ICTStrategy:
    def __init__(self, mt5_client, config):
        self.mt5 = mt5_client
        self.config = config
        
    def analyze_4h_trend(self, symbol):
        """
        วิเคราะห์ HTF (4H) เพื่อหาทิศทางหลัก (Market Structure)
        คืนค่า 'BULLISH', 'BEARISH' หรือ 'NEUTRAL'
        """
        df = self.mt5.get_rates(symbol, "H4", 100)
        if df is None or df.empty:
            return "NEUTRAL"
            
        # ใช้ smartmoneyconcepts หา BOS/CHOCH
        # smc คาดหวัง DataFrame ที่มีคอลัมน์ [open, high, low, close, volume]
        df.rename(columns={'tick_volume': 'volume'}, inplace=True)
        
        try:
            mss_df = smc.bos_choch(df)
            
            # เช็คสัญญาณล่าสุดที่เกิดขึ้น (BOS หรือ CHOCH)
            last_signal = mss_df[mss_df['BOS'] != 0].tail(1)
            last_choch = mss_df[mss_df['CHOCH'] != 0].tail(1)
            
            # ตรรกะแบบง่าย: ถ้า BOS ล่าสุดเป็นบวก (Break Up) ถือว่าเป็น Bullish
            # อาจต้องผสมผสานกับ CHOCH และเวลาที่เกิด
            is_bullish = False
            is_bearish = False
            
            if not last_signal.empty:
                val = last_signal['BOS'].iloc[0]
                if val == 1: is_bullish = True
                elif val == -1: is_bearish = True
                
            if not last_choch.empty:
                val = last_choch['CHOCH'].iloc[0]
                # CHOCH อาจจะหักล้าง BOS ก่อนหน้าได้ (ถ้าเกิดทีหลัง)
                if last_signal.empty or last_choch.index[0] > last_signal.index[0]:
                    is_bullish = (val == 1)
                    is_bearish = (val == -1)
                    
            if is_bullish: return "BULLISH"
            if is_bearish: return "BEARISH"
            
        except Exception as e:
            logger.error(f"Error in SMC 4H analysis for {symbol}: {e}")
            
        return "NEUTRAL"

    def find_15m_entry(self, symbol, trend):
        """
        หาจุดเข้า (Entry Model) บน 15M ด้วย FVG หรือ OB
        คืนค่า dict ของ setup (entry, sl, tp, type) หรือ None
        """
        if trend == "NEUTRAL":
            return None
            
        df = self.mt5.get_rates(symbol, "M15", 100)
        if df is None or df.empty:
            return None
            
        df.rename(columns={'tick_volume': 'volume'}, inplace=True)
        
        try:
            fvg_df = smc.fvg(df)
            ob_df = smc.ob(df)
            
            # ดึงราคาปัจจุบัน
            tick = self.mt5.get_tick(symbol)
            if not tick: return None
            current_price = tick.bid
            
            # ลอจิก: ถ้า Trend เป็น BULLISH ให้หา Bullish FVG หรือ OB ที่ราคาปัจจุบันกำลังลงมาแตะ (Mitigation)
            setup = None
            if trend == "BULLISH":
                # กรองหา Bullish FVG ที่ยังไม่ถูกเติมเต็ม (Unmitigated) และอยู่ต่ำกว่าราคาปัจจุบันเล็กน้อย
                # (เพื่อความเรียบง่าย สมมติว่าคืนค่า Bullish Orderblock ล่าสุดมาเป็นจุดเข้า)
                bullish_obs = ob_df[ob_df['OB'] == 1]
                if not bullish_obs.empty:
                    last_ob = bullish_obs.tail(1)
                    entry_price = last_ob['high'].iloc[0]  # ขอบบนของ OB
                    sl_price = last_ob['low'].iloc[0]      # ขอบล่างของ OB (SL)
                    
                    # ตั้ง TP โดยอิงจาก High ล่าสุดที่เห็นชัด
                    tp_price = df['high'].rolling(20).max().iloc[-1]
                    
                    # ถ้า current_price อยู่ใกล้ entry_price (ในระยะ 0.1%)
                    if abs(current_price - entry_price) / entry_price < 0.001:
                        setup = {
                            "type": "BUY",
                            "entry": entry_price,
                            "sl": sl_price,
                            "tp": tp_price,
                            "fvg_size": abs(entry_price - sl_price) # อนุโลมให้บันทึกเป็นขนาดโซน
                        }
                        
            elif trend == "BEARISH":
                bearish_obs = ob_df[ob_df['OB'] == -1]
                if not bearish_obs.empty:
                    last_ob = bearish_obs.tail(1)
                    entry_price = last_ob['low'].iloc[0]   # ขอบล่างของ OB
                    sl_price = last_ob['high'].iloc[0]     # ขอบบนของ OB (SL)
                    
                    tp_price = df['low'].rolling(20).min().iloc[-1]
                    
                    if abs(current_price - entry_price) / entry_price < 0.001:
                        setup = {
                            "type": "SELL",
                            "entry": entry_price,
                            "sl": sl_price,
                            "tp": tp_price,
                            "fvg_size": abs(sl_price - entry_price)
                        }
                        
            return setup
            
        except Exception as e:
            logger.error(f"Error in SMC 15M entry for {symbol}: {e}")
            return None

    def is_in_killzone(self):
        """
        ตรวจสอบว่าเวลาปัจจุบัน (เทียบกับ NY Time) อยู่ใน Killzones หรือไม่
        """
        ny_tz = pytz.timezone("America/New_York")
        now_ny = datetime.now(ny_tz)
        current_time = now_ny.time()
        
        kz_config = self.config.get("killzones_ny_time", {})
        
        for kz_name, kz_data in kz_config.items():
            if not kz_data.get("enabled", True):
                continue
                
            start = datetime.strptime(kz_data["start"], "%H:%M").time()
            end = datetime.strptime(kz_data["end"], "%H:%M").time()
            
            if start <= current_time <= end:
                logger.info(f"Currently in {kz_name} Killzone")
                return True, kz_name
                
        return False, None
