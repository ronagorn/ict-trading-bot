import sys
sys.stdout.reconfigure(encoding='utf-8')
# 8-Pair Optimised Portfolio Backtest (no AUDUSD#, no USDCHF#)
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import json
import os
from dotenv import load_dotenv
from smartmoneyconcepts import smc
from bot.mt5_client import MT5Client
from services.telegram_bot import TelegramNotifier

load_dotenv()

def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    with open(config_path, "r") as f:
        return json.load(f)

def calculate_atr(df, period=14):
    high = df['high']
    low = df['low']
    close = df['close']
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean().bfill()

def run_portfolio_backtest(days=30):
    config = load_config()
    symbols = config.get("symbols", ["GOLD#", "BTCUSD#", "USDCAD#", "GBPUSD#", "EURUSD#"])
    label = f"{days} วัน ({days//30} เดือน)" if days < 365 else f"365 วัน (1 ปีเต็ม)"
    print(f"🚀 Starting Top-5 XM Portfolio Backtest ({label}) with Per-Symbol -3% Daily Cap...")
    
    client = MT5Client()
    if not client.connect():
        print("Failed to connect to MT5.")
        return

    bars_needed = days * 96
    results = {}
    total_wins = 0
    total_losses = 0
    total_net_profit = 0.0

    for symbol in symbols:
        print(f"⏳ Processing {symbol}...")
        mt5.symbol_select(symbol, True)
        rates_m15 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, bars_needed)
        rates_h4  = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H4,  0, 1000)

        if rates_m15 is None:
            print(f"  ❌ Failed to fetch data for {symbol}")
            continue

        df = pd.DataFrame(rates_m15)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df['date'] = df['time'].dt.date
        df.rename(columns={'tick_volume': 'volume'}, inplace=True)
        df['ema200'] = df['close'].ewm(span=200).mean()
        df['atr'] = calculate_atr(df, 14)

        # 4H HTF Shield — ใช้กับทุกคู่เงิน ไม่ใช่แค่ GOLD#
        mss_h4 = None
        df_h4 = None
        if rates_h4 is not None:
            df_h4 = pd.DataFrame(rates_h4)
            df_h4['time'] = pd.to_datetime(df_h4['time'], unit='s')
            df_h4.rename(columns={'tick_volume': 'volume'}, inplace=True)
            try:
                swing_h4 = smc.swing_highs_lows(df_h4)
                mss_h4 = smc.bos_choch(df_h4, swing_h4)
            except Exception:
                mss_h4 = None

        try:
            fvg_df = smc.fvg(df)
        except Exception as e:
            print(f"  ❌ SMC error for {symbol}: {e}")
            continue

        # จำลองทีละวัน บังคับ Per-Symbol -3% Cap
        days_covered = 0
        sym_wins = 0
        sym_losses = 0

        for date_val, group in df.groupby('date'):
            days_covered += 1
            day_pnl = 0.0
            day_stopped = False

            for i in group.index:
                if i < 200 or i >= len(df) - 30: continue
                if day_stopped: break

                c_close = df.loc[i, 'close']
                c_low   = df.loc[i, 'low']
                c_high  = df.loc[i, 'high']
                c_open  = df.loc[i, 'open']
                ema200  = df.loc[i, 'ema200']
                atr     = df.loc[i, 'atr']
                t_utc   = df.loc[i, 'time']

                m15_trend = 1 if c_close > ema200 else -1

                # 4H HTF Shield (ใช้กับทุกคู่เงิน)
                if mss_h4 is not None and df_h4 is not None:
                    slice_h4 = mss_h4[df_h4['time'] <= t_utc]
                    if slice_h4.empty: continue
                    v_bos   = slice_h4[slice_h4['BOS'].isin([1, -1])].tail(1)
                    v_choch = slice_h4[slice_h4['CHOCH'].isin([1, -1])].tail(1)
                    h4_trend = 0
                    if not v_bos.empty:
                        h4_trend = int(v_bos['BOS'].iloc[0])
                    if not v_choch.empty and (v_bos.empty or v_choch.index[0] > v_bos.index[0]):
                        h4_trend = int(v_choch['CHOCH'].iloc[0])
                    if h4_trend == 0 or h4_trend != m15_trend:
                        continue

                recent_fvg = fvg_df.iloc[i-5:i]
                if recent_fvg.empty: continue
                last_fvg = recent_fvg[recent_fvg['FVG'].notna()].tail(1)
                if last_fvg.empty: continue

                fvg_dir  = int(last_fvg['FVG'].iloc[0])
                fvg_top  = last_fvg['Top'].iloc[0]
                fvg_bot  = last_fvg['Bottom'].iloc[0]
                fvg_size = abs(fvg_top - fvg_bot)
                if fvg_size < (atr * 0.3): continue

                # BUY
                if fvg_dir == 1 and m15_trend == 1 and c_low <= fvg_top and c_high >= fvg_bot:
                    entry = fvg_top if c_open > fvg_top else c_open
                    sl = fvg_bot - (atr * 0.8)
                    risk = abs(entry - sl)
                    if risk == 0: continue
                    tp = entry + (risk * 1.5)
                    for m in range(i+1, min(i+50, len(df))):
                        if df.loc[m, 'low'] <= sl:
                            sym_losses += 1; day_pnl -= 1.0
                            if day_pnl <= -3.0: day_stopped = True
                            break
                        if df.loc[m, 'high'] >= tp:
                            sym_wins += 1; day_pnl += 1.5
                            break

                # SELL
                elif fvg_dir == -1 and m15_trend == -1 and c_high >= fvg_bot and c_low <= fvg_top:
                    entry = fvg_bot if c_open < fvg_bot else c_open
                    sl = fvg_top + (atr * 0.8)
                    risk = abs(sl - entry)
                    if risk == 0: continue
                    tp = entry - (risk * 1.5)
                    for m in range(i+1, min(i+50, len(df))):
                        if df.loc[m, 'high'] >= sl:
                            sym_losses += 1; day_pnl -= 1.0
                            if day_pnl <= -3.0: day_stopped = True
                            break
                        if df.loc[m, 'low'] <= tp:
                            sym_wins += 1; day_pnl += 1.5
                            break

        total = sym_wins + sym_losses
        wr = (sym_wins / total * 100) if total > 0 else 0
        net = (sym_wins * 1.5) - (sym_losses * 1.0)
        roi = (net / 100.0) * 100

        total_wins += sym_wins
        total_losses += sym_losses
        total_net_profit += net

        results[symbol] = {
            "days": days_covered,
            "total": total,
            "wins": sym_wins,
            "losses": sym_losses,
            "wr": f"{wr:.2f}%",
            "net": f"${net:.2f}",
            "roi": f"{roi:.2f}%"
        }

    client.shutdown()

    portfolio_total = total_wins + total_losses
    portfolio_wr    = (total_wins / portfolio_total * 100) if portfolio_total > 0 else 0
    portfolio_roi   = (total_net_profit / 100.0) * 100
    daily_trades    = portfolio_total / days

    report  = f"🔥 <b>TOP-5 XM PORTFOLIO BACKTEST ({label}) + 4H Shield ทุกคู่ + Per-Symbol -3% Cap</b>\n\n"
    for sym, r in results.items():
        report += f"<b>📌 {sym} ({r['days']} วัน)</b>: {r['total']} ไม้ | ชนะ: {r['wins']} | แพ้: {r['losses']} | WR: {r['wr']} | Net: {r['net']} ({r['roi']})\n"
    report += "\n----------------------------------------\n"
    report += f"🏆 <b>สรุปผลรวมพอร์ต Top-5 ({label}):</b>\n"
    report += f"🔹 ออเดอร์รวม: <b>{portfolio_total} ไม้ (~{daily_trades:.1f} ไม้/วัน)</b>\n"
    report += f"🔹 ชนะ: <b>{total_wins} ไม้</b> | แพ้: <b>{total_losses} ไม้</b>\n"
    report += f"🔹 <b>Win Rate รวม: {portfolio_wr:.2f}%</b>\n"
    report += f"💵 <b>กำไรสุทธิรวม (ทุน $100/คู่): ${total_net_profit:.2f} (ROI: {portfolio_roi:.2f}%)</b>\n"
    report += f"💵 <b>กำไรสุทธิรวม (ทุน $1,000/คู่): ${total_net_profit*10:.2f} (ROI: {portfolio_roi:.2f}%)</b>\n"

    print("\n" + report.replace('<b>', '').replace('</b>', ''))

    tg = TelegramNotifier()
    if tg.enabled:
        tg.send_message(report)
        print("Top-5 Portfolio Backtest sent to Telegram.")

if __name__ == "__main__":
    run_portfolio_backtest(30)
    run_portfolio_backtest(365)
