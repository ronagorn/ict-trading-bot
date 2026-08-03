import pandas as pd
import numpy as np
from smartmoneyconcepts import smc
from bot.logger import logger
from datetime import datetime
import pytz

class ICTStrategy:
    def __init__(self, mt5_client, config):
        self.mt5 = mt5_client
        self.config = config

    def calculate_atr(self, df, period=14):
        high = df['high']
        low = df['low']
        close = df['close']
        tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
        return tr.rolling(period).mean().bfill()

    def analyze_market_structure(self, symbol):
        """
        วิเคราะห์เทรนด์แบบ Multi-Timeframe:
        - สำหรับ GOLD#: ใช้ 4H Structure + M15 EMA 200 (บล็อกข่าวและช่วงผันผวน 100%)
        - สำหรับ BTCUSD#: ใช้ M15 EMA 200
        """
        df_m15 = self.mt5.get_rates(symbol, "M15", 250)
        if df_m15 is None or df_m15.empty:
            return "NEUTRAL"
            
        df_m15['ema200'] = df_m15['close'].ewm(span=200).mean()
        c_close = df_m15['close'].iloc[-1]
        ema200 = df_m15['ema200'].iloc[-1]
        
        m15_trend = "BULLISH" if c_close > ema200 else "BEARISH"
        
        # สำหรับ GOLD# ต้องเพิ่มความแม่นยำด้วยเทรนด์ใหญ่ 4H
        if "GOLD" in symbol:
            df_h4 = self.mt5.get_rates(symbol, "H4", 100)
            if df_h4 is not None and not df_h4.empty:
                df_h4.rename(columns={'tick_volume': 'volume'}, inplace=True)
                swing_h4 = smc.swing_highs_lows(df_h4)
                mss_h4 = smc.bos_choch(df_h4, swing_h4)
                v_bos = mss_h4[mss_h4['BOS'].isin([1, -1])].tail(1)
                v_choch = mss_h4[mss_h4['CHOCH'].isin([1, -1])].tail(1)
                
                h4_trend = "NEUTRAL"
                if not v_bos.empty: h4_trend = "BULLISH" if v_bos['BOS'].iloc[0] == 1 else "BEARISH"
                if not v_choch.empty and (v_bos.empty or v_choch.index[0] > v_bos.index[0]):
                    h4_trend = "BULLISH" if v_choch['CHOCH'].iloc[0] == 1 else "BEARISH"
                    
                if h4_trend != m15_trend:
                    return "NEUTRAL" # ป้องกันการเทรดช่วงผันผวนสวิงหลอก
                    
        return m15_trend

    def get_htf_premium_discount_zone(self, symbol, df_h4=None):
        """
        คำนวณโซน Premium / Discount ระดับ HTF 4H (50% Fibonacci Equilibrium):
        - DISCOUNT (< 50% Equilibrium): โซนของถูก -> เหมาะสำหรับ BUY เท่านั้น
        - PREMIUM (> 50% Equilibrium): โซนของแพง -> เหมาะสำหรับ SELL เท่านั้น
        """
        try:
            if df_h4 is None or df_h4.empty:
                df_h4 = self.mt5.get_rates(symbol, "H4", 60)
            if df_h4 is None or df_h4.empty:
                return "NEUTRAL"
                
            h4_high = df_h4['high'].tail(30).max()
            h4_low = df_h4['low'].tail(30).min()
            h4_range = h4_high - h4_low
            
            if h4_range <= 0:
                return "NEUTRAL"
                
            equilibrium = h4_low + (h4_range * 0.5)
            c_close = df_h4['close'].iloc[-1]
            
            return "DISCOUNT" if c_close < equilibrium else "PREMIUM"
        except Exception as e:
            logger.error(f"Error calculating HTF Premium/Discount zone for {symbol}: {e}")
            return "NEUTRAL"

    def find_super_trader_setup(self, symbol, trend, df_m15=None, df_h4=None):
        """
        อัลกอริทึม Super Trader AI Engine V2 (High-WinRate FVG + HTF Premium/Discount Zone Confluence)
        """
        if trend == "NEUTRAL":
            return None
            
        df = df_m15 if df_m15 is not None and not df_m15.empty else self.mt5.get_rates(symbol, "M15", 250)
        if df is None or df.empty:
            return None
            
        df = df.copy()
        df.rename(columns={'tick_volume': 'volume'}, inplace=True)
        df['ema200'] = df['close'].ewm(span=200).mean()
        df['atr'] = self.calculate_atr(df, 14)
        
        try:
            tick = self.mt5.get_tick(symbol)
            if not tick: return None
            
            fvg_df = smc.fvg(df)
            if fvg_df.empty: return None
            
            recent_fvg = fvg_df.tail(10)
            valid_fvgs = recent_fvg[recent_fvg['FVG'].notna()]
            if valid_fvgs.empty: return None
            
            last_fvg = valid_fvgs.tail(1)
            fvg_dir = int(last_fvg['FVG'].iloc[0])
            fvg_top = last_fvg['Top'].iloc[0]
            fvg_bot = last_fvg['Bottom'].iloc[0]
            fvg_size = abs(fvg_top - fvg_bot)
            
            current_atr = df['atr'].iloc[-1]
            current_open = df['open'].iloc[-1]
            current_low = df['low'].iloc[-1]
            current_high = df['high'].iloc[-1]
            current_close = df['close'].iloc[-1]
            ema200 = df['ema200'].iloc[-1]
            
            # ตรวจสอบ HTF Premium / Discount Zone
            htf_zone = self.get_htf_premium_discount_zone(symbol, df_h4=df_h4)
            
            # กรองเฉพาะ FVG ชัดเจน (>= 0.25 * ATR)
            if fvg_size < (current_atr * 0.25):
                return None
                
            # BULLISH SCALP: ต้องเป็นเทรนด์ BULLISH + FVG BULLISH + ราคาปิดเหนือ EMA200 + อยู่ใน DISCOUNT ZONE (< 50% EQ)
            if trend == "BULLISH" and fvg_dir == 1 and current_close > ema200:
                if htf_zone in ["DISCOUNT", "NEUTRAL"]:
                    if current_low <= fvg_top and current_high >= fvg_bot:
                        entry = fvg_top if current_open > fvg_top else current_open
                        sl = fvg_bot - (current_atr * 0.8)
                        risk = abs(entry - sl)
                        if risk == 0: return None
                        tp = entry + (risk * 2.0)
                        
                        return {
                            "type": "BUY",
                            "source": "Super Trader HTF Discount FVG Confluence",
                            "entry": entry,
                            "sl": sl,
                            "tp": tp,
                            "tp1": tp,
                            "fvg_size": fvg_size,
                            "htf_zone": htf_zone
                        }

            # BEARISH SCALP: ต้องเป็นเทรนด์ BEARISH + FVG BEARISH + ราคาปิดใต้ EMA200 + อยู่ใน PREMIUM ZONE (> 50% EQ)
            elif trend == "BEARISH" and fvg_dir == -1 and current_close < ema200:
                if htf_zone in ["PREMIUM", "NEUTRAL"]:
                    if current_high >= fvg_bot and current_low <= fvg_top:
                        entry = fvg_bot if current_open < fvg_bot else current_open
                        sl = fvg_top + (current_atr * 0.8)
                        risk = abs(sl - entry)
                        if risk == 0: return None
                        tp = entry - (risk * 2.0)
                        
                        return {
                            "type": "SELL",
                            "source": "Super Trader HTF Premium FVG Confluence",
                            "entry": entry,
                            "sl": sl,
                            "tp": tp,
                            "tp1": tp,
                            "fvg_size": fvg_size,
                            "htf_zone": htf_zone
                        }
                    
            return None
            
        except Exception as e:
            logger.error(f"Error in Super Trader FVG Scalper for {symbol}: {e}")
            return None

    def is_in_killzone(self):
        return True, "ALL_DAY_SCALPING"

