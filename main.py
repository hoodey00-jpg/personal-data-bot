import os
import json
import logging
from flask import Flask, request
from transaction_parser import parse_transaction
from sheets import write_transaction, query_transactions
from query import format_monthly_summary, format_comparison

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

@app.route("/webhook", methods=["POST"])
def webhook():
    """Telegram webhook handler"""
    data = request.get_json()

    if "message" not in data:
        return {"ok": True}

    message = data["message"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()
    photo = message.get("photo")

    try:
        # Query commands
        if text.lower().startswith("เดือน"):
            # "เดือนนี้จ่ายไปเท่าไหร่"
            transactions = query_transactions()
            response = format_monthly_summary(transactions)
            send_message(chat_id, response)

        elif text.lower().startswith("เทียบ"):
            # "เทียบเดือนที่แล้ว"
            transactions = query_transactions()
            response = format_comparison(transactions)
            send_message(chat_id, response)

        elif text.lower() == "chatid":
            send_message(chat_id, f"Your chat ID: {chat_id}")

        elif text.lower() == "help":
            help_text = """
📝 ใช้ให้คุ้มสุด:

💰 บันทึกรายจ่าย:
  "กาแฟ 65" → auto detect expense
  "รับเงิน 5000" → auto detect income
  "ข้าว 80 ร้านแมว"

📸 ส่งรูปสลิป → อ่านอัตโนมัติ

📊 ถามค่าใช้จ่าย:
  "เดือนนี้จ่ายไปเท่าไหร่"
  "เทียบเดือนที่แล้ว"
            """
            send_message(chat_id, help_text)

        elif photo:
            # Process image
            send_message(chat_id, "🔄 กำลังอ่านรูปสลิป...")

            file_id = photo[-1]["file_id"]
            file_path = get_file_path(file_id)

            if file_path:
                result = parse_transaction(file_path=file_path, is_image=True)
                if result:
                    write_transaction(result)
                    send_message(chat_id, f"✅ บันทึกเสร็จ\n{format_result(result)}")
                else:
                    send_message(chat_id, "❌ อ่านรูปไม่ได้ ลองใหม่หรือพิมพ์มือ")

        elif text:
            # Parse text transaction
            result = parse_transaction(text)
            if result:
                write_transaction(result)
                send_message(chat_id, f"✅ บันทึกเสร็จ\n{format_result(result)}")
            else:
                send_message(chat_id, "❌ Parse ไม่ได้ ลองใหม่เช่น 'กาแฟ 65'")

        else:
            send_message(chat_id, "พิมพ์ /help ดูวิธีใช้")

    except Exception as e:
        logger.error(f"Error: {e}")
        send_message(chat_id, f"❌ เกิดข้อผิดพลาด: {str(e)}")

    return {"ok": True}

def send_message(chat_id, text):
    """Send message to Telegram"""
    import requests
    requests.post(
        f"{TELEGRAM_API}/sendMessage",
        json={"chat_id": chat_id, "text": text}
    )

def get_file_path(file_id):
    """Get file path from Telegram"""
    import requests
    resp = requests.post(f"{TELEGRAM_API}/getFile", json={"file_id": file_id})
    if resp.status_code == 200:
        file_path = resp.json()["result"]["file_path"]
        return f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
    return None

def format_result(result):
    """Format transaction for display"""
    date = result.get("date", "?")
    amount = result.get("amount", "?")
    merchant = result.get("merchant", "-")
    return f"{date} | {amount} บาท | {merchant}"

@app.route("/health", methods=["GET"])
def health():
    """Health check"""
    return {"status": "ok"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
