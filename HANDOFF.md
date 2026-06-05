# Personal Data Bot — Handoff 2026-06-05

## สิ่งที่สร้าง

Telegram bot (@nut_money_bot) รับข้อความ/รูปสลิป → AI parse → เขียน Google Sheets

**Tech stack:**
- Flask webhook (gunicorn)
- OpenRouter API (anthropic/claude-haiku-4-5)
- Google Sheets API (service account)
- Deploy: Railway (https://personal-data-bot-production.up.railway.app)

---

## สถานะตอนนี้

| ส่วน | สถานะ |
|------|-------|
| Telegram webhook | ✅ ทำงาน |
| Bot ตอบกลับ | ✅ ทำงาน |
| OpenRouter parse | ✅ ทำงาน (ตอบ "2024-12-19 | -70 บาท | กาแฟ") |
| Google Sheets write | ❌ ยังไม่เขียน |

---

## ปัญหาที่เจอและแก้ไปแล้ว

### 1. `parser.py` ชนกับ Python built-in module
- **ปัญหา:** Python มี built-in module ชื่อ `parser` อยู่แล้ว → import ชนกัน → worker crash ทันที
- **แก้:** rename เป็น `transaction_parser.py`

### 2. Port ไม่ตรง → 502 Bad Gateway
- **ปัญหา:** hardcode `--bind 0.0.0.0:8000` แต่ Railway inject `$PORT` (8080) มาให้
- **แก้:** สร้าง `gunicorn_conf.py` ที่อ่าน `PORT` จาก `os.getenv()` แทน shell expansion (shell ใน railway.toml ไม่ expand `$PORT`)

### 3. OpenRouter URL ผิด domain
- **ปัญหา:** ใช้ `openrouter.io` → domain ไม่มี request ไม่ถึง API เลย error ว่างเปล่า
- **แก้:** เปลี่ยนเป็น `openrouter.ai`

### 4. GOOGLE_CREDENTIALS_JSON เพี้ยนตอน paste ใน Railway
- **ปัญหา:** JSON มี `\n` ใน private_key → Railway env var parse `\n` เป็น newline จริง → `json.loads()` พัง ที่ char 59
- **แก้:** encode เป็น base64 → ใส่ใน `GOOGLE_CREDENTIALS_B64` แทน → โค้ดอ่านแบบ base64 decode ก่อน

### 5. ❌ ยังไม่แก้: Google Sheets ไม่เขียน
- **สาเหตุที่สงสัย:** service account อาจยังไม่ได้รับสิทธิ์เป็น Editor ใน Google Sheet
- **ต้องทำต่อ:** ดู section "งานที่เหลือ" ด้านล่าง

---

## Environment Variables ที่ต้องมีใน Railway

| ชื่อ | ค่า |
|------|-----|
| `BOT_TOKEN` | ดูใน Railway Variables |
| `OPENROUTER_API_KEY` | ดูใน Railway Variables |
| `SHEET_ID` | ดูใน Railway Variables |
| `GOOGLE_CREDENTIALS_B64` | ดูใน Railway Variables |

> ⚠️ ลบ `GOOGLE_CREDENTIALS_JSON` ออกถ้ายังมีอยู่

---

## Files สำคัญ

```
personal-data-bot/
├── main.py                — Flask webhook handler
├── transaction_parser.py  — OpenRouter parse (text + vision)
├── sheets.py              — Google Sheets read/write
├── query.py               — monthly summary, comparison
├── gunicorn_conf.py       — อ่าน $PORT จาก Railway env
├── Dockerfile
├── railway.toml
└── .env                   — local only (gitignored)
```

---

## งานที่เหลือ (ต้องทำต่อ)

### ❌ Fix: Google Sheets ไม่เขียน

**สิ่งที่ต้องเช็ก:**

1. **ตรวจสอบว่า share Sheet ถูกต้องไหม**
   - ไปที่ Google Sheet "Personal Data"
   - กด Share
   - ต้องมี email: `personal-data-bot@nut-money-tracker.iam.gserviceaccount.com`
   - สิทธิ์ต้องเป็น **Editor**

2. **ดู Railway log หลังส่ง Telegram**
   - ควรเห็น `[sheets]` log
   - ถ้าเห็น `[sheets] credentials load error` → credentials ยังพัง
   - ถ้าเห็น `[sheets] ensure_tab error` → permission issue

3. **ตรวจสอบ tab ชื่อ**
   - โค้ดเขียนไป `Transactions!A:G`
   - Google Sheets อาจยังมีแค่ `Sheet1`
   - โค้ดล่าสุดมี `ensure_tab()` สร้างอัตโนมัติแล้ว (ถ้า credentials ผ่าน)

---

## Service Account Email

```
personal-data-bot@nut-money-tracker.iam.gserviceaccount.com
```

Sheet ต้อง share ให้ email นี้เป็น **Editor**

---

## Links

- GitHub: https://github.com/hoodey00-jpg/personal-data-bot
- Railway: https://railway.com/project/7bd7ae3c-dfbc-48ac-b2c9-c769b397d924
- Bot: @nut_money_bot
