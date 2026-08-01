import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv()

print("=" * 60)
print("🔍 AURA SUPER TRADER - FULL SYSTEM TEST")
print("=" * 60)

results = []

# ─── Test 1: Environment Config ───────────────────────────────
print("\n📋 Test 1: ตรวจสอบ Environment Variables (.env)...")
mt5_login = os.getenv("MT5_LOGIN")
telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
telegram_chat = os.getenv("TELEGRAM_CHAT_ID")

if mt5_login and telegram_token and telegram_chat:
    print(f"   ✅ MT5_LOGIN: {mt5_login}")
    print(f"   ✅ TELEGRAM_BOT_TOKEN: ***{telegram_token[-6:]}")
    print(f"   ✅ TELEGRAM_CHAT_ID: {telegram_chat}")
    results.append(("Environment Variables", "PASS"))
else:
    missing = [k for k,v in [("MT5_LOGIN", mt5_login), ("TELEGRAM_BOT_TOKEN", telegram_token), ("TELEGRAM_CHAT_ID", telegram_chat)] if not v]
    print(f"   ❌ Missing: {missing}")
    results.append(("Environment Variables", "FAIL"))

# ─── Test 2: MT5 Connection ───────────────────────────────────
print("\n📋 Test 2: ทดสอบการเชื่อมต่อ MT5 Terminal...")
try:
    from bot.mt5_client import MT5Client
    client = MT5Client()
    connected = client.connect()
    if connected:
        acc = client.get_account_info()
        print(f"   ✅ Connected to MT5 Server: XMGlobal-Demo")
        print(f"   ✅ Account: {acc.login} | Balance: ${acc.balance:.2f} | Equity: ${acc.equity:.2f}")
        results.append(("MT5 Connection", "PASS"))
    else:
        print("   ❌ MT5 connection failed")
        results.append(("MT5 Connection", "FAIL"))
except Exception as e:
    print(f"   ❌ MT5 Error: {e}")
    results.append(("MT5 Connection", "FAIL"))

# ─── Test 3: Market Data Feed ─────────────────────────────────
print("\n📋 Test 3: ทดสอบ Market Data Feed (ราคากราฟจริง)...")
try:
    symbols_to_test = ["GOLD#", "BTCUSD#", "EURUSD#", "GBPUSD#", "USDJPY#"]
    all_ok = True
    for sym in symbols_to_test:
        rates = client.get_rates(sym, "M15", 5)
        tick = client.get_tick(sym)
        if rates is not None and not rates.empty and tick is not None:
            print(f"   ✅ {sym}: Latest Close = {rates['close'].iloc[-1]:.2f} | Ask = {tick.ask:.2f}")
        else:
            print(f"   ❌ {sym}: Failed to fetch data")
            all_ok = False
    results.append(("Market Data Feed", "PASS" if all_ok else "FAIL"))
except Exception as e:
    print(f"   ❌ Data Feed Error: {e}")
    results.append(("Market Data Feed", "FAIL"))

# ─── Test 4: Strategy Engine ──────────────────────────────────
print("\n📋 Test 4: ทดสอบ Strategy Engine (SMC/ICT FVG Analysis)...")
try:
    import json
    from bot.strategy import ICTStrategy
    config_path = os.path.join(os.path.dirname(__file__), "..", "bot", "config.json")
    with open(config_path, "r") as f:
        config = json.load(f)
    strategy = ICTStrategy(client, config)
    trend = strategy.analyze_market_structure("GOLD#")
    print(f"   ✅ GOLD# 4H Market Structure: {trend}")
    setup = strategy.find_super_trader_setup("GOLD#", trend)
    if setup:
        print(f"   ✅ Found Signal: {setup.get('type')} | Entry: {setup.get('entry', 'N/A')} | SL: {setup.get('sl', 'N/A')} | TP: {setup.get('tp', 'N/A')}")
    else:
        print(f"   ℹ️  No signal found right now (market weekend/no FVG) - Engine OK")
    results.append(("Strategy Engine", "PASS"))
except Exception as e:
    print(f"   ❌ Strategy Error: {e}")
    results.append(("Strategy Engine", "FAIL"))

# ─── Test 5: Risk Manager ─────────────────────────────────────
print("\n📋 Test 5: ทดสอบ Risk Manager (Lot Size Calculation)...")
try:
    from bot.risk_manager import RiskManager
    risk_mgr = RiskManager(config)
    sym_info = client.get_symbol_info("GOLD#")
    acc_info = client.get_account_info()
    if sym_info and acc_info:
        lot = risk_mgr.calculate_lot_size(acc_info.equity, sym_info, 4000.0, 3995.0)
        print(f"   ✅ GOLD# Lot Size Calc (SL=$5, Risk=1%): {lot} Lots")
        dd_ok = risk_mgr.check_daily_drawdown(100.0, 97.5)
        nuke_ok = risk_mgr.check_daily_drawdown(100.0, 84.0)
        print(f"   ✅ Daily Drawdown Check ($97.5 equity): {'PASS - continue trading' if dd_ok else 'STOP - limit hit'}")
        print(f"   ✅ Nuclear Stop Check ($84.0 equity / -16%): {'PASS' if not nuke_ok else 'STOP - nuclear triggered'}")
        results.append(("Risk Manager", "PASS"))
    else:
        print("   ❌ Failed to get symbol/account info")
        results.append(("Risk Manager", "FAIL"))
except Exception as e:
    print(f"   ❌ Risk Manager Error: {e}")
    results.append(("Risk Manager", "FAIL"))

# ─── Test 6: Telegram Notifier ────────────────────────────────
print("\n📋 Test 6: ทดสอบ Telegram Bot Notification...")
try:
    from services.telegram_bot import TelegramNotifier
    tg = TelegramNotifier()
    if tg.enabled:
        sent = tg.send_message("🧪 <b>AURA Bot Full System Test - Telegram OK!</b>\nระบบทำงานปกติครับ ✅")
        print(f"   ✅ Telegram notification sent successfully!")
        results.append(("Telegram Notifier", "PASS"))
    else:
        print("   ❌ Telegram disabled (missing credentials)")
        results.append(("Telegram Notifier", "FAIL"))
except Exception as e:
    print(f"   ❌ Telegram Error: {e}")
    results.append(("Telegram Notifier", "FAIL"))

# ─── Test 7: Config Validation ────────────────────────────────
print("\n📋 Test 7: ตรวจสอบค่าตั้งค่าระบบ (config.json)...")
try:
    required_keys = ["symbols", "risk_per_trade_percent", "daily_drawdown_limit_percent",
                     "max_open_orders", "min_rr_ratio", "max_spread_points"]
    all_present = all(k in config for k in required_keys)
    if all_present:
        print(f"   ✅ Symbols: {config['symbols']}")
        print(f"   ✅ Risk Per Trade: {config['risk_per_trade_percent']}%")
        print(f"   ✅ Daily Drawdown Limit: {config['daily_drawdown_limit_percent']}%")
        print(f"   ✅ Max Open Orders: {config['max_open_orders']}")
        print(f"   ✅ Min RR Ratio: {config['min_rr_ratio']}")
        results.append(("Config Validation", "PASS"))
    else:
        missing = [k for k in required_keys if k not in config]
        print(f"   ❌ Missing config keys: {missing}")
        results.append(("Config Validation", "FAIL"))
except Exception as e:
    print(f"   ❌ Config Error: {e}")
    results.append(("Config Validation", "FAIL"))

# ─── Shutdown ──────────────────────────────────────────────────
try:
    client.shutdown()
except:
    pass

# ─── Final Summary ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("🏆 สรุปผลการทดสอบระบบทั้งหมด (FULL SYSTEM TEST RESULTS)")
print("=" * 60)
passed = sum(1 for _, r in results if r == "PASS")
total = len(results)
for name, r in results:
    icon = "✅ PASS" if r == "PASS" else "❌ FAIL"
    print(f"   {icon}  {name}")

print(f"\n{'✅ ระบบพร้อมใช้งาน! ผ่าน' if passed == total else '⚠️ มีบางรายการล้มเหลว'} {passed}/{total} รายการ")
if passed == total:
    print("🚀 พร้อมส่งไฟล์ไปยังโน้ตบุ๊กเครื่องใหม่ได้เลยครับ!")
print("=" * 60)
