import streamlit as st
import pandas as pd

from config import HOUSEKEEPING_STATUSES
from database import get_connection, new_id
from styles import status_pill
from utils import log_audit
import auth

HK_COLORS = {"Dirty": "#dc2626", "Cleaning": "#3b82f6", "Clean": "#16a34a",
             "Inspected": "#0891b2", "Maintenance": "#a855f7"}


def _rooms_with_hk(tenant_id):
    conn = get_connection()
    rows = conn.execute("""
        SELECT r.room_id, r.room_number, r.status as room_status,
               (SELECT status FROM housekeeping h WHERE h.room_id = r.room_id AND h.tenant_id = ?
                ORDER BY h.updated_at DESC LIMIT 1) as hk_status,
               (SELECT assigned_staff FROM housekeeping h WHERE h.room_id = r.room_id AND h.tenant_id = ?
                ORDER BY h.updated_at DESC LIMIT 1) as assigned_staff,
               (SELECT remarks FROM housekeeping h WHERE h.room_id = r.room_id AND h.tenant_id = ?
                ORDER BY h.updated_at DESC LIMIT 1) as remarks
        FROM rooms r
        WHERE r.tenant_id = ? AND r.is_active = TRUE
        ORDER BY r.room_number
    """, (tenant_id, tenant_id, tenant_id, tenant_id)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def render():
    st.markdown('<div class="section-title">🧹 Housekeeping</div>', unsafe_allow_html=True)
    user = st.session_state.get("user", {})
    tenant_id = auth.current_tenant_id()

    conn = get_connection()
    rooms = conn.execute("SELECT room_id, room_number FROM rooms WHERE tenant_id = ? AND is_active = TRUE ORDER BY room_number",
                        (tenant_id,)).fetchall()
    staff = conn.execute("SELECT staff_id, name FROM staff WHERE tenant_id = ? AND department = 'Housekeeping' AND status = 'Active'",
                        (tenant_id,)).fetchall()
    conn.close()
    rooms = [dict(r) for r in rooms]
    staff = [dict(r) for r in staff]

    if not rooms:
        st.info("No rooms found. Add rooms in Room Management first.")
        return

    with st.form("hk_form"):
        room_map = {r["room_number"]: r["room_id"] for r in rooms}
        c1, c2 = st.columns(2)
        room_number = c1.selectbox("Room", list(room_map.keys()))
        status = c2.selectbox("Status", HOUSEKEEPING_STATUSES)

        staff_names = [s["name"] for s in staff] or ["-- no housekeeping staff added --"]
        assigned_staff = st.selectbox("Assigned Staff", staff_names)
        remarks = st.text_area("Remarks (e.g. maintenance request)")

        if st.form_submit_button("Update Housekeeping Status", type="primary"):
            conn = get_connection()
            hk_id = new_id("HK-")
            conn.execute(
                """INSERT INTO housekeeping (hk_id, tenant_id, room_id, status, assigned_staff, remarks)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (hk_id, tenant_id, room_map[room_number], status, assigned_staff, remarks),
            )
            if status in ("Clean", "Inspected"):
                conn.execute("UPDATE rooms SET status = 'Available' WHERE room_id = ? AND tenant_id = ?",
                            (room_map[room_number], tenant_id))
            elif status == "Maintenance":
                conn.execute("UPDATE rooms SET status = 'Maintenance' WHERE room_id = ? AND tenant_id = ?",
                            (room_map[room_number], tenant_id))
            elif status == "Cleaning":
                conn.execute("UPDATE rooms SET status = 'Cleaning' WHERE room_id = ? AND tenant_id = ?",
                            (room_map[room_number], tenant_id))
            conn.commit()
            conn.close()
            log_audit(tenant_id, user.get("username", ""), f"Housekeeping status -> {status}", "housekeeping", hk_id)
            st.success(f"Room {room_number} housekeeping status updated to {status}.")
            st.rerun()

    st.markdown("##### Current Housekeeping Status")
    data = _rooms_with_hk(tenant_id)
    cols = st.columns(4)
    for i, r in enumerate(data):
        hk_status = r["hk_status"] or "Dirty"
        color = HK_COLORS.get(hk_status, "#6b7280")
        with cols[i % 4]:
            st.markdown(
                f"""<div style="border:1px solid #e5e7eb;border-left:6px solid {color};border-radius:10px;
                    padding:10px 12px;margin-bottom:10px;background:white;">
                    <b>Room {r['room_number']}</b><br/>{status_pill(hk_status, color)}<br/>
                    <span style="font-size:12px;color:#64748b;">{r.get('assigned_staff') or '-'}</span>
                    </div>""",
                unsafe_allow_html=True,
            )
