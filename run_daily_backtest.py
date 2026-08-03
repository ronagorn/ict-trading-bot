import sys
import os
from datetime import datetime, timedelta

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

import MetaTrader5 as mt5
import pandas as pd
from dotenv import load_dotenv
from bot.mt5_client import MT5Client
from services.telegram_bot import TelegramNotifier

load_dotenv()

def run_daily_backtest_report(days=1):
    print("=========================================================================")
    print(f"📊 Running On-Demand Daily Performance Backtest ({days} Day Report)")
    print("=========================================================================")
    
    client = MT5Client()
    if not client.connect():
        print("❌ Failed to connect to MT5.")
        return
        
    symbols = ["GOLD#", "BTCUSD#", "EURUSD#", "GBPUSD#", "USDJPY#"]
    tg = TelegramNotifier()
    
    total_trades = 0
    total_wins = 0
    total_losses = 0
    total_pnl = 0.0
    
    from_time = datetime.now() - timedelta(days=days)
    deals = mt5.history_deals_get(from_time, datetime.now())
    
    report_lines = []
    if deals:
        trades_dict = {}
        for d in deals:
            if not d.symbol: continue
            pos_id = d.position_id
            if pos_id not in trades_dict:
                trades_dict[pos_id] = {'symbol': d.symbol, 'pnl': 0.0, 'type': 'BUY' if d.type==0 else 'SELL'}
            trades_dict[pos_id]['pnl'] += d.profit
            
        for pos_id, tdata in trades_dict.items():
            pnl = tdata['pnl']
            total_trades += 1
            if pnl > 0:
                total_wins += 1
            elif pnl < 0:
                total_losses += 1
            total_pnl += pnl
            report_lines.append(f"• #{pos_id} {tdata['symbol']} ({tdata['type']}): {'+$' if pnl>=0 else '-$'}{abs(pnl):.2f}")

    win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0
    
    acc_info = client.get_account_info()
    balance = acc_info.balance if acc_info else 0
    equity = acc_info.equity if acc_info else 0

    report_text = (
        f"📊 <b>AURA Daily Backtest & Performance Summary ({days} Day)</b>\n"
        f"--------------------------------------------------\n"
        f"• <b>Total Trades:</b> {total_trades} ไม้\n"
        f"• <b>Win / Loss:</b> 🟢 {total_wins} / 🔴 {total_losses}\n"
        f"• <b>Win Rate:</b> {win_rate:.1f}%\n"
        f"• <b>Net P/L:</b> {'+$' if total_pnl >= 0 else '-$'}{abs(total_pnl):.2f}\n"
        f"--------------------------------------------------\n"
        f"💰 <b>Current Balance:</b> ${balance:,.2f}\n"
        f"📈 <b>Current Equity:</b> ${equity:,.2f}\n"
    )
    
    print("\n" + report_text.replace("<b>", "").replace("</b>", ""))
    
    if tg.enabled:
        tg.send_message(report_text)
        print("✅ Report sent to Telegram successfully!")
        
    client.disconnect()

if __name__ == "__main__":
    run_daily_backtest_report(1)
