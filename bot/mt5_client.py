import MetaTrader5 as mt5
import pandas as pd
from dotenv import load_dotenv
import os
import time
from bot.logger import logger

load_dotenv()

class MT5Client:
    def __init__(self):
        self.login = int(os.getenv("MT5_LOGIN", 0))
        self.password = os.getenv("MT5_PASSWORD", "")
        self.server = os.getenv("MT5_SERVER", "")
        self.connected = False

    def connect(self):
        """เชื่อมต่อกับ MetaTrader 5 Terminal"""
        if not mt5.initialize():
            logger.error(f"MT5 initialize failed, error code: {mt5.last_error()}")
            return False

        if not mt5.login(self.login, self.password, self.server):
            logger.error(f"MT5 login failed, error code: {mt5.last_error()}")
            mt5.shutdown()
            return False
            
        logger.info(f"Connected to MT5 Server: {self.server} (Account: {self.login})")
        self.connected = True
        return True

    def ensure_connection(self):
        """ตรวจสอบและ Reconnect ถ้าการเชื่อมต่อหลุด"""
        if not self.connected or mt5.terminal_info() is None:
            logger.warning("Connection lost. Attempting to reconnect...")
            self.connect()

    def get_rates(self, symbol, timeframe, num_bars):
        """ดึงข้อมูลราคา (OHLCV) กลับมาเป็น Pandas DataFrame"""
        self.ensure_connection()
        
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
        self.ensure_connection()
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.error(f"Failed to get tick for {symbol}")
            return None
        return tick

    def get_symbol_info(self, symbol):
        """ดึงข้อมูลเชิงลึกของคู่เงิน (เช่น ขนาด point, trade_contract_size)"""
        self.ensure_connection()
        # เพิ่ม: สั่งให้ MT5 ดึงคู่เงินนี้มาแสดงใน Market Watch ก่อน ไม่งั้นจะหาไม่เจอ
        mt5.symbol_select(symbol, True)
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
        """ตรวจสอบว่า Spread ปัจจุบันเกินกำหนดหรือไม่ (เพื่อป้องกันการเทรดตอนข่าวหรือสภาพคล่องต่ำ)"""
        info = self.get_symbol_info(symbol)
        if not info: return False
        
        spread = info.spread
        if spread > max_spread_points:
            logger.warning(f"Spread for {symbol} is too high: {spread} > {max_spread_points}")
            return False
        return True

    def place_order(self, symbol, order_type, volume, price, sl, tp, comment="ICT_Bot"):
        """ส่งคำสั่งเทรด (Buy Limit / Sell Limit / Market)"""
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
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Order failed, retcode={result.retcode}, comment={result.comment}")
            return None
            
        logger.info(f"Order placed successfully: Ticket {result.order}")
        return result.order

    def shutdown(self):
        mt5.shutdown()
        self.connected = False
        logger.info("MT5 connection closed.")
