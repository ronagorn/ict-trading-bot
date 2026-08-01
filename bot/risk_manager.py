import math
from bot.logger import logger

class RiskManager:
    def __init__(self, config):
        self.config = config

    def calculate_lot_size(self, account_equity, symbol_info, entry_price, stop_loss_price):
        """
        คำนวณ Lot size เพื่อจำกัดความเสี่ยงไม่เกิน X% ของพอร์ต
        สูตร (สำหรับ Forex/Gold ทั่วไป แต่อาจต้องปรับตาม Contract Size):
        Risk Amount = Equity * (Risk % / 100)
        Pip Value = (Contract Size * Pip Size)
        Lot Size = Risk Amount / (Stop Loss in Pips * Pip Value)
        
        การคำนวณเบื้องต้นแบบง่าย (ใช้กับ XM XAUUSD, BTCUSD):
        """
        risk_percent = self.config.get("risk_per_trade_percent", 1.0)
        risk_amount = account_equity * (risk_percent / 100.0)
        
        # ระยะ SL
        sl_distance = abs(entry_price - stop_loss_price)
        if sl_distance <= 0:
            return 0
            
        # มูลค่าต่อการขยับ 1 point สำหรับ 1 Lot
        # = contract_size * point
        tick_value = symbol_info.trade_contract_size * symbol_info.point
        if tick_value == 0:
            # Fallback หากดึง contract size ไม่ได้
            logger.warning("Tick value is 0, using fallback calculation.")
            return 0.01

        # ขาดทุนต่อ 1 Lot = (SL Distance / Point) * tick_value
        loss_per_lot = (sl_distance / symbol_info.point) * tick_value
        
        if loss_per_lot <= 0:
            return 0
            
        raw_lot = risk_amount / loss_per_lot
        
        # ปัดเศษลงตาม Volume Step
        volume_step = symbol_info.volume_step
        min_vol = symbol_info.volume_min
        max_vol = symbol_info.volume_max
        
        lot_size = math.floor(raw_lot / volume_step) * volume_step
        
        # จำกัดให้อยู่ในขอบเขต
        lot_size = max(min_vol, min(lot_size, max_vol))
        
        return round(lot_size, 2)

    def validate_setup(self, entry, sl, tp, symbol):
        """
        ตรวจสอบ Risk/Reward Ratio และอื่นๆ ตามกฎที่ตั้งไว้
        """
        min_rr = self.config.get("min_rr_ratio", 3.0)
        
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        
        if risk == 0:
            logger.warning(f"Invalid setup for {symbol}: Risk is 0")
            return False
            
        rr_ratio = reward / risk
        if rr_ratio < min_rr:
            logger.info(f"Setup rejected for {symbol}: R:R ratio {rr_ratio:.2f} is less than minimum {min_rr}")
            return False
            
        logger.info(f"Setup validated for {symbol}: R:R ratio is {rr_ratio:.2f}")
        return True

    def check_daily_drawdown(self, initial_balance, current_equity):
        """
        เช็คว่า Equity ปัจจุบันลดลงเกิน Daily Drawdown Limit หรือไม่
        (เพื่อเรียกใช้ฟังก์ชันหยุดเทรดประจำวัน)
        """
        limit_percent = self.config.get("daily_drawdown_limit_percent", 2.0)
        
        # ถ้ากำไรอยู่แล้วไม่ต้องทำอะไร
        if current_equity >= initial_balance:
            return True
            
        drawdown_percent = ((initial_balance - current_equity) / initial_balance) * 100
        
        if drawdown_percent >= limit_percent:
            logger.warning(f"Daily drawdown limit reached: {drawdown_percent:.2f}% >= {limit_percent}%")
            return False
            
        return True
