import streamlit as st
import pandas as pd

from database import get_connection
from utils import fmt_date
from whatsapp import (build_whatsapp_url, render_custom_template, log_whatsapp_message,
                       TEMPLATE_VARIABLES, booking_confirmation_message, payment_reminder_message)
import auth

DEFAULT_TEMPLATES = {
    "Custom / Blank": "Dear {guest_name},\n\n\n\nThank you,\n{resort_name}",
    "Booking Confirmation": None,   # generated via dedicated function
    "Payment Reminder": None,
    "General Update": (
        "Dear {guest_name},\n\nThis is a message regarding your booking {booking_id} with {resort_name}.\n\n"
        "Regards,\n{resort_name}\n{resort_mobile}"
    ),
}


def render():
    st.markdown('<div class="section-title">📱 WhatsApp Message Center</div>', unsafe_allow_html=True)
    user = st.session_state.get("user", {})
    tenant_id = auth.current_tenant_id()

    tab1, tab2 = st.tabs(["Send Message", "Communication Log"])

    with tab1:
        search = st.text_input("🔍 Search guest or booking (name, mobile, or booking ID)")
        conn = get_connection()
        if search:
            like = f"%{search}%"
            rows = conn.execute("""
                SELECT res.*, rm.room_number FROM reservations res
                LEFT JOIN rooms rm ON res.room_id = rm.room_id
                WHERE res.tenant_id = ? AND (res.guest_name LIKE ? OR res.mobile LIKE ? OR res.booking_id LIKE ?)
                ORDER BY res.created_at DESC LIMIT 30
            """, (tenant_id, like, like, like)).fetchall()
        else:
            rows = conn.execute("""
                SELECT res.*, rm.room_number FROM reservations res
                LEFT JOIN rooms rm ON res.room_id = rm.room_id
                WHERE res.tenant_id = ?
                ORDER BY res.created_at DESC LIMIT 30
            """, (tenant_id,)).fetchall()
        conn.close()
        bookings = [dict(r) for r in rows]

        if not bookings:
            st.info("No bookings found.")
            return

        booking_map = {f"{b['booking_id']} - {b['guest_name']} ({b['mobile']})": b for b in bookings}
        selected_label = st.selectbox("Select Booking / Guest", list(booking_map.keys()))
        b = booking_map[selected_label]

        template_name = st.selectbox("Select Template", list(DEFAULT_TEMPLATES.keys()))

        if template_name == "Booking Confirmation":
            message_text = booking_confirmation_message(tenant_id, b)
        elif template_name == "Payment Reminder":
            message_text = payment_reminder_message(tenant_id, b)
        else:
            raw_template = DEFAULT_TEMPLATES[template_name]
            message_text = render_custom_template(tenant_id, raw_template, b)

        st.caption("Available variables: " + ", ".join(TEMPLATE_VARIABLES))
        edited_message = st.text_area("Message Preview / Edit", value=message_text, height=220)

        url = build_whatsapp_url(b["mobile"], edited_message, b.get("country_code"))
        if url:
            if st.button("📱 Open WhatsApp", type="primary"):
                log_whatsapp_message(tenant_id, b["booking_id"], b["guest_id"], b["mobile"], template_name,
                                     edited_message, user.get("username", ""), status="Initiated")
                st.link_button("👉 Click here to open WhatsApp", url)
        else:
            st.warning("This guest doesn't have a valid mobile number on file.")

    with tab2:
        conn = get_connection()
        rows = conn.execute("SELECT * FROM whatsapp_logs WHERE tenant_id = ? ORDER BY date DESC, time DESC LIMIT 300",
                            (tenant_id,)).fetchall()
        conn.close()
        logs = [dict(r) for r in rows]
        if not logs:
            st.info("No WhatsApp messages sent yet.")
        else:
            df = pd.DataFrame(logs)
            df["date"] = df["date"].apply(fmt_date)
            display_df = df[["date", "time", "mobile_number", "message_type", "status", "sent_by"]]
            display_df.columns = ["Date", "Time", "Mobile", "Type", "Status", "Sent By"]
            st.dataframe(display_df, use_container_width=True, hide_index=True)
