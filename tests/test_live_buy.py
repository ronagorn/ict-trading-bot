import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv()

from bot.mt5_client import MT5Client
from bot.risk_manager import RiskManager
from services.telegram_bot import TelegramNotifier
import json

def run_test_buy():
    print("🚀 Initiating Test Demo BUY Order Demonstration...")
    tg = TelegramNotifier()
    client = MT5Client(tg)
    
    if not client.connect():
        print("❌ Failed to connect to MT5.")
        return
        
    config_path = os.path.join(os.path.dirname(__file__), "..", "bot", "config.json")
    with open(config_path, "r") as f:
        config = json.load(f)
        
    risk_mgr = RiskManager(config)
    symbol = "GOLD#"
    
    # 1. Fetch current price
    tick = client.get_tick(symbol)
    sym_info = client.get_symbol_info(symbol)
    acc_info = client.get_account_info()
    
    if not tick or not sym_info or not acc_info:
        print(f"❌ Failed to fetch market info for {symbol}")
        client.shutdown()
        return

    entry_price = tick.ask
    # SL 5.00 dollars below, TP 7.50 dollars above (RR 1:1.5)
    sl_price = entry_price - 5.00
    tp_price = entry_price + 7.50
    
    # 2. Calculate Lot Size based on Risk Manager (1% risk of account equity)
    lot_size = risk_mgr.calculate_lot_size(acc_info.equity, sym_info, entry_price, sl_price)
    if lot_size <= 0:
        lot_size = sym_info.volume_min # Default to 0.01 min volume
        
    print(f"📊 Market Info for {symbol}:")
    print(f"  - Account Equity: ${acc_info.equity:.2f}")
    print(f"  - Account Balance: ${acc_info.balance:.2f}")
    print(f"  - Risk Setting: {config.get('risk_per_trade_percent', 1.0)}% per trade")
    print(f"  - Current Ask Price: ${entry_price:.2f}")
    print(f"  - Proposed Stop Loss: ${sl_price:.2f}")
    print(f"  - Proposed Take Profit: ${tp_price:.2f}")
    print(f"  - Calculated Lot Size: {lot_size} Lots")

    # 3. Execute Trade on MT5
    print("\n💥 Placing test BUY order on MT5 Demo Account...")
    ticket = client.place_order(symbol, "BUY", lot_size, entry_price, sl_price, tp_price, comment="Demo_Test_Order")
    
    if ticket:
        print(f"✅ Success! Ticket #{ticket} placed on MT5 Demo!")
        
        # Send Telegram notification
        msg = f"🧪 <b>DEMO TEST ORDER EXECUTED</b>\n\n"
        msg += f"<b>Ticket:</b> #{ticket}\n"
        msg += f"<b>Symbol:</b> {symbol}\n"
        msg += f"<b>Type:</b> BUY\n"
        msg += f"<b>Entry Price:</b> {entry_price:.2f}\n"
        msg += f"<b>Stop Loss (SL):</b> {sl_price:.2f}\n"
        msg += f"<b>Take Profit (TP):</b> {tp_price:.2f}\n"
        msg += f"<b>Lot Size:</b> {lot_size} Lots\n"
        msg += f"<b>Account Balance:</b> ${acc_info.balance:.2f}\n"
        
        if tg.enabled:
            tg.send_message(msg)
            print("📩 Telegram Notification sent!")
    else:
        print("❌ Order placement failed. Please check MT5 trading status or market hours.")
        
    client.shutdown()

if __name__ == "__main__":
    run_test_buy()
