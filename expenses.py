import datetime as dt

import streamlit as st
import pandas as pd

from config import EXPENSE_CATEGORIES, PAYMENT_MODES
from database import get_connection, new_id
from utils import currency, fmt_date, log_audit
import auth


def render():
    st.markdown('<div class="section-title">💰 Expense Management</div>', unsafe_allow_html=True)
    user = st.session_state.get("user", {})
    tenant_id = auth.current_tenant_id()

    tab1, tab2 = st.tabs(["Expense List", "Add Expense"])

    with tab2:
        with st.form("expense_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            date = c1.date_input("Date", value=dt.date.today())
            category = c2.selectbox("Category", EXPENSE_CATEGORIES)
            amount = c3.number_input("Amount (₹)", min_value=0.0, value=0.0, step=100.0)

            c4, c5 = st.columns(2)
            payment_mode = c4.selectbox("Payment Mode", PAYMENT_MODES)
            vendor = c5.text_input("Vendor")

            description = st.text_area("Description")
            remarks = st.text_input("Remarks")

            if st.form_submit_button("Save Expense", type="primary"):
                if amount <= 0:
                    st.error("Please enter a valid amount.")
                else:
                    conn = get_connection()
                    expense_id = new_id("EXP-")
                    conn.execute(
                        """INSERT INTO expenses (expense_id, tenant_id, date, category, description, amount,
                           payment_mode, vendor, remarks, created_by)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (expense_id, tenant_id, date.isoformat(), category, description, amount, payment_mode,
                         vendor, remarks, user.get("username", "")),
                    )
                    conn.commit()
                    conn.close()
                    log_audit(tenant_id, user.get("username", ""), f"Expense recorded: {currency(tenant_id, amount)}",
                              "expenses", expense_id)
                    st.success(f"Expense of {currency(tenant_id, amount)} recorded.")
                    st.rerun()

    with tab1:
        c1, c2 = st.columns(2)
        start_date = c1.date_input("From", value=dt.date.today().replace(day=1), key="exp_start")
        end_date = c2.date_input("To", value=dt.date.today(), key="exp_end")

        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM expenses WHERE tenant_id = ? AND date BETWEEN ? AND ? ORDER BY date DESC",
            (tenant_id, start_date.isoformat(), end_date.isoformat()),
        ).fetchall()
        conn.close()
        expenses = [dict(r) for r in rows]

        if not expenses:
            st.info("No expenses in this date range.")
        else:
            df = pd.DataFrame(expenses)
            df["date"] = df["date"].apply(fmt_date)
            category_totals = df.groupby("category")["amount"].sum()

            display_df = df[["date", "category", "description", "amount", "payment_mode", "vendor"]]
            display_df.columns = ["Date", "Category", "Description", "Amount", "Mode", "Vendor"]
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            st.metric("Total Expenses", currency(tenant_id, df["amount"].sum()))

            st.markdown("##### By Category")
            st.bar_chart(category_totals)
