import streamlit as st

from database import get_connection, new_id
from utils import currency, fmt_date, log_audit, push_notification
from whatsapp import build_whatsapp_url, checkin_details_message, log_whatsapp_message
import auth


def _pending_bookings(tenant_id):
    conn = get_connection()
    rows = conn.execute("""
        SELECT res.*, rm.room_number, rt.name as room_type_name FROM reservations res
        LEFT JOIN rooms rm ON res.room_id = rm.room_id
        LEFT JOIN room_types rt ON res.room_type_id = rt.room_type_id
        WHERE res.tenant_id = ? AND res.status = 'Confirmed'
        ORDER BY res.checkin_date
    """, (tenant_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def render():
    st.markdown('<div class="section-title">🧾 Check-In</div>', unsafe_allow_html=True)
    user = st.session_state.get("user", {})
    tenant_id = auth.current_tenant_id()

    bookings = _pending_bookings(tenant_id)
    if not bookings:
        st.info("No confirmed bookings pending check-in.")
        return

    search = st.text_input("🔍 Search reservation by guest name, booking ID or mobile")
    if search:
        s = search.lower()
        bookings = [b for b in bookings if s in b["guest_name"].lower() or s in b["booking_id"].lower()
                    or s in (b["mobile"] or "")]

    booking_map = {f"{b['booking_id']} - {b['guest_name']} (Room {b['room_number']}, {fmt_date(b['checkin_date'])})": b
                   for b in bookings}
    if not booking_map:
        st.warning("No matching reservation found.")
        return

    selected_label = st.selectbox("Select Reservation", list(booking_map.keys()))
    b = booking_map[selected_label]

    c1, c2, c3 = st.columns(3)
    c1.metric("Guest", b["guest_name"])
    c2.metric("Room", b["room_number"])
    c3.metric("Balance Due", currency(tenant_id, b["balance"]))

    with st.form("checkin_form"):
        c1, c2 = st.columns(2)
        num_guests = c1.number_input("Number of Guests", min_value=1, value=b["adults"] + b["children"])
        id_verified = c2.checkbox("ID Proof Verified", value=True)

        additional_advance = st.number_input("Additional Advance Payment (₹)", min_value=0.0, value=0.0, step=500.0)
        remarks = st.text_area("Remarks")

        submitted = st.form_submit_button("✅ Complete Check-In", type="primary")

        if submitted:
            conn = get_connection()
            checkin_id = new_id("CI-")
            conn.execute(
                """INSERT INTO checkins (checkin_id, tenant_id, booking_id, guest_id, room_id, id_verified,
                   num_guests, advance_payment, remarks, created_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (checkin_id, tenant_id, b["booking_id"], b["guest_id"], b["room_id"], bool(id_verified),
                 num_guests, additional_advance, remarks, user.get("username", "")),
            )
            new_advance_total = b["advance_payment"] + additional_advance
            new_balance = b["total_amount"] - new_advance_total
            conn.execute(
                """UPDATE reservations SET status = 'Checked-In', advance_payment = ?, balance = ?
                   WHERE booking_id = ? AND tenant_id = ?""",
                (new_advance_total, new_balance, b["booking_id"], tenant_id),
            )
            conn.execute("UPDATE rooms SET status = 'Occupied' WHERE room_id = ? AND tenant_id = ?",
                        (b["room_id"], tenant_id))
            if additional_advance > 0:
                conn.execute(
                    """INSERT INTO payments (payment_id, tenant_id, booking_id, guest_id, amount, payment_mode,
                       payment_type, created_by) VALUES (?, ?, ?, ?, ?, 'Cash', 'Advance', ?)""",
                    (new_id("PAY-"), tenant_id, b["booking_id"], b["guest_id"], additional_advance,
                     user.get("username", "")),
                )
            conn.commit()
            conn.close()

            log_audit(tenant_id, user.get("username", ""), "Guest checked in", "checkins", checkin_id)
            push_notification(tenant_id, "checkin", f"{b['guest_name']} checked in to Room {b['room_number']}")

            st.session_state["last_checkin_booking"] = b["booking_id"]
            st.success(f"✅ {b['guest_name']} checked in successfully to Room {b['room_number']}!")
            st.rerun()

    if st.session_state.get("last_checkin_booking") == b["booking_id"]:
        st.markdown("---")
        message = checkin_details_message(tenant_id, b)
        url = build_whatsapp_url(b["mobile"], message, b.get("country_code"))
        if url:
            st.link_button("📱 Send Check-In Details on WhatsApp", url)
            log_whatsapp_message(tenant_id, b["booking_id"], b["guest_id"], b["mobile"], "Check-In",
                                 message, user.get("username", ""), status="Initiated")
