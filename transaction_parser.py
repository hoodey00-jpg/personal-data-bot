import os
import json
import re
import logging
from datetime import datetime
import requests
from tz import TH_TZ

logger = logging.getLogger(__name__)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def _today_th():
    """Return today's date in Thailand timezone as YYYY-MM-DD."""
    return datetime.now(TH_TZ).strftime("%Y-%m-%d")

def classify_intent(text):
    """Classify user message intent. Returns one of:
    query_today | query_month | query_compare | save_transaction | help | unknown | api_error
    """
    prompt = f"""จำแนกความตั้งใจของข้อความภาษาไทยนี้: "{text}"

ตอบด้วย label เดียวเท่านั้น (ห้ามมีคำอื่น):
- query_today  → ถามยอดวันนี้ เช่น "วันนี้ใช้ไปเท่าไหร่" "สรุปวันนี้" "ใช้เงินไปกี่บาทแล้ว"
- query_month  → ถามยอดเดือนนี้ เช่น "เดือนนี้จ่ายไปเท่าไหร่" "สรุปเดือนนี้" "ค่าใช้จ่ายเดือนนี้"
- query_compare → เปรียบเทียบเดือน เช่น "เทียบเดือนที่แล้ว" "เดือนนี้กับเดือนก่อน"
- save_transaction → บันทึกรายการเงิน เช่น "กาแฟ 65" "รับเงินเดือน 30000" "ข้าว 80"
- help → ขอความช่วยเหลือ เช่น "help" "วิธีใช้" "ใช้ยังไง"
- unknown → ไม่ตรงกับอะไรข้างบน"""

    try:
        response = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "HTTP-Referer": "https://personal-data-bot-production.up.railway.app",
                "X-Title": "Personal Data Bot",
            },
            json={
                "model": "deepseek/deepseek-v4-flash",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 20,
            },
            timeout=15,
        )
        if response.status_code != 200:
            return "api_error"
        content = response.json()["choices"][0]["message"]["content"].strip().lower()
        valid = {"query_today", "query_month", "query_compare", "save_transaction", "help", "unknown"}
        for label in valid:
            if label in content:
                return label
        return "save_transaction"
    except Exception:
        return "api_error"


def parse_transaction(text=None, file_path=None, is_image=False):
    """
    Parse transaction from text or image
    Returns: {date, amount, type, category, merchant, note}
    """
    if is_image and file_path:
        return parse_image(file_path)
    else:
        return parse_text(text)

def parse_text(text):
    """Parse text like '80 ข้าว' or 'รับเงิน 5000'"""
    if not text or len(text.strip()) < 2:
        return None

    today = _today_th()

    prompt = f"""วันนี้คือวันที่ {today} (รูปแบบ YYYY-MM-DD, เวลาประเทศไทย)

แยกรายการเงินจากข้อความภาษาไทยนี้: "{text}"

ตอบกลับเป็น JSON เท่านั้น ไม่ต้องมี markdown หรือคำอธิบาย:
{{
  "amount": ตัวเลข (บวกถ้ารายรับ, ลบถ้ารายจ่าย),
  "type": "income" หรือ "expense",
  "category": "food|transport|shopping|bills|entertainment|health|salary|other",
  "merchant": "ชื่อสิ่งที่ซื้อหรือร้าน หรือ null",
  "date": "{today}",
  "note": "บันทึกสั้นๆ เป็นภาษาไทย หรือ null"
}}

กฎ:
- ถ้าไม่ระบุเครื่องหมาย ให้ถือเป็นรายจ่าย (amount เป็นลบ)
- ถ้ามีคำว่า "รับ", "ได้เงิน", "เงินเดือน", "โอนเข้า" = รายรับ (amount เป็นบวก)
- merchant = สิ่งที่ซื้อ เช่น "กาแฟ 65" -> merchant คือ "กาแฟ"
- เดา category จากบริบท เช่น กาแฟ/ข้าว = food, แท็กซี่/รถเมล์ = transport
- date ใช้ {today} เสมอ (เว้นแต่ข้อความระบุวันอื่นชัดเจน)
- note สรุปสั้นๆ เป็นภาษาไทย
"""

    try:
        response = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "HTTP-Referer": "https://personal-data-bot-production.up.railway.app",
                "X-Title": "Personal Data Bot",
            },
            json={
                "model": "deepseek/deepseek-v4-flash",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 300,
            },
            timeout=30,
        )

        logger.debug(f"[parser] Response status: {response.status_code}")

        if response.status_code != 200:
            logger.warning(f"[parser] OpenRouter HTTP {response.status_code}: {response.text[:300]}")
            return None

        result = response.json()
        content = result["choices"][0]["message"]["content"].strip()
        logger.debug(f"[parser] Content: {content}")

        # Clean markdown if present
        if "```" in content:
            content = content.split("```")[1].strip()
            if content.startswith("json"):
                content = content[4:].strip()

        data = json.loads(content)

        if not data.get("amount") or data.get("amount") == 0:
            return None

        return {
            "date": data.get("date") or _today_th(),
            "amount": data.get("amount"),
            "type": data.get("type", "expense"),
            "category": data.get("category", "other"),
            "merchant": data.get("merchant"),
            "note": data.get("note"),
            "raw_input": text,
        }

    except requests.exceptions.Timeout:
        logger.warning("[parser] OpenRouter timeout!")
        return None
    except Exception as e:
        logger.exception(f"[parser] Parse error: {e}")
        return None

def parse_image(file_path):
    """Parse receipt image using vision model"""
    try:
        # Download image
        response = requests.get(file_path)
        if response.status_code != 200:
            return None

        import base64
        image_data = base64.b64encode(response.content).decode()
        today = _today_th()

        prompt = f"""วันนี้คือวันที่ {today} (YYYY-MM-DD, เวลาประเทศไทย)

อ่านสลิป/ใบเสร็จในรูปนี้ แล้วดึงข้อมูล:
- ยอดเงินรวม (total)
- ชื่อร้าน/ผู้รับเงิน
- วันที่ในสลิป (ถ้าไม่เห็นชัด ใช้ {today})
- ประเภท (food, shopping, transport, bills ฯลฯ)

ตอบเป็น JSON เท่านั้น ไม่ต้องมี markdown:
{{
  "amount": ตัวเลข,
  "type": "expense",
  "category": "food|transport|shopping|bills|entertainment|health|other",
  "merchant": "ชื่อร้าน",
  "date": "{today}",
  "note": "บันทึกสั้นๆ เป็นภาษาไทย หรือ null"
}}

ถ้าอ่านไม่ออก ตอบ null
"""

        resp = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "HTTP-Referer": "https://personal-data-bot-production.up.railway.app",
                "X-Title": "Personal Data Bot",
            },
            json={
                "model": "deepseek/deepseek-v4-flash",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt,
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_data}"
                                },
                            },
                        ],
                    }
                ],
                "temperature": 0.2,
                "max_tokens": 500,
            },
            timeout=60,
        )

        logger.debug(f"[parser-img] status: {resp.status_code}")
        if resp.status_code != 200:
            return None

        result = resp.json()
        content = result["choices"][0]["message"]["content"].strip()

        if "```" in content:
            content = content.split("```")[1].strip()
            if content.startswith("json"):
                content = content[4:].strip()

        data = json.loads(content)

        if not data.get("amount"):
            return None

        return {
            "date": data.get("date") or today,
            "amount": -abs(data.get("amount")),
            "type": "expense",
            "category": data.get("category", "other"),
            "merchant": data.get("merchant"),
            "note": data.get("note"),
            "raw_input": "[receipt image]",
        }

    except Exception as e:
        logger.exception(f"Image parse error: {e}")
        return None
