import MetaTrader5 as mt5
import pandas as pd
from dotenv import load_dotenv
import os
import time
from datetime import datetime, timezone
from bot.logger import logger

load_dotenv()

import ctypes

class MT5Client:
    def __init__(self, tg=None):
        self.login = int(os.getenv("MT5_LOGIN", 0))
        self.password = os.getenv("MT5_PASSWORD", "")
        self.server = os.getenv("MT5_SERVER", "")
        self.mt5_path = os.getenv("MT5_PATH", r"C:\Program Files\XM Global MT5\terminal64.exe")
        self.connected = False
        self.tg = tg

    def hide_window(self):
        """ซ่อนหน้าต่าง XM MT5 และซ่อนไอคอนจาก Taskbar ด้านล่างทั้งหมด (SW_HIDE + WS_EX_TOOLWINDOW)"""
        try:
            import subprocess
            target_pids = set()
            try:
                info = mt5.terminal_info()
                if info:
                    pid = getattr(info, 'pid', getattr(info, 'process_id', None))
                    if pid: target_pids.add(pid)
            except Exception:
                pass

            try:
                out = subprocess.check_output('tasklist /FI "IMAGENAME eq terminal64.exe" /FO CSV /NH', shell=True, text=True)
                for line in out.strip().splitlines():
                    parts = line.split('","')
                    if len(parts) >= 2:
                        try:
                            target_pids.add(int(parts[1].replace('"', '')))
                        except ValueError:
                            pass
            except Exception:
                pass

            if not target_pids:
                return False

            user32 = ctypes.windll.user32
            GWL_EXSTYLE = -20
            WS_EX_APPWINDOW = 0x00040000
            WS_EX_TOOLWINDOW = 0x00000080
            
            EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
            found_count = [0]

            def foreach_window(hwnd, lparam):
                pid = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value in target_pids:
                    # ปรับแต่ง Window Extended Style เพื่อลบไอคอนออกจาก Taskbar ด้านล่างโดยตรง
                    ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                    new_ex_style = (ex_style & ~WS_EX_APPWINDOW) | WS_EX_TOOLWINDOW
                    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_ex_style)
                    # ซ่อนหน้าต่าง
                    user32.ShowWindow(hwnd, 0)  # 0 = SW_HIDE
                    found_count[0] += 1
                return True

            user32.EnumWindows(EnumWindowsProc(foreach_window), 0)
            if found_count[0] > 0:
                logger.info(f"XM MT5 Terminal window & Taskbar icon hidden (PIDs: {target_pids}).")
                return True
            return False
        except Exception as e:
            logger.warning(f"Could not hide MT5 window/Taskbar: {e}")
            return False

    def show_window(self):
        """แสดงหน้าต่าง XM MT5 กลับขึ้นมาบน Taskbar"""
        try:
            import subprocess
            target_pids = set()
            try:
                info = mt5.terminal_info()
                if info:
                    pid = getattr(info, 'pid', getattr(info, 'process_id', None))
                    if pid: target_pids.add(pid)
            except Exception:
                pass

            try:
                out = subprocess.check_output('tasklist /FI "IMAGENAME eq terminal64.exe" /FO CSV /NH', shell=True, text=True)
                for line in out.strip().splitlines():
                    parts = line.split('","')
                    if len(parts) >= 2:
                        try:
                            target_pids.add(int(parts[1].replace('"', '')))
                        except ValueError:
                            pass
            except Exception:
                pass

            if not target_pids:
                return False

            user32 = ctypes.windll.user32
            GWL_EXSTYLE = -20
            WS_EX_APPWINDOW = 0x00040000
            WS_EX_TOOLWINDOW = 0x00000080
            
            EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
            def foreach_window(hwnd, lparam):
                pid = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value in target_pids:
                    ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                    new_ex_style = (ex_style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
                    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_ex_style)
                    user32.ShowWindow(hwnd, 5)  # 5 = SW_SHOW
                return True

            user32.EnumWindows(EnumWindowsProc(foreach_window), 0)
            return True
        except Exception as e:
            logger.warning(f"Could not show MT5 window: {e}")
            return False

    def connect(self):
        """เชื่อมต่อกับ MetaTrader 5 Terminal (เปิดโปรแกรมและ Login อัตโนมัติในคลิกเดียว)"""
        init_success = False
        if os.path.exists(self.mt5_path):
            logger.info(f"Auto-launching XM MT5 Terminal: {self.mt5_path}")
            init_success = mt5.initialize(path=self.mt5_path, login=self.login, password=self.password, server=self.server)
        else:
            init_success = mt5.initialize()
            
        if not init_success:
            logger.error(f"MT5 initialize failed, error code: {mt5.last_error()}")
            if self.tg:
                self.tg.send_message("⚠️ <b>MT5 Connection Warning:</b> ไม่สามารถเปิดโปรแกรม XM MT5 ได้")
            return False

        if not mt5.login(self.login, self.password, self.server):
            logger.error(f"MT5 login failed, error code: {mt5.last_error()}")
            if self.tg:
                self.tg.send_message("⚠️ <b>MT5 Login Warning:</b> ล็อกอินเข้า XM MT5 ไม่สำเร็จ กรุณาเช็คพาสเวิร์ด")
            mt5.shutdown()
            return False
            
        logger.info(f"Connected to MT5 Server: {self.server} (Account: {self.login})")
        self.connected = True

        # ซ่อนหน้าต่าง XM MT5 จาก Taskbar แบบอัตโนมัติเมื่อตั้งค่า HIDE_MT5=1 ใน .env
        if os.getenv("HIDE_MT5", "0") == "1":
            import threading
            def auto_hide_loop():
                for _ in range(12):
                    time.sleep(0.5)
                    if self.hide_window():
                        break
            threading.Thread(target=auto_hide_loop, daemon=True).start()

        return True

    def ensure_connection(self):
        """ตรวจสอบและ Reconnect ถ้าการเชื่อมต่อหลุด"""
        if not self.connected or mt5.terminal_info() is None:
            logger.warning("Connection lost. Attempting to reconnect...")
            if self.tg:
                self.tg.send_message("⚠️ <b>MT5 Connection Lost!</b>\nสัญญาณอินเทอร์เน็ตหรือการเชื่อมต่อโบรกเกอร์หลุด กำลัง Reconnect อัตโนมัติ...")
            self.connect()

    def ensure_symbol_selected(self, symbol: str) -> bool:
        """เปิดการรับข้อมูลราคาของคู่เงินใน Market Watch (ไม่ต้องเปิดหน้าต่างกราฟใน MT5 GUI)"""
        self.ensure_connection()
        selected = mt5.symbol_select(symbol, True)
        if not selected:
            logger.warning(f"Failed to select symbol {symbol} in MT5 Market Watch")
        return selected

    def subscribe_symbols(self, symbols: list):
        """เปิดรับข้อมูลราคาของคู่เงินทั้งหมดที่ตั้งค่าไว้"""
        for sym in symbols:
            if self.ensure_symbol_selected(sym):
                logger.info(f"Background subscription active for symbol: {sym}")

    def get_rates(self, symbol, timeframe, num_bars):
        """ดึงข้อมูลราคา (OHLCV) กลับมาเป็น Pandas DataFrame"""
        self.ensure_symbol_selected(symbol)
        
        tf_map = {
            "M1": mt5.TIMEFRAME_M1,
            "M15": mt5.TIMEFRAME_M15,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1
        }
        
        rates = mt5.copy_rates_from_pos(symbol, tf_map.get(timeframe, mt5.TIMEFRAME_M15), 0, num_bars)
        if rates is None:
            logger.error(f"Failed to get rates for {symbol}, error code: {mt5.last_error()}")
            return None
            
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        return df

    def get_tick(self, symbol):
        """ดึงราคาปัจจุบัน (Bid/Ask)"""
        self.ensure_symbol_selected(symbol)
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.error(f"Failed to get tick for {symbol}")
            return None
        return tick

    def get_symbol_info(self, symbol):
        """ดึงข้อมูลเชิงลึกของคู่เงิน"""
        self.ensure_symbol_selected(symbol)
        info = mt5.symbol_info(symbol)
        if info is None:
            logger.error(f"Failed to get symbol info for {symbol}")
            return None
        return info

    def get_account_info(self):
        """ดึงข้อมูลบัญชี (Equity, Balance)"""
        self.ensure_connection()
        info = mt5.account_info()
        if info is None:
            logger.error("Failed to get account info")
            return None
        return info

    def check_spread(self, symbol, max_spread_points):
        """ตรวจสอบ Spread"""
        info = self.get_symbol_info(symbol)
        if not info: return False
        
        spread = info.spread
        if spread > max_spread_points:
            logger.warning(f"Spread for {symbol} is too high: {spread} > {max_spread_points}")
            return False
        return True

    def is_market_open(self, symbol):
        """ตรวจสอบว่าตลาดเปิดทำการอยู่หรือไม่ (Forex/Metals ปิดวันเสาร์-อาทิตย์, Crypto เปิด 24/7)"""
        now_utc = datetime.now(timezone.utc)
        weekday = now_utc.weekday()  # 5 = Saturday, 6 = Sunday
        
        if "BTC" in symbol or "ETH" in symbol or "CRYPTO" in symbol:
            return True
            
        if weekday in [5, 6]:
            return False
            
        return True

    def place_order(self, symbol, order_type, volume, price, sl, tp, comment="ICT_Bot"):
        """ส่งคำสั่งเทรด"""
        self.ensure_connection()
        
        type_dict = {
            "BUY": mt5.ORDER_TYPE_BUY,
            "SELL": mt5.ORDER_TYPE_SELL,
            "BUY_LIMIT": mt5.ORDER_TYPE_BUY_LIMIT,
            "SELL_LIMIT": mt5.ORDER_TYPE_SELL_LIMIT
        }

        request = {
            "action": mt5.TRADE_ACTION_DEAL if order_type in ["BUY", "SELL"] else mt5.TRADE_ACTION_PENDING,
            "symbol": symbol,
            "volume": float(volume),
            "type": type_dict.get(order_type),
            "price": float(price),
            "sl": float(sl),
            "tp": float(tp),
            "deviation": 20,
            "magic": 123456,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result.retcode == 10018: # TRADE_RETCODE_MARKET_CLOSED
            logger.warning(f"Order skipped for {symbol}: ตลาดปิดทำการอยู่ในขณะนี้ (Market Closed)")
            return None
            
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Order failed for {symbol}, retcode={result.retcode}, comment={result.comment}")
            return None
            
        logger.info(f"Order placed successfully: Ticket {result.order}")
        return result.order

    def shutdown(self):
        mt5.shutdown()
        self.connected = False
        logger.info("MT5 connection closed.")
