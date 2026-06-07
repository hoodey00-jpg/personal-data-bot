import os
import json
import re
from datetime import datetime, timezone, timedelta
import requests

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Thailand timezone (UTC+7), independent of server clock.
TH_TZ = timezone(timedelta(hours=7))


def _today_th():
    """Return today's date in Thailand timezone as YYYY-MM-DD."""
    return datetime.now(TH_TZ).strftime("%Y-%m-%d")

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

    try:
        print(f"[parser] Calling OpenRouter with key: {OPENROUTER_API_KEY[:20] if OPENROUTER_API_KEY else 'NONE'}...")
        response = requests.post(
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
                        "role": "system",
                        "content": 'แยกรายการเงินไทย → JSON: {"amount"(ลบ=จ่าย/บวก=รับ),"type"(income/expense),"category"(food/transport/shopping/bills/entertainment/health/salary/other),"merchant","date","note"} ไม่มี markdown. รับ/เงินเดือน/โอนเข้า=income อื่น=expense merchant=สิ่งที่ซื้อหรือร้าน',
                    },
                    {
                        "role": "user",
                        "content": f"{today} | {text}",
                    },
                ],
                "temperature": 0.3,
                "max_tokens": 300,
            },
            timeout=30,
        )

        print(f"[parser] Response status: {response.status_code}")
        print(f"[parser] Response body: {response.text[:500]}")

        if response.status_code != 200:
            print(f"[parser] OpenRouter HTTP {response.status_code}: {response.text[:300]}")
            return None

        result = response.json()
        content = result["choices"][0]["message"]["content"].strip()
        print(f"[parser] Content: {content}")

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
        print(f"[parser] OpenRouter timeout!")
        return None
    except Exception as e:
        import traceback
        print(f"[parser] Parse error: {e}")
        print(traceback.format_exc())
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
                        "role": "system",
                        "content": 'อ่านสลิป/ใบเสร็จ → JSON: {"amount","type":"expense","category"(food/transport/shopping/bills/entertainment/health/other),"merchant","date","note"} ไม่มี markdown. ถ้าอ่านไม่ออกตอบ null',
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"date={today}",
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_data}"
                                },
                            },
                        ],
                    },
                ],
                "temperature": 0.2,
                "max_tokens": 500,
            },
            timeout=60,
        )

        print(f"[parser-img] status: {resp.status_code}, body: {resp.text[:300]}")
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
        print(f"Image parse error: {e}")
        return None
