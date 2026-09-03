import datetime as dt

import streamlit as st
import pandas as pd
import plotly.express as px

from database import get_connection
from styles import kpi_card_html
from utils import currency
import auth


def _q(query, params=()):
    conn = get_connection()
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def render():
    st.markdown('<div class="section-title">🏠 Dashboard</div>', unsafe_allow_html=True)
    tenant_id = auth.current_tenant_id()

    today = dt.date.today().isoformat()
    month_start = dt.date.today().replace(day=1).isoformat()

    # ---------------- KPI calculations ----------------
    total_rooms = _q("SELECT COUNT(*) c FROM rooms WHERE tenant_id = ? AND is_active = TRUE", (tenant_id,))[0]["c"]

    if total_rooms == 0:
        st.info("👋 **New here?** Add sample rooms, guests, bookings and more in one click from "
               "**⚙️ Settings → Demo Data** — great for exploring the system before entering real data. "
               "Or just start by adding your own rooms in **🛏️ Room Management**.")

    available_rooms = _q("SELECT COUNT(*) c FROM rooms WHERE tenant_id = ? AND is_active = TRUE AND status = 'Available'",
                         (tenant_id,))[0]["c"]
    occupied_rooms = _q("SELECT COUNT(*) c FROM rooms WHERE tenant_id = ? AND is_active = TRUE AND status = 'Occupied'",
                        (tenant_id,))[0]["c"]
    reserved_rooms = _q("SELECT COUNT(*) c FROM rooms WHERE tenant_id = ? AND is_active = TRUE AND status = 'Reserved'",
                        (tenant_id,))[0]["c"]

    todays_checkins = _q(
        "SELECT COUNT(*) c FROM reservations WHERE tenant_id = ? AND checkin_date = ? AND status IN ('Confirmed','Checked-In')",
        (tenant_id, today))[0]["c"]
    todays_checkouts = _q(
        "SELECT COUNT(*) c FROM reservations WHERE tenant_id = ? AND checkout_date = ? AND status IN ('Checked-In','Checked-Out')",
        (tenant_id, today))[0]["c"]

    occupancy_pct = round((occupied_rooms / total_rooms) * 100, 1) if total_rooms else 0.0

    todays_revenue = _q(
        "SELECT COALESCE(SUM(amount), 0) t FROM payments WHERE tenant_id = ? AND date(payment_date) = ?",
        (tenant_id, today))[0]["t"]
    monthly_revenue = _q(
        "SELECT COALESCE(SUM(amount), 0) t FROM payments WHERE tenant_id = ? AND date(payment_date) >= ?",
        (tenant_id, month_start))[0]["t"]
    pending_payments = _q(
        "SELECT COALESCE(SUM(balance), 0) t FROM reservations WHERE tenant_id = ? AND status IN ('Confirmed','Checked-In')",
        (tenant_id,))[0]["t"]
    total_guests = _q("SELECT COUNT(*) c FROM guests WHERE tenant_id = ?", (tenant_id,))[0]["c"]
    total_bookings = _q("SELECT COUNT(*) c FROM reservations WHERE tenant_id = ?", (tenant_id,))[0]["c"]

    # ---------------- KPI Cards ----------------
    row1 = st.columns(4)
    kpis1 = [
        ("Total Rooms", total_rooms, "#2563eb", "#1e40af"),
        ("Available", available_rooms, "#16a34a", "#15803d"),
        ("Occupied", occupied_rooms, "#dc2626", "#b91c1c"),
        ("Reserved", reserved_rooms, "#d97706", "#b45309"),
    ]
    for col, (label, value, c1, c2) in zip(row1, kpis1):
        col.markdown(kpi_card_html(label, value, c1, c2), unsafe_allow_html=True)

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    row2 = st.columns(4)
    kpis2 = [
        ("Today's Check-ins", todays_checkins, "#0891b2", "#0e7490"),
        ("Today's Check-outs", todays_checkouts, "#7c3aed", "#6d28d9"),
        ("Occupancy %", f"{occupancy_pct}%", "#db2777", "#be185d"),
        ("Today's Revenue", currency(tenant_id, todays_revenue), "#059669", "#047857"),
    ]
    for col, (label, value, c1, c2) in zip(row2, kpis2):
        col.markdown(kpi_card_html(label, value, c1, c2), unsafe_allow_html=True)

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    row3 = st.columns(4)
    kpis3 = [
        ("Monthly Revenue", currency(tenant_id, monthly_revenue), "#4f46e5", "#4338ca"),
        ("Pending Payments", currency(tenant_id, pending_payments), "#ea580c", "#c2410c"),
        ("Total Guests", total_guests, "#0284c7", "#0369a1"),
        ("Total Bookings", total_bookings, "#65a30d", "#4d7c0f"),
    ]
    for col, (label, value, c1, c2) in zip(row3, kpis3):
        col.markdown(kpi_card_html(label, value, c1, c2), unsafe_allow_html=True)

    st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)

    # ---------------- Charts ----------------
    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        st.markdown("##### 📈 Revenue - Last 14 Days")
        rev_rows = _q("""
            SELECT date(payment_date) d, SUM(amount) t FROM payments
            WHERE tenant_id = ? AND date(payment_date) >= CURRENT_DATE - INTERVAL '13 days'
            GROUP BY date(payment_date) ORDER BY d
        """, (tenant_id,))
        if rev_rows:
            df = pd.DataFrame(rev_rows)
            fig = px.bar(df, x="d", y="t", labels={"d": "Date", "t": "Revenue"},
                         color_discrete_sequence=["#2563eb"])
            fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=300)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No payment data yet.")

    with chart_col2:
        st.markdown("##### 🛏️ Room Status Distribution")
        status_rows = _q("SELECT status, COUNT(*) c FROM rooms WHERE tenant_id = ? AND is_active = TRUE GROUP BY status",
                         (tenant_id,))
        if status_rows:
            df = pd.DataFrame(status_rows)
            fig = px.pie(df, names="status", values="c", hole=0.45,
                         color_discrete_sequence=px.colors.qualitative.Set2)
            fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=300)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No rooms added yet.")

    chart_col3, chart_col4 = st.columns(2)

    with chart_col3:
        st.markdown("##### 📊 Booking Trend - Last 30 Days")
        booking_rows = _q("""
            SELECT date(booking_date) d, COUNT(*) c FROM reservations
            WHERE tenant_id = ? AND date(booking_date) >= CURRENT_DATE - INTERVAL '29 days'
            GROUP BY date(booking_date) ORDER BY d
        """, (tenant_id,))
        if booking_rows:
            df = pd.DataFrame(booking_rows)
            fig = px.line(df, x="d", y="c", markers=True, labels={"d": "Date", "c": "Bookings"},
                          color_discrete_sequence=["#7c3aed"])
            fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=300)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No booking data yet.")

    with chart_col4:
        st.markdown("##### 🧾 Booking Source Breakdown")
        source_rows = _q("SELECT booking_source, COUNT(*) c FROM reservations WHERE tenant_id = ? GROUP BY booking_source",
                         (tenant_id,))
        if source_rows:
            df = pd.DataFrame(source_rows)
            fig = px.pie(df, names="booking_source", values="c", hole=0.45,
                        color_discrete_sequence=px.colors.qualitative.Pastel)
            fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=300)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No booking source data yet.")
