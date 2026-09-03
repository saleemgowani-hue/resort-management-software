import os

import streamlit as st

from config import DEFAULT_TAX_PERCENT, DATA_DIR
from database import get_connection, new_id
import db
from utils import currency, fmt_date, log_audit, push_notification, next_invoice_number, get_resort_profile
from whatsapp import build_whatsapp_url, final_bill_message, log_whatsapp_message
from pdf_generator import generate_invoice_pdf
import auth

INVOICE_DIR = os.path.join(DATA_DIR, "invoices")
os.makedirs(INVOICE_DIR, exist_ok=True)


def _checked_in_bookings(tenant_id):
    conn = get_connection()
    rows = conn.execute("""
        SELECT res.*, rm.room_number, rt.name as room_type_name FROM reservations res
        LEFT JOIN rooms rm ON res.room_id = rm.room_id
        LEFT JOIN room_types rt ON res.room_type_id = rt.room_type_id
        WHERE res.tenant_id = ? AND res.status = 'Checked-In'
        ORDER BY res.checkout_date
    """, (tenant_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _restaurant_charges_for_booking(tenant_id, booking_id):
    conn = get_connection()
    row = conn.execute(
        """SELECT COALESCE(SUM(total_amount), 0) as total FROM restaurant_orders
           WHERE tenant_id = ? AND booking_id = ? AND posted_to_room = TRUE""",
        (tenant_id, booking_id),
    ).fetchone()
    conn.close()
    return row["total"] or 0


def render():
    st.markdown('<div class="section-title">🚪 Check-Out</div>', unsafe_allow_html=True)
    user = st.session_state.get("user", {})
    tenant_id = auth.current_tenant_id()
    profile = get_resort_profile(tenant_id)

    bookings = _checked_in_bookings(tenant_id)
    if not bookings:
        st.info("No guests are currently checked in.")
        return

    booking_map = {f"{b['booking_id']} - {b['guest_name']} (Room {b['room_number']})": b for b in bookings}
    selected_label = st.selectbox("Select Checked-In Guest", list(booking_map.keys()))
    b = booking_map[selected_label]

    restaurant_charges = _restaurant_charges_for_booking(tenant_id, b["booking_id"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Guest", b["guest_name"])
    c2.metric("Room", b["room_number"])
    c3.metric("Room Charges", currency(tenant_id, b["room_tariff"]))
    c4.metric("Restaurant Charges", currency(tenant_id, restaurant_charges))

    with st.form("checkout_form"):
        c1, c2 = st.columns(2)
        other_charges = c1.number_input("Other Charges (₹)", min_value=0.0, value=0.0, step=100.0)
        extra_discount = c2.number_input("Additional Discount (₹)", min_value=0.0, value=0.0, step=100.0)

        subtotal = b["room_tariff"] + restaurant_charges + other_charges
        total_discount = b["discount"] + extra_discount
        taxable = max(subtotal - total_discount, 0)
        tax_percent = profile.get("tax_percent", DEFAULT_TAX_PERCENT)
        tax_amount = round(taxable * tax_percent / 100, 2)
        total_amount = round(taxable + tax_amount, 2)
        balance = round(total_amount - b["advance_payment"], 2)

        st.markdown(f"""
        **Bill Summary**
        - Subtotal: {currency(tenant_id, subtotal)}
        - Discount: {currency(tenant_id, total_discount)}
        - Tax ({tax_percent}%): {currency(tenant_id, tax_amount)}
        - **Total: {currency(tenant_id, total_amount)}**
        - Advance Paid: {currency(tenant_id, b['advance_payment'])}
        - **Balance Due: {currency(tenant_id, balance)}**
        """)

        final_payment_mode = st.selectbox("Settle Balance Via", ["Cash", "UPI", "Card", "Bank Transfer", "Other", "Balance Pending"])

        submitted = st.form_submit_button("✅ Complete Check-Out & Generate Invoice", type="primary")

        if submitted:
            checkout_id = new_id("CO-")
            invoice_number = next_invoice_number(tenant_id)
            invoice_id = new_id("INVID-")
            balance_after = 0 if (final_payment_mode != "Balance Pending" and balance > 0) else balance

            # Phase 22: all these writes succeed or fail together.
            with db.transaction() as conn:
                conn.execute(
                    """INSERT INTO checkouts (checkout_id, tenant_id, booking_id, guest_id, room_id, room_charges,
                       restaurant_charges, other_charges, discount, tax, total_amount, advance_paid, balance, created_by)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (checkout_id, tenant_id, b["booking_id"], b["guest_id"], b["room_id"], b["room_tariff"],
                     restaurant_charges, other_charges, total_discount, tax_amount, total_amount,
                     b["advance_payment"], balance, user.get("username", "")),
                )
                conn.execute("UPDATE reservations SET status = 'Checked-Out' WHERE booking_id = ? AND tenant_id = ?",
                            (b["booking_id"], tenant_id))
                conn.execute("UPDATE rooms SET status = 'Cleaning' WHERE room_id = ? AND tenant_id = ?",
                            (b["room_id"], tenant_id))
                conn.execute(
                    "UPDATE guests SET visits = visits + 1, last_visit = CURRENT_DATE WHERE guest_id = ? AND tenant_id = ?",
                    (b["guest_id"], tenant_id),
                )

                if final_payment_mode != "Balance Pending" and balance > 0:
                    conn.execute(
                        """INSERT INTO payments (payment_id, tenant_id, booking_id, guest_id, amount, payment_mode,
                           payment_type, created_by) VALUES (?, ?, ?, ?, ?, ?, 'Final', ?)""",
                        (new_id("PAY-"), tenant_id, b["booking_id"], b["guest_id"], balance, final_payment_mode,
                         user.get("username", "")),
                    )

                conn.execute(
                    """INSERT INTO invoices (invoice_id, tenant_id, invoice_number, booking_id, guest_id, invoice_type,
                       subtotal, discount, tax, total_amount, file_path)
                       VALUES (?, ?, ?, ?, ?, 'Final', ?, ?, ?, ?, ?)""",
                    (invoice_id, tenant_id, invoice_number, b["booking_id"], b["guest_id"], subtotal,
                     total_discount, tax_amount, total_amount, None),
                )

            invoice_data = {
                "invoice_number": invoice_number, "booking_id": b["booking_id"], "guest_name": b["guest_name"],
                "mobile": b["mobile"], "room_number": b["room_number"], "checkin_date": b["checkin_date"],
                "checkout_date": b["checkout_date"], "nights": b["nights"], "subtotal": subtotal,
                "discount": total_discount, "tax": tax_amount, "total_amount": total_amount,
                "advance_paid": b["advance_payment"], "balance": balance_after,
            }
            line_items = [{"description": f"Room Charges ({b['nights']} nights)", "amount": b["room_tariff"]}]
            if restaurant_charges:
                line_items.append({"description": "Restaurant / Room Service", "amount": restaurant_charges})
            if other_charges:
                line_items.append({"description": "Other Charges", "amount": other_charges})

            pdf_path = os.path.join(INVOICE_DIR, f"{invoice_number}.pdf")
            generate_invoice_pdf(tenant_id, invoice_data, line_items, output_path=pdf_path)

            conn2 = get_connection()
            conn2.execute("UPDATE invoices SET file_path = ? WHERE invoice_id = ? AND tenant_id = ?",
                         (pdf_path, invoice_id, tenant_id))
            conn2.commit()
            conn2.close()

            log_audit(tenant_id, user.get("username", ""), "Guest checked out, invoice generated", "checkouts", checkout_id)
            push_notification(tenant_id, "checkout", f"{b['guest_name']} checked out. Invoice {invoice_number} generated.")

            st.session_state["last_checkout"] = {
                **b, **invoice_data, "invoice_number": invoice_number, "pdf_path": pdf_path,
                "room_charges": b["room_tariff"], "restaurant_charges": restaurant_charges,
                "other_charges": other_charges, "advance_paid": b["advance_payment"], "balance": balance_after,
            }
            st.success(f"✅ Check-out complete. Invoice {invoice_number} generated.")
            st.rerun()

    last = st.session_state.get("last_checkout")
    if last and last.get("booking_id") == b.get("booking_id"):
        st.markdown("---")
        c1, c2 = st.columns(2)
        with c1:
            if os.path.exists(last["pdf_path"]):
                with open(last["pdf_path"], "rb") as f:
                    st.download_button("⬇️ Download Invoice PDF", f, file_name=f"{last['invoice_number']}.pdf",
                                       mime="application/pdf")
        with c2:
            message = final_bill_message(tenant_id, last, last["invoice_number"])
            url = build_whatsapp_url(last["mobile"], message, last.get("country_code"))
            if url:
                st.link_button("📱 Send Final Bill on WhatsApp", url)
                log_whatsapp_message(tenant_id, last["booking_id"], last["guest_id"], last["mobile"], "Check-Out",
                                     message, user.get("username", ""), status="Initiated")
