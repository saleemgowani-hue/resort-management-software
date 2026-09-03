import datetime as dt

import streamlit as st

from database import get_connection
from utils import currency, fmt_date
import auth


def _gather_live_alerts(tenant_id):
    """Compute real-time alerts directly from current data (not the notifications log)."""
    alerts = []
    today = dt.date.today().isoformat()
    conn = get_connection()

    checkins = conn.execute(
        "SELECT COUNT(*) c FROM reservations WHERE tenant_id = ? AND checkin_date = ? AND status = 'Confirmed'",
        (tenant_id, today)
    ).fetchone()["c"]
    if checkins:
        alerts.append(("🛎️", f"{checkins} guest(s) scheduled to check in today.", "#2563eb"))

    checkouts = conn.execute(
        "SELECT COUNT(*) c FROM reservations WHERE tenant_id = ? AND checkout_date = ? AND status = 'Checked-In'",
        (tenant_id, today)
    ).fetchone()["c"]
    if checkouts:
        alerts.append(("🚪", f"{checkouts} guest(s) scheduled to check out today.", "#7c3aed"))

    pending_row = conn.execute(
        """SELECT COUNT(*) c, COALESCE(SUM(balance),0) t FROM reservations
           WHERE tenant_id = ? AND balance > 0 AND status IN ('Confirmed','Checked-In')""",
        (tenant_id,)
    ).fetchone()
    if pending_row["c"]:
        alerts.append(("💰", f"{pending_row['c']} booking(s) have pending payments totalling "
                             f"{currency(tenant_id, pending_row['t'])}.", "#dc2626"))

    low_stock = conn.execute("SELECT COUNT(*) c FROM inventory WHERE tenant_id = ? AND current_stock <= minimum_stock",
                             (tenant_id,)).fetchone()["c"]
    if low_stock:
        alerts.append(("📦", f"{low_stock} inventory item(s) are at or below minimum stock.", "#ea580c"))

    maintenance = conn.execute("SELECT COUNT(*) c FROM rooms WHERE tenant_id = ? AND status = 'Maintenance'",
                               (tenant_id,)).fetchone()["c"]
    if maintenance:
        alerts.append(("🔧", f"{maintenance} room(s) currently under maintenance.", "#a855f7"))

    unconfirmed = conn.execute("SELECT COUNT(*) c FROM reservations WHERE tenant_id = ? AND status = 'Pending'",
                               (tenant_id,)).fetchone()["c"]
    if unconfirmed:
        alerts.append(("❓", f"{unconfirmed} booking(s) are still unconfirmed.", "#d97706"))

    conn.close()
    return alerts


def render():
    st.markdown('<div class="section-title">🔔 Notifications</div>', unsafe_allow_html=True)
    tenant_id = auth.current_tenant_id()

    from license import get_status
    lic_status = get_status(tenant_id)
    if lic_status["state"] == "LICENCE_EXPIRING":
        st.warning(f"⚠️ {lic_status['message']}")
    elif lic_status["state"] == "LICENCE_EXPIRED":
        st.error(f"❌ {lic_status['message']}")

    alerts = _gather_live_alerts(tenant_id)
    if not alerts:
        st.success("✅ No pending alerts — everything looks good!")
    else:
        for icon, message, color in alerts:
            st.markdown(
                f"""<div style="border-left:5px solid {color};background:white;border-radius:8px;
                    padding:12px 16px;margin-bottom:10px;box-shadow:0 1px 4px rgba(0,0,0,0.06);">
                    {icon} &nbsp; {message}</div>""",
                unsafe_allow_html=True,
            )
