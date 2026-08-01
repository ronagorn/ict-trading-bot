import os
from supabase import create_client, Client
from bot.logger import logger

class SupabaseClient:
    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if url and key:
            self.client: Client = create_client(url, key)
            self.enabled = True
        else:
            logger.warning("Supabase credentials not found. DB logging disabled.")
            self.enabled = False

    def log_trade(self, ticket_id, symbol, trade_type, entry_time, entry_price, sl, tp, lot_size, fvg_size, session):
        """บันทึกออเดอร์ใหม่ลงฐานข้อมูล"""
        if not self.enabled: return False
        
        data = {
            "ticket_id": ticket_id,
            "symbol": symbol,
            "type": trade_type,
            "entry_time": entry_time.isoformat() if hasattr(entry_time, 'isoformat') else entry_time,
            "entry_price": entry_price,
            "sl": sl,
            "tp": tp,
            "lot_size": lot_size,
            "fvg_size": fvg_size,
            "session": session,
            "status": "OPEN",
            "profit_loss": 0.0
        }
        
        try:
            self.client.table("trades").insert(data).execute()
            logger.info(f"Trade {ticket_id} logged to Supabase.")
            return True
        except Exception as e:
            logger.error(f"Failed to log trade {ticket_id} to DB: {e}")
            return False

    def update_trade_close(self, ticket_id, close_time, profit_loss):
        """อัปเดตเมื่อออเดอร์ถูกปิด (เช็คกำไรขาดทุน)"""
        if not self.enabled: return False
        
        status = "WIN" if profit_loss > 0 else ("LOSS" if profit_loss < 0 else "BREAKEVEN")
        
        data = {
            "close_time": close_time.isoformat() if hasattr(close_time, 'isoformat') else close_time,
            "profit_loss": profit_loss,
            "status": status
        }
        
        try:
            self.client.table("trades").update(data).eq("ticket_id", ticket_id).execute()
            logger.info(f"Trade {ticket_id} close updated in Supabase.")
            return True
        except Exception as e:
            logger.error(f"Failed to update closed trade {ticket_id}: {e}")
            return False

    def get_recent_losing_trades(self, limit=50):
        """ดึงประวัติเทรดที่ขาดทุนล่าสุดเพื่อส่งให้ AI วิเคราะห์"""
        if not self.enabled: return []
        
        try:
            response = self.client.table("trades").select("*").eq("status", "LOSS").order("entry_time", desc=True).limit(limit).execute()
            return response.data
        except Exception as e:
            logger.error(f"Failed to fetch losing trades: {e}")
            return []
