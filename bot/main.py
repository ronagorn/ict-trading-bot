import json
import time
import os
from datetime import datetime, timezone
import pytz

from bot.mt5_client import MT5Client
from bot.strategy import ICTStrategy
from bot.risk_manager import RiskManager
from bot.logger import logger
from services.db_client import SupabaseClient
from services.telegram_bot import TelegramNotifier
from services.ai_analyzer import AIAnalyzer

def load_config():
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load config.json: {e}")
        return {}

def main():
    logger.info("Initializing ICT Trading Bot...")
    config = load_config()
    
    mt5_client = MT5Client()
    if not mt5_client.connect():
        logger.error("Failed to connect to MT5. Exiting.")
        return

    db = SupabaseClient()
    tg = TelegramNotifier()
    ai = AIAnalyzer(db, tg)
    
    strategy = ICTStrategy(mt5_client, config)
    risk_manager = RiskManager(config)
    
    symbols = config.get("symbols", ["XAUUSD"])
    max_trades = config.get("max_trades_per_day", 2)
    daily_trades_count = 0
    current_date = datetime.now().date()
    
    # แจ้งเตือนเมื่อบอทเริ่มทำงาน
    tg.send_message("🚀 <b>ICT Bot Started Successfully</b>\nReady to scan for setups.")

    try:
        while True:
            now_date = datetime.now().date()
            
            # Reset daily counters
            if now_date != current_date:
                current_date = now_date
                daily_trades_count = 0
                logger.info("New day started, resetting trade counters.")
                # รัน AI Analyzer ตอนจบวัน (หรือเมื่อขึ้นวันใหม่)
                ai.analyze_daily_performance()
                
            # ตรวจสอบ Drawdown limit
            acc_info = mt5_client.get_account_info()
            if not acc_info:
                time.sleep(10)
                continue
                
            # สมมติฐาน: initial_balance ของวันใช้ balance ปัจจุบัน + profit/loss ถ้าอยากให้แม่นต้องเก็บลง DB ทุกเริ่มวัน
            # ในที่นี้เพื่อความเรียบง่าย จะเช็ค Equity เทียบกับ Balance (ซึ่ง MT5 Balance จะอัปเดตเมื่อไม้ปิด)
            if not risk_manager.check_daily_drawdown(acc_info.balance, acc_info.equity):
                logger.warning("Daily drawdown limit reached. Pausing for the day.")
                time.sleep(3600)  # พัก 1 ชั่วโมงแล้ววนลูปใหม่ เผื่อข้ามวัน
                continue
                
            # ตรวจสอบ Trade Limit
            if daily_trades_count >= max_trades:
                logger.info("Max daily trades reached. Waiting for next day.")
                time.sleep(3600)
                continue

            # ตรวจสอบ Killzone
            in_killzone, session_name = strategy.is_in_killzone()
            if not in_killzone:
                logger.debug("Outside of killzones. Waiting...")
                time.sleep(60)
                continue
                
            # วนลูปตรวจสอบแต่ละคู่เงิน
            for symbol in symbols:
                # 1. เช็ค Spread Filter
                max_spread = config.get("max_spread_points", {}).get(symbol, 30)
                if not mt5_client.check_spread(symbol, max_spread):
                    continue

                # 2. วิเคราะห์ 4H Trend
                trend = strategy.analyze_4h_trend(symbol)
                logger.debug(f"{symbol} 4H Trend: {trend}")
                
                # 3. หา 15M Entry Setup
                setup = strategy.find_15m_entry(symbol, trend)
                if setup:
                    # 4. ตรวจสอบ R:R Ratio
                    if not risk_manager.validate_setup(setup['entry'], setup['sl'], setup['tp'], symbol):
                        continue
                        
                    # 5. คำนวณ Lot Size
                    sym_info = mt5_client.get_symbol_info(symbol)
                    if not sym_info:
                        continue
                        
                    lot_size = risk_manager.calculate_lot_size(acc_info.equity, sym_info, setup['entry'], setup['sl'])
                    if lot_size <= 0:
                        logger.warning(f"Calculated lot size is 0 for {symbol}")
                        continue
                        
                    # 6. ส่งคำสั่งซื้อขาย (ส่งเป็น Market หรือ Limit ขึ้นอยู่กับ Setup, ในนี้ส่ง Market ไปที่ Entry Price ถ้าราคาถึง)
                    # หมายเหตุ: ในความจริงอาจจะต้องใช้ MT5_ORDER_TYPE_BUY/SELL (Market) เพราะ current price แตะ zone พอดี
                    ticket = mt5_client.place_order(
                        symbol, setup['type'], lot_size, setup['entry'], setup['sl'], setup['tp']
                    )
                    
                    if ticket:
                        daily_trades_count += 1
                        logger.info(f"Trade executed: #{ticket} {setup['type']} {symbol} Lot: {lot_size}")
                        
                        # บันทึกฐานข้อมูล
                        db.log_trade(
                            ticket, symbol, setup['type'], datetime.now(), setup['entry'], 
                            setup['sl'], setup['tp'], lot_size, setup.get('fvg_size', 0), session_name
                        )
                        
                        # แจ้งเตือน
                        tg.notify_order_placed(symbol, setup['type'], setup['entry'], setup['sl'], setup['tp'], ticket)

            # หน่วงเวลาลูป
            time.sleep(60)

    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    finally:
        mt5_client.shutdown()

if __name__ == "__main__":
    main()
