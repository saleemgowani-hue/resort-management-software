import os

import streamlit as st
import pandas as pd

from config import PAYMENT_MODES, DATA_DIR
from database import get_connection, new_id
from utils import currency, fmt_date, log_audit
from whatsapp import build_whatsapp_url, payment_receipt_message, log_whatsapp_message
from pdf_generator import generate_receipt_pdf
import auth

RECEIPT_DIR = os.path.join(DATA_DIR, "receipts")
os.makedirs(RECEIPT_DIR, exist_ok=True)


def _active_bookings(tenant_id):
    conn = get_connection()
    rows = conn.execute("""
        SELECT booking_id, guest_name, mobile, country_code, guest_id, total_amount, advance_payment, balance
        FROM reservations WHERE tenant_id = ? AND status IN ('Confirmed', 'Checked-In') AND balance > 0
        ORDER BY created_at DESC
    """, (tenant_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _recent_payments(tenant_id):
    conn = get_connection()
    rows = conn.execute("""
        SELECT p.*, res.guest_name FROM payments p
        LEFT JOIN reservations res ON p.booking_id = res.booking_id
        WHERE p.tenant_id = ?
        ORDER BY p.payment_date DESC LIMIT 200
    """, (tenant_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def render():
    st.markdown('<div class="section-title">💳 Billing & Payments</div>', unsafe_allow_html=True)
    user = st.session_state.get("user", {})
    tenant_id = auth.current_tenant_id()

    tab1, tab2 = st.tabs(["Record Payment", "Payment History"])

    with tab1:
        bookings = _active_bookings(tenant_id)
        if not bookings:
            st.info("No bookings currently have a pending balance.")
        else:
            booking_map = {f"{b['booking_id']} - {b['guest_name']} (Balance: {currency(tenant_id, b['balance'])})": b
                           for b in bookings}
            selected_label = st.selectbox("Select Booking", list(booking_map.keys()))
            b = booking_map[selected_label]

            c1, c2, c3 = st.columns(3)
            c1.metric("Total Amount", currency(tenant_id, b["total_amount"]))
            c2.metric("Paid So Far", currency(tenant_id, b["advance_payment"]))
            c3.metric("Balance Due", currency(tenant_id, b["balance"]))

            with st.form("payment_form"):
                c1, c2 = st.columns(2)
                amount = c1.number_input("Amount Received (₹)", min_value=0.0, max_value=float(b["balance"]) or 1e9,
                                          value=float(b["balance"]), step=100.0)
                payment_mode = c2.selectbox("Payment Mode", PAYMENT_MODES)
                reference_no = st.text_input("Reference No. (UPI/Txn ID, optional)")
                remarks = st.text_input("Remarks")

                if st.form_submit_button("💰 Record Payment", type="primary"):
                    conn = get_connection()
                    payment_id = new_id("PAY-")
                    conn.execute(
                        """INSERT INTO payments (payment_id, tenant_id, booking_id, guest_id, amount, payment_mode,
                           payment_type, reference_no, remarks, created_by)
                           VALUES (?, ?, ?, ?, ?, ?, 'Partial', ?, ?, ?)""",
                        (payment_id, tenant_id, b["booking_id"], b["guest_id"], amount, payment_mode, reference_no,
                         remarks, user.get("username", "")),
                    )
                    new_advance = b["advance_payment"] + amount
                    new_balance = b["total_amount"] - new_advance
                    conn.execute(
                        "UPDATE reservations SET advance_payment = ?, balance = ? WHERE booking_id = ? AND tenant_id = ?",
                        (new_advance, new_balance, b["booking_id"], tenant_id))
                    conn.commit()
                    conn.close()

                    log_audit(tenant_id, user.get("username", ""), f"Payment recorded: {currency(tenant_id, amount)}",
                              "payments", payment_id)

                    receipt_data = {"receipt_no": payment_id, "booking_id": b["booking_id"],
                                     "guest_name": b["guest_name"], "amount": amount, "payment_mode": payment_mode,
                                     "date": None, "remarks": remarks}
                    pdf_path = os.path.join(RECEIPT_DIR, f"{payment_id}.pdf")
                    generate_receipt_pdf(tenant_id, receipt_data, output_path=pdf_path)

                    st.session_state["last_payment"] = {**receipt_data, "mobile": b["mobile"],
                                                          "country_code": b.get("country_code"),
                                                          "guest_id": b["guest_id"], "pdf_path": pdf_path}
                    st.success(f"Payment of {currency(tenant_id, amount)} recorded successfully.")
                    st.rerun()

        last = st.session_state.get("last_payment")
        if last:
            st.markdown("---")
            c1, c2 = st.columns(2)
            with c1:
                if os.path.exists(last["pdf_path"]):
                    with open(last["pdf_path"], "rb") as f:
                        st.download_button("⬇️ Download Receipt PDF", f, file_name=f"{last['receipt_no']}.pdf",
                                           mime="application/pdf")
            with c2:
                message = payment_receipt_message(tenant_id, last, last["guest_name"])
                url = build_whatsapp_url(last["mobile"], message, last.get("country_code"))
                if url:
                    st.link_button("📱 Send Payment Receipt on WhatsApp", url)
                    log_whatsapp_message(tenant_id, last["booking_id"], last["guest_id"], last["mobile"],
                                         "Payment Receipt", message, user.get("username", ""), status="Initiated")

    with tab2:
        payments = _recent_payments(tenant_id)
        if not payments:
            st.info("No payments recorded yet.")
        else:
            df = pd.DataFrame(payments)
            df["payment_date"] = df["payment_date"].apply(lambda x: str(x)[:16])
            display_df = df[["payment_id", "booking_id", "guest_name", "amount", "payment_mode",
                             "payment_type", "payment_date"]]
            display_df.columns = ["Payment ID", "Booking ID", "Guest", "Amount", "Mode", "Type", "Date/Time"]
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            st.caption(f"Total Collected: {currency(tenant_id, df['amount'].sum())}")
