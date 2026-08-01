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
    logger.info("Initializing Institutional ICT Trading Bot...")
    config = load_config()
    tg = TelegramNotifier()
    
    mt5_client = MT5Client(tg)
    if not mt5_client.connect():
        logger.error("Failed to connect to MT5. Exiting.")
        tg.send_message("🚨 <b>Bot Error:</b> ไม่สามารถเปิดหรือเชื่อมต่อโปรแกรม XM MT5 ได้")
        return

    db = SupabaseClient()
    ai = AIAnalyzer(db, tg)
    
    strategy = ICTStrategy(mt5_client, config)
    risk_manager = RiskManager(config)
    
    symbols = config.get("symbols", ["GOLD#", "BTCUSD#"])
    max_trades = config.get("max_trades_per_day", 30)
    daily_trades_count = 0
    current_date = datetime.now().date()
    last_heartbeat_hour = -1
    
    # แจ้งเตือนเมื่อบอทเริ่มทำงาน
    tg.send_message("🚀 <b>AURA Super Trader Bot Started</b>\nพร้อมสแกนกราฟเทรดจริง GOLD# & BTCUSD# ( High-Frequency FVG Engine + 4H Shield )")

    try:
        while True:
            now_date = datetime.now().date()
            now_dt = datetime.now()
            
            # Hourly Heartbeat (แจ้งเตือนความพร้อมของบอททุกๆ 4 ชั่วโมง)
            if now_dt.hour % 4 == 0 and now_dt.hour != last_heartbeat_hour:
                last_heartbeat_hour = now_dt.hour
                logger.info("Heartbeat: Bot running smoothly.")
                tg.send_message(f"💓 <b>AURA System Heartbeat</b>\nบอททำงานปกติกำลังเฝ้าสแกนตลาด ({now_dt.strftime('%H:%M')} น.)")
            
            # Reset daily counters
            if now_date != current_date:
                current_date = now_date
                daily_trades_count = 0
                logger.info("New day started, resetting trade counters.")
                ai.analyze_daily_performance()
                
            # ตรวจสอบ Drawdown limit
            acc_info = mt5_client.get_account_info()
            if not acc_info:
                time.sleep(10)
                continue
                
            if not risk_manager.check_daily_drawdown(acc_info.balance, acc_info.equity):
                logger.warning("Daily drawdown limit reached. Pausing for the day.")
                tg.send_message("⚠️ <b>Circuit Breaker Triggered</b>\nพอร์ตแตะขีดจำกัดความเสี่ยงรายวัน หยุดเทรดชั่วคราวเพื่อความปลอดภัย 24 ชม.")
                time.sleep(3600)
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
                max_spread = config.get("max_spread_points", {}).get(symbol, 40)
                if not mt5_client.check_spread(symbol, max_spread):
                    continue

                # 2. วิเคราะห์ Multi-Timeframe Structure
                trend = strategy.analyze_market_structure(symbol)
                logger.debug(f"{symbol} MTF Trend: {trend}")
                
                # 3. หา Entry Setup ระดับสไนเปอร์
                setup = strategy.find_super_trader_setup(symbol, trend)
                if setup:
                    tp_target = setup.get('tp2', setup.get('tp1'))
                    
                    # 4. ตรวจสอบ R:R Ratio
                    if not risk_manager.validate_setup(setup['entry'], setup['sl'], tp_target, symbol):
                        continue
                        
                    # 5. คำนวณ Lot Size
                    sym_info = mt5_client.get_symbol_info(symbol)
                    if not sym_info:
                        continue
                        
                    lot_size = risk_manager.calculate_lot_size(acc_info.equity, sym_info, setup['entry'], setup['sl'])
                    if lot_size <= 0:
                        logger.warning(f"Calculated lot size is 0 for {symbol}")
                        continue
                        
                    # 6. ส่งคำสั่งซื้อขาย
                    ticket = mt5_client.place_order(
                        symbol, setup['type'], lot_size, setup['entry'], setup['sl'], tp_target
                    )
                    
                    if ticket:
                        daily_trades_count += 1
                        logger.info(f"Trade executed: #{ticket} {setup['type']} {symbol} Lot: {lot_size} [{setup['source']}]")
                        
                        # บันทึกฐานข้อมูล
                        db.log_trade(
                            ticket, symbol, setup['type'], datetime.now(), setup['entry'], 
                            setup['sl'], tp_target, lot_size, setup.get('fvg_size', 0), session_name
                        )
                        
                        # แจ้งเตือน Telegram
                        msg = f"💥 <b>ENTRY SIGNAL EXECUTED [{setup['source']}]</b>\n\n"
                        msg += f"<b>Ticket:</b> #{ticket}\n"
                        msg += f"<b>Symbol:</b> {symbol}\n"
                        msg += f"<b>Type:</b> {setup['type']}\n"
                        msg += f"<b>Entry:</b> {setup['entry']:.2f}\n"
                        msg += f"<b>SL:</b> {setup['sl']:.2f}\n"
                        msg += f"<b>TP (1:3 Target):</b> {setup['tp']:.2f}\n"
                        msg += f"<b>Lot Size:</b> {lot_size}\n"
                        tg.send_message(msg)

            # หน่วงเวลาลูป
            time.sleep(10)

    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
        tg.send_message("🛑 <b>AURA Bot Shutting Down</b>\nผู้ใช้ได้ทำการปิดระบบการทำงานของบอทเรียบร้อยแล้ว")
    except Exception as e:
        logger.error(f"Bot error: {e}")
        tg.send_message(f"🚨 <b>AURA Bot Error Crash:</b>\nเกิดข้อผิดพลาดทำให้บอทหยุดทำงาน: {e}")
    finally:
        tg.send_message("🔴 <b>AURA Bot Status: OFFLINE</b>")
        mt5_client.shutdown()

if __name__ == "__main__":
    main()
