"""
auth.py
Sign Up / Sign In / session management for SN SOFTECH SOLUTIONS Resort
Management SaaS. Passwords are hashed with bcrypt - never stored or
compared in plain text.

SaaS change from the old single-tenant desktop build: Sign Up now creates
a brand NEW, fully isolated tenant every time (this is the actual point of
multi-tenancy) instead of being blocked after the first account. Everything
that account creates or sees is scoped to its own tenant_id from then on.
"""

import re
import bcrypt
import streamlit as st

from database import get_connection, new_id, create_tenant, is_demo_tenant
from license import initialize_licence_record


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def valid_email(email: str) -> bool:
    if not email:
        return True  # optional field in some flows
    return re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email) is not None


def valid_mobile(mobile: str) -> bool:
    digits = re.sub(r"\D", "", mobile or "")
    return len(digits) >= 7


def username_exists(username: str) -> bool:
    """Username is unique across the whole platform (see database.py docstring)."""
    conn = get_connection()
    row = conn.execute("SELECT 1 FROM users WHERE username = ?", (username.strip(),)).fetchone()
    conn.close()
    return row is not None


def email_exists(email: str) -> bool:
    if not email:
        return False
    conn = get_connection()
    row = conn.execute("SELECT 1 FROM users WHERE email = ?", (email.strip(),)).fetchone()
    conn.close()
    return row is not None


def sign_up(resort_name, owner_name, mobile, email, username, password, confirm_password):
    """
    Creates a brand new tenant (resort) plus its owner/ADMIN account.
    Returns (success, message). This is the core multi-tenant entry point —
    every signup is fully isolated from every other tenant on the platform.
    """
    username = (username or "").strip()
    email = (email or "").strip()

    if not all([resort_name, owner_name, mobile, username, password, confirm_password]):
        return False, "Please fill in all required fields."
    if not valid_mobile(mobile):
        return False, "Please enter a valid mobile number."
    if not valid_email(email):
        return False, "Please enter a valid email address."
    if len(password) < 6:
        return False, "Password must be at least 6 characters long."
    if password != confirm_password:
        return False, "Password and Confirm Password do not match."
    if username_exists(username):
        return False, "This username is already taken."
    if email_exists(email):
        return False, "This email is already registered."

    tenant_id = create_tenant(resort_name, is_demo=False)

    conn = get_connection()
    try:
        user_id = new_id("USR-")
        conn.execute(
            """INSERT INTO users (user_id, tenant_id, username, email, mobile, full_name,
               password_hash, role, is_active) VALUES (?, ?, ?, ?, ?, ?, ?, 'ADMIN', TRUE)""",
            (user_id, tenant_id, username, email or None, mobile, owner_name, hash_password(password)),
        )
        conn.execute("UPDATE resort_profile SET mobile = ?, email = ? WHERE tenant_id = ?",
                     (mobile, email or None, tenant_id))
        conn.commit()
    finally:
        conn.close()

    # licence row already created by create_tenant() as INACTIVE - nothing further needed here.
    return True, "Account created successfully! Please activate your licence key to continue."


def sign_in(username_or_email: str, password: str):
    """Returns (success: bool, message: str, user_row_or_None). The returned
    user dict includes tenant_id — every subsequent query in the app must
    filter by this value."""
    identifier = (username_or_email or "").strip()
    if not identifier or not password:
        return False, "Please enter your username/email and password.", None

    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM users WHERE (username = ? OR email = ?) AND is_active = TRUE",
        (identifier, identifier),
    ).fetchone()
    conn.close()

    if row is None:
        return False, "No account found with that username/email.", None
    if not verify_password(password, row["password_hash"]):
        return False, "Incorrect password. Please try again.", None

    return True, "Login successful.", dict(row)


def logout():
    for key in ["authenticated", "user", "current_page"]:
        st.session_state.pop(key, None)


def is_authenticated() -> bool:
    return bool(st.session_state.get("authenticated"))


def current_user():
    return st.session_state.get("user")


def current_tenant_id():
    user = st.session_state.get("user")
    return user.get("tenant_id") if user else None


# ---------------------------------------------------------------------------
# STAFF USER MANAGEMENT (Admin-only, scoped to the admin's own tenant)
# Additional logins for the SAME resort - they share that resort's licence
# and data. This is the intended way to add more logins, instead of using
# the public Sign Up form again (which now creates a brand new tenant).
# ---------------------------------------------------------------------------
def create_staff_user(tenant_id, full_name, mobile, email, username, password, confirm_password, role):
    from config import USER_ROLES

    if is_demo_tenant(tenant_id):
        return False, "Staff logins cannot be added to the shared Demo account."

    username = (username or "").strip()
    email = (email or "").strip()

    if not all([full_name, username, password, confirm_password, role]):
        return False, "Please fill in all required fields."
    if role not in USER_ROLES:
        return False, "Please select a valid role."
    if not valid_email(email):
        return False, "Please enter a valid email address."
    if len(password) < 6:
        return False, "Password must be at least 6 characters long."
    if password != confirm_password:
        return False, "Password and Confirm Password do not match."
    if username_exists(username):
        return False, "This username is already taken."
    if email_exists(email):
        return False, "This email is already registered."

    conn = get_connection()
    user_id = new_id("USR-")
    conn.execute(
        """INSERT INTO users (user_id, tenant_id, username, email, mobile, full_name,
           password_hash, role, is_active) VALUES (?, ?, ?, ?, ?, ?, ?, ?, TRUE)""",
        (user_id, tenant_id, username, email or None, mobile, full_name, hash_password(password), role),
    )
    conn.commit()
    conn.close()
    return True, f"Staff login '{username}' created successfully with role {role}."


def list_users(tenant_id):
    conn = get_connection()
    rows = conn.execute(
        """SELECT user_id, tenant_id, username, email, mobile, full_name, role, is_active, created_at
           FROM users WHERE tenant_id = ? ORDER BY created_at""",
        (tenant_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_user_active(tenant_id, user_id: str, is_active: bool):
    if is_demo_tenant(tenant_id):
        return False, "The shared Demo account's login cannot be disabled."
    conn = get_connection()
    conn.execute("UPDATE users SET is_active = ? WHERE user_id = ? AND tenant_id = ?",
                (is_active, user_id, tenant_id))
    conn.commit()
    conn.close()
    return True, "Updated."


def reset_user_password(tenant_id, user_id: str, new_password: str):
    if is_demo_tenant(tenant_id):
        return False, "The shared Demo account's password cannot be changed."
    if len(new_password or "") < 6:
        return False, "Password must be at least 6 characters long."
    conn = get_connection()
    conn.execute("UPDATE users SET password_hash = ? WHERE user_id = ? AND tenant_id = ?",
                (hash_password(new_password), user_id, tenant_id))
    conn.commit()
    conn.close()
    return True, "Password reset successfully."
