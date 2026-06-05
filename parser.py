import os
import json
import re
from datetime import datetime
import requests

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.io/api/v1/chat/completions"

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

    prompt = f"""
Parse Thai transaction: "{text}"

Return ONLY valid JSON (no markdown, no explanation):
{{
  "amount": number (positive for income, negative for expense),
  "type": "income" or "expense",
  "category": "food|transport|shopping|salary|other",
  "merchant": "string or null",
  "date": "YYYY-MM-DD",
  "note": "string or null"
}}

Rules:
- If amount has no sign, default to expense (negative)
- If text says "รับเงิน" or "เงินเดือน", it's income (positive)
- Detect category from merchant/context
- Use today's date if not specified
- merchant = ร้านชื่อหรือ null
- Keep note short, clear
- Return null for empty fields
"""

    try:
        response = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "HTTP-Referer": "personal-data-bot",
                "X-Title": "Personal Data Bot",
            },
            json={
                "model": "openrouter/auto",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
            },
        )

        if response.status_code != 200:
            print(f"OpenRouter error: {response.text}")
            return None

        result = response.json()
        content = result["choices"][0]["message"]["content"].strip()

        # Clean markdown if present
        if content.startswith("```"):
            content = content.split("```")[1].strip()
            if content.startswith("json"):
                content = content[4:].strip()

        data = json.loads(content)

        # Validate
        if not data.get("amount") or data.get("amount") == 0:
            return None

        return {
            "date": data.get("date", datetime.now().strftime("%Y-%m-%d")),
            "amount": data.get("amount"),
            "type": data.get("type", "expense"),
            "category": data.get("category", "other"),
            "merchant": data.get("merchant"),
            "note": data.get("note"),
            "raw_input": text,
        }

    except Exception as e:
        print(f"Parse error: {e}")
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

        prompt = """
Read this receipt image and extract:
- Total amount (ยอดรวม)
- Merchant/Shop name
- Date if visible
- Category (food, shopping, etc)

Return ONLY valid JSON:
{
  "amount": number,
  "type": "expense",
  "category": "string",
  "merchant": "string",
  "date": "YYYY-MM-DD",
  "note": "string or null"
}

If can't read, return null.
"""

        resp = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "HTTP-Referer": "personal-data-bot",
                "X-Title": "Personal Data Bot",
            },
            json={
                "model": "openrouter/auto",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt,
                            },
                            {
                                "type": "image",
                                "image": image_data,
                                "mimeType": "image/jpeg",
                            },
                        ],
                    }
                ],
                "temperature": 0.2,
            },
        )

        if resp.status_code != 200:
            return None

        result = resp.json()
        content = result["choices"][0]["message"]["content"].strip()

        if content.startswith("```"):
            content = content.split("```")[1].strip()
            if content.startswith("json"):
                content = content[4:].strip()

        data = json.loads(content)

        if not data.get("amount"):
            return None

        return {
            "date": data.get("date", datetime.now().strftime("%Y-%m-%d")),
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
