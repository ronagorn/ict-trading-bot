# 🌐 คู่มือการนำบอทขึ้น Render.com แบบทีละขั้นตอน (Step-by-step Render.com Guide)

ยินดีด้วยครับ! การเลือกย้ายระบบขึ้น **Render.com** จะช่วยให้บอทสแกนและส่งสัญญาณเทรดเข้า Telegram ได้ตลอด 24 ชั่วโมง โดยที่คุณ **ไม่ต้องเปิดคอมพิวเตอร์บ้านทิ้งไว้เลย 100%**

---

## 🛠️ สิ่งที่คุณต้องเตรียมก่อนเริ่ม (เตรียม 3 อย่าง)

1. **บัญชี GitHub (ฟรี)**: สมัครที่ [github.com](https://github.com)
2. **บัญชี Render.com (ฟรี)**: สมัครที่ [render.com](https://render.com) (แนะนำกด Sign up with GitHub)
3. **บัญชี MetaAPI (ฟรี)**: สมัครที่ [metaapi.cloud](https://metaapi.cloud)

---

## 🚀 ขั้นตอนการติดตั้งบน Render.com (4 ขั้นตอนง่ายๆ)

---

### ขั้นตอนที่ 1: ผูกบัญชี XM Demo เข้ากับ MetaAPI (รับ API Token)
1. เข้าเว็บ [metaapi.cloud](https://metaapi.cloud) ➔ ไปที่เมนู **Accounts** ➔ กด **Add Account**
2. เลือกประเภท: `MetaTrader 5`
3. กรอกข้อมูลบัญชี XM ของคุณ:
   - **Account name**: `XM Demo Bot`
   - **Login**: `108130219`
   - **Password**: (รหัสผ่านพอร์ต Demo ของคุณ)
   - **Server**: `XMGlobal-Demo` (หรือ Server จริงเมื่อต้องการเปลี่ยนเป็นพอร์ตจริง)
4. เมื่อผูกสำเร็จ ให้คัดลอกค่า 2 ตัวนี้ไว้:
   - **Account ID** (เช่น `a1b2c3d4-xxxx-xxxx`)
   - **Access Token** (คัดลอกได้จากเมนู API Access ด้านซ้าย)

---

### ขั้นตอนที่ 2: นำโค้ดโครงการขึ้น GitHub
1. เข้าไปที่ [github.com/new](https://github.com/new) ➔ สร้าง Repository ใหม่ชื่อ `ict-trading-bot`
2. เลือกตั้งค่าเป็น **Private** (เพื่อความปลอดภัยของรหัสผ่าน)
3. อัปโหลดไฟล์ทั้งหมดในโฟลเดอร์ `ict-trading-bot` ขึ้นไปยัง Repository บน GitHub

---

### ขั้นตอนที่ 3: เปิดใช้งาน Service บน Render.com
1. เข้าไปที่ [render.com](https://render.com) ➔ กดปุ่ม **New +** ที่มุมขวาบน ➔ เลือก **Background Worker**
2. เลือกเชื่อมต่อกับ Repository `ict-trading-bot` บน GitHub ที่สร้างไว้
3. ตั้งค่าระบบ:
   - **Name**: `aura-trading-bot`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python -m bot.main`
   - **Instance Type**: **Free Tier**

---

### ขั้นตอนที่ 4: ใส่รหัสผ่านใน Environment Variables บน Render.com
เลื่อนลงมาที่หัวข้อ **Environment Variables** กดปุ่ม **Add Environment Variable** ใส่ค่าดังนี้:

| Key | Value (ค่าที่ต้องใส่) |
| :--- | :--- |
| `MT5_LOGIN` | `108130219` |
| `MT5_PASSWORD` | (รหัสผ่านพอร์ต XM ของคุณ) |
| `MT5_SERVER` | `XMGlobal-Demo` |
| `TELEGRAM_BOT_TOKEN` | (Token บอท Telegram ของคุณ) |
| `TELEGRAM_CHAT_ID` | (ID แชท Telegram ของคุณ) |
| `METAAPI_TOKEN` | (Token จาก MetaAPI) |
| `METAAPI_ACCOUNT_ID` | (Account ID จาก MetaAPI) |

กดปุ่ม **Create Background Worker** ! 🚀

---

## ✅ สภาพหลังติดตั้งเสร็จสมบูรณ์

1. Render.com จะเริ่มดาวน์โหลดและรันบอทออนไลน์ให้อัตโนมัติทันที
2. บอทจะส่งข้อความแจ้งเตือนเข้า Telegram: `🚀 AURA Super Trader Bot Started`
3. **คุณสามารถกดปิดคอมพิวเตอร์บ้าน ปิดโน้ตบุ๊ก หรือปิดเน็ตได้เลย!**
4. บอทจะทำงานสแกนกราฟ XM และส่งสัญญาณแจ้งเตือนเข้า Telegram ของคุณตลอด 24 ชั่วโมงโดยไม่ต้องเปิดคอมเลยแม้แต่นาทีเดียวครับ!
