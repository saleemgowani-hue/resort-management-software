import datetime as dt

import streamlit as st
import pandas as pd

from database import get_connection, new_id
from utils import fmt_date, log_audit
import auth


def render():
    st.markdown('<div class="section-title">📅 Attendance</div>', unsafe_allow_html=True)
    user = st.session_state.get("user", {})
    tenant_id = auth.current_tenant_id()

    conn = get_connection()
    staff_rows = conn.execute("SELECT staff_id, name FROM staff WHERE tenant_id = ? AND status = 'Active' ORDER BY name",
                              (tenant_id,)).fetchall()
    conn.close()
    staff_list = [dict(r) for r in staff_rows]

    if not staff_list:
        st.info("Please add staff members first (Staff Management module).")
        return

    tab1, tab2 = st.tabs(["Mark Attendance", "Attendance Reports"])

    with tab1:
        with st.form("attendance_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            date = c1.date_input("Date", value=dt.date.today())
            staff_map = {s["name"]: s["staff_id"] for s in staff_list}
            staff_name = c2.selectbox("Staff Member", list(staff_map.keys()))

            c3, c4, c5 = st.columns(3)
            status = c3.selectbox("Status", ["Present", "Absent", "Half Day", "Leave"])
            in_time = c4.time_input("In Time", value=dt.time(9, 0))
            out_time = c5.time_input("Out Time", value=dt.time(18, 0))

            if st.form_submit_button("Mark Attendance", type="primary"):
                conn = get_connection()
                existing = conn.execute(
                    "SELECT attendance_id FROM attendance WHERE tenant_id = ? AND staff_id = ? AND date = ?",
                    (tenant_id, staff_map[staff_name], date.isoformat()),
                ).fetchone()
                if existing:
                    conn.execute(
                        "UPDATE attendance SET status = ?, in_time = ?, out_time = ? WHERE attendance_id = ? AND tenant_id = ?",
                        (status, in_time.strftime("%H:%M"), out_time.strftime("%H:%M"),
                         existing["attendance_id"], tenant_id),
                    )
                else:
                    conn.execute(
                        """INSERT INTO attendance (attendance_id, tenant_id, staff_id, date, status, in_time, out_time)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (new_id("ATT-"), tenant_id, staff_map[staff_name], date.isoformat(), status,
                         in_time.strftime("%H:%M"), out_time.strftime("%H:%M")),
                    )
                conn.commit()
                conn.close()
                log_audit(tenant_id, user.get("username", ""), f"Attendance marked: {status}", "attendance",
                          staff_map[staff_name])
                st.success(f"Attendance for {staff_name} on {fmt_date(date.isoformat())} marked as {status}.")
                st.rerun()

    with tab2:
        c1, c2 = st.columns(2)
        start_date = c1.date_input("From", value=dt.date.today().replace(day=1), key="att_start")
        end_date = c2.date_input("To", value=dt.date.today(), key="att_end")

        conn = get_connection()
        rows = conn.execute("""
            SELECT a.*, s.name as staff_name, s.department FROM attendance a
            JOIN staff s ON a.staff_id = s.staff_id
            WHERE a.tenant_id = ? AND a.date BETWEEN ? AND ?
            ORDER BY a.date DESC
        """, (tenant_id, start_date.isoformat(), end_date.isoformat())).fetchall()
        conn.close()
        records = [dict(r) for r in rows]

        if not records:
            st.info("No attendance records for this range.")
        else:
            df = pd.DataFrame(records)
            df["date"] = df["date"].apply(fmt_date)
            display_df = df[["date", "staff_name", "department", "status", "in_time", "out_time"]]
            display_df.columns = ["Date", "Staff", "Department", "Status", "In Time", "Out Time"]
            st.dataframe(display_df, use_container_width=True, hide_index=True)

            summary = df.groupby("staff_name")["status"].value_counts().unstack(fill_value=0)
            st.markdown("##### Staff-wise Summary")
            st.dataframe(summary, use_container_width=True)
