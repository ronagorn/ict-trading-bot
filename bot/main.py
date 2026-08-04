import sys
import os

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import json
import time
import gc
import socket
import MetaTrader5 as mt5
from datetime import datetime, timezone, timedelta
import pytz

from bot.mt5_client import MT5Client
from bot.strategy import ICTStrategy
from bot.risk_manager import RiskManager
from bot.news_filter import NewsFilter
from bot.logger import logger
from services.db_client import SupabaseClient
from services.telegram_bot import TelegramNotifier
from services.ai_analyzer import AIAnalyzer

def ensure_single_instance():
    """ป้องกันการเปิดบอทซ้ำหลายหน้าต่าง (Single Instance Guard)"""
    try:
        lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lock_socket.bind(('127.0.0.1', 47382))
        return lock_socket
    except OSError:
        logger.warning("Another instance of AURA Trading Bot is already running!")
        print("⚠️ AURA Trading Bot is already running! (ระบบบอทเปิดทำงานอยู่แล้ว ไม่เปิดซ้ำ)")
        sys.exit(0)

def load_config():
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load config.json: {e}")
        return {}

def check_closed_trades(open_tickets: set, tg: TelegramNotifier, db) -> set:
    """
    ตรวจสอบว่ามีออเดอร์ที่เปิดอยู่ก่อนหน้า แต่ตอนนี้ปิดไปแล้วไหม
    ถ้าปิดแล้วให้แจ้งเตือนผลการเทรดผ่าน Telegram ทันที
    """
    current_positions = mt5.positions_get()
    current_tickets = set()
    if current_positions:
        current_tickets = {pos.ticket for pos in current_positions}

    # หา ticket ที่หายไป = ออเดอร์ปิดแล้ว
    closed_tickets = open_tickets - current_tickets

    for ticket in closed_tickets:
        try:
            # ดึงประวัติออเดอร์ที่ปิดแล้วจาก MT5 (เฉพาะ 7 วันล่าสุด เพื่อประหยัด CPU/RAM)
            from_time = datetime.now(timezone.utc) - timedelta(days=7)
            to_time = datetime.now(timezone.utc)
            deals = mt5.history_deals_get(from_time, to_time)

            if deals is None:
                continue

            # หา deal ที่ตรงกับ ticket นี้ (entry + exit)
            deal_list = [d for d in deals if d.position_id == ticket]
            if not deal_list:
                continue

            # entry deal = deal แรก, exit deal = deal สุดท้าย
            entry_deal = next((d for d in deal_list if d.entry == 0), None)  # DEAL_ENTRY_IN = 0
            exit_deal = next((d for d in deal_list if d.entry == 1), None)   # DEAL_ENTRY_OUT = 1

            if not exit_deal:
                continue

            pnl = exit_deal.profit
            symbol = exit_deal.symbol
            volume = exit_deal.volume
            close_price = exit_deal.price
            close_time = datetime.fromtimestamp(exit_deal.time, tz=pytz.timezone('Asia/Bangkok')).strftime('%H:%M:%S')

            entry_price = entry_deal.price if entry_deal else 0
            order_type = "BUY" if exit_deal.type == 1 else "SELL"  # reverse: exit type 1 = closed buy

            # สร้างข้อความแจ้งเตือน
            if pnl > 0:
                emoji = "✅"
                result_text = "TP Hit! กำไร"
                pnl_text = f"+${pnl:.2f} 💰"
            elif pnl < 0:
                emoji = "❌"
                result_text = "SL Hit! ขาดทุน"
                pnl_text = f"-${abs(pnl):.2f} 📉"
            else:
                emoji = "⚖️"
                result_text = "Breakeven"
                pnl_text = "$0.00"

            msg = f"{emoji} <b>TRADE CLOSED — {result_text}</b>\n\n"
            msg += f"<b>Ticket:</b> #{ticket}\n"
            msg += f"<b>Symbol:</b> {symbol}\n"
            msg += f"<b>Type:</b> {order_type}\n"
            msg += f"<b>Entry Price:</b> {entry_price:.2f}\n"
            msg += f"<b>Close Price:</b> {close_price:.2f}\n"
            msg += f"<b>Lot Size:</b> {volume}\n"
            msg += f"<b>Close Time:</b> {close_time} (ICT)\n"
            msg += f"━━━━━━━━━━━━━━━━\n"
            msg += f"<b>ผลกำไร/ขาดทุน: {pnl_text}</b>"

            tg.send_message(msg)
            logger.info(f"Trade #{ticket} closed. PnL: {pnl:.2f}")

            # อัปเดตฐานข้อมูล
            try:
                db.update_trade_close(ticket, datetime.now(), pnl)
            except Exception:
                pass

        except Exception as e:
            logger.error(f"Error processing closed trade #{ticket}: {e}")

    return current_tickets  # return ชุด tickets ที่ยังเปิดอยู่ตอนนี้


def main():
    instance_lock = ensure_single_instance()
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
    
    aura_cfg = config.get("aura_ultimate", {})
    symbols = config.get("symbols", ["GOLD#", "BTCUSD#"])
    if aura_cfg.get("whitelist_only", False):
        symbols = [s for s in symbols if s in aura_cfg.get("whitelist_symbols", symbols)]
    mt5_client.subscribe_symbols(symbols)
    max_trades = config.get("max_trades_per_day", 30)
    daily_trades_count = 0
    loop_counter = 0
    current_date = datetime.now().date()
    last_heartbeat_hour = -1

    # ติดตาม open positions ปัจจุบัน
    tracked_open_tickets = set()
    positions = mt5.positions_get()
    if positions:
        tracked_open_tickets = {pos.ticket for pos in positions}
    
    # ---------------------------------------------------------
    # ตั้งค่า Callbacks ให้กับ Telegram Bot Listener
    # ---------------------------------------------------------
    def get_status_summary():
        current_pos = mt5.positions_get()
        active_pos_count = len(current_pos) if current_pos else 0
        return (
            f"<b>MT5 Terminal:</b> Connected ✅\n"
            f"<b>คู่เงินที่สแกน:</b> {', '.join(symbols)}\n"
            f"<b>ออเดอร์เปิดอยู่:</b> {active_pos_count} ไม้\n"
            f"<b>โควตาเทรดวันนี้:</b> {daily_trades_count}/{max_trades} ไม้"
        )

    def get_balance_summary():
        acc_info = mt5_client.get_account_info()
        if not acc_info:
            return "❌ ไม่สามารถดึงข้อมูลบัญชี MT5 ได้"
        floating_profit = acc_info.equity - acc_info.balance
        pnl_prefix = "+" if floating_profit >= 0 else ""
        return (
            f"<b>Balance:</b> ${acc_info.balance:,.2f}\n"
            f"<b>Equity:</b> ${acc_info.equity:,.2f}\n"
            f"<b>Free Margin:</b> ${acc_info.margin_free:,.2f}\n"
            f"<b>Floating P/L:</b> {pnl_prefix}${floating_profit:,.2f}"
        )

    def get_positions_summary():
        open_pos = mt5.positions_get()
        if not open_pos:
            return "ℹ️ ไม่มีออเดอร์ที่เปิดอยู่ ณ ขณะนี้"
        
        lines = []
        for pos in open_pos:
            pos_type = "BUY 🟢" if pos.type == 0 else "SELL 🔴"
            pnl_str = f"+${pos.profit:.2f}" if pos.profit >= 0 else f"-${abs(pos.profit):.2f}"
            lines.append(
                f"• <b>#{pos.ticket}</b> {pos.symbol} ({pos_type})\n"
                f"  Lot: {pos.volume} | Entry: {pos.price_open:.2f}\n"
                f"  SL: {pos.sl:.2f} | TP: {pos.tp:.2f}\n"
                f"  กำไร/ขาดทุน: <b>{pnl_str}</b>"
            )
        return "\n\n".join(lines)

    def get_ai_summary():
        result = ai.analyze_daily_performance()
        if not result:
            return "ℹ️ Gemini AI ยังไม่มีข้อมูลบทวิเคราะห์เพิ่มเติมสำหรับวันนี้"
        return result

    tg.set_callback("status", get_status_summary)
    tg.set_callback("balance", get_balance_summary)
    tg.set_callback("positions", get_positions_summary)
    tg.set_callback("ai_summary", get_ai_summary)

    # เริ่มระบบ Telegram Command Listener (Background Thread)
    tg.start_polling()

    # แจ้งเตือนเมื่อบอทเริ่มทำงาน
    tg.send_message("🚀 <b>AURA Super Trader Bot Started</b>\nพร้อมสแกนกราฟเทรดจริง GOLD# & BTCUSD# ( High-Frequency FVG Engine + 4H Shield )\n<i>คุณสามารถสั่งการหรือพิมพ์ถามผ่าน Telegram ได้แล้วครับ</i>")

    try:
        while True:
            now_date = datetime.now().date()
            now_dt = datetime.now()
            
            # ✅ ตรวจสอบออเดอร์ที่ปิดไปแล้วและแจ้งผลทาง Telegram
            tracked_open_tickets = check_closed_trades(tracked_open_tickets, tg, db)

            # หากถูกสั่ง PAUSE ผ่าน Telegram ให้รอและข้ามการสแกนเปิดออเดอร์
            if tg.is_paused():
                time.sleep(10)
                continue

            # Heartbeat ทุก 4 ชั่วโมง
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
                # 0.0 ตรวจสอบโควตาความเสี่ยง: สิทธิเปิดออเดอร์ต่อคู่เงิน (ไม่เกิน 2 ไม้), รวมทั้งพอร์ต (ไม่เกิน 4 ไม้) และ Currency Correlation
                current_positions = mt5.positions_get() or []
                if not risk_manager.can_open_new_position(current_positions, symbol):
                    continue

                # 0.1 เช็คว่าตลาดเปิดทำการอยู่หรือไม่ (เสาร์-อาทิตย์ ตลาด Forex & Gold ปิด, Crypto เปิด 24/7)
                if not mt5_client.is_market_open(symbol):
                    continue

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
                        
                    risk_pct = aura_cfg.get("risk_percent")
                    lot_size = risk_manager.calculate_lot_size(acc_info.equity, sym_info, setup['entry'], setup['sl'], risk_percent=risk_pct)
                    if lot_size <= 0:
                        logger.warning(f"Calculated lot size is 0 for {symbol}")
                        continue
                        
                    # 6. ส่งคำสั่งซื้อขาย
                    ticket = mt5_client.place_order(
                        symbol, setup['type'], lot_size, setup['entry'], setup['sl'], tp_target
                    )
                    
                    if ticket:
                        daily_trades_count += 1
                        tracked_open_tickets.add(ticket)  # เพิ่ม ticket ใหม่เข้า tracker
                        logger.info(f"Trade executed: #{ticket} {setup['type']} {symbol} Lot: {lot_size} [{setup['source']}]")
                        
                        # บันทึกฐานข้อมูล
                        db.log_trade(
                            ticket, symbol, setup['type'], datetime.now(), setup['entry'], 
                            setup['sl'], tp_target, lot_size, setup.get('fvg_size', 0), session_name
                        )
                        
                    # แจ้งเตือน Telegram (Entry)
                    sniper_badge = " SNIPER" if setup.get("is_sniper") else ""
                    msg = f"💥 <b>ENTRY SIGNAL EXECUTED [{setup['source']}{sniper_badge}]</b>\n\n"
                    msg += f"<b>Ticket:</b> #{ticket}\n"
                    msg += f"<b>Symbol:</b> {symbol}\n"
                    msg += f"<b>Type:</b> {setup['type']}\n"
                    msg += f"<b>Entry:</b> {setup['entry']:.2f}\n"
                    msg += f"<b>SL:</b> {setup['sl']:.2f}\n"
                    msg += f"<b>TP:</b> {tp_target:.2f}\n"
                    msg += f"<b>Lot Size:</b> {lot_size}\n"
                    tg.send_message(msg)

            # เคลียร์ memory ทุกๆ 30 ลูป (ประมาณ 5 นาที)
            loop_counter += 1
            if loop_counter % 30 == 0:
                gc.collect()

            # หน่วงเวลาลูป (10 วิเพื่อสแกน + ตรวจออเดอร์ที่ปิด)
            time.sleep(10)

    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
        tg.send_message("🛑 <b>AURA Bot Shutting Down</b>\nผู้ใช้ได้ทำการปิดระบบการทำงานของบอทเรียบร้อยแล้ว")
    except Exception as e:
        logger.error(f"Bot error: {e}")
        tg.send_message(f"🚨 <b>AURA Bot Error Crash:</b>\nเกิดข้อผิดพลาดทำให้บอทหยุดทำงาน: {e}")
    finally:
        tg.stop_polling()
        tg.send_message("🔴 <b>AURA Bot Status: OFFLINE</b>")
        mt5_client.shutdown()

if __name__ == "__main__":
    main()
