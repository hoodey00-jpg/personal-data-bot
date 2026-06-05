# Personal Data Bot — Handoff Document

> **เอกสารส่งต่อบริบท (Session Handoff)** — อ่านไฟล์นี้แล้วจะเข้าใจทั้งโปรเจกต์
> ทำถึงไหน ใช้วิธีอะไร อะไรเคยพัง และตอนนี้มีทรัพยากรอะไรบ้าง
>
> อัปเดตล่าสุด: 2026-06-05

---

## 1. ภาพรวมโปรเจกต์ (What & Why)

**เป้าหมาย:** ระบบเก็บข้อมูลส่วนตัวของนัท ที่ AI ตอบคำถามได้ เช่น "เดือนนี้จ่ายไปเท่าไหร่"
เริ่มจาก **Phase 1: รายรับ-รายจ่าย** ก่อน

**หลักการออกแบบ (สำคัญ — ตัดสินใจร่วมกับ user แล้ว):**
- **แยก store ตามธรรมชาติของข้อมูล** ไม่ยัดทุกอย่างที่เดียว
  - ตัวเลข/transaction → Google Sheets / DB
  - ความคิด/ไอเดีย/frame → LLM Wiki (markdown, มีอยู่แล้วที่ `THEALL Vault`)
  - health/habit → เพิ่มทีหลัง
- **AI เป็น router** ตัดสินว่าข้อมูลแต่ละชิ้นไปไหน — user แค่โยนข้อมูลเข้า
- โปรเจกต์นี้คือ store ตัวแรก (Financial) ของภาพใหญ่ที่ชื่อ **PAIOS (Personal AI OS)**

**User เป็นใคร:** นัท (hoodey00@gmail.com) — vibe coder, ไม่เขียนโค้ดเอง,
ให้ AI ทำทั้งหมด, สื่อสารภาษาไทยแบบปาก

**กฎเหล็ก (ห้ามละเมิด):**
- ❌ ห้ามเปิด repo หรือข้อมูลการเงินเป็น public เด็ดขาด
- ❌ ห้าม commit secrets (token/key/credentials) ลง git
- ✅ Vibe code เท่านั้น — AI ทำให้หมด ไม่โยนงานให้ user ทำเองใน browser/tool ภายนอกถ้าเลี่ยงได้

---

## 2. สถานะปัจจุบัน (Current State)

### ✅ ทำงานครบ end-to-end แล้ว

```
นัทพิมพ์ใน Telegram → webhook → AI parse → เขียน Google Sheets → ตอบกลับ
```

**ผลทดสอบจริง (2026-06-05) — ถูกต้องสมบูรณ์:**

| input | amount | type | category | merchant |
|-------|--------|------|----------|----------|
| กาแฟ 65 | -65 | expense | food | กาแฟ |
| ข้าวมันไก่ 50 ร้านป้าแดง | -50 | expense | food | ร้านป้าแดง |
| รับเงินเดือน 30000 | +30000 | income | salary | — |
| แท็กซี่ 120 | -120 | expense | transport | แท็กซี่ |

- ✅ date ถูกต้อง (timezone ไทย)
- ✅ แยก income/expense ถูก
- ✅ category + merchant ฉลาด
- ✅ note ภาษาไทย

### ⏳ ยังไม่ได้ทำ (Phase ถัดไป)
- **Query ผ่าน Telegram** — โค้ดมีแล้ว (`query.py`) แต่ยังไม่ได้เทสต์จริง
  ลองพิมพ์ "เดือนนี้จ่ายไปเท่าไหร่" / "เทียบเดือนที่แล้ว"
- **รูปสลิป (vision)** — โค้ดมีแล้ว แก้ format ถูกต้องแล้ว แต่ยังไม่ได้เทสต์ด้วยรูปจริง
- **Dashboard** — ยังไม่เริ่ม
- **เชื่อมกับ KBank Tracker** (โปรเจกต์เดิม ที่ `C:\Users\asus\Desktop\kbank-tracker`)
- **3 แถวขยะแรกใน Sheet** (date 2024, raw_input เป็น `?????`) — user จะลบเอง
  สาเหตุ: เกิดจาก AI เทสต์ผ่าน `curl` บน Windows shell ที่ทำให้ไทยเพี้ยน ไม่ใช่ bug ของ bot

---

## 3. สถาปัตยกรรม (Architecture)

```
┌─────────────┐   webhook    ┌──────────────────────┐
│  Telegram   │ ───────────> │  Flask app (Railway) │
│ @nut_money  │              │  main.py             │
│   _bot      │ <─────────── │   ├─ transaction_    │
└─────────────┘   ตอบกลับ     │   │   parser.py      │ ──> OpenRouter API
                              │   ├─ sheets.py       │ ──> Google Sheets
                              │   └─ query.py        │
                              └──────────────────────┘
```

**Stack:**
- **Web:** Flask + gunicorn
- **AI parse:** OpenRouter API, model `anthropic/claude-haiku-4-5` (text + vision)
- **Storage:** Google Sheets API (service account auth)
- **Hosting:** Railway (auto-deploy จาก GitHub push)

**Data flow ละเอียด:**
1. Telegram ส่ง webhook POST มาที่ `/webhook`
2. `main.py` แยกว่าเป็น text / photo / query command
3. `transaction_parser.py` ส่งข้อความ + วันที่ไทยวันนี้ ให้ OpenRouter → ได้ JSON
4. `sheets.py` เขียนลง tab `Transactions` (สร้าง tab + header อัตโนมัติถ้ายังไม่มี)
5. ตอบกลับ Telegram ว่าบันทึกแล้ว

---

## 4. ไฟล์สำคัญ (File Map)

```
personal-data-bot/
├── main.py                — Flask webhook, แยก text/photo/query, ส่ง Telegram
├── transaction_parser.py  — เรียก OpenRouter parse (มี _today_th() = วันที่ไทย)
├── sheets.py              — Google Sheets: ensure_tab/header, write, query
├── query.py               — สรุปรายเดือน, เทียบเดือน (ยังไม่เทสต์)
├── gunicorn_conf.py       — อ่าน PORT จาก env (Railway inject มา)
├── Dockerfile             — python:3.11-slim
├── railway.toml           — startCommand = gunicorn main:app -c gunicorn_conf.py
├── requirements.txt
├── .gitignore             — กัน .env, credentials.json ไม่ให้ขึ้น git
├── .env                   — secrets (local only, ห้าม commit)
└── HANDOFF.md             — ไฟล์นี้
```

---

## 5. บทเรียน: อะไรเคยพัง และแก้ยังไง (Failures & Fixes)

> ส่วนนี้สำคัญสุด — AI ตัวต่อไปจะได้ไม่พลาดซ้ำ

| # | อาการ | สาเหตุจริง | วิธีแก้ |
|---|-------|-----------|---------|
| 1 | worker crash ทันทีที่รับ request | ตั้งชื่อไฟล์ `parser.py` ชนกับ Python built-in module `parser` | rename เป็น `transaction_parser.py` |
| 2 | 502 Bad Gateway ทุก request | gunicorn bind port 8000 ตายตัว แต่ Railway route ไป `$PORT` (8080) | อ่าน PORT ผ่าน `gunicorn_conf.py` (Python `os.getenv`) แทน shell |
| 3 | `'$PORT' is not a valid port` | shell ใน railway.toml ไม่ expand `$PORT` ส่ง literal string | เลิกพึ่ง shell expand, ใช้ Python config file |
| 4 | parser error ว่างเปล่าตลอด | OpenRouter URL ผิด domain: `openrouter.io` (ที่ถูก `.ai`) | แก้เป็น `openrouter.ai` |
| 5 | `json.loads` พัง char 59 | paste credentials JSON ลง Railway env → `\n` ใน private_key เพี้ยน | encode เป็น **base64** ใส่ `GOOGLE_CREDENTIALS_B64` แทน |
| 6 | เขียน Sheets ไม่ได้ | ยังไม่ได้ share Sheet ให้ service account | share Sheet ให้ service-account email เป็น Editor |
| 7 | date เป็น 2024, category มั่ว | prompt ไม่ได้ส่งวันที่จริงเข้าไป model เดาเอง | ส่ง `_today_th()` เข้า prompt + เขียน prompt ไทยใหม่ |
| 8 | ไทยเป็น `?????` ใน Sheet | **ไม่ใช่ bug** — เกิดตอนเทสต์ผ่าน curl บน Windows shell | เทสต์ผ่าน UTF-8 จริง (urllib/Telegram) แทน |

**บทเรียนรวบยอด:**
- อย่าตั้งชื่อไฟล์ชนกับ stdlib (`parser`, `json`, `queue`, `code`, ...)
- Railway/PaaS ส่ง port มาทาง env เสมอ — อย่า hardcode
- secrets ที่มี newline → ใช้ base64 กันเพี้ยน
- เทสต์ภาษาไทยอย่าผ่าน Windows shell (curl) — ใช้ Python urllib ที่บังคับ UTF-8

---

## 6. ทรัพยากรที่มีตอนนี้ (Resources)

### Accounts / Services
| ทรัพยากร | รายละเอียด | secret อยู่ที่ไหน |
|----------|-----------|------------------|
| Telegram bot | @nut_money_bot | BOT_TOKEN ใน Railway |
| OpenRouter | model claude-haiku-4-5 | OPENROUTER_API_KEY ใน Railway |
| Google Cloud | project `nut-money-tracker`, service account | GOOGLE_CREDENTIALS_B64 ใน Railway |
| Google Sheet | "Personal Data", tab `Transactions` | SHEET_ID ใน Railway |
| Railway | auto-deploy จาก GitHub main | — |
| GitHub | hoodey00-jpg/personal-data-bot (private) | — |

### Service Account email (ต้อง share Sheet ให้)
```
personal-data-bot@nut-money-tracker.iam.gserviceaccount.com
```

### Environment Variables ที่ Railway ต้องมี
- `BOT_TOKEN`
- `OPENROUTER_API_KEY`
- `SHEET_ID`
- `GOOGLE_CREDENTIALS_B64`  (base64 ของ service account JSON — **ไม่ใช่** raw JSON)

> ค่าจริงทั้งหมดอยู่ในไฟล์ `.env` (local, gitignored) และใน Railway Variables
> **ห้าม** เขียนค่าจริงลงไฟล์ที่ commit ขึ้น git

### Schema ของ Sheet `Transactions`
```
date | amount | type | category | merchant | note | raw_input
```
- `amount`: บวก=รายรับ, ลบ=รายจ่าย
- `type`: income / expense
- `category`: food | transport | shopping | bills | entertainment | health | salary | other

---

## 7. งานถัดไปที่แนะนำ (Next Steps)

1. **เทสต์ query** — พิมพ์ "เดือนนี้จ่ายไปเท่าไหร่" ใน Telegram (โค้ดพร้อมแล้ว)
2. **เทสต์รูปสลิป** — ส่งรูปจริง ดูว่า vision parse ถูกไหม
3. **ลบ 3 แถวขยะ** ใน Sheet (user จะทำเอง)
4. **Dashboard** — Phase 2 (HTML + Chart.js แบบ KBank Tracker)
5. **เชื่อม store อื่น** — ตาม architecture ข้อ 1 (Knowledge → LLM Wiki)
6. **Ingest บทเรียนนี้** เข้า LLM Wiki ที่ `THEALL Vault` (decision: แยก store, AI router)

---

## 8. Links
- GitHub: https://github.com/hoodey00-jpg/personal-data-bot
- Railway: https://railway.com/project/7bd7ae3c-dfbc-48ac-b2c9-c769b397d924
- Bot: @nut_money_bot
- โปรเจกต์พี่น้อง: `C:\Users\asus\Desktop\kbank-tracker` (KBank email → Sheets)
- LLM Wiki: `C:\Users\asus\Desktop\TheAll\THEALL Vault`
