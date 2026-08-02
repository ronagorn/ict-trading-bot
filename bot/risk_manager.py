import math
from bot.logger import logger

class RiskManager:
    def __init__(self, config):
        self.config = config

    def calculate_lot_size(self, account_equity, symbol_info, entry_price, stop_loss_price):
        """
        คำนวณ Lot size เพื่อจำกัดความเสี่ยงไม่เกิน X% ของพอร์ต
        """
        risk_percent = self.config.get("risk_per_trade_percent", 1.0)
        risk_amount = account_equity * (risk_percent / 100.0)
        
        sl_distance = abs(entry_price - stop_loss_price)
        if sl_distance <= 0:
            return 0
            
        tick_value = symbol_info.trade_contract_size * symbol_info.point
        if tick_value == 0:
            logger.warning("Tick value is 0, using fallback calculation.")
            return 0.01

        loss_per_lot = (sl_distance / symbol_info.point) * tick_value
        
        if loss_per_lot <= 0:
            return 0
            
        raw_lot = risk_amount / loss_per_lot
        
        volume_step = symbol_info.volume_step
        min_vol = symbol_info.volume_min
        max_vol = symbol_info.volume_max
        
        lot_size = math.floor(raw_lot / volume_step) * volume_step
        lot_size = max(min_vol, min(lot_size, max_vol))
        
        return round(lot_size, 2)

    def validate_setup(self, entry, sl, tp, symbol):
        """
        ตรวจสอบ Risk/Reward Ratio ตามกฎที่ตั้งไว้
        """
        min_rr = self.config.get("min_rr_ratio", 1.5)
        
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        
        if risk == 0:
            logger.warning(f"Invalid setup for {symbol}: Risk is 0")
            return False
            
        rr_ratio = reward / risk
        if rr_ratio < (min_rr - 0.05):
            logger.info(f"Setup rejected for {symbol}: R:R ratio {rr_ratio:.2f} is less than minimum {min_rr}")
            return False
            
        logger.info(f"Setup validated for {symbol}: R:R ratio is {rr_ratio:.2f}")
        return True

    def check_correlation_exposure(self, open_positions, new_symbol, max_same_currency=2):
        """
        ตัวกรองความสัมพันธ์ของสกุลเงิน (Currency Correlation Filter):
        ป้องกันการเปิดออเดอร์ในสกุลเงินเดียวกันซ้อนกันเกิน N ออเดอร์เมื่อมีข่าวแรง
        """
        if not open_positions:
            return True
            
        # สกัดสกุลเงินหลัก
        def get_currencies(sym):
            s = sym.replace("#", "")
            if "GOLD" in s or "XAU" in s: return ["USD"]
            if "BTC" in s: return ["BTC"]
            if len(s) == 6: return [s[:3], s[3:]]
            return [s]

        new_curs = get_currencies(new_symbol)
        
        for cur in new_curs:
            same_count = 0
            for pos in open_positions:
                pos_curs = get_currencies(pos.symbol)
                if cur in pos_curs:
                    same_count += 1
            if same_count >= max_same_currency:
                logger.warning(f"Correlation limit reached for currency {cur}: {same_count} active orders on {cur}")
                return False
                
        return True

    def can_open_new_position(self, open_positions, target_symbol):
        """
        ตรวจสอบว่าสามารถเปิดออเดอร์ใหม่สำหรับคู่เงิน target_symbol ได้หรือไม่:
        1. จำนวนออเดอร์รวมทั้งพอร์ต ไม่เกิน max_total_open_orders (default: 4)
        2. จำนวนออเดอร์เฉพาะคู่เงิน target_symbol ไม่เกิน max_orders_per_symbol (default: 2)
        3. Currency Correlation Filter (ไม่เกิน N ออเดอร์ในกลุ่มสกุลเงินเดียวกัน)
        """
        if not open_positions:
            return True
            
        max_total = self.config.get("max_total_open_orders", 4)
        if len(open_positions) >= max_total:
            logger.debug(f"Total portfolio open orders limit reached: {len(open_positions)}/{max_total}")
            return False
            
        max_per_symbol = self.config.get("max_orders_per_symbol", 2)
        symbol_count = sum(1 for pos in open_positions if pos.symbol == target_symbol)
        if symbol_count >= max_per_symbol:
            logger.debug(f"Max open orders limit reached for {target_symbol}: {symbol_count}/{max_per_symbol}")
            return False
            
        max_same_curr = self.config.get("max_same_currency_exposure", 2)
        if not self.check_correlation_exposure(open_positions, target_symbol, max_same_curr):
            return False
            
        return True

    def check_daily_drawdown(self, initial_balance, current_equity):
        """
        เช็คว่า Equity ปัจจุบันลดลงเกิน Daily Drawdown Limit หรือไม่
        """
        limit_percent = self.config.get("daily_drawdown_limit_percent", 8.0)
        
        if current_equity >= initial_balance:
            return True
            
        drawdown_percent = ((initial_balance - current_equity) / initial_balance) * 100
        
        if drawdown_percent >= limit_percent:
            logger.warning(f"Daily drawdown limit reached: {drawdown_percent:.2f}% >= {limit_percent}%")
            return False
            
        return True
