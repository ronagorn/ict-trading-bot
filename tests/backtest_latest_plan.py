import sys
import os
sys.stdout.reconfigure(encoding='utf-8')

import json
import pandas as pd
import numpy as np
import MetaTrader5 as mt5
from datetime import datetime
from smartmoneyconcepts import smc

# เพิ่ม root dir ใน sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from services.telegram_bot import TelegramNotifier

def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "..", "bot", "config.json")
    with open(config_path, "r") as f:
        return json.load(f)

def calculate_atr(df, period=14):
    high = df['high']
    low = df['low']
    close = df['close']
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean().bfill()

def get_currencies(sym):
    s = sym.replace("#", "")
    if "GOLD" in s or "XAU" in s: return ["USD"]
    if "BTC" in s: return ["BTC"]
    if len(s) == 6: return [s[:3], s[3:]]
    return [s]

def run_latest_plan_backtest(days=30):
    config = load_config()
    symbols = config.get("symbols", ["GOLD#", "BTCUSD#", "EURUSD#", "GBPUSD#", "USDJPY#", "USDCAD#", "EURGBP#", "GBPJPY#"])
    
    label = f"{days} วัน (1 เดือน)" if days <= 31 else f"{days} วัน (1 ปีเต็ม)"
    print(f"\n==================================================================")
    print(f"🚀 Starting Fast Portfolio Backtest ({label})")
    print(f"   Config: Daily DD: 8%, Max Symbol: 2, Max Portfolio: 4, R:R 1:1.5")
    print(f"==================================================================")

    if not mt5.initialize():
        print("❌ Failed to initialize MT5")
        return

    bars_needed = days * 96  # 96 M15 bars per day
    data_dict = {}

    for sym in symbols:
        mt5.symbol_select(sym, True)
        rates_m15 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, bars_needed + 300)
        if rates_m15 is None or len(rates_m15) == 0:
            print(f"  ⚠️ Warning: No M15 data for {sym}")
            continue

        df = pd.DataFrame(rates_m15)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df['date'] = df['time'].dt.date
        df.rename(columns={'tick_volume': 'volume'}, inplace=True)
        df['ema200'] = df['close'].ewm(span=200).mean()
        df['atr'] = calculate_atr(df, 14)

        # 4H HTF Trend for GOLD#
        df_h4 = None
        mss_h4 = None
        if "GOLD" in sym:
            rates_h4 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H4, 0, (days // 4) * 6 + 200)
            if rates_h4 is not None and len(rates_h4) > 0:
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
        except Exception:
            fvg_df = pd.DataFrame()

        # Pre-process FVG numpy arrays for ultra-fast lookup
        fvg_dir = fvg_df['FVG'].to_numpy() if not fvg_df.empty and 'FVG' in fvg_df else np.full(len(df), np.nan)
        fvg_top = fvg_df['Top'].to_numpy() if not fvg_df.empty and 'Top' in fvg_df else np.full(len(df), np.nan)
        fvg_bot = fvg_df['Bottom'].to_numpy() if not fvg_df.empty and 'Bottom' in fvg_df else np.full(len(df), np.nan)

        data_dict[sym] = {
            "df": df,
            "time": df['time'].to_numpy(),
            "date": df['date'].to_numpy(),
            "open": df['open'].to_numpy(),
            "high": df['high'].to_numpy(),
            "low": df['low'].to_numpy(),
            "close": df['close'].to_numpy(),
            "ema200": df['ema200'].to_numpy(),
            "atr": df['atr'].to_numpy(),
            "fvg_dir": fvg_dir,
            "fvg_top": fvg_top,
            "fvg_bot": fvg_bot,
            "df_h4": df_h4,
            "mss_h4": mss_h4
        }

    mt5.shutdown()

    if not data_dict:
        print("❌ No data loaded.")
        return

    # Determine common backtest length
    min_len = min(len(v["open"]) for v in data_dict.values())
    start_idx = max(250, min_len - bars_needed)

    open_positions = []
    closed_trades = []
    
    initial_balance = 1000.0
    current_balance = initial_balance
    daily_start_balance = current_balance
    current_date = None
    daily_circuit_breaker = False

    for idx in range(start_idx, min_len):
        sample_sym = list(data_dict.keys())[0]
        bar_time = data_dict[sample_sym]["df"].loc[idx, "time"]
        bar_date = data_dict[sample_sym]["date"][idx]

        # Daily reset
        if bar_date != current_date:
            current_date = bar_date
            daily_start_balance = current_balance
            daily_circuit_breaker = False

        # 1. Update active positions & check TP/SL
        still_open = []
        for pos in open_positions:
            sym = pos["symbol"]
            d_sym = data_dict[sym]
            c_high = d_sym["high"][idx]
            c_low = d_sym["low"][idx]

            closed = False
            pnl_pct = 0.0

            if pos["type"] == "BUY":
                if c_low <= pos["sl"]:
                    pnl_pct = -1.0
                    closed = True
                    result = "SL"
                elif c_high >= pos["tp"]:
                    pnl_pct = 1.5
                    closed = True
                    result = "TP"
            else: # SELL
                if c_high >= pos["sl"]:
                    pnl_pct = -1.0
                    closed = True
                    result = "SL"
                elif c_low <= pos["tp"]:
                    pnl_pct = 1.5
                    closed = True
                    result = "TP"

            if closed:
                current_balance += (initial_balance * (pnl_pct / 100.0))
                closed_trades.append({
                    "symbol": sym,
                    "type": pos["type"],
                    "entry": pos["entry"],
                    "close_time": bar_time,
                    "pnl_pct": pnl_pct,
                    "result": result
                })
            else:
                still_open.append(pos)

        open_positions = still_open

        # 2. Check Daily Drawdown Limit (8%)
        floating_pnl_pct = 0.0
        for pos in open_positions:
            sym = pos["symbol"]
            c_close = data_dict[sym]["close"][idx]
            risk_dist = abs(pos["entry"] - pos["sl"])
            if risk_dist > 0:
                dist = (c_close - pos["entry"]) if pos["type"] == "BUY" else (pos["entry"] - c_close)
                floating_pnl_pct += (dist / risk_dist)

        current_equity = current_balance + (initial_balance * (floating_pnl_pct / 100.0))
        drawdown = ((daily_start_balance - current_equity) / daily_start_balance) * 100.0

        if drawdown >= 8.0:
            daily_circuit_breaker = True

        if daily_circuit_breaker:
            continue

        # 3. Check entry signals
        for sym, d in data_dict.items():
            if len(open_positions) >= 4:
                break

            sym_pos_count = sum(1 for p in open_positions if p["symbol"] == sym)
            if sym_pos_count >= 2:
                continue

            sym_curs = get_currencies(sym)
            currency_blocked = False
            for cur in sym_curs:
                same_cnt = sum(1 for p in open_positions if cur in get_currencies(p["symbol"]))
                if same_cnt >= 2:
                    currency_blocked = True
                    break
            if currency_blocked:
                continue

            c_close = d["close"][idx]
            c_open = d["open"][idx]
            c_high = d["high"][idx]
            c_low = d["low"][idx]
            ema200 = d["ema200"][idx]
            atr = d["atr"][idx]

            m15_trend = "BULLISH" if c_close > ema200 else "BEARISH"

            # GOLD 4H HTF Shield
            if "GOLD" in sym and d["mss_h4"] is not None and d["df_h4"] is not None:
                slice_h4 = d["mss_h4"][d["df_h4"]['time'] <= bar_time]
                if slice_h4.empty: continue
                v_bos = slice_h4[slice_h4['BOS'].isin([1, -1])].tail(1)
                v_choch = slice_h4[slice_h4['CHOCH'].isin([1, -1])].tail(1)
                h4_trend = "NEUTRAL"
                if not v_bos.empty: h4_trend = "BULLISH" if v_bos['BOS'].iloc[0] == 1 else "BEARISH"
                if not v_choch.empty and (v_bos.empty or v_choch.index[0] > v_bos.index[0]):
                    h4_trend = "BULLISH" if v_choch['CHOCH'].iloc[0] == 1 else "BEARISH"

                if h4_trend != m15_trend:
                    continue

            # FVG Check from pre-processed arrays
            sub_dir = d["fvg_dir"][max(0, idx-5):idx]
            valid_mask = ~np.isnan(sub_dir)
            if not np.any(valid_mask):
                continue

            last_valid_idx = max(0, idx-5) + np.where(valid_mask)[0][-1]
            last_fvg_dir = d["fvg_dir"][last_valid_idx]
            last_fvg_top = d["fvg_top"][last_valid_idx]
            last_fvg_bot = d["fvg_bot"][last_valid_idx]
            fvg_size = abs(last_fvg_top - last_fvg_bot)

            if fvg_size < (atr * 0.3):
                continue

            # BUY Signal
            if m15_trend == "BULLISH" and last_fvg_dir == 1 and c_close > ema200:
                if c_low <= last_fvg_top and c_high >= last_fvg_bot:
                    entry = last_fvg_top if c_open > last_fvg_top else c_open
                    sl = last_fvg_bot - (atr * 0.8)
                    risk = abs(entry - sl)
                    if risk > 0:
                        tp = entry + (risk * 1.5)
                        open_positions.append({
                            "symbol": sym,
                            "type": "BUY",
                            "entry": entry,
                            "sl": sl,
                            "tp": tp
                        })

            # SELL Signal
            elif m15_trend == "BEARISH" and last_fvg_dir == -1 and c_close < ema200:
                if c_high >= last_fvg_bot and c_low <= last_fvg_top:
                    entry = last_fvg_bot if c_open < last_fvg_bot else c_open
                    sl = last_fvg_top + (atr * 0.8)
                    risk = abs(sl - entry)
                    if risk > 0:
                        tp = entry - (risk * 1.5)
                        open_positions.append({
                            "symbol": sym,
                            "type": "SELL",
                            "entry": entry,
                            "sl": sl,
                            "tp": tp
                        })

    # Summary Stats
    total_trades = len(closed_trades)
    wins = sum(1 for t in closed_trades if t["pnl_pct"] > 0)
    losses = sum(1 for t in closed_trades if t["pnl_pct"] < 0)
    win_rate = (wins / total_trades * 100.0) if total_trades > 0 else 0.0
    net_pnl_dollar = current_balance - initial_balance
    roi = (net_pnl_dollar / initial_balance) * 100.0

    print(f"\n📊 --- BACKTEST REPORT ({label}) ---")
    print(f"  • ทุนเริ่มต้น: ${initial_balance:,.2f}")
    print(f"  • ยอดเงินสิ้นสุด: ${current_balance:,.2f}")
    print(f"  • กำไรสุทธิ (Net Profit): ${net_pnl_dollar:,.2f} ({roi:+.2f}%)")
    print(f"  • ออเดอร์ทั้งหมด: {total_trades} ไม้ (เฉลี่ย {total_trades/days:.1f} ไม้/วัน)")
    print(f"  • ชนะ (TP): {wins} ไม้")
    print(f"  • แพ้ (SL): {losses} ไม้")
    print(f"  • Win Rate: {win_rate:.2f}%")

    sym_stats = {}
    for t in closed_trades:
        s = t["symbol"]
        if s not in sym_stats:
            sym_stats[s] = {"wins": 0, "losses": 0, "pnl": 0.0}
        if t["pnl_pct"] > 0:
            sym_stats[s]["wins"] += 1
            sym_stats[s]["pnl"] += 1.5
        else:
            sym_stats[s]["losses"] += 1
            sym_stats[s]["pnl"] -= 1.0

    print("\n  📌 ผลตอบแทนแยกตามคู่เงิน:")
    for s, st in sym_stats.items():
        tot = st["wins"] + st["losses"]
        wr = (st["wins"] / tot * 100) if tot > 0 else 0
        print(f"    - {s:10s}: {tot:3d} ไม้ | TP: {st['wins']:2d} | SL: {st['losses']:2d} | WinRate: {wr:6.2f}% | PnL: {st['pnl']:+5.1f}%")

    # Telegram notification
    tg = TelegramNotifier()
    if tg.enabled:
        msg = f"🏆 <b>AURA BACKTEST REPORT — แผนล่าสุด ({label})</b>\n\n"
        msg += f"<b>ทุนเริ่มต้น:</b> ${initial_balance:,.2f}\n"
        msg += f"<b>ยอดเงินสิ้นสุด:</b> ${current_balance:,.2f}\n"
        msg += f"<b>กำไรสุทธิ (Net ROI):</b> <b>{roi:+.2f}% (${net_pnl_dollar:,.2f})</b>\n"
        msg += f"<b>ออเดอร์ทั้งหมด:</b> {total_trades} ไม้ (~{total_trades/days:.1f} ไม้/วัน)\n"
        msg += f"<b>Win Rate:</b> <b>{win_rate:.2f}%</b> (TP {wins} / SL {losses})\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"<b>รายละเอียดตามคู่เงิน:</b>\n"
        for s, st in sym_stats.items():
            tot = st["wins"] + st["losses"]
            wr = (st["wins"] / tot * 100) if tot > 0 else 0
            msg += f"• <b>{s}:</b> {tot} ไม้ | WR: {wr:.1f}% | PnL: {st['pnl']:+.1f}%\n"
        tg.send_message(msg)

if __name__ == "__main__":
    run_latest_plan_backtest(30)
    run_latest_plan_backtest(365)
