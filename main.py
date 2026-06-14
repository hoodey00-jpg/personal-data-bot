import os
import json
import logging
from flask import Flask, request
from transaction_parser import (
    parse_transaction,
    analyze_message,
    answer_query,
    record_from_data,
)
from sheets import write_transaction, query_transactions
from query import build_query_context

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
        if text.lower() == "chatid":
            send_message(chat_id, f"Your chat ID: {chat_id}")

        elif photo:
            send_message(chat_id, "🔄 กำลังอ่านรูปสลิป...")
            file_id = photo[-1]["file_id"]
            file_path = get_file_path(file_id)
            if file_path:
                result = parse_transaction(file_path=file_path, is_image=True)
                if result:
                    if write_transaction(result):
                        send_message(chat_id, f"✅ บันทึกเสร็จ\n{format_result(result)}")
                    else:
                        send_message(chat_id, "❌ บันทึกลง Sheet ไม่สำเร็จ ลองใหม่อีกครั้ง")
                else:
                    send_message(chat_id, "❌ อ่านรูปไม่ได้ ลองใหม่หรือพิมพ์มือ")

        elif text:
            analysis = analyze_message(text)
            kind = analysis["kind"]
            logger.info(f"[analyze] '{text}' → {kind}")

            if kind == "save":
                # transaction was parsed in the same call; fall back to a
                # dedicated parse only if the merged parse came back empty.
                result = record_from_data(analysis.get("transaction"), text)
                if not result:
                    result = parse_transaction(text)
                if result:
                    if write_transaction(result):
                        send_message(chat_id, f"✅ บันทึกเสร็จ\n{format_result(result)}")
                    else:
                        send_message(chat_id, "❌ บันทึกลง Sheet ไม่สำเร็จ ลองใหม่อีกครั้ง")
                else:
                    send_message(chat_id, "❌ ไม่เข้าใจ ลองใหม่เช่น 'กาแฟ 65' หรือ 'รับเงิน 5000'")

            elif kind == "query":
                transactions = query_transactions()
                context = build_query_context(transactions)
                answer = answer_query(text, context)
                if answer:
                    send_message(chat_id, answer)
                else:
                    send_message(chat_id, "🤖 ระบบ AI ขัดข้องชั่วคราว ลองพิมพ์ใหม่อีกครั้งใน 1 นาที")

            elif kind == "help":
                send_message(chat_id, (
                    "📝 บันทึกรายการ:\n"
                    "  \"กาแฟ 65\" → รายจ่าย\n"
                    "  \"รับเงิน 5000\" → รายรับ\n"
                    "  \"ข้าว 80 ร้านแมว\"\n\n"
                    "📸 ส่งรูปสลิป → อ่านอัตโนมัติ\n\n"
                    "📊 ถามได้เลยภาษาพูด:\n"
                    "  \"วันนี้ใช้เงินไปเท่าไหร่\"\n"
                    "  \"เดือนนี้วันไหนใช้เยอะสุด\"\n"
                    "  \"ค่ากาแฟเดือนนี้กี่บาท\"\n"
                    "  \"เทียบเดือนที่แล้ว\""
                ))

            elif kind == "api_error":
                send_message(chat_id, "🤖 ระบบ AI ขัดข้องชั่วคราว ลองพิมพ์ใหม่อีกครั้งใน 1 นาที")

            else:  # unknown
                send_message(chat_id, "❓ ไม่เข้าใจ ลองพิมพ์ help ดูวิธีใช้")

        else:
            send_message(chat_id, "พิมพ์ help ดูวิธีใช้")

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
