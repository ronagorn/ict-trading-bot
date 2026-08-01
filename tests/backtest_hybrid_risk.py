import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import date
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

def run_hybrid_backtest(days=365):
    """
    ระบบ Hybrid 2 ชั้น:
    ชั้นที่ 1 (Per-Symbol -3%): แต่ละคู่เงินหยุดเฉพาะตัวเมื่อขาดทุน -3% ต่อวัน
    ชั้นที่ 2 (Total Portfolio Nuclear Stop -15%): หากขาดทุนรวมทั้งพอร์ตใน 1 วันแตะ -15% หยุดทุกคู่ทันที
    """
    print(f"🚀 Running Hybrid 2-Layer Risk Backtest (365 Days - Real MT5 Data)...")
    print(f"   ชั้น 1: Per-Symbol Daily Cap = -3% ($3) per symbol")
    print(f"   ชั้น 2: Total Portfolio Nuclear Stop = -15% ($15) total per day\n")
    
    client = MT5Client()
    if not client.connect():
        print("Failed to connect to MT5.")
        return

    symbols = ["GOLD#", "BTCUSD#", "EURUSD#", "GBPUSD#", "USDJPY#",
               "AUDUSD#", "USDCAD#", "USDCHF#", "EURGBP#", "GBPJPY#"]
    bars_needed = days * 96

    # ดึงข้อมูลราคาทั้งหมดสำหรับทุกคู่เงินก่อน
    symbol_data = {}
    for symbol in symbols:
        mt5.symbol_select(symbol, True)
        rates_m15 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, bars_needed)
        rates_h4 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H4, 0, 1000)
        if rates_m15 is None:
            continue
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
            symbol_data[symbol] = (df, df_h4, mss_h4)
        else:
            symbol_data[symbol] = (df, None, None)

    client.shutdown()

    # รวบรวม trade signals ทั้งหมดแยกตามวันและคู่เงิน
    # โครงสร้าง: { date: { symbol: [(result, pnl), ...] } }
    all_dates = set()
    symbol_daily_trades = {s: {} for s in symbols}  # symbol -> {date -> [trades]}

    for symbol, (df, df_h4, mss_h4) in symbol_data.items():
        try:
            fvg_df = smc.fvg(df)
        except Exception:
            continue

        for i in range(200, len(df) - 30):
            c_close = df.loc[i, 'close']
            c_low = df.loc[i, 'low']
            c_high = df.loc[i, 'high']
            c_open = df.loc[i, 'open']
            ema200 = df.loc[i, 'ema200']
            atr = df.loc[i, 'atr']
            t_utc = df.loc[i, 'time']
            trade_date = df.loc[i, 'date']

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

            result = None
            if fvg_dir == 1 and m15_trend == 1 and c_low <= fvg_top and c_high >= fvg_bot:
                entry = fvg_top if c_open > fvg_top else c_open
                sl = fvg_bot - (atr * 0.8)
                risk = abs(entry - sl)
                if risk == 0: continue
                tp = entry + (risk * 1.5)
                for m in range(i+1, min(i+40, len(df))):
                    if df.loc[m, 'low'] <= sl:
                        result = ("LOSS", -1.0)
                        break
                    if df.loc[m, 'high'] >= tp:
                        result = ("WIN", 1.5)
                        break

            elif fvg_dir == -1 and m15_trend == -1 and c_high >= fvg_bot and c_low <= fvg_top:
                entry = fvg_bot if c_open < fvg_bot else c_open
                sl = fvg_top + (atr * 0.8)
                risk = abs(sl - entry)
                if risk == 0: continue
                tp = entry - (risk * 1.5)
                for m in range(i+1, min(i+40, len(df))):
                    if df.loc[m, 'high'] <= sl:
                        result = ("LOSS", -1.0)
                        break
                    if df.loc[m, 'low'] <= tp:
                        result = ("WIN", 1.5)
                        break

            if result:
                if trade_date not in symbol_daily_trades[symbol]:
                    symbol_daily_trades[symbol][trade_date] = []
                symbol_daily_trades[symbol][trade_date].append(result)
                all_dates.add(trade_date)

    # จำลองการเทรดจริงด้วยระบบ Hybrid 2 ชั้น
    sorted_dates = sorted(all_dates)
    total_portfolio_pnl = 0.0
    total_wins = 0
    total_losses = 0
    total_trades = 0
    nuclear_stop_days = []
    per_symbol_stop_days = {s: 0 for s in symbols}
    daily_pnl_log = []

    SYMBOL_CAP = -3.0    # ชั้นที่ 1: -3% ต่อคู่เงิน/วัน
    NUCLEAR_CAP = -15.0  # ชั้นที่ 2: -15% รวมทั้งพอร์ต/วัน

    for trade_date in sorted_dates:
        day_total_pnl = 0.0
        nuclear_triggered = False
        day_wins = 0
        day_losses = 0

        for symbol in symbols:
            if nuclear_triggered:
                break
            if trade_date not in symbol_daily_trades[symbol]:
                continue

            sym_day_pnl = 0.0
            sym_stopped = False

            for (outcome, pnl) in symbol_daily_trades[symbol][trade_date]:
                if sym_stopped or nuclear_triggered:
                    break
                # บันทึก trade
                sym_day_pnl += pnl
                day_total_pnl += pnl
                total_trades += 1
                if outcome == "WIN":
                    total_wins += 1
                    day_wins += 1
                else:
                    total_losses += 1
                    day_losses += 1

                # ชั้นที่ 1: Per-Symbol cap
                if sym_day_pnl <= SYMBOL_CAP:
                    per_symbol_stop_days[symbol] += 1
                    sym_stopped = True

                # ชั้นที่ 2: Nuclear stop
                if day_total_pnl <= NUCLEAR_CAP:
                    nuclear_triggered = True
                    nuclear_stop_days.append(str(trade_date))

        total_portfolio_pnl += day_total_pnl
        daily_pnl_log.append({
            "date": str(trade_date),
            "pnl": day_total_pnl,
            "wins": day_wins,
            "losses": day_losses,
            "nuclear": nuclear_triggered
        })

    winrate = (total_wins / total_trades * 100) if total_trades > 0 else 0.0
    roi = total_portfolio_pnl  # % บน $100 capital per pair

    # สรุปผล
    report = f"🔥 <b>HYBRID 2-LAYER RISK BACKTEST - 1 ปี (365 วัน / ข้อมูลจริง MT5)</b>\n\n"
    report += f"🛡️ <b>ระบบเกราะ 2 ชั้น:</b>\n"
    report += f"   ชั้น 1: หยุดรายคู่เงิน เมื่อแพ้ -3%/วัน\n"
    report += f"   ชั้น 2: Nuclear Stop หยุดทุกคู่ เมื่อพอร์ตรวมแพ้ -15%/วัน\n\n"
    report += f"📊 <b>ผลลัพธ์รวม 1 ปี (10 คู่เงิน XM):</b>\n"
    report += f"🔹 ออเดอร์เทรดรวมทั้งปี: <b>{total_trades} ไม้</b> (~{total_trades//365} ไม้/วัน)\n"
    report += f"🔹 ชนะรวม (TP 1:1.5): <b>{total_wins} ไม้</b> | แพ้รวม (SL): <b>{total_losses} ไม้</b>\n"
    report += f"🔹 <b>Win Rate รวม: {winrate:.2f}%</b>\n"
    report += f"💵 <b>กำไรสุทธิรวม (ทุน $100): ${total_portfolio_pnl:.2f} (ROI: {roi:.2f}%)</b>\n"
    report += f"💵 <b>กำไรสุทธิรวม (ทุน $1,000): ${total_portfolio_pnl*10:.2f} (ROI: {roi:.2f}%)</b>\n\n"
    report += f"🚨 <b>จำนวนวันที่โดน Nuclear Stop (-15% รวมทั้งพอร์ต):</b> <b>{len(nuclear_stop_days)} วัน ใน 1 ปี</b>\n"

    if nuclear_stop_days:
        report += f"   วันที่โดน Nuclear Stop: {', '.join(nuclear_stop_days[:10])}"
        if len(nuclear_stop_days) > 10:
            report += f"... (และอีก {len(nuclear_stop_days)-10} วัน)"
        report += "\n"

    top_blocked = sorted(per_symbol_stop_days.items(), key=lambda x: -x[1])
    report += f"\n📋 <b>จำนวนวันที่แต่ละคู่เงินถูกสั่งหยุดโดยระบบชั้น 1 (-3%/วัน):</b>\n"
    for sym, cnt in top_blocked:
        report += f"   {sym}: {cnt} วัน\n"

    print("\n" + report.replace('<b>', '').replace('</b>', ''))

    tg = TelegramNotifier()
    if tg.enabled:
        tg.send_message(report)
        print("Hybrid Backtest Report sent to Telegram.")

if __name__ == "__main__":
    run_hybrid_backtest(365)
