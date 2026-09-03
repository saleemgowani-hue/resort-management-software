import streamlit as st
import pandas as pd

from database import get_connection, new_id
from utils import log_audit
import auth


def render():
    st.markdown('<div class="section-title">📦 Inventory Management</div>', unsafe_allow_html=True)
    user = st.session_state.get("user", {})
    tenant_id = auth.current_tenant_id()

    tab1, tab2, tab3 = st.tabs(["Stock Overview", "Add Item", "Purchase / Consume"])

    with tab2:
        with st.form("inv_item_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            name = c1.text_input("Item Name *")
            category = c2.text_input("Category", value="Housekeeping Supplies")
            unit = c3.selectbox("Unit", ["pcs", "kg", "litre", "box", "packet", "set"])

            c4, c5 = st.columns(2)
            opening_stock = c4.number_input("Opening Stock", min_value=0.0, value=0.0)
            minimum_stock = c5.number_input("Minimum Stock Level", min_value=0.0, value=5.0)

            if st.form_submit_button("Add Item", type="primary"):
                if not name:
                    st.error("Item name is required.")
                else:
                    conn = get_connection()
                    item_id = new_id("INV-")
                    conn.execute(
                        """INSERT INTO inventory (item_id, tenant_id, name, category, unit, opening_stock,
                           current_stock, minimum_stock) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (item_id, tenant_id, name, category, unit, opening_stock, opening_stock, minimum_stock),
                    )
                    conn.commit()
                    conn.close()
                    log_audit(tenant_id, user.get("username", ""), "Inventory item added", "inventory", item_id)
                    st.success(f"'{name}' added to inventory.")
                    st.rerun()

    with tab3:
        conn = get_connection()
        items = conn.execute("SELECT * FROM inventory WHERE tenant_id = ? ORDER BY name", (tenant_id,)).fetchall()
        conn.close()
        items = [dict(r) for r in items]

        if not items:
            st.info("Add inventory items first.")
        else:
            item_map = {f"{i['name']} ({i['current_stock']} {i['unit']})": i for i in items}
            selected = st.selectbox("Item", list(item_map.keys()))
            item = item_map[selected]

            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Purchase (add stock)**")
                purchase_qty = st.number_input("Quantity Purchased", min_value=0.0, value=0.0, key="purchase_qty")
                purchase_rate = st.number_input("Rate per unit (₹)", min_value=0.0, value=0.0, key="purchase_rate")
                if st.button("➕ Record Purchase") and purchase_qty > 0:
                    conn = get_connection()
                    conn.execute(
                        "INSERT INTO purchases (purchase_id, tenant_id, item_id, quantity, rate, total) VALUES (?, ?, ?, ?, ?, ?)",
                        (new_id("PUR-"), tenant_id, item["item_id"], purchase_qty, purchase_rate,
                         purchase_qty * purchase_rate),
                    )
                    conn.execute("UPDATE inventory SET current_stock = current_stock + ? WHERE item_id = ? AND tenant_id = ?",
                                (purchase_qty, item["item_id"], tenant_id))
                    conn.execute(
                        """INSERT INTO stock_movements (movement_id, tenant_id, item_id, movement_type, quantity)
                           VALUES (?, ?, ?, 'Purchase', ?)""",
                        (new_id("MOV-"), tenant_id, item["item_id"], purchase_qty),
                    )
                    conn.commit()
                    conn.close()
                    log_audit(tenant_id, user.get("username", ""), f"Purchased {purchase_qty} {item['unit']}",
                              "inventory", item["item_id"])
                    st.success("Purchase recorded and stock updated.")
                    st.rerun()

            with c2:
                st.markdown("**Consumption / Adjustment (reduce stock)**")
                consume_qty = st.number_input("Quantity Used", min_value=0.0, value=0.0, key="consume_qty")
                if st.button("➖ Record Consumption") and consume_qty > 0:
                    conn = get_connection()
                    conn.execute("UPDATE inventory SET current_stock = current_stock - ? WHERE item_id = ? AND tenant_id = ?",
                                (consume_qty, item["item_id"], tenant_id))
                    conn.execute(
                        """INSERT INTO stock_movements (movement_id, tenant_id, item_id, movement_type, quantity)
                           VALUES (?, ?, ?, 'Consumption', ?)""",
                        (new_id("MOV-"), tenant_id, item["item_id"], consume_qty),
                    )
                    conn.commit()
                    conn.close()
                    log_audit(tenant_id, user.get("username", ""), f"Consumed {consume_qty} {item['unit']}",
                              "inventory", item["item_id"])
                    st.success("Consumption recorded and stock updated.")
                    st.rerun()

    with tab1:
        conn = get_connection()
        items = conn.execute("SELECT * FROM inventory WHERE tenant_id = ? ORDER BY name", (tenant_id,)).fetchall()
        conn.close()
        items = [dict(r) for r in items]
        if not items:
            st.info("No inventory items yet.")
        else:
            df = pd.DataFrame(items)
            low_stock = df[df["current_stock"] <= df["minimum_stock"]]
            if not low_stock.empty:
                st.warning(f"⚠️ {len(low_stock)} item(s) at or below minimum stock level: "
                           f"{', '.join(low_stock['name'].tolist())}")

            display_df = df[["name", "category", "unit", "current_stock", "minimum_stock"]]
            display_df.columns = ["Item", "Category", "Unit", "Current Stock", "Min Level"]
            st.dataframe(display_df, use_container_width=True, hide_index=True)
