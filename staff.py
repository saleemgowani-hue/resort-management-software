import streamlit as st
import pandas as pd

from config import STAFF_DEPARTMENTS
from database import get_connection, new_id
from utils import currency, fmt_date, log_audit
import auth


def render():
    st.markdown('<div class="section-title">👨‍💼 Staff Management</div>', unsafe_allow_html=True)
    user = st.session_state.get("user", {})
    tenant_id = auth.current_tenant_id()

    tab1, tab2 = st.tabs(["Staff List", "Add Staff"])

    with tab2:
        with st.form("staff_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            name = c1.text_input("Staff Name *")
            mobile = c2.text_input("Mobile Number")
            department = c3.selectbox("Department", STAFF_DEPARTMENTS)

            c4, c5, c6 = st.columns(3)
            designation = c4.text_input("Designation")
            joining_date = c5.date_input("Joining Date")
            salary = c6.number_input("Salary (₹)", min_value=0.0, value=15000.0, step=500.0)

            if st.form_submit_button("Save Staff", type="primary"):
                if not name:
                    st.error("Staff name is required.")
                else:
                    conn = get_connection()
                    staff_id = new_id("STF-")
                    conn.execute(
                        """INSERT INTO staff (staff_id, tenant_id, name, mobile, department, designation,
                           joining_date, salary, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Active')""",
                        (staff_id, tenant_id, name, mobile, department, designation,
                         joining_date.isoformat(), salary),
                    )
                    conn.commit()
                    conn.close()
                    log_audit(tenant_id, user.get("username", ""), "Staff added", "staff", staff_id)
                    st.success(f"Staff member '{name}' added.")
                    st.rerun()

    with tab1:
        conn = get_connection()
        rows = conn.execute("SELECT * FROM staff WHERE tenant_id = ? ORDER BY name", (tenant_id,)).fetchall()
        conn.close()
        staff = [dict(r) for r in rows]
        if not staff:
            st.info("No staff members added yet.")
        else:
            df = pd.DataFrame(staff)
            df["joining_date"] = df["joining_date"].apply(fmt_date)
            display_df = df[["name", "mobile", "department", "designation", "joining_date", "salary", "status"]]
            display_df.columns = ["Name", "Mobile", "Department", "Designation", "Joined", "Salary", "Status"]
            st.dataframe(display_df, use_container_width=True, hide_index=True)
