from datetime import datetime
from sheets import get_monthly_total
from tz import TH_TZ

def format_monthly_summary(transactions):
    """Format monthly summary for Telegram"""
    if not transactions:
        return "ไม่มีข้อมูลเดือนนี้"

    now = datetime.now(TH_TZ)
    current_month_total = get_monthly_total(transactions, now.year, now.month, "expense")
    current_income = get_monthly_total(transactions, now.year, now.month, "income")

    msg = f"""
📊 สรุปเดือนนี้ ({now.strftime("%B %Y")}):

💸 รายจ่าย: {abs(current_month_total):,.0f} บาท
💰 รายรับ: {current_income:,.0f} บาท
📈 สุทธิ: {current_income + current_month_total:,.0f} บาท

📝 ทำรายการ {len(transactions)} อัน
    """
    return msg.strip()

def format_comparison(transactions):
    """Compare this month vs last month"""
    if not transactions:
        return "ไม่มีข้อมูล"

    now = datetime.now(TH_TZ)
    current_month = get_monthly_total(transactions, now.year, now.month, "expense")

    # Last month
    if now.month == 1:
        last_year = now.year - 1
        last_month = 12
    else:
        last_year = now.year
        last_month = now.month - 1

    prev_month = get_monthly_total(transactions, last_year, last_month, "expense")

    if prev_month == 0:
        change_pct = 0
        change_text = "ไม่มีข้อมูล"
    else:
        change = current_month - prev_month
        change_pct = (change / abs(prev_month)) * 100
        if change < 0:
            change_text = f"📉 ลดลง {abs(change):,.0f} บาท ({abs(change_pct):.1f}%)"
        else:
            change_text = f"📈 เพิ่มขึ้น {change:,.0f} บาท ({change_pct:.1f}%)"

    msg = f"""
📊 เทียบเดือนที่แล้ว:

เดือนนี้: {abs(current_month):,.0f} บาท
เดือนที่แล้ว: {abs(prev_month):,.0f} บาท

{change_text}
    """
    return msg.strip()

def get_top_merchants(transactions, limit=5):
    """Get top merchants by spending"""
    by_merchant = {}
    for trans in transactions:
        if trans["type"] == "expense" and trans["merchant"]:
            merchant = trans["merchant"]
            by_merchant[merchant] = by_merchant.get(merchant, 0) + abs(trans["amount"])

    sorted_merchants = sorted(by_merchant.items(), key=lambda x: x[1], reverse=True)
    return sorted_merchants[:limit]

def get_spending_by_category(transactions):
    """Get spending by category"""
    by_category = {}
    for trans in transactions:
        if trans["type"] == "expense":
            cat = trans["category"]
            by_category[cat] = by_category.get(cat, 0) + abs(trans["amount"])

    return sorted(by_category.items(), key=lambda x: x[1], reverse=True)


def build_query_context(transactions):
    """Build a small, pre-aggregated JSON-able summary for the LLM to answer
    arbitrary analytical questions. Keeps token cost low by sending totals,
    not raw rows. Amounts are positive floats, rounded to whole baht."""
    now = datetime.now(TH_TZ)
    this_ym = now.strftime("%Y-%m")

    # last month key
    if now.month == 1:
        last_ym = f"{now.year - 1}-12"
    else:
        last_ym = f"{now.year}-{now.month - 1:02d}"

    daily = {}            # "YYYY-MM-DD" -> {"income": x, "expense": y}  (this month)
    by_category = {}      # this month expenses
    by_merchant = {}      # this month expenses
    month_income = 0.0
    month_expense = 0.0
    last_month_expense = 0.0

    for t in transactions:
        date = t.get("date") or ""
        amt = abs(t.get("amount") or 0)
        is_income = t.get("type") == "income"

        if date.startswith(this_ym):
            day = daily.setdefault(date, {"income": 0.0, "expense": 0.0})
            if is_income:
                day["income"] += amt
                month_income += amt
            else:
                day["expense"] += amt
                month_expense += amt
                cat = t.get("category") or "other"
                by_category[cat] = by_category.get(cat, 0.0) + amt
                merch = t.get("merchant")
                if merch:
                    by_merchant[merch] = by_merchant.get(merch, 0.0) + amt
        elif date.startswith(last_ym) and not is_income:
            last_month_expense += amt

    def _round_map(d):
        return {k: round(v) for k, v in d.items()}

    def _round_daily(d):
        return {k: {"income": round(v["income"]), "expense": round(v["expense"])}
                for k, v in sorted(d.items())}

    # keep merchant list short to save tokens
    top_merchants = dict(sorted(by_merchant.items(), key=lambda x: x[1], reverse=True)[:10])

    return {
        "today": now.strftime("%Y-%m-%d"),
        "this_month": this_ym,
        "daily": _round_daily(daily),
        "by_category": _round_map(by_category),
        "by_merchant": _round_map(top_merchants),
        "month_income": round(month_income),
        "month_expense": round(month_expense),
        "month_net": round(month_income - month_expense),
        "last_month_expense": round(last_month_expense),
    }
