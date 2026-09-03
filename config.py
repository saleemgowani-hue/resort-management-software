"""
config.py
Central configuration for SN SOFTECH SOLUTIONS - Resort Management System.
Keep all constants here so branding / business rules are changed in ONE place.
"""

import os

# ---------------------------------------------------------------------------
# BRANDING
# ---------------------------------------------------------------------------
COMPANY_NAME = "SN SOFTECH SOLUTIONS"
PRODUCT_NAME = "RESORT MANAGEMENT SYSTEM"
APP_TITLE = f"{PRODUCT_NAME} | {COMPANY_NAME}"

# ---------------------------------------------------------------------------
# PATHS
# Note: DATA_DIR still holds generated PDFs (invoices/receipts) and the
# bundled Unicode font/icon assets. There is no longer a local database
# file here (DB_PATH/BACKUP_DIR from the old single-tenant SQLite build were
# removed) — the app now always connects to PostgreSQL via DATABASE_URL.
# On Streamlit Cloud, this local filesystem is ephemeral across restarts;
# PDFs are generated fresh and offered for download within the same run,
# so this is fine for that use case but is not a persistent file store.
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(ASSETS_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# LICENCE (no free trial — activation required immediately after sign-up)
# ---------------------------------------------------------------------------
LICENCE_WARNING_DAYS_LEFT = 15

# Secret used to sign/verify licence keys (HMAC-based checksum). This lets a
# customer's offline installation verify a key is genuine WITHOUT needing any
# key-generation ability of its own, and without needing to phone home to a
# server. Only SN SOFTECH SOLUTIONS' private key-generator tool (kept OUT of
# the customer package) should know this value.
#
# IMPORTANT FOR SN SOFTECH SOLUTIONS:
# - Change this to your own random secret before selling this software.
# - Keep it identical between this file and your private key-generator tool
#   — if they don't match, previously issued keys will stop validating.
# - This offers real protection against a customer casually generating their
#   own keys (as happened before), but it is NOT unbreakable: this is an
#   offline desktop app, so someone with strong reverse-engineering skills
#   who reads this source file can still find the secret. True airtight
#   protection would require an online licence-activation server.
LICENCE_SIGNING_SECRET = "SN-SOFTECH-RMS-2026-CHANGE-THIS-SECRET-BEFORE-SELLING"

# ---------------------------------------------------------------------------
# DEFAULTS
# ---------------------------------------------------------------------------
DEFAULT_CURRENCY_SYMBOL = "\u20b9"   # INR
DEFAULT_COUNTRY_CODE = "+91"
DEFAULT_DATE_FORMAT = "%d-%m-%Y"
DEFAULT_TAX_PERCENT = 12.0

ROOM_STATUSES = ["Available", "Reserved", "Occupied", "Cleaning", "Maintenance", "Out of Order"]
BOOKING_STATUSES = ["Pending", "Confirmed", "Checked-In", "Checked-Out", "Cancelled", "No Show"]
PAYMENT_MODES = ["Cash", "UPI", "Card", "Bank Transfer", "Other"]
HOUSEKEEPING_STATUSES = ["Dirty", "Cleaning", "Clean", "Inspected", "Maintenance"]
EXPENSE_CATEGORIES = ["Electricity", "Water", "Salary", "Maintenance", "Food Purchase",
                       "Cleaning", "Transport", "Marketing", "Other"]
STAFF_DEPARTMENTS = ["Reception", "Housekeeping", "Restaurant", "Kitchen",
                      "Security", "Maintenance", "Management", "Other"]

ROOM_STATUS_COLORS = {
    "Available": "#22c55e",
    "Reserved": "#f59e0b",
    "Occupied": "#ef4444",
    "Cleaning": "#3b82f6",
    "Maintenance": "#a855f7",
    "Out of Order": "#6b7280",
}

USER_ROLES = ["ADMIN", "MANAGER", "RECEPTIONIST", "HOUSEKEEPING", "ACCOUNTANT"]

# Menu items visible per role (module_key list). "ALL" = every module.
ROLE_MENU_ACCESS = {
    "ADMIN": "ALL",
    "MANAGER": ["dashboard", "reservations", "rooms", "guests", "checkin", "checkout",
                "billing", "restaurant", "housekeeping", "staff", "attendance",
                "inventory", "expenses", "reports", "kpi", "whatsapp", "notifications", "settings", "licence"],
    "RECEPTIONIST": ["dashboard", "reservations", "guests", "checkin", "checkout",
                      "billing", "whatsapp", "notifications", "licence"],
    "HOUSEKEEPING": ["dashboard", "housekeeping", "notifications", "licence"],
    "ACCOUNTANT": ["dashboard", "billing", "expenses", "reports", "kpi", "notifications", "licence"],
}

# ---------------------------------------------------------------------------
# DEMO LOGIN (first-run convenience; document in README)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# SHARED PLATFORM DEMO ACCOUNT (Phase 9) — fixed credentials, auto-created and
# auto-seeded on first app startup. Isolated in its own tenant; see
# database.create_tenant(is_demo=True) and app.py's ensure_demo_tenant().
# ---------------------------------------------------------------------------
DEMO_USERNAME = "demo"
DEMO_PASSWORD = "Demo@1234"
