import streamlit as st
import pandas as pd

from database import get_connection, new_id
from utils import log_audit, fmt_date
import auth


def _get_guests(tenant_id, search=""):
    conn = get_connection()
    if search:
        like = f"%{search}%"
        rows = conn.execute(
            """SELECT * FROM guests WHERE tenant_id = ?
               AND (name LIKE ? OR mobile LIKE ? OR email LIKE ?) ORDER BY created_at DESC""",
            (tenant_id, like, like, like),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM guests WHERE tenant_id = ? ORDER BY created_at DESC",
                            (tenant_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def render():
    st.markdown('<div class="section-title">👤 Guest Management</div>', unsafe_allow_html=True)
    user = st.session_state.get("user", {})
    tenant_id = auth.current_tenant_id()

    tab1, tab2 = st.tabs(["Guest List", "Add / Edit Guest"])

    with tab2:
        with st.form("guest_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            name = c1.text_input("Guest Name *")
            country_code = c2.text_input("Country Code", value="+91")
            mobile = c3.text_input("Mobile Number *")

            c4, c5 = st.columns(2)
            whatsapp_number = c4.text_input("WhatsApp Number (if different)")
            email = c5.text_input("Email")

            c6, c7, c8 = st.columns(3)
            city = c6.text_input("City")
            state = c7.text_input("State")
            country = c8.text_input("Country", value="India")

            address = st.text_area("Address")

            c9, c10 = st.columns(2)
            id_proof_type = c9.selectbox("ID Proof Type", ["Aadhaar", "Passport", "Driving Licence", "Voter ID", "Other"])
            id_proof_number = c10.text_input("ID Proof Number")

            notes = st.text_area("Notes")

            if st.form_submit_button("Save Guest", type="primary"):
                if not name or not mobile:
                    st.error("Guest Name and Mobile Number are required.")
                else:
                    conn = get_connection()
                    guest_id = new_id("GST-")
                    conn.execute(
                        """INSERT INTO guests (guest_id, tenant_id, name, mobile, country_code, whatsapp_number, email,
                           address, city, state, country, id_proof_type, id_proof_number, notes)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (guest_id, tenant_id, name, mobile, country_code, whatsapp_number or mobile, email,
                         address, city, state, country, id_proof_type, id_proof_number, notes),
                    )
                    conn.commit()
                    conn.close()
                    log_audit(tenant_id, user.get("username", ""), "Guest created", "guests", guest_id)
                    st.success(f"Guest '{name}' saved successfully.")
                    st.rerun()

    with tab1:
        search = st.text_input("🔍 Search by name, mobile or email")
        guests = _get_guests(tenant_id, search)
        if not guests:
            st.info("No guests found.")
        else:
            df = pd.DataFrame(guests)
            df["last_visit"] = df["last_visit"].apply(fmt_date)
            display_df = df[["name", "mobile", "email", "city", "id_proof_type", "visits", "last_visit"]]
            display_df.columns = ["Name", "Mobile", "Email", "City", "ID Proof", "Visits", "Last Visit"]
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            st.caption(f"Total Guests: {len(guests)}")
