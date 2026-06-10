import os
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from datetime import datetime, timedelta

SHEET_ID = os.getenv("SHEET_ID")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

def get_sheets_service():
    """Get Google Sheets API service"""
    import json
    import base64

    creds = None

    # Preferred: base64-encoded JSON (avoids newline/quote corruption when
    # pasting the service-account key into Railway env vars).
    creds_b64 = os.getenv("GOOGLE_CREDENTIALS_B64")
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")

    try:
        if creds_b64:
            decoded = base64.b64decode(creds_b64).decode("utf-8")
            creds_dict = json.loads(decoded)
            creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        elif creds_json:
            creds_dict = json.loads(creds_json)
            creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        elif os.path.exists("credentials.json"):
            creds = Credentials.from_service_account_file(
                "credentials.json", scopes=SCOPES
            )
    except Exception as e:
        print(f"[sheets] credentials load error: {e}")
        return None

    if creds:
        return build("sheets", "v4", credentials=creds)

    return None

def ensure_tab():
    """Create 'Transactions' tab if it doesn't exist"""
    service = get_sheets_service()
    if not service:
        return False
    try:
        meta = service.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
        titles = [s["properties"]["title"] for s in meta.get("sheets", [])]
        if "Transactions" not in titles:
            service.spreadsheets().batchUpdate(
                spreadsheetId=SHEET_ID,
                body={"requests": [{"addSheet": {"properties": {"title": "Transactions"}}}]},
            ).execute()
            print("[sheets] created Transactions tab")
        return True
    except Exception as e:
        print(f"[sheets] ensure_tab error: {e}")
        return False

def ensure_header():
    """Ensure header row exists in sheet"""
    service = get_sheets_service()
    if not service:
        return False

    try:
        ensure_tab()
        sheet = service.spreadsheets()
        request = sheet.values().get(
            spreadsheetId=SHEET_ID, range="Transactions!A1:G1"
        )
        result = request.execute()
        values = result.get("values", [])

        if not values:
            headers = [["date", "amount", "type", "category", "merchant", "note", "raw_input"]]
            sheet.values().update(
                spreadsheetId=SHEET_ID,
                range="Transactions!A1:G1",
                valueInputOption="RAW",
                body={"values": headers},
            ).execute()
        return True
    except Exception as e:
        print(f"Header error: {e}")
        return False

def write_transaction(transaction):
    """Write transaction to Google Sheet"""
    service = get_sheets_service()
    if not service:
        print("No Google credentials found")
        return False

    try:
        ensure_header()
        sheet = service.spreadsheets()

        # Prepare row
        row = [
            transaction.get("date", ""),
            transaction.get("amount", ""),
            transaction.get("type", ""),
            transaction.get("category", ""),
            transaction.get("merchant", ""),
            transaction.get("note", ""),
            transaction.get("raw_input", ""),
        ]

        # Append to Transactions sheet
        request = sheet.values().append(
            spreadsheetId=SHEET_ID,
            range="Transactions!A:G",
            valueInputOption="RAW",
            body={"values": [row]},
        )
        request.execute()

        return True

    except Exception as e:
        print(f"Write error: {e}")
        return False

def query_transactions(days=None):
    """Query transactions from sheet
    If days=None, return all
    If days=30, return last 30 days
    """
    service = get_sheets_service()
    if not service:
        return []

    try:
        sheet = service.spreadsheets()

        # Read all data from Transactions sheet
        request = sheet.values().get(
            spreadsheetId=SHEET_ID, range="Transactions!A:G"
        )
        result = request.execute()
        values = result.get("values", [])

        if not values or len(values) < 2:
            return []

        # Skip header, parse data
        headers = values[0]
        transactions = []

        for row in values[1:]:
            if len(row) < 2:
                continue

            trans = {
                "date": row[0] if len(row) > 0 else "",
                "amount": float(row[1]) if len(row) > 1 and row[1] else 0,
                "type": row[2] if len(row) > 2 else "",
                "category": row[3] if len(row) > 3 else "",
                "merchant": row[4] if len(row) > 4 else "",
                "note": row[5] if len(row) > 5 else "",
                "raw_input": row[6] if len(row) > 6 else "",
            }
            transactions.append(trans)

        # Filter by days if specified
        if days:
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            transactions = [t for t in transactions if t["date"] >= cutoff]

        return transactions

    except Exception as e:
        print(f"Query error: {e}")
        return []

def compute_daily_totals(date_str):
    """Sum income and expense for a given date. Returns (income, expense) as positive floats."""
    transactions = query_transactions()
    income = 0.0
    expense = 0.0
    for t in transactions:
        if t["date"] != date_str:
            continue
        if t["type"] == "income":
            income += t["amount"]
        elif t["type"] == "expense":
            expense += abs(t["amount"])
    return income, expense


def get_monthly_total(year, month, trans_type="expense"):
    """Get total for specific month
    trans_type: 'expense', 'income', or 'all'
    """
    transactions = query_transactions()

    total = 0
    for trans in transactions:
        if trans["type"] == trans_type or trans_type == "all":
            try:
                trans_date = datetime.strptime(trans["date"], "%Y-%m-%d")
                if trans_date.year == year and trans_date.month == month:
                    total += trans["amount"]
            except:
                pass

    return total
