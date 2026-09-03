"""
utils.py
Shared helper functions used across modules.
"""

import datetime as dt
import re

from database import get_connection, new_id


def today_str():
    return dt.date.today().isoformat()


def now_str():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def fmt_date(iso_date_str, fmt="%d-%m-%Y"):
    if not iso_date_str:
        return "-"
    try:
        return dt.datetime.strptime(str(iso_date_str)[:10], "%Y-%m-%d").strftime(fmt)
    except ValueError:
        return str(iso_date_str)


def nights_between(checkin_date: str, checkout_date: str) -> int:
    try:
        ci = dt.datetime.strptime(checkin_date, "%Y-%m-%d").date()
        co = dt.datetime.strptime(checkout_date, "%Y-%m-%d").date()
        return max((co - ci).days, 1)
    except (ValueError, TypeError):
        return 1


def clean_mobile(mobile: str) -> str:
    return re.sub(r"\D", "", mobile or "")


def get_resort_profile(tenant_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM resort_profile WHERE tenant_id = ?", (tenant_id,)).fetchone()
    conn.close()
    return dict(row) if row else {}


def next_invoice_number(tenant_id):
    profile = get_resort_profile(tenant_id)
    prefix = profile.get("invoice_prefix") or "INV"
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) c FROM invoices WHERE tenant_id = ?", (tenant_id,)).fetchone()["c"]
    conn.close()
    year = dt.date.today().strftime("%y")
    return f"{prefix}-{year}-{count + 1:05d}"


def log_audit(tenant_id, user, action, module, record_id=""):
    conn = get_connection()
    conn.execute(
        'INSERT INTO audit_logs (log_id, tenant_id, "user", action, module, record_id) VALUES (?, ?, ?, ?, ?, ?)',
        (new_id("LOG-"), tenant_id, user, action, module, record_id),
    )
    conn.commit()
    conn.close()


def push_notification(tenant_id, ntype, message):
    conn = get_connection()
    conn.execute(
        "INSERT INTO notifications (notification_id, tenant_id, type, message) VALUES (?, ?, ?, ?)",
        (new_id("NTF-"), tenant_id, ntype, message),
    )
    conn.commit()
    conn.close()


def room_overlaps(tenant_id, room_id: str, checkin_date: str, checkout_date: str, exclude_booking_id: str = None) -> bool:
    """
    True if the room already has an active (non-cancelled, non-checked-out) booking
    whose date range overlaps [checkin_date, checkout_date), WITHIN THIS TENANT ONLY.
    """
    conn = get_connection()
    query = """
        SELECT booking_id FROM reservations
        WHERE tenant_id = ? AND room_id = ?
          AND status NOT IN ('Cancelled', 'No Show', 'Checked-Out')
          AND checkin_date < ? AND checkout_date > ?
    """
    params = [tenant_id, room_id, checkout_date, checkin_date]
    if exclude_booking_id:
        query += " AND booking_id != ?"
        params.append(exclude_booking_id)
    row = conn.execute(query, params).fetchone()
    conn.close()
    return row is not None


def currency(tenant_id, amount):
    profile = get_resort_profile(tenant_id)
    symbol = profile.get("currency_symbol") or "\u20b9"
    try:
        return f"{symbol}{float(amount):,.2f}"
    except (TypeError, ValueError):
        return f"{symbol}0.00"
