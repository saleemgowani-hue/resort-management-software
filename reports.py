import datetime as dt
import io

import streamlit as st
import pandas as pd

from database import get_connection
from utils import fmt_date
from pdf_generator import generate_simple_report_pdf
import auth

# Each entry: (sql, headers, needs_date_filter). Every query already has a
# `tenant_id = ?` predicate baked in as the FIRST placeholder; date params
# (if needs_date_filter) are appended after it.
REPORT_DEFS = {
    "Daily Booking Report": (
        "SELECT booking_id, guest_name, mobile, checkin_date, checkout_date, status, total_amount "
        "FROM reservations WHERE tenant_id = ? AND booking_date BETWEEN ? AND ? ORDER BY booking_date DESC",
        ["Booking ID", "Guest", "Mobile", "Check-in", "Check-out", "Status", "Total"], True,
    ),
    "Cancelled Bookings": (
        "SELECT booking_id, guest_name, mobile, checkin_date, checkout_date, total_amount "
        "FROM reservations WHERE tenant_id = ? AND status = 'Cancelled' AND booking_date BETWEEN ? AND ?",
        ["Booking ID", "Guest", "Mobile", "Check-in", "Check-out", "Total"], True,
    ),
    "Booking Source Report": (
        "SELECT booking_source, COUNT(*) as bookings, SUM(total_amount) as revenue "
        "FROM reservations WHERE tenant_id = ? AND booking_date BETWEEN ? AND ? GROUP BY booking_source",
        ["Source", "Bookings", "Revenue"], True,
    ),
    "Revenue Report (Payments)": (
        "SELECT date(payment_date) as d, payment_mode, SUM(amount) as amount "
        "FROM payments WHERE tenant_id = ? AND date(payment_date) BETWEEN ? AND ? GROUP BY d, payment_mode ORDER BY d DESC",
        ["Date", "Mode", "Amount"], True,
    ),
    "Room-wise Occupancy": (
        "SELECT rm.room_number, COUNT(res.booking_id) as bookings, SUM(res.nights) as nights_booked "
        "FROM rooms rm LEFT JOIN reservations res ON rm.room_id = res.room_id "
        "AND res.checkin_date BETWEEN ? AND ? AND res.status != 'Cancelled' "
        "WHERE rm.tenant_id = ? "
        "GROUP BY rm.room_number ORDER BY rm.room_number",
        ["Room No", "Bookings", "Nights Booked"], "room_occupancy",
    ),
    "Guest List": (
        "SELECT name, mobile, city, visits, last_visit FROM guests "
        "WHERE tenant_id = ? AND created_at BETWEEN ? AND ? ORDER BY created_at DESC",
        ["Name", "Mobile", "City", "Visits", "Last Visit"], True,
    ),
    "Returning Guests": (
        "SELECT name, mobile, city, visits, last_visit FROM guests WHERE tenant_id = ? AND visits > 1 ORDER BY visits DESC",
        ["Name", "Mobile", "City", "Visits", "Last Visit"], False,
    ),
    "Pending Payments": (
        "SELECT booking_id, guest_name, mobile, total_amount, advance_payment, balance FROM reservations "
        "WHERE tenant_id = ? AND balance > 0 AND status IN ('Confirmed','Checked-In')",
        ["Booking ID", "Guest", "Mobile", "Total", "Paid", "Balance"], False,
    ),
    "Expense Report": (
        "SELECT date, category, description, amount, payment_mode, vendor FROM expenses "
        "WHERE tenant_id = ? AND date BETWEEN ? AND ? ORDER BY date DESC",
        ["Date", "Category", "Description", "Amount", "Mode", "Vendor"], True,
    ),
}


def render():
    st.markdown('<div class="section-title">📊 Reports Hub</div>', unsafe_allow_html=True)
    tenant_id = auth.current_tenant_id()

    c1, c2, c3 = st.columns([2, 1, 1])
    report_name = c1.selectbox("Select Report", list(REPORT_DEFS.keys()))
    start_date = c2.date_input("From", value=dt.date.today().replace(day=1))
    end_date = c3.date_input("To", value=dt.date.today())

    search = st.text_input("🔍 Search within results")

    query, headers, needs_date_filter = REPORT_DEFS[report_name]
    conn = get_connection()
    if needs_date_filter == "room_occupancy":
        # date params come before the tenant_id predicate in this particular query's WHERE clause order
        rows = conn.execute(query, (start_date.isoformat(), end_date.isoformat(), tenant_id)).fetchall()
    elif needs_date_filter:
        rows = conn.execute(query, (tenant_id, start_date.isoformat(), end_date.isoformat())).fetchall()
    else:
        rows = conn.execute(query, (tenant_id,)).fetchall()
    conn.close()

    data = [dict(r) for r in rows]
    if not data:
        st.info("No records found for this report / date range.")
        return

    df = pd.DataFrame(data)
    # Nicely format any date-like columns
    for col in df.columns:
        if "date" in col.lower() or col.lower() == "d":
            df[col] = df[col].apply(fmt_date)

    if search:
        mask = df.apply(lambda row: row.astype(str).str.contains(search, case=False).any(), axis=1)
        df = df[mask]

    display_df = df.copy()
    display_df.columns = headers[: len(display_df.columns)]
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    numeric_cols = [c for c in display_df.columns if display_df[c].dtype.kind in "if"]
    if numeric_cols:
        totals = " | ".join(f"{c}: {display_df[c].sum():,.2f}" for c in numeric_cols)
        st.caption(f"**Totals:** {totals}")

    st.markdown("##### Export")
    c1, c2 = st.columns(2)

    with c1:
        excel_buf = io.BytesIO()
        with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
            display_df.to_excel(writer, index=False, sheet_name="Report")
        st.download_button("⬇️ Export to Excel", excel_buf.getvalue(),
                           file_name=f"{report_name.replace(' ', '_')}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    with c2:
        rows_for_pdf = display_df.astype(str).values.tolist()
        pdf_bytes = generate_simple_report_pdf(tenant_id, report_name, list(display_df.columns), rows_for_pdf)
        st.download_button("⬇️ Export to PDF", pdf_bytes, file_name=f"{report_name.replace(' ', '_')}.pdf",
                           mime="application/pdf")
