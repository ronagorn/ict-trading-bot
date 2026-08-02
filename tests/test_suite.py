import os
import sys
import unittest
from dotenv import load_dotenv

load_dotenv()

# เพิ่ม root dir ใน sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

class SystemDiagnosticTestSuite(unittest.TestCase):

    def test_01_environment_config(self):
        """ตรวจสอบความถูกต้องของไฟล์ตั้งค่าและ API Keys"""
        print("\n🔍 Test 1: Validating Environment Configuration...")
        supabase_url = os.getenv("SUPABASE_URL")
        telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        mt5_login = os.getenv("MT5_LOGIN")
        
        self.assertIsNotNone(supabase_url, "SUPABASE_URL is missing")
        self.assertIsNotNone(telegram_token, "TELEGRAM_BOT_TOKEN is missing")
        self.assertIsNotNone(mt5_login, "MT5_LOGIN is missing")
        print("  ✅ Environment & API Keys validated successfully.")

    def test_02_mt5_connectivity(self):
        """ทดสอบการเชื่อมต่อและดึงราคากราฟจริงจาก MetaTrader 5"""
        print("\n🔍 Test 2: Testing MT5 Broker Connection & Data Feed...")
        from bot.mt5_client import MT5Client
        client = MT5Client()
        connected = client.connect()
        self.assertTrue(connected, "Failed to connect to MT5 terminal")
        
        rates_gold = client.get_rates("GOLD#", "M15", 10)
        self.assertIsNotNone(rates_gold, "Failed to fetch GOLD# candle rates")
        self.assertFalse(rates_gold.empty, "GOLD# candles dataframe is empty")
        
        rates_btc = client.get_rates("BTCUSD#", "M15", 10)
        self.assertIsNotNone(rates_btc, "Failed to fetch BTCUSD# candle rates")
        self.assertFalse(rates_btc.empty, "BTCUSD# candles dataframe is empty")
        
        client.shutdown()
        print("  ✅ MT5 Terminal connection and tick data for GOLD# & BTCUSD# verified.")

    def test_03_super_trader_strategy_engine(self):
        """ทดสอบอัลกอริทึม Super Trader (RSI Divergence & Liquidity Sweep) ปราศจาก Crash/NaN"""
        print("\n🔍 Test 3: Testing Super Trader AI Strategy & Math Engine...")
        from bot.mt5_client import MT5Client
        from bot.strategy import ICTStrategy
        import json
        
        client = MT5Client()
        client.connect()
        
        config_path = os.path.join(os.path.dirname(__file__), "..", "bot", "config.json")
        with open(config_path, "r") as f:
            config = json.load(f)
            
        strategy = ICTStrategy(client, config)
        
        # ทดสอบวิเคราะห์โครงสร้างราคา H4/H1
        trend = strategy.analyze_market_structure("GOLD#")
        self.assertIn(trend, ["BULLISH", "BEARISH", "NEUTRAL"])
        
        # ทดสอบสแกนหาจุดเข้าเทรดสไนเปอร์
        setup = strategy.find_super_trader_setup("GOLD#", "BULLISH")
        if setup:
            self.assertIn("type", setup)
            self.assertIn("sl", setup)
            self.assertIn("tp", setup)
            
        client.shutdown()
        print(f"  ✅ Super Trader Engine executed cleanly. Detected Trend: {trend}")

    def test_04_telegram_notifier(self):
        """ทดสอบระบบส่งสัญญาณแจ้งเตือน Telegram"""
        print("\n🔍 Test 4: Testing Telegram Bot Alert Engine...")
        from services.telegram_bot import TelegramNotifier
        notifier = TelegramNotifier()
        self.assertTrue(notifier.enabled, "Telegram Notifier is disabled or missing credentials")
        print("  ✅ Telegram Bot Engine ready.")

if __name__ == "__main__":
    unittest.main()
