import streamlit as st

import license as licence_engine
from utils import get_resort_profile, fmt_date, log_audit
import auth


def render():
    st.markdown('<div class="section-title">🔐 Licence</div>', unsafe_allow_html=True)
    user = st.session_state.get("user", {})
    tenant_id = auth.current_tenant_id()
    profile = get_resort_profile(tenant_id)
    status = licence_engine.get_status(tenant_id)
    details = licence_engine.get_licence_details(tenant_id)

    c1, c2, c3 = st.columns(3)
    c1.metric("Resort Name", profile.get("resort_name", "-"))
    c2.metric("Installation ID", details.get("installation_id", "-"))
    c3.metric("Status", details.get("status", "-"))

    st.markdown("---")

    if details.get("status") == "ACTIVE":
        plan_label = details.get("plan_type") or "Yearly"
        st.success(f"✅ **LICENSE ACTIVE ({plan_label})** — Valid until {fmt_date(details.get('licence_expiry'))}")
        c1, c2, c3 = st.columns(3)
        c1.metric("Plan", plan_label)
        c2.metric("Activation Date", fmt_date(details.get("activation_date")))
        c3.metric("Days Remaining", status["days_remaining"])
        st.text_input("Licence Key", value=details.get("licence_key", ""), disabled=True)
        if status["state"] == "LICENCE_EXPIRING":
            st.warning(f"⚠️ Your licence expires in {status['days_remaining']} day(s). Please renew soon.")
            st.caption("To renew, purchase a new key from SN SOFTECH SOLUTIONS and activate it below "
                       "once your current one runs out.")
    else:
        if status["state"] == "LICENCE_REQUIRED":
            st.error("🔐 **LICENCE REQUIRED** — Please activate a Monthly or Yearly licence key to "
                     "start using the Resort Management System.")
        elif status["state"] == "LICENCE_EXPIRED":
            st.error("❌ **LICENCE EXPIRED** — Please activate a new licence key to continue using the system.")

        st.markdown("##### Activate Your Licence")
        st.caption("Enter the licence key provided by SN SOFTECH SOLUTIONS after purchase "
                   "(Monthly or Yearly plan — detected automatically from the key).")

        licence_key = st.text_input("Licence Key", placeholder="SNMRMS-XXXX-XXXX-XXXX-XXXX (Monthly) "
                                     "or SNYRMS-XXXX-XXXX-XXXX-XXXX (Yearly)")
        if st.button("✅ Activate Licence", type="primary"):
            success, message = licence_engine.activate_licence(tenant_id, licence_key)
            if success:
                log_audit(tenant_id, user.get("username", ""), "Licence activated", "licence", licence_key)
                st.success(message)
                st.rerun()
            else:
                st.error(message)

        st.caption("Don't have a licence key yet? Contact SN SOFTECH SOLUTIONS to purchase one.")
