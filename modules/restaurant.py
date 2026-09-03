import json

import streamlit as st
import pandas as pd

from database import get_connection, new_id
from utils import currency, log_audit, get_resort_profile
from config import DEFAULT_TAX_PERCENT
import auth


def _menu_items(tenant_id):
    conn = get_connection()
    rows = conn.execute("SELECT * FROM restaurant_items WHERE tenant_id = ? AND is_active = TRUE ORDER BY category, name",
                        (tenant_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _occupied_rooms_with_bookings(tenant_id):
    conn = get_connection()
    rows = conn.execute("""
        SELECT res.booking_id, res.guest_name, rm.room_id, rm.room_number FROM reservations res
        JOIN rooms rm ON res.room_id = rm.room_id
        WHERE res.tenant_id = ? AND res.status = 'Checked-In'
        ORDER BY rm.room_number
    """, (tenant_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def render():
    st.markdown('<div class="section-title">🍽️ Restaurant / Room Service</div>', unsafe_allow_html=True)
    user = st.session_state.get("user", {})
    tenant_id = auth.current_tenant_id()
    profile = get_resort_profile(tenant_id)

    tab1, tab2, tab3 = st.tabs(["New Order", "Order History", "Menu Management"])

    with tab3:
        with st.form("menu_item_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            name = c1.text_input("Item Name *")
            category = c2.text_input("Category", value="Main Course")
            rate = c3.number_input("Rate (₹)", min_value=0.0, value=100.0, step=10.0)
            tax_percent = st.number_input("Tax %", min_value=0.0, value=5.0, step=1.0)
            if st.form_submit_button("Add Menu Item", type="primary"):
                if name:
                    conn = get_connection()
                    conn.execute(
                        "INSERT INTO restaurant_items (item_id, tenant_id, name, category, rate, tax_percent) VALUES (?, ?, ?, ?, ?, ?)",
                        (new_id("ITM-"), tenant_id, name, category, rate, tax_percent),
                    )
                    conn.commit()
                    conn.close()
                    st.success(f"'{name}' added to menu.")
                    st.rerun()
                else:
                    st.error("Item name is required.")

        items = _menu_items(tenant_id)
        if items:
            df = pd.DataFrame(items)[["name", "category", "rate", "tax_percent"]]
            df.columns = ["Item", "Category", "Rate", "Tax %"]
            st.dataframe(df, use_container_width=True, hide_index=True)

    with tab1:
        items = _menu_items(tenant_id)
        rooms = _occupied_rooms_with_bookings(tenant_id)

        if not items:
            st.warning("Please add menu items first (Menu Management tab).")
            return

        order_target = st.radio("Order For", ["Room (post to bill)", "Restaurant Table (walk-in)"], horizontal=True)

        booking_id = room_id = None
        guest_name = table_number = ""

        if order_target.startswith("Room"):
            if not rooms:
                st.info("No occupied rooms right now.")
                return
            room_map = {f"Room {r['room_number']} - {r['guest_name']}": r for r in rooms}
            selected = st.selectbox("Select Room", list(room_map.keys()))
            r = room_map[selected]
            booking_id, room_id, guest_name = r["booking_id"], r["room_id"], r["guest_name"]
        else:
            table_number = st.text_input("Table Number")
            guest_name = st.text_input("Guest Name (optional)")

        st.markdown("##### Select Items")
        item_map = {f"{i['name']} - {currency(tenant_id, i['rate'])}": i for i in items}
        selected_items = st.multiselect("Menu Items", list(item_map.keys()))

        order_lines = []
        subtotal = 0.0
        tax_total = 0.0
        for label in selected_items:
            it = item_map[label]
            qty = st.number_input(f"Qty - {it['name']}", min_value=1, value=1, key=f"qty_{it['item_id']}")
            line_amount = it["rate"] * qty
            line_tax = round(line_amount * it["tax_percent"] / 100, 2)
            subtotal += line_amount
            tax_total += line_tax
            order_lines.append({"item_id": it["item_id"], "name": it["name"], "qty": qty,
                                "rate": it["rate"], "tax": line_tax, "amount": line_amount})

        discount = st.number_input("Discount (₹)", min_value=0.0, value=0.0, step=10.0)
        total_amount = round(subtotal - discount + tax_total, 2)
        st.markdown(f"**Subtotal:** {currency(tenant_id, subtotal)} | **Tax:** {currency(tenant_id, tax_total)} | "
                   f"**Total: {currency(tenant_id, total_amount)}**")

        if st.button("💾 Save Order", type="primary", disabled=not order_lines):
            conn = get_connection()
            order_id = new_id("ORD-")
            post_to_room = bool(booking_id)
            conn.execute(
                """INSERT INTO restaurant_orders (order_id, tenant_id, table_number, room_id, booking_id, guest_name,
                   items_json, subtotal, discount, tax, total_amount, payment_status, posted_to_room, created_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (order_id, tenant_id, table_number, room_id, booking_id, guest_name, json.dumps(order_lines), subtotal,
                 discount, tax_total, total_amount,
                 "Posted to Room" if post_to_room else "Paid", post_to_room, user.get("username", "")),
            )
            conn.commit()
            conn.close()
            log_audit(tenant_id, user.get("username", ""), "Restaurant order created", "restaurant_orders", order_id)
            if post_to_room:
                st.success(f"Order saved and posted to Room bill for {guest_name}.")
            else:
                st.success("Walk-in order saved.")
            st.rerun()

    with tab2:
        conn = get_connection()
        rows = conn.execute("SELECT * FROM restaurant_orders WHERE tenant_id = ? ORDER BY order_date DESC LIMIT 200",
                            (tenant_id,)).fetchall()
        conn.close()
        orders = [dict(r) for r in rows]
        if not orders:
            st.info("No orders yet.")
        else:
            df = pd.DataFrame(orders)
            display_df = df[["order_id", "guest_name", "table_number", "total_amount", "payment_status", "order_date"]]
            display_df.columns = ["Order ID", "Guest", "Table", "Total", "Status", "Date"]
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            st.caption(f"Total Restaurant Revenue: {currency(tenant_id, df['total_amount'].sum())}")
