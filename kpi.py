import datetime as dt

import streamlit as st
import plotly.express as px
import pandas as pd

from database import get_connection
from utils import currency
import auth


def _range_from_filter(choice, custom_start=None, custom_end=None):
    today = dt.date.today()
    if choice == "Today":
        return today, today
    if choice == "This Week":
        return today - dt.timedelta(days=today.weekday()), today
    if choice == "This Month":
        return today.replace(day=1), today
    if choice == "This Year":
        return today.replace(month=1, day=1), today
    return custom_start, custom_end


def render():
    st.markdown('<div class="section-title">📈 KPI & Business Analytics</div>', unsafe_allow_html=True)
    tenant_id = auth.current_tenant_id()

    c1, c2 = st.columns([1, 2])
    choice = c1.selectbox("Period", ["Today", "This Week", "This Month", "This Year", "Custom Date Range"])
    custom_start = custom_end = None
    if choice == "Custom Date Range":
        with c2:
            cs, ce = st.columns(2)
            custom_start = cs.date_input("From")
            custom_end = ce.date_input("To")

    start, end = _range_from_filter(choice, custom_start, custom_end)
    if not start or not end:
        st.info("Please select a date range.")
        return

    conn = get_connection()

    total_room_nights = conn.execute(
        "SELECT COALESCE(SUM(nights),0) t FROM reservations WHERE tenant_id = ? AND checkin_date BETWEEN ? AND ? AND status != 'Cancelled'",
        (tenant_id, start.isoformat(), end.isoformat()),
    ).fetchone()["t"]

    room_revenue = conn.execute(
        "SELECT COALESCE(SUM(room_tariff),0) t FROM reservations WHERE tenant_id = ? AND checkin_date BETWEEN ? AND ? AND status != 'Cancelled'",
        (tenant_id, start.isoformat(), end.isoformat()),
    ).fetchone()["t"]

    total_rooms = conn.execute("SELECT COUNT(*) c FROM rooms WHERE tenant_id = ? AND is_active = TRUE",
                               (tenant_id,)).fetchone()["c"] or 1
    days_in_range = max((end - start).days + 1, 1)
    available_room_nights = total_rooms * days_in_range

    total_bookings = conn.execute(
        "SELECT COUNT(*) c FROM reservations WHERE tenant_id = ? AND booking_date BETWEEN ? AND ?",
        (tenant_id, start.isoformat(), end.isoformat()),
    ).fetchone()["c"]

    cancelled = conn.execute(
        "SELECT COUNT(*) c FROM reservations WHERE tenant_id = ? AND booking_date BETWEEN ? AND ? AND status = 'Cancelled'",
        (tenant_id, start.isoformat(), end.isoformat()),
    ).fetchone()["c"]

    no_show = conn.execute(
        "SELECT COUNT(*) c FROM reservations WHERE tenant_id = ? AND booking_date BETWEEN ? AND ? AND status = 'No Show'",
        (tenant_id, start.isoformat(), end.isoformat()),
    ).fetchone()["c"]

    total_guests = conn.execute("SELECT COUNT(*) c FROM guests WHERE tenant_id = ?", (tenant_id,)).fetchone()["c"]
    repeat_guests = conn.execute("SELECT COUNT(*) c FROM guests WHERE tenant_id = ? AND visits > 1",
                                 (tenant_id,)).fetchone()["c"]

    collected = conn.execute(
        "SELECT COALESCE(SUM(amount),0) t FROM payments WHERE tenant_id = ? AND date(payment_date) BETWEEN ? AND ?",
        (tenant_id, start.isoformat(), end.isoformat()),
    ).fetchone()["t"]
    billed = conn.execute(
        "SELECT COALESCE(SUM(total_amount),0) t FROM reservations WHERE tenant_id = ? AND checkin_date BETWEEN ? AND ? AND status != 'Cancelled'",
        (tenant_id, start.isoformat(), end.isoformat()),
    ).fetchone()["t"]

    total_expenses = conn.execute(
        "SELECT COALESCE(SUM(amount),0) t FROM expenses WHERE tenant_id = ? AND date BETWEEN ? AND ?",
        (tenant_id, start.isoformat(), end.isoformat()),
    ).fetchone()["t"]

    conn.close()

    occupancy_pct = round((total_room_nights / available_room_nights) * 100, 1) if available_room_nights else 0
    adr = round(room_revenue / total_room_nights, 2) if total_room_nights else 0
    revpar = round(room_revenue / available_room_nights, 2) if available_room_nights else 0
    avg_los = round(total_room_nights / total_bookings, 1) if total_bookings else 0
    avg_booking_value = round(billed / total_bookings, 2) if total_bookings else 0
    cancellation_pct = round((cancelled / total_bookings) * 100, 1) if total_bookings else 0
    noshow_pct = round((no_show / total_bookings) * 100, 1) if total_bookings else 0
    repeat_pct = round((repeat_guests / total_guests) * 100, 1) if total_guests else 0
    collection_eff = round((collected / billed) * 100, 1) if billed else 0
    expense_ratio = round((total_expenses / collected) * 100, 1) if collected else 0
    net_revenue = round(collected - total_expenses, 2)

    metrics = [
        ("Occupancy %", f"{occupancy_pct}%"), ("ADR (Avg Daily Rate)", currency(tenant_id, adr)),
        ("RevPAR", currency(tenant_id, revpar)), ("Avg Length of Stay", f"{avg_los} nights"),
        ("Avg Booking Value", currency(tenant_id, avg_booking_value)), ("Cancellation %", f"{cancellation_pct}%"),
        ("No-show %", f"{noshow_pct}%"), ("Repeat Guest %", f"{repeat_pct}%"),
        ("Collection Efficiency %", f"{collection_eff}%"), ("Expense Ratio %", f"{expense_ratio}%"),
        ("Net Revenue", currency(tenant_id, net_revenue)), ("Total Bookings", total_bookings),
    ]

    for i in range(0, len(metrics), 4):
        cols = st.columns(4)
        for col, (label, value) in zip(cols, metrics[i:i + 4]):
            col.metric(label, value)

    st.markdown("---")
    df = pd.DataFrame({"Metric": ["Collected", "Expenses"], "Amount": [collected, total_expenses]})
    fig = px.bar(df, x="Metric", y="Amount", color="Metric",
                 color_discrete_sequence=["#059669", "#dc2626"])
    fig.update_layout(height=320, margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig, use_container_width=True)
