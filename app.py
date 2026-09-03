"""
app.py
SN SOFTECH SOLUTIONS - RESORT MANAGEMENT SYSTEM (Multi-Tenant SaaS)
Main Streamlit entry point: PostgreSQL schema init, sign up (creates a new
isolated tenant every time) / sign in, immediate licence-key gating (no
free trial), a shared read-only-ish Demo account (Phase 9), and the
professional multicolour-sidebar dashboard shell.
"""

import datetime as dt

import streamlit as st

from config import APP_TITLE, COMPANY_NAME, PRODUCT_NAME, DEMO_USERNAME, DEMO_PASSWORD
from database import init_db, get_connection, create_tenant, is_demo_tenant, new_id
import auth
import license as licence_engine
from styles import inject_css, SIDEBAR_COLORS
from utils import get_resort_profile

st.set_page_config(page_title=APP_TITLE, page_icon="🏨", layout="wide", initial_sidebar_state="expanded")

init_db()
inject_css()

MENU_ITEMS = [
    ("dashboard", "🏠 Dashboard"),
    ("reservations", "🛎️ Reservations"),
    ("rooms", "🛏️ Room Management"),
    ("guests", "👤 Guest Management"),
    ("checkin", "🧾 Check-In"),
    ("checkout", "🚪 Check-Out"),
    ("billing", "💳 Billing & Payments"),
    ("restaurant", "🍽️ Restaurant / Room Service"),
    ("housekeeping", "🧹 Housekeeping"),
    ("staff", "👨‍💼 Staff Management"),
    ("attendance", "📅 Attendance"),
    ("inventory", "📦 Inventory"),
    ("expenses", "💰 Expenses"),
    ("reports", "📊 Reports"),
    ("kpi", "📈 KPI & Analytics"),
    ("whatsapp", "📱 WhatsApp Center"),
    ("notifications", "🔔 Notifications"),
    ("settings", "⚙️ Settings"),
    ("licence", "🔐 Licence"),
]


# ---------------------------------------------------------------------------
# PHASE 9: SHARED PLATFORM DEMO ACCOUNT
# Created once, idempotently, on first startup. Fixed credentials, its own
# isolated tenant, pre-seeded sample data, and a licence that never expires
# (10 years) so a prospect can always click straight in without activating
# a key. Settings/User Management block all changes for this tenant (see
# modules/settings.py's _demo_guard).
# ---------------------------------------------------------------------------
def ensure_demo_tenant():
    if auth.username_exists(DEMO_USERNAME):
        return  # already bootstrapped

    tenant_id = create_tenant("SN Softech Demo Resort", is_demo=True)

    conn = get_connection()
    conn.execute(
        """INSERT INTO users (user_id, tenant_id, username, email, mobile, full_name,
           password_hash, role, is_active) VALUES (?, ?, ?, ?, ?, ?, ?, 'ADMIN', TRUE)""",
        (new_id("USR-"), tenant_id, DEMO_USERNAME, None, "", "Demo Explorer",
         auth.hash_password(DEMO_PASSWORD)),
    )
    conn.execute("UPDATE resort_profile SET resort_name = ? WHERE tenant_id = ?",
                ("SN Softech Demo Resort", tenant_id))
    # Give the demo tenant a long-lived active licence directly (no key needed).
    far_future = (dt.date.today() + dt.timedelta(days=3650)).isoformat()
    conn.execute(
        """UPDATE licence SET status = 'ACTIVE', licence_key = 'DEMO-PERMANENT', plan_type = 'Yearly',
           activation_date = ?, licence_expiry = ? WHERE tenant_id = ?""",
        (dt.date.today().isoformat(), far_future, tenant_id),
    )
    conn.commit()
    conn.close()

    import demo_data
    demo_data.seed_demo_data(tenant_id, created_by="system")


ensure_demo_tenant()


# ---------------------------------------------------------------------------
# AUTH SCREENS
# ---------------------------------------------------------------------------
def render_auth_screens():
    st.markdown(
        f"""
        <div style="text-align:center;padding:26px 0 10px 0;">
            <h1 style="color:#1e3a8a;font-weight:800;margin-bottom:0;">🏨 {PRODUCT_NAME}</h1>
            <p style="color:#64748b;font-size:14px;">by {COMPANY_NAME}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _, center, _ = st.columns([1, 1.4, 1])
    with center:
        st.markdown(
            """<div style="background:white;border-radius:16px;padding:24px 28px;
                box-shadow:0 6px 24px rgba(15,23,42,0.08);border:1px solid #e5e7eb;">""",
            unsafe_allow_html=True,
        )

        tab1, tab2 = st.tabs(["🔑 Sign In", "📝 Sign Up"])

        with tab1:
            st.markdown("###### Sign in to your resort dashboard")
            with st.form("signin_form"):
                identifier = st.text_input("Username or Email")
                password = st.text_input("Password", type="password")
                remember = st.checkbox("Remember Login", value=True)
                submitted = st.form_submit_button("Sign In", type="primary", use_container_width=True)

                if submitted:
                    success, message, user = auth.sign_in(identifier, password)
                    if success:
                        st.session_state["authenticated"] = True
                        st.session_state["user"] = user
                        st.session_state["remember"] = remember
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)

            with st.expander("Forgot Password?"):
                st.caption("Please contact your resort's Admin to reset your password "
                           "(Settings -> User Management), or SN SOFTECH SOLUTIONS support.")

            st.markdown("---")
            st.caption("Just want to look around first?")
            if st.button("👀 Try the Live Demo (no signup needed)", use_container_width=True):
                success, message, user = auth.sign_in(DEMO_USERNAME, DEMO_PASSWORD)
                if success:
                    st.session_state["authenticated"] = True
                    st.session_state["user"] = user
                    st.rerun()

        with tab2:
            st.markdown("###### Create your resort account — activate with a Monthly or Yearly licence key")
            st.caption("Every account gets its own completely private workspace — your data is never "
                      "visible to any other resort on the platform.")
            with st.form("signup_form"):
                c1, c2 = st.columns(2)
                resort_name = c1.text_input("Resort/Business Name *")
                owner_name = c2.text_input("Owner/Admin Name *")

                c3, c4 = st.columns(2)
                mobile = c3.text_input("Mobile Number *")
                email = c4.text_input("Email")

                c5, c6 = st.columns(2)
                username = c5.text_input("Username *")
                password = st.text_input("Password *", type="password")
                confirm_password = st.text_input("Confirm Password *", type="password")

                submitted = st.form_submit_button("Create Account", type="primary",
                                                    use_container_width=True)
                if submitted:
                    success, message = auth.sign_up(resort_name, owner_name, mobile, email, username,
                                                      password, confirm_password)
                    if success:
                        st.success(message)
                        st.balloons()
                        success2, _, user = auth.sign_in(username, password)
                        if success2:
                            st.session_state["authenticated"] = True
                            st.session_state["user"] = user
                            st.rerun()
                    else:
                        st.error(message)

        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown(
            f"<p style='text-align:center;color:#94a3b8;font-size:11px;margin-top:14px;'>"
            f"Powered by {COMPANY_NAME}</p>",
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# LICENCE GATE
# ---------------------------------------------------------------------------
def render_licence_gate(status):
    st.markdown(
        f"""
        <div style="text-align:center;padding:20px 0;">
            <h1 style="color:#dc2626;">🔐 {status['state'].replace('_', ' ')}</h1>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _, center, _ = st.columns([1, 1.4, 1])
    with center:
        st.error(status["message"])
        st.info("Please activate your Monthly or Yearly licence key to start using the Resort Management System.")

        from modules import licence_page
        licence_page.render()

        if st.button("Logout"):
            auth.logout()
            st.rerun()


# ---------------------------------------------------------------------------
# MAIN APP SHELL
# ---------------------------------------------------------------------------
def render_sidebar(status, tenant_id):
    from config import ROLE_MENU_ACCESS

    user = auth.current_user()
    role = user.get("role", "ADMIN") if user else "ADMIN"
    allowed = ROLE_MENU_ACCESS.get(role, [])

    with st.sidebar:
        st.markdown(
            f"""<div class="brand-box"><h2>🏨 {PRODUCT_NAME}</h2><p>{COMPANY_NAME}</p></div>""",
            unsafe_allow_html=True,
        )

        if is_demo_tenant(tenant_id):
            st.markdown('<div class="licence-banner" style="background:#7c3aed;">'
                        '👀 DEMO MODE — settings & users are locked</div>', unsafe_allow_html=True)
        elif status["state"] == "LICENCE_EXPIRING":
            st.markdown(f'<div class="licence-banner" style="background:#f59e0b;">'
                        f'⚠️ Licence expiring – {status["days_remaining"]} day(s) left</div>',
                        unsafe_allow_html=True)
        elif status["state"] == "ACTIVE":
            st.markdown('<div class="licence-banner" style="background:#16a34a;">✅ LICENSE ACTIVE</div>',
                        unsafe_allow_html=True)

        current_page = st.session_state.get("current_page", "dashboard")

        for i, (key, label) in enumerate(MENU_ITEMS):
            if allowed != "ALL" and key not in allowed:
                continue
            is_active = key == current_page
            btn_label = f"● {label}" if is_active else label
            if st.button(btn_label, key=f"nav_{key}", use_container_width=True):
                st.session_state["current_page"] = key
                st.rerun()

        st.markdown("---")
        st.markdown(f"**{user.get('full_name') or user.get('username')}**")
        st.caption(f"Role: {role}")
        if st.button("🚪 Logout", use_container_width=True):
            auth.logout()
            st.rerun()


def apply_sidebar_button_colors():
    """Inject per-button colours by order using nth-of-type CSS."""
    css_rules = []
    for i, color in enumerate(SIDEBAR_COLORS, start=1):
        css_rules.append(
            f'section[data-testid="stSidebar"] div.stButton:nth-of-type({i}) button {{'
            f'background:{color} !important;}}'
        )
    st.markdown(f"<style>{''.join(css_rules)}</style>", unsafe_allow_html=True)


def render_topbar(status, tenant_id):
    user = auth.current_user()
    profile = get_resort_profile(tenant_id)
    today_display = dt.date.today().strftime("%d %b %Y")

    if is_demo_tenant(tenant_id):
        status_badge = ("DEMO ACCOUNT", "#7c3aed")
    else:
        status_badge = {
            "ACTIVE": ("LICENSE ACTIVE", "#16a34a"), "LICENCE_EXPIRING": ("LICENCE EXPIRING", "#f59e0b"),
        }.get(status["state"], ("-", "#6b7280"))

    st.markdown(
        f"""
        <div class="rms-topbar">
            <div>
                <h1>{profile.get('resort_name', 'Resort')}</h1>
                <div class="sub">{PRODUCT_NAME} | {COMPANY_NAME}</div>
            </div>
            <div class="meta">
                👤 {user.get('full_name') or user.get('username')} &nbsp;|&nbsp; 📅 {today_display}<br/>
                <span class="status-pill" style="background:{status_badge[1]};margin-top:4px;display:inline-block;">
                    {status_badge[0]}
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def route(page_key):
    from modules import (dashboard, reservations, rooms, guests, checkin, checkout, billing,
                          restaurant, housekeeping, staff, attendance, inventory, expenses,
                          reports, kpi, whatsapp_center, settings, notifications, licence_page)

    pages = {
        "dashboard": dashboard.render, "reservations": reservations.render, "rooms": rooms.render,
        "guests": guests.render, "checkin": checkin.render, "checkout": checkout.render,
        "billing": billing.render, "restaurant": restaurant.render, "housekeeping": housekeeping.render,
        "staff": staff.render, "attendance": attendance.render, "inventory": inventory.render,
        "expenses": expenses.render, "reports": reports.render, "kpi": kpi.render,
        "whatsapp": whatsapp_center.render, "settings": settings.render,
        "notifications": notifications.render, "licence": licence_page.render,
    }
    render_fn = pages.get(page_key, dashboard.render)
    render_fn()


def main():
    if not auth.is_authenticated():
        render_auth_screens()
        return

    tenant_id = auth.current_tenant_id()
    status = licence_engine.get_status(tenant_id)

    if not status["can_access"]:
        render_topbar(status, tenant_id)
        render_licence_gate(status)
        return

    render_topbar(status, tenant_id)
    render_sidebar(status, tenant_id)
    apply_sidebar_button_colors()

    current_page = st.session_state.get("current_page", "dashboard")
    route(current_page)


if __name__ == "__main__":
    main()
