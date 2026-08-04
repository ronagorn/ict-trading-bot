import os
import sys
import unittest
import json
from dotenv import load_dotenv

load_dotenv()

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

class SystemDiagnosticTestSuite(unittest.TestCase):

    def test_01_environment_config(self):
        """ตรวจสอบความถูกต้องของไฟล์ตั้งค่า"""
        print("\n🔍 Test 1: Validating Environment Configuration...")
        mt5_login = os.getenv("MT5_LOGIN")
        self.assertIsNotNone(mt5_login, "MT5_LOGIN is missing")
        self.assertNotEqual(mt5_login, "0", "MT5_LOGIN is 0 — check .env")
        print("  ✅ MT5 Login configured.")

        supabase_url = os.getenv("SUPABASE_URL")
        if supabase_url:
            print("  ✅ SUPABASE_URL configured.")
        else:
            print("  ⚠️  SUPABASE_URL not set (optional, skipping).")

        telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if telegram_token:
            print("  ✅ TELEGRAM_BOT_TOKEN configured.")
        else:
            print("  ⚠️  TELEGRAM_BOT_TOKEN not set (optional, skipping).")

    def test_02_mt5_connectivity(self):
        """ทดสอบการเชื่อมต่อและดึงราคากราฟจริงจาก MetaTrader 5"""
        print("\n🔍 Test 2: Testing MT5 Broker Connection & Data Feed...")
        import MetaTrader5 as mt5
        connected = mt5.initialize()
        self.assertTrue(connected, "Failed to connect to MT5 terminal")

        for sym in ["EURUSD", "BTCUSD#"]:
            rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 10)
            self.assertIsNotNone(rates, f"Failed to fetch {sym} candle rates")
            self.assertGreater(len(rates), 0, f"{sym} returned 0 candles")
            print(f"  ✅ {sym}: {len(rates)} candles fetched.")

        mt5.shutdown()
        print("  ✅ MT5 connection and data feed verified.")

    def test_03_super_trader_strategy_engine(self):
        """ทดสอบอัลกอริทึม Super Trader Strategy"""
        print("\n🔍 Test 3: Testing Super Trader Strategy Engine...")
        from bot.strategy import ICTStrategy
        from bot.mt5_client import MT5Client

        client = MT5Client()
        client.connect()

        config_path = os.path.join(os.path.dirname(__file__), "..", "bot", "config.json")
        with open(config_path, "r") as f:
            config = json.load(f)

        strategy = ICTStrategy(client, config)

        trend = strategy.analyze_market_structure("EURUSD")
        self.assertIn(trend, ["BULLISH", "BEARISH", "NEUTRAL"])
        print(f"  ✅ EURUSD Trend: {trend}")

        if trend != "NEUTRAL":
            setup = strategy.find_super_trader_setup("EURUSD", trend)
            if setup:
                self.assertIn("type", setup)
                self.assertIn("sl", setup)
                self.assertIn("tp", setup)
                print(f"  ✅ Setup found: {setup['type']} | SL={setup['sl']:.5f} | TP={setup['tp']:.5f}")

        client.shutdown()
        print("  ✅ Super Trader Engine executed cleanly.")

    def test_04_telegram_notifier(self):
        """ทดสอบระบบส่งสัญญาณแจ้งเตือน Telegram"""
        print("\n🔍 Test 4: Testing Telegram Bot Alert Engine...")
        telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not telegram_token:
            print("  ⚠️  TELEGRAM_BOT_TOKEN not set — skipping Telegram test.")
            return

        from services.telegram_bot import TelegramNotifier
        notifier = TelegramNotifier()
        self.assertTrue(notifier.enabled, "Telegram Notifier is disabled or missing credentials")
        print("  ✅ Telegram Bot Engine ready.")

if __name__ == "__main__":
    unittest.main()
