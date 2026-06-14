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
OPENROUTER_MODEL = "google/gemma-3-12b-it"


def _today_th():
    """Return today's date in Thailand timezone as YYYY-MM-DD."""
    return datetime.now(TH_TZ).strftime("%Y-%m-%d")

def _extract_json(content):
    """Extract and parse the first JSON object found in the model's reply."""
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in: {content[:200]}")
    return json.loads(match.group(0))

def _normalize_amount(data):
    """Make amount sign match type (type is the source of truth)."""
    amount = abs(data.get("amount") or 0)
    if data.get("type") == "income":
        return amount, "income"
    return -amount, "expense"

def _post_openrouter(messages, max_tokens, temperature, timeout):
    """Single OpenRouter chat call. Returns the message content string, or raises."""
    response = requests.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "HTTP-Referer": "https://personal-data-bot-production.up.railway.app",
            "X-Title": "Personal Data Bot",
        },
        json={
            "model": OPENROUTER_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=timeout,
    )
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:300]}")
    return response.json()["choices"][0]["message"]["content"].strip()


def record_from_data(data, raw_input):
    """Turn a parsed transaction dict into a normalized record, or None if invalid."""
    if not data or not data.get("amount") or data.get("amount") == 0:
        return None
    amount, tx_type = _normalize_amount(data)
    return {
        "date": data.get("date") or _today_th(),
        "amount": amount,
        "type": tx_type,
        "category": data.get("category", "other"),
        "merchant": data.get("merchant"),
        "note": data.get("note"),
        "raw_input": raw_input,
    }


def analyze_message(text):
    """Single LLM call that classifies intent AND parses a transaction if it's a save.

    Returns one of:
      {"kind": "save",    "transaction": {...}}   # parse a money entry
      {"kind": "query",   "transaction": None}    # any analytical question
      {"kind": "help",    "transaction": None}
      {"kind": "unknown", "transaction": None}
      {"kind": "api_error","transaction": None}   # only after retries fail
    """
    today = _today_th()
    prompt = f"""วันนี้คือวันที่ {today} (YYYY-MM-DD, เวลาประเทศไทย)

ข้อความจากผู้ใช้: "{text}"

งานของคุณ: จำแนกข้อความนี้ แล้วตอบเป็น JSON เท่านั้น (ห้ามมี markdown หรือคำอธิบาย)

ประเภท (kind):
- "save"  = บันทึกรายการเงิน เช่น "กาแฟ 65", "รับเงินเดือน 30000", "ข้าว 80 ร้านแมว"
- "query" = ถาม/ขอสรุป/วิเคราะห์ข้อมูลการเงิน เช่น "เดือนนี้ใช้ไปเท่าไหร่", "วันไหนใช้เยอะสุด", "ค่ากาแฟเดือนนี้กี่บาท", "เฉลี่ยวันละเท่าไหร่", "เทียบเดือนที่แล้ว", "สรุปวันนี้"
- "help"  = ขอวิธีใช้ เช่น "help", "ใช้ยังไง"
- "unknown" = ไม่เกี่ยวกับการเงินเลย

รูปแบบ JSON:
{{
  "kind": "save" | "query" | "help" | "unknown",
  "transaction": {{...}} หรือ null
}}

ถ้า kind = "save" เท่านั้น ให้ transaction เป็น:
{{
  "amount": ตัวเลขบวกเสมอ,
  "type": "income" หรือ "expense",
  "category": "food|transport|shopping|bills|entertainment|health|salary|other",
  "merchant": "สิ่งที่ซื้อหรือร้าน หรือ null",
  "date": "{today}",
  "note": "บันทึกสั้นๆ ภาษาไทย หรือ null"
}}

กฎสำหรับ save:
- ถ้ามีคำว่า "รับ", "ได้เงิน", "เงินเดือน", "โอนเข้า" = income, นอกนั้น = expense
- merchant = สิ่งที่ซื้อ เช่น "กาแฟ 65" -> "กาแฟ"
- ถ้า kind ไม่ใช่ save ให้ transaction = null"""

    for attempt in range(2):
        try:
            content = _post_openrouter(
                [{"role": "user", "content": prompt}],
                max_tokens=300, temperature=0.1, timeout=20,
            )
            data = _extract_json(content)
            kind = str(data.get("kind") or "").lower().strip()
            if kind not in {"save", "query", "help", "unknown"}:
                kind = "save"  # safest default: most messages are entries
            return {"kind": kind, "transaction": data.get("transaction")}
        except Exception as e:
            logger.warning(f"[analyze] error (attempt {attempt + 1}): {e}")
            continue
    return {"kind": "api_error", "transaction": None}


def answer_query(question, context):
    """Answer an analytical money question from pre-aggregated context (small JSON).
    Returns a Thai answer string, or None on failure."""
    today = _today_th()
    prompt = f"""วันนี้คือวันที่ {today} (เวลาประเทศไทย)

ผู้ใช้ถาม: "{question}"

ข้อมูลการเงินที่สรุปไว้แล้ว (หน่วย: บาท) เป็น JSON:
{json.dumps(context, ensure_ascii=False)}

ตอบคำถามของผู้ใช้จากข้อมูลนี้เท่านั้น เป็นภาษาไทย สั้น กระชับ ตรงคำถาม:
- ใช้เฉพาะตัวเลขที่อยู่ในข้อมูล ห้ามแต่งตัวเลขเอง
- ถ้าถาม "วันไหนใช้เยอะสุด" ให้ดู daily แล้วบอกวันที่ + จำนวนเงิน
- ถ้าถามหมวด/ร้าน ให้ดู by_category / by_merchant
- ใส่คอมมาในตัวเลข เช่น 1,234 บาท
- ถ้าข้อมูลไม่พอจะตอบ บอกตรงๆ ว่ายังไม่มีข้อมูล
- ตอบเป็นข้อความล้วน ไม่ต้องมี JSON หรือ markdown"""

    for attempt in range(2):
        try:
            return _post_openrouter(
                [{"role": "user", "content": prompt}],
                max_tokens=400, temperature=0.3, timeout=25,
            )
        except Exception as e:
            logger.warning(f"[answer] error (attempt {attempt + 1}): {e}")
            continue
    return None


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

    for attempt in range(2):
        try:
            response = requests.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "HTTP-Referer": "https://personal-data-bot-production.up.railway.app",
                    "X-Title": "Personal Data Bot",
                },
                json={
                    "model": OPENROUTER_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 300,
                },
                timeout=30,
            )

            logger.debug(f"[parser] Response status: {response.status_code}")

            if response.status_code != 200:
                logger.warning(f"[parser] OpenRouter HTTP {response.status_code}: {response.text[:300]}")
                continue

            result = response.json()
            content = result["choices"][0]["message"]["content"].strip()
            logger.debug(f"[parser] Content: {content}")

            data = _extract_json(content)

            if not data.get("amount") or data.get("amount") == 0:
                return None

            amount, tx_type = _normalize_amount(data)

            return {
                "date": data.get("date") or _today_th(),
                "amount": amount,
                "type": tx_type,
                "category": data.get("category", "other"),
                "merchant": data.get("merchant"),
                "note": data.get("note"),
                "raw_input": text,
            }

        except requests.exceptions.Timeout:
            logger.warning("[parser] OpenRouter timeout!")
            continue
        except Exception as e:
            logger.warning(f"[parser] Parse error (attempt {attempt + 1}): {e}")
            continue

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
                "model": OPENROUTER_MODEL,
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

        data = _extract_json(content)

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
