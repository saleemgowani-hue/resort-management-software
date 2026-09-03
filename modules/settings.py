import io
import json
import os

import streamlit as st
import pandas as pd

from config import ASSETS_DIR, USER_ROLES
from database import get_connection, is_demo_tenant
from utils import get_resort_profile, log_audit, fmt_date
import auth


def _demo_guard(tenant_id) -> bool:
    """Returns True (and shows a message) if this tenant is the shared
    platform Demo account, which must never have its settings/users
    changed (Phase 9 requirement)."""
    if is_demo_tenant(tenant_id):
        st.warning("🔒 This is the shared **Demo** account. Settings, backups and user management are "
                   "disabled here so every visitor sees the same clean demo. Sign up for your own free "
                   "account to unlock these.")
        return True
    return False


def render():
    st.markdown('<div class="section-title">⚙️ Settings</div>', unsafe_allow_html=True)
    user = st.session_state.get("user", {})
    tenant_id = auth.current_tenant_id()
    role = user.get("role", "ADMIN")
    profile = get_resort_profile(tenant_id)
    is_demo = is_demo_tenant(tenant_id)

    if role == "ADMIN":
        tab1, tab2, tab3, tab4, tab5 = st.tabs(
            ["Resort Profile", "System Settings", "Data Export", "Demo Data", "User Management"]
        )
    else:
        tab1, tab2, tab3, tab4 = st.tabs(["Resort Profile", "System Settings", "Data Export", "Demo Data"])
        tab5 = None

    with tab1:
        if _demo_guard(tenant_id):
            st.text_input("Resort Name", value=profile.get("resort_name", ""), disabled=True)
        else:
            with st.form("resort_profile_form"):
                c1, c2 = st.columns(2)
                resort_name = c1.text_input("Resort Name", value=profile.get("resort_name", ""))
                mobile = c2.text_input("Mobile", value=profile.get("mobile", ""))

                c3, c4 = st.columns(2)
                whatsapp_number = c3.text_input("WhatsApp Number", value=profile.get("whatsapp_number", "") or "")
                email = c4.text_input("Email", value=profile.get("email", "") or "")

                c5, c6 = st.columns(2)
                gst_number = c5.text_input("GST Number", value=profile.get("gst_number", "") or "")
                website = c6.text_input("Website", value=profile.get("website", "") or "")

                address = st.text_area("Address", value=profile.get("address", "") or "")
                invoice_footer = st.text_area("Invoice Footer", value=profile.get("invoice_footer", "") or "")
                terms = st.text_area("Terms & Conditions", value=profile.get("terms_conditions", "") or "")

                logo_file = st.file_uploader("Upload Logo (PNG/JPG)", type=["png", "jpg", "jpeg"])

                if st.form_submit_button("💾 Save Resort Profile", type="primary"):
                    conn = get_connection()
                    conn.execute(
                        """UPDATE resort_profile SET resort_name=?, mobile=?, whatsapp_number=?, email=?,
                           gst_number=?, website=?, address=?, invoice_footer=?, terms_conditions=? WHERE tenant_id=?""",
                        (resort_name, mobile, whatsapp_number, email, gst_number, website, address,
                         invoice_footer, terms, tenant_id),
                    )
                    if logo_file is not None:
                        os.makedirs(ASSETS_DIR, exist_ok=True)
                        tenant_logo_path = os.path.join(ASSETS_DIR, f"logo_{tenant_id}.png")
                        with open(tenant_logo_path, "wb") as f:
                            f.write(logo_file.getbuffer())
                        conn.execute("UPDATE resort_profile SET logo_path = ? WHERE tenant_id = ?",
                                    (tenant_logo_path, tenant_id))
                    conn.commit()
                    conn.close()
                    log_audit(tenant_id, user.get("username", ""), "Resort profile updated", "settings", "")
                    st.success("Resort profile saved.")
                    st.rerun()

            logo_path = profile.get("logo_path")
            if logo_path and os.path.exists(logo_path):
                st.image(logo_path, width=120, caption="Current Logo")

    with tab2:
        if not _demo_guard(tenant_id):
            with st.form("system_settings_form"):
                c1, c2 = st.columns(2)
                currency_symbol = c1.text_input("Currency Symbol", value=profile.get("currency_symbol", "₹"))
                tax_percent = c2.number_input("Default Tax/GST %", min_value=0.0,
                                               value=float(profile.get("tax_percent", 12.0)), step=0.5)

                c3, c4 = st.columns(2)
                invoice_prefix = c3.text_input("Invoice Number Prefix", value=profile.get("invoice_prefix", "INV"))
                whatsapp_country_code = c4.text_input("Default WhatsApp Country Code",
                                                        value=profile.get("whatsapp_country_code", "+91"))

                if st.form_submit_button("💾 Save System Settings", type="primary"):
                    conn = get_connection()
                    conn.execute(
                        """UPDATE resort_profile SET currency_symbol=?, tax_percent=?, invoice_prefix=?,
                           whatsapp_country_code=? WHERE tenant_id=?""",
                        (currency_symbol, tax_percent, invoice_prefix, whatsapp_country_code, tenant_id),
                    )
                    conn.commit()
                    conn.close()
                    log_audit(tenant_id, user.get("username", ""), "System settings updated", "settings", "")
                    st.success("System settings saved.")
                    st.rerun()

    with tab3:
        st.markdown("##### Export Your Data")
        st.caption("Downloads a JSON snapshot of everything belonging to YOUR resort only — rooms, guests, "
                   "bookings, staff, payments, etc. This never includes any other tenant's data. "
                   "(A shared multi-tenant database can't safely offer a raw whole-database backup/restore "
                   "to individual tenants — that used to copy the SQLite file directly in the single-tenant "
                   "build, which is no longer possible or safe now that many resorts share one database.)")

        if _demo_guard(tenant_id):
            pass
        else:
            if st.button("📦 Export My Data as JSON"):
                tables = ["resort_profile", "rooms", "room_types", "guests", "reservations", "checkins",
                          "checkouts", "invoices", "payments", "restaurant_items", "restaurant_orders",
                          "housekeeping", "staff", "attendance", "suppliers", "inventory", "purchases",
                          "expenses", "whatsapp_logs"]
                conn = get_connection()
                snapshot = {}
                for t in tables:
                    rows = conn.execute(f"SELECT * FROM {t} WHERE tenant_id = ?", (tenant_id,)).fetchall()
                    snapshot[t] = [dict(r) for r in rows]
                conn.close()

                json_bytes = json.dumps(snapshot, indent=2, default=str).encode("utf-8")
                log_audit(tenant_id, user.get("username", ""), "Data export downloaded", "settings", "")
                st.download_button("⬇️ Download JSON Export", json_bytes,
                                   file_name=f"resort_data_export_{tenant_id}.json", mime="application/json")

    with tab4:
        import demo_data

        st.markdown("##### Sample / Demo Data")
        st.caption("Populate YOUR resort account with realistic sample rooms, guests, bookings, staff, "
                   "inventory and expenses — useful for exploring the software before entering real data.")

        if _demo_guard(tenant_id):
            pass
        elif demo_data.demo_data_exists(tenant_id):
            st.success("✅ Demo data is currently loaded in your account.")
            st.warning("⚠️ Clearing demo data will permanently delete ALL rooms, guests, bookings, staff, "
                       "inventory and expense records in YOUR account. Your login, resort profile and "
                       "licence are kept.")
            confirm_clear = st.checkbox("I understand this will delete all current data.")
            if st.button("🗑️ Clear Demo Data", type="secondary", disabled=not confirm_clear):
                success, message = demo_data.clear_demo_data(tenant_id)
                log_audit(tenant_id, user.get("username", ""), "Demo data cleared", "settings", "")
                st.success(message)
                st.rerun()
        else:
            st.info("No demo data loaded yet. This is a good option right after signing up, so you can "
                   "explore every module before entering your real resort's data.")
            if st.button("✨ Add Demo Data", type="primary"):
                success, message = demo_data.seed_demo_data(tenant_id, created_by=user.get("username", "system"))
                if success:
                    log_audit(tenant_id, user.get("username", ""), "Demo data added", "settings", "")
                    st.success(message)
                    st.balloons()
                    st.rerun()
                else:
                    st.warning(message)

    if tab5 is not None:
        with tab5:
            if _demo_guard(tenant_id):
                pass
            else:
                st.markdown("##### Staff Logins")
                st.caption("Add additional logins for your team. They share this resort's licence and data — "
                           "each just has their own username, password, and role-based menu access. This is "
                           "the correct way to add more users; the public Sign Up form creates a brand new, "
                           "separate resort account instead.")

                with st.expander("➕ Add New Staff Login", expanded=False):
                    with st.form("add_staff_user_form", clear_on_submit=True):
                        c1, c2 = st.columns(2)
                        full_name = c1.text_input("Full Name *")
                        mobile_no = c2.text_input("Mobile Number")

                        c3, c4 = st.columns(2)
                        email_addr = c3.text_input("Email")
                        role_choice = c4.selectbox("Role *", [r for r in USER_ROLES if r != "ADMIN"] + ["ADMIN"])

                        c5, c6, c7 = st.columns(3)
                        username_new = c5.text_input("Username *")
                        password_new = c6.text_input("Password *", type="password")
                        confirm_new = c7.text_input("Confirm Password *", type="password")

                        if st.form_submit_button("Create Staff Login", type="primary"):
                            success, message = auth.create_staff_user(
                                tenant_id, full_name, mobile_no, email_addr, username_new, password_new,
                                confirm_new, role_choice,
                            )
                            if success:
                                log_audit(tenant_id, user.get("username", ""),
                                          f"Staff user created: {username_new} ({role_choice})", "users", "")
                                st.success(message)
                                st.rerun()
                            else:
                                st.error(message)

                st.markdown("##### All Logins")
                users = auth.list_users(tenant_id)
                if users:
                    df = pd.DataFrame(users)
                    df["created_at"] = df["created_at"].apply(lambda x: str(x)[:16])
                    df["Status"] = df["is_active"].apply(lambda v: "Active" if v else "Disabled")
                    display_df = df[["username", "full_name", "role", "email", "mobile", "Status", "created_at"]]
                    display_df.columns = ["Username", "Name", "Role", "Email", "Mobile", "Status", "Created"]
                    st.dataframe(display_df, use_container_width=True, hide_index=True)

                    st.markdown("##### Manage a Login")
                    user_map = {f"{u['username']} ({u['role']})": u for u in users}
                    selected_label = st.selectbox("Select User", list(user_map.keys()))
                    selected_user = user_map[selected_label]

                    if selected_user["username"] == user.get("username"):
                        st.caption("This is your own login — sign in as another Admin to disable or reset it.")
                    else:
                        c1, c2 = st.columns(2)
                        with c1:
                            if selected_user["is_active"]:
                                if st.button("🚫 Disable This Login"):
                                    auth.set_user_active(tenant_id, selected_user["user_id"], False)
                                    log_audit(tenant_id, user.get("username", ""),
                                              f"Disabled login: {selected_user['username']}",
                                              "users", selected_user["user_id"])
                                    st.success(f"{selected_user['username']} has been disabled.")
                                    st.rerun()
                            else:
                                if st.button("✅ Re-enable This Login"):
                                    auth.set_user_active(tenant_id, selected_user["user_id"], True)
                                    log_audit(tenant_id, user.get("username", ""),
                                              f"Re-enabled login: {selected_user['username']}",
                                              "users", selected_user["user_id"])
                                    st.success(f"{selected_user['username']} has been re-enabled.")
                                    st.rerun()
                        with c2:
                            new_pw = st.text_input("New Password", type="password", key="reset_pw")
                            if st.button("🔑 Reset Password") and new_pw:
                                success, message = auth.reset_user_password(tenant_id, selected_user["user_id"], new_pw)
                                if success:
                                    log_audit(tenant_id, user.get("username", ""),
                                              f"Password reset: {selected_user['username']}",
                                              "users", selected_user["user_id"])
                                    st.success(message)
                                else:
                                    st.error(message)
