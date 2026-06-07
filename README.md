# Personal Data Bot — Nut Money Tracker

Telegram bot ที่บันทึกรายรับ-รายจ่าย → Google Sheets + AI query

## Setup

### 1. Google Sheet
- สร้าง Google Sheet ชื่อ "Personal Data"
- ชื่อ sheet แรก: `Transactions`
- Headers: `date | amount | type | category | merchant | note | raw_input`

### 2. Telegram Bot (BotFather)
- ไปที่ @BotFather ใน Telegram
- `/newbot` → ตั้งชื่อ + username
- Copy token

### 3. Google Service Account (for API)
- ไป https://console.cloud.google.com
- สร้าง service account
- Download credentials JSON
- Share Google Sheet กับ service account email

### 4. Railway Deploy
```bash
# Init repo
git init
git add .
git commit -m "init"

# Push to GitHub
git remote add origin https://github.com/YOUR_USERNAME/personal-data-bot.git
git push -u origin main

# Connect to Railway
# Go to railway.app → import GitHub repo
# ตั้ง env vars:
# - BOT_TOKEN
# - OPENROUTER_API_KEY
# - SHEET_ID
# - GOOGLE_CREDENTIALS_JSON (entire JSON as string)
```

### 5. Set Telegram Webhook
```bash
curl -X POST https://api.telegram.org/botBOT_TOKEN/setWebhook \
  -H "Content-Type: application/json" \
  -d '{"url":"https://YOUR_RAILWAY_URL/webhook"}'
```

## Usage

### Record Transaction
- `"กาแฟ 65"` → auto expense
- `"รับเงิน 5000"` → auto income
- `"ข้าว 80 ร้านแมว"` → with merchant
- Send receipt image → auto parse

### Query
- `"เดือนนี้จ่ายไปเท่าไหร่"` → monthly summary
- `"เทียบเดือนที่แล้ว"` → compare months
- `/help` → show commands

## Tech Stack
- Flask (webhook)
- OpenRouter API — model `deepseek/deepseek-v4-flash` (text + vision)
- Google Sheets API
- Railway (hosting)
