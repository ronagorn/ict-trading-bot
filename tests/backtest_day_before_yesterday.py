import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import json
from datetime import datetime, date
from dotenv import load_dotenv
from smartmoneyconcepts import smc
from bot.mt5_client import MT5Client
from services.telegram_bot import TelegramNotifier

load_dotenv()

def calculate_atr(df, period=14):
    high = df['high']
    low = df['low']
    close = df['close']
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean().bfill()

def run_day_before_yesterday_backtest():
    print("🚀 Starting Backtest for Day Before Yesterday (Thursday 30 July 2026)...")
    client = MT5Client()
    if not client.connect():
        print("Failed to connect to MT5.")
        return
        
    symbols = ["GOLD#", "BTCUSD#", "EURUSD#", "GBPUSD#", "USDJPY#", "AUDUSD#", "USDCAD#", "USDCHF#", "EURGBP#", "GBPJPY#"]
    bars_needed = 350
    
    target_date = date(2026, 7, 30)
    all_executed_trades = []
    
    total_wins = 0
    total_losses = 0
    total_net_pnl = 0.0
    
    for symbol in symbols:
        mt5.symbol_select(symbol, True)
        rates_m15 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, bars_needed)
        rates_h4 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H4, 0, 500)
        
        if rates_m15 is None: continue
        
        df = pd.DataFrame(rates_m15)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df['date'] = df['time'].dt.date
        df.rename(columns={'tick_volume': 'volume'}, inplace=True)
        df['ema200'] = df['close'].ewm(span=200).mean()
        df['atr'] = calculate_atr(df, 14)
        
        mss_h4 = None
        if "GOLD" in symbol and rates_h4 is not None:
            df_h4 = pd.DataFrame(rates_h4)
            df_h4['time'] = pd.to_datetime(df_h4['time'], unit='s')
            df_h4.rename(columns={'tick_volume': 'volume'}, inplace=True)
            swing_h4 = smc.swing_highs_lows(df_h4)
            mss_h4 = smc.bos_choch(df_h4, swing_h4)

        try:
            fvg_df = smc.fvg(df)
        except Exception:
            continue
            
        # กรองเฉพาะแท่งที่เป็นของวันพฤหัสบดีที่ 30 ก.ค. 2026
        group = df[df['date'] == target_date]
        if group.empty: continue
        
        for i in group.index:
            if i < 200 or i >= len(df) - 30: continue
            
            c_close = df.loc[i, 'close']
            c_low = df.loc[i, 'low']
            c_high = df.loc[i, 'high']
            c_open = df.loc[i, 'open']
            ema200 = df.loc[i, 'ema200']
            atr = df.loc[i, 'atr']
            t_utc = df.loc[i, 'time']
            
            m15_trend = 1 if c_close > ema200 else -1
            
            if "GOLD" in symbol and mss_h4 is not None:
                slice_h4 = mss_h4[df_h4['time'] <= t_utc]
                if slice_h4.empty: continue
                v_bos = slice_h4[slice_h4['BOS'].isin([1, -1])].tail(1)
                v_choch = slice_h4[slice_h4['CHOCH'].isin([1, -1])].tail(1)
                h4_trend = 0
                if not v_bos.empty: h4_trend = int(v_bos['BOS'].iloc[0])
                if not v_choch.empty and (v_bos.empty or v_choch.index[0] > v_bos.index[0]):
                    h4_trend = int(v_choch['CHOCH'].iloc[0])
                if h4_trend != m15_trend: continue

            recent_fvg = fvg_df.iloc[i-5:i]
            if recent_fvg.empty: continue
            
            last_fvg = recent_fvg[recent_fvg['FVG'].notna()].tail(1)
            if last_fvg.empty: continue
            
            fvg_dir = int(last_fvg['FVG'].iloc[0])
            fvg_top = last_fvg['Top'].iloc[0]
            fvg_bot = last_fvg['Bottom'].iloc[0]
            fvg_size = abs(fvg_top - fvg_bot)
            
            if fvg_size < (atr * 0.3): continue
            
            # BUY
            if fvg_dir == 1 and m15_trend == 1 and c_low <= fvg_top and c_high >= fvg_bot:
                entry = fvg_top if c_open > fvg_top else c_open
                sl = fvg_bot - (atr * 0.8)
                risk = abs(entry - sl)
                if risk == 0: continue
                tp = entry + (risk * 1.5)
                
                for m in range(i+1, min(i+40, len(df))):
                    if df.loc[m, 'low'] <= sl:
                        all_executed_trades.append({
                            "time": t_utc.strftime("%Y-%m-%d %H:%M"),
                            "symbol": symbol,
                            "type": "BUY",
                            "entry": entry,
                            "sl": sl,
                            "tp": tp,
                            "result": "LOSS",
                            "pnl": -1.00
                        })
                        total_losses += 1
                        total_net_pnl -= 1.00
                        break
                    if df.loc[m, 'high'] >= tp:
                        all_executed_trades.append({
                            "time": t_utc.strftime("%Y-%m-%d %H:%M"),
                            "symbol": symbol,
                            "type": "BUY",
                            "entry": entry,
                            "sl": sl,
                            "tp": tp,
                            "result": "WIN",
                            "pnl": 1.50
                        })
                        total_wins += 1
                        total_net_pnl += 1.50
                        break

            # SELL
            elif fvg_dir == -1 and m15_trend == -1 and c_high >= fvg_bot and c_low <= fvg_top:
                entry = fvg_bot if c_open < fvg_bot else c_open
                sl = fvg_top + (atr * 0.8)
                risk = abs(sl - entry)
                if risk == 0: continue
                tp = entry - (risk * 1.5)
                
                for m in range(i+1, min(i+40, len(df))):
                    if df.loc[m, 'high'] <= sl:
                        all_executed_trades.append({
                            "time": t_utc.strftime("%Y-%m-%d %H:%M"),
                            "symbol": symbol,
                            "type": "SELL",
                            "entry": entry,
                            "sl": sl,
                            "tp": tp,
                            "result": "LOSS",
                            "pnl": -1.00
                        })
                        total_losses += 1
                        total_net_pnl -= 1.00
                        break
                    if df.loc[m, 'low'] <= tp:
                        all_executed_trades.append({
                            "time": t_utc.strftime("%Y-%m-%d %H:%M"),
                            "symbol": symbol,
                            "type": "SELL",
                            "entry": entry,
                            "sl": sl,
                            "tp": tp,
                            "result": "WIN",
                            "pnl": 1.50
                        })
                        total_wins += 1
                        total_net_pnl += 1.50
                        break
                        
    client.shutdown()
    
    total_trades = len(all_executed_trades)
    winrate = (total_wins / total_trades * 100) if total_trades > 0 else 0.0
    
    report = f"📅 <b>REAL XM BACKTEST REPORT (วันวานซืน - พฤหัสบดีที่ 30 กรกฎาคม 2026)</b>\n"
    report += f"📊 <b>รวม 10 คู่เงินหลัก XM</b>\n\n"
    
    if all_executed_trades:
        report += "<b>📋 รายการออเดอร์เทรดจริงของวันวานซืน (30 ก.ค.):</b>\n"
        for idx, tr in enumerate(all_executed_trades, 1):
            icon = "✅ WIN (+1.5%)" if tr['result'] == "WIN" else "❌ LOSS (-1.0%)"
            report += f"{idx}. [{tr['time']}] <b>{tr['symbol']}</b> {tr['type']} Entry: {tr['entry']:.2f} | {icon}\n"
    else:
        report += "ไม่มีสัญญาณออเดอร์ในวันวานซืน\n"
        
    report += "\n----------------------------------------\n"
    report += f"🏆 <b>สรุปผลวันวานซืน (30 ก.ค.) (ทุน $100):</b>\n"
    report += f"🔹 สัญญาณเทรดรวม: <b>{total_trades} ไม้</b>\n"
    report += f"🔹 ชนะ (TP 1:1.5): <b>{total_wins} ไม้</b> | แพ้ (SL): <b>{total_losses} ไม้</b>\n"
    report += f"🔹 <b>Win Rate วานซืน: {winrate:.2f}%</b>\n"
    report += f"💵 <b>กำไรสุทธิรวมวานซืน (ทุน $100): ${total_net_pnl:.2f} (ROI: {total_net_pnl:.2f}%)</b>\n"
    report += f"💵 <b>กำไรสุทธิรวมวานซืน (ทุน $1,000): ${total_net_pnl*10:.2f} (ROI: {total_net_pnl:.2f}%)</b>\n"
    
    print("\n" + report.replace('<b>', '').replace('</b>', ''))
    
    tg = TelegramNotifier()
    if tg.enabled:
        tg.send_message(report)
        print("Day Before Yesterday Backtest Report sent to Telegram.")

if __name__ == "__main__":
    run_day_before_yesterday_backtest()
