import datetime as dt

import streamlit as st
import pandas as pd

from config import BOOKING_STATUSES, DEFAULT_TAX_PERCENT
from database import get_connection, new_id
from utils import (nights_between, room_overlaps, currency, fmt_date, log_audit,
                    push_notification, get_resort_profile)
from whatsapp import build_whatsapp_url, booking_confirmation_message, log_whatsapp_message
import auth


def _available_rooms_for(tenant_id, checkin_date, checkout_date, exclude_booking_id=None):
    conn = get_connection()
    rooms = conn.execute("""
        SELECT r.*, rt.name as room_type_name FROM rooms r
        LEFT JOIN room_types rt ON r.room_type_id = rt.room_type_id
        WHERE r.tenant_id = ? AND r.is_active = TRUE AND r.status != 'Out of Order'
        ORDER BY r.room_number
    """, (tenant_id,)).fetchall()
    conn.close()
    free = []
    for r in rooms:
        r = dict(r)
        if not room_overlaps(tenant_id, r["room_id"], checkin_date, checkout_date, exclude_booking_id):
            free.append(r)
    return free


def _get_bookings(tenant_id, status_filter=None, search=""):
    conn = get_connection()
    query = """
        SELECT res.*, rm.room_number, rt.name as room_type_name
        FROM reservations res
        LEFT JOIN rooms rm ON res.room_id = rm.room_id
        LEFT JOIN room_types rt ON res.room_type_id = rt.room_type_id
        WHERE res.tenant_id = ?
    """
    params = [tenant_id]
    if status_filter and status_filter != "All":
        query += " AND res.status = ?"
        params.append(status_filter)
    if search:
        query += " AND (res.guest_name LIKE ? OR res.booking_id LIKE ? OR res.mobile LIKE ?)"
        like = f"%{search}%"
        params += [like, like, like]
    query += " ORDER BY res.created_at DESC LIMIT 300"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def render():
    st.markdown('<div class="section-title">🛎️ Reservations</div>', unsafe_allow_html=True)
    user = st.session_state.get("user", {})
    tenant_id = auth.current_tenant_id()
    profile = get_resort_profile(tenant_id)
    tax_percent = profile.get("tax_percent", DEFAULT_TAX_PERCENT)

    tab1, tab2 = st.tabs(["New Booking", "All Bookings"])

    # ------------------------------------------------------------------
    with tab1:
        c1, c2 = st.columns(2)
        checkin_date = c1.date_input("Check-in Date", value=dt.date.today())
        checkout_date = c2.date_input("Check-out Date", value=dt.date.today() + dt.timedelta(days=1))

        if checkout_date <= checkin_date:
            st.error("Check-out date must be after check-in date.")
            return

        nights = (checkout_date - checkin_date).days
        st.caption(f"Stay duration: **{nights} night(s)**")

        available_rooms = _available_rooms_for(tenant_id, checkin_date.isoformat(), checkout_date.isoformat())
        if not available_rooms:
            st.warning("No rooms available for the selected dates. Try different dates or add rooms in Room Management.")

        with st.form("new_booking_form"):
            c1, c2, c3 = st.columns(3)
            guest_name = c1.text_input("Guest Name *")
            country_code = c2.text_input("Country Code", value=profile.get("whatsapp_country_code", "+91"))
            mobile = c3.text_input("Mobile Number *")

            c4, c5 = st.columns(2)
            email = c4.text_input("Email")
            booking_source = c5.selectbox("Booking Source", ["Direct", "Walk-in", "Phone", "Website", "OTA", "Agent", "Other"])

            c6, c7, c8 = st.columns(3)
            checkin_time = c6.time_input("Check-in Time", value=dt.time(12, 0))
            checkout_time = c7.time_input("Check-out Time", value=dt.time(11, 0))
            adults = c8.number_input("Adults", min_value=1, value=2)
            children = st.number_input("Children", min_value=0, value=0)

            room_options = {f"{r['room_number']} - {r['room_type_name'] or ''} ({currency(tenant_id, r['tariff'])}/night)": r
                             for r in available_rooms}
            selected_room_label = st.selectbox("Select Room *", list(room_options.keys()) or ["-- no rooms available --"])

            c9, c10 = st.columns(2)
            discount = c9.number_input("Discount (₹)", min_value=0.0, value=0.0, step=100.0)
            advance_payment = c10.number_input("Advance Payment (₹)", min_value=0.0, value=0.0, step=500.0)

            special_request = st.text_area("Special Request")

            submitted = st.form_submit_button("Create Booking", type="primary")

            if submitted:
                if not guest_name or not mobile:
                    st.error("Guest Name and Mobile Number are required.")
                elif not available_rooms:
                    st.error("No room selected / available.")
                else:
                    room = room_options[selected_room_label]
                    # Re-check for race condition safety right before insert
                    if room_overlaps(tenant_id, room["room_id"], checkin_date.isoformat(), checkout_date.isoformat()):
                        st.error("Sorry, this room was just booked for overlapping dates by someone else. Please choose another room.")
                    else:
                        room_tariff = room["tariff"] * nights
                        taxable = max(room_tariff - discount, 0)
                        tax_amount = round(taxable * tax_percent / 100, 2)
                        total_amount = round(taxable + tax_amount, 2)
                        balance = round(total_amount - advance_payment, 2)

                        conn = get_connection()
                        # find or create guest (scoped to this tenant)
                        guest_row = conn.execute("SELECT guest_id FROM guests WHERE tenant_id = ? AND mobile = ?",
                                                 (tenant_id, mobile)).fetchone()
                        if guest_row:
                            guest_id = guest_row["guest_id"]
                        else:
                            guest_id = new_id("GST-")
                            conn.execute(
                                """INSERT INTO guests (guest_id, tenant_id, name, mobile, country_code, whatsapp_number, email)
                                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                                (guest_id, tenant_id, guest_name, mobile, country_code, mobile, email),
                            )

                        booking_id = new_id("BK-")
                        conn.execute(
                            """INSERT INTO reservations
                               (booking_id, tenant_id, guest_id, guest_name, mobile, email, country_code,
                                checkin_date, checkin_time, checkout_date, checkout_time, adults, children,
                                room_type_id, room_id, nights, room_tariff, discount, tax, total_amount,
                                advance_payment, balance, booking_source, special_request, status, created_by)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Confirmed', ?)""",
                            (booking_id, tenant_id, guest_id, guest_name, mobile, email, country_code,
                             checkin_date.isoformat(), checkin_time.strftime("%H:%M"),
                             checkout_date.isoformat(), checkout_time.strftime("%H:%M"), adults, children,
                             room["room_type_id"], room["room_id"], nights, room_tariff, discount, tax_amount,
                             total_amount, advance_payment, balance, booking_source, special_request,
                             user.get("username", "")),
                        )
                        conn.execute("UPDATE rooms SET status = 'Reserved' WHERE room_id = ? AND tenant_id = ?",
                                    (room["room_id"], tenant_id))
                        conn.commit()
                        conn.close()

                        log_audit(tenant_id, user.get("username", ""), "Booking created", "reservations", booking_id)
                        push_notification(tenant_id, "booking",
                                          f"New booking {booking_id} for {guest_name}, Room {room['room_number']}")

                        st.session_state["last_booking_id"] = booking_id
                        st.success(f"✅ Booking {booking_id} created successfully for {guest_name}!")
                        st.rerun()

        # WhatsApp send button appears after a booking was just created
        if st.session_state.get("last_booking_id"):
            booking_id = st.session_state["last_booking_id"]
            conn = get_connection()
            b = conn.execute("""
                SELECT res.*, rm.room_number, rt.name as room_type_name FROM reservations res
                LEFT JOIN rooms rm ON res.room_id = rm.room_id
                LEFT JOIN room_types rt ON res.room_type_id = rt.room_type_id
                WHERE res.booking_id = ? AND res.tenant_id = ?""", (booking_id, tenant_id)).fetchone()
            conn.close()
            if b:
                b = dict(b)
                st.markdown("---")
                st.markdown(f"**Booking {booking_id} ready.** Send confirmation to guest:")
                message = booking_confirmation_message(tenant_id, b)
                url = build_whatsapp_url(b["mobile"], message, b.get("country_code"))
                colA, colB = st.columns([1, 3])
                with colA:
                    if url:
                        st.link_button("📱 Send Booking on WhatsApp", url)
                        log_whatsapp_message(tenant_id, booking_id, b["guest_id"], b["mobile"], "Booking Confirmation",
                                             message, user.get("username", ""), status="Initiated")
                    else:
                        st.warning("Invalid mobile number for WhatsApp.")
                with colB:
                    if st.button("Dismiss"):
                        del st.session_state["last_booking_id"]
                        st.rerun()

    # ------------------------------------------------------------------
    with tab2:
        c1, c2 = st.columns([1, 3])
        status_filter = c1.selectbox("Filter by Status", ["All"] + BOOKING_STATUSES)
        search = c2.text_input("🔍 Search by guest name, booking ID or mobile")

        bookings = _get_bookings(tenant_id, status_filter, search)
        if not bookings:
            st.info("No bookings found.")
        else:
            df = pd.DataFrame(bookings)
            df["checkin_date"] = df["checkin_date"].apply(fmt_date)
            df["checkout_date"] = df["checkout_date"].apply(fmt_date)
            display_cols = ["booking_id", "guest_name", "mobile", "room_number", "checkin_date",
                             "checkout_date", "nights", "total_amount", "advance_payment", "balance", "status"]
            display_df = df[display_cols].copy()
            display_df.columns = ["Booking ID", "Guest", "Mobile", "Room", "Check-in", "Check-out",
                                   "Nights", "Total", "Advance", "Balance", "Status"]
            st.dataframe(display_df, use_container_width=True, hide_index=True)

            st.markdown("##### Update Booking Status")
            booking_map = {f"{b['booking_id']} - {b['guest_name']}": b for b in bookings}
            selected_label = st.selectbox("Select Booking", list(booking_map.keys()))
            selected_booking = booking_map[selected_label]
            new_status = st.selectbox("New Status", BOOKING_STATUSES,
                                       index=BOOKING_STATUSES.index(selected_booking["status"])
                                       if selected_booking["status"] in BOOKING_STATUSES else 0)
            colX, colY = st.columns(2)
            with colX:
                if st.button("Update Status", type="primary"):
                    conn = get_connection()
                    conn.execute("UPDATE reservations SET status = ? WHERE booking_id = ? AND tenant_id = ?",
                                 (new_status, selected_booking["booking_id"], tenant_id))
                    if new_status in ("Cancelled", "No Show"):
                        conn.execute("UPDATE rooms SET status = 'Available' WHERE room_id = ? AND tenant_id = ?",
                                     (selected_booking["room_id"], tenant_id))
                    conn.commit()
                    conn.close()
                    log_audit(tenant_id, user.get("username", ""), f"Booking status -> {new_status}", "reservations",
                               selected_booking["booking_id"])
                    st.success("Booking status updated.")
                    st.rerun()
            with colY:
                message = booking_confirmation_message(tenant_id, selected_booking)
                url = build_whatsapp_url(selected_booking["mobile"], message, selected_booking.get("country_code"))
                if url:
                    st.link_button("📱 Resend Confirmation on WhatsApp", url)
