"""
database.py
Multi-tenant PostgreSQL schema + connection helper for SN SOFTECH SOLUTIONS
Resort Management SaaS.

Design notes (see TECHNICAL_AUDIT.md for the full migration rationale):
- One shared PostgreSQL database serves every tenant (resort). Every
  business table carries a `tenant_id` column, and every query in every
  module must filter on it — this is the actual isolation boundary
  (Phase 3), never just UI-level filtering.
- `resort_profile` and `licence` used to be SQLite singleton rows
  (`id INTEGER PRIMARY KEY CHECK (id = 1)`) representing "the one resort
  this install belongs to." They are now one row PER TENANT, keyed by
  `tenant_id`.
- `users.username` / `users.email` are kept GLOBALLY unique across the
  whole platform (not per-tenant) — there is a single shared login screen
  with no tenant subdomain/selector, so a user's tenant is looked up from
  their own account after authenticating, not chosen at login time.
- All other natural-key uniqueness (room_number, room_type name, etc.) is
  scoped per tenant via composite UNIQUE constraints, so two different
  resorts can each have a "Room 101" without conflict.
- Primary keys stay as application-generated TEXT ids (new_id()), exactly
  as in the original SQLite build — this meant zero ID remapping was
  needed during migration.
"""

from contextlib import contextmanager
import uuid

from db import get_connection, transaction  # noqa: F401  (re-exported for existing `from database import get_connection` call sites)


def new_id(prefix=""):
    """Generate a short, human-friendlier unique id. Unchanged from the SQLite build."""
    raw = uuid.uuid4().hex[:10].upper()
    return f"{prefix}{raw}" if prefix else raw


@contextmanager
def get_cursor(commit=False):
    conn = get_connection()
    try:
        yield conn
        if commit:
            conn.commit()
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id TEXT PRIMARY KEY,
    tenant_name TEXT NOT NULL,
    is_demo BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS resort_profile (
    tenant_id TEXT PRIMARY KEY REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    resort_name TEXT NOT NULL,
    address TEXT,
    mobile TEXT,
    whatsapp_number TEXT,
    email TEXT,
    gst_number TEXT,
    logo_path TEXT,
    website TEXT,
    invoice_footer TEXT,
    terms_conditions TEXT,
    currency_symbol TEXT DEFAULT '₹',
    tax_percent REAL DEFAULT 12.0,
    date_format TEXT DEFAULT '%d-%m-%Y',
    invoice_prefix TEXT DEFAULT 'INV',
    whatsapp_country_code TEXT DEFAULT '+91',
    installation_id TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE,
    mobile TEXT,
    full_name TEXT,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'ADMIN',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- One subscription row per tenant (was a singleton in the old SQLite build).
CREATE TABLE IF NOT EXISTS licence (
    tenant_id TEXT PRIMARY KEY REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    installation_id TEXT,
    status TEXT DEFAULT 'INACTIVE',          -- INACTIVE / ACTIVE / EXPIRED
    licence_key TEXT,
    plan_type TEXT,                          -- Monthly / Yearly
    activation_date DATE,
    licence_expiry DATE
);

-- Records keys that have been ACTIVATED (offline reuse-guard; the key
-- itself is checksum-verified, not looked up — see license.py).
CREATE TABLE IF NOT EXISTS licence_keys (
    licence_key TEXT PRIMARY KEY,
    tenant_id TEXT REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    plan_type TEXT NOT NULL,
    status TEXT DEFAULT 'Used',
    generated_date TIMESTAMP DEFAULT NOW(),
    used_date DATE,
    used_by_installation TEXT
);

CREATE TABLE IF NOT EXISTS room_types (
    room_type_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    base_tariff REAL DEFAULT 0,
    weekend_tariff REAL DEFAULT 0,
    extra_person_charge REAL DEFAULT 0,
    description TEXT,
    UNIQUE (tenant_id, name)
);

CREATE TABLE IF NOT EXISTS rooms (
    room_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    room_number TEXT NOT NULL,
    room_type_id TEXT,
    floor TEXT,
    capacity INTEGER DEFAULT 2,
    adult_capacity INTEGER DEFAULT 2,
    child_capacity INTEGER DEFAULT 1,
    tariff REAL DEFAULT 0,
    weekend_tariff REAL DEFAULT 0,
    extra_person_charge REAL DEFAULT 0,
    ac_type TEXT DEFAULT 'AC',
    amenities TEXT,
    status TEXT DEFAULT 'Available',
    is_active BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (room_type_id) REFERENCES room_types(room_type_id),
    UNIQUE (tenant_id, room_number)
);

CREATE TABLE IF NOT EXISTS guests (
    guest_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    mobile TEXT,
    country_code TEXT DEFAULT '+91',
    whatsapp_number TEXT,
    email TEXT,
    address TEXT,
    city TEXT,
    state TEXT,
    country TEXT,
    id_proof_type TEXT,
    id_proof_number TEXT,
    visits INTEGER DEFAULT 0,
    last_visit DATE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS reservations (
    booking_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    booking_date DATE DEFAULT CURRENT_DATE,
    guest_id TEXT,
    guest_name TEXT,
    mobile TEXT,
    email TEXT,
    country_code TEXT DEFAULT '+91',
    checkin_date DATE,
    checkin_time TEXT,
    checkout_date DATE,
    checkout_time TEXT,
    adults INTEGER DEFAULT 1,
    children INTEGER DEFAULT 0,
    room_type_id TEXT,
    room_id TEXT,
    nights INTEGER DEFAULT 1,
    room_tariff REAL DEFAULT 0,
    discount REAL DEFAULT 0,
    tax REAL DEFAULT 0,
    total_amount REAL DEFAULT 0,
    advance_payment REAL DEFAULT 0,
    balance REAL DEFAULT 0,
    booking_source TEXT DEFAULT 'Direct',
    special_request TEXT,
    status TEXT DEFAULT 'Pending',
    created_by TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (guest_id) REFERENCES guests(guest_id),
    FOREIGN KEY (room_id) REFERENCES rooms(room_id)
);

CREATE TABLE IF NOT EXISTS checkins (
    checkin_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    booking_id TEXT,
    guest_id TEXT,
    room_id TEXT,
    actual_checkin TIMESTAMP DEFAULT NOW(),
    id_verified BOOLEAN DEFAULT FALSE,
    num_guests INTEGER,
    advance_payment REAL DEFAULT 0,
    remarks TEXT,
    created_by TEXT,
    FOREIGN KEY (booking_id) REFERENCES reservations(booking_id)
);

CREATE TABLE IF NOT EXISTS checkouts (
    checkout_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    booking_id TEXT,
    guest_id TEXT,
    room_id TEXT,
    actual_checkout TIMESTAMP DEFAULT NOW(),
    room_charges REAL DEFAULT 0,
    restaurant_charges REAL DEFAULT 0,
    other_charges REAL DEFAULT 0,
    discount REAL DEFAULT 0,
    tax REAL DEFAULT 0,
    total_amount REAL DEFAULT 0,
    advance_paid REAL DEFAULT 0,
    balance REAL DEFAULT 0,
    created_by TEXT,
    FOREIGN KEY (booking_id) REFERENCES reservations(booking_id)
);

CREATE TABLE IF NOT EXISTS invoices (
    invoice_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    invoice_number TEXT,
    booking_id TEXT,
    guest_id TEXT,
    invoice_type TEXT DEFAULT 'Final',
    subtotal REAL DEFAULT 0,
    discount REAL DEFAULT 0,
    tax REAL DEFAULT 0,
    total_amount REAL DEFAULT 0,
    file_path TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (booking_id) REFERENCES reservations(booking_id),
    UNIQUE (tenant_id, invoice_number)
);

CREATE TABLE IF NOT EXISTS payments (
    payment_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    booking_id TEXT,
    guest_id TEXT,
    amount REAL DEFAULT 0,
    payment_mode TEXT DEFAULT 'Cash',
    payment_type TEXT DEFAULT 'Advance',
    payment_date TIMESTAMP DEFAULT NOW(),
    reference_no TEXT,
    remarks TEXT,
    created_by TEXT,
    FOREIGN KEY (booking_id) REFERENCES reservations(booking_id)
);

CREATE TABLE IF NOT EXISTS restaurant_items (
    item_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    category TEXT,
    rate REAL DEFAULT 0,
    tax_percent REAL DEFAULT 5.0,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS restaurant_orders (
    order_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    order_date TIMESTAMP DEFAULT NOW(),
    table_number TEXT,
    room_id TEXT,
    booking_id TEXT,
    guest_name TEXT,
    items_json TEXT,
    subtotal REAL DEFAULT 0,
    discount REAL DEFAULT 0,
    tax REAL DEFAULT 0,
    total_amount REAL DEFAULT 0,
    payment_status TEXT DEFAULT 'Posted to Room',
    posted_to_room BOOLEAN DEFAULT FALSE,
    created_by TEXT
);

CREATE TABLE IF NOT EXISTS housekeeping (
    hk_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    room_id TEXT,
    status TEXT DEFAULT 'Dirty',
    assigned_staff TEXT,
    cleaning_start TIMESTAMP,
    cleaning_end TIMESTAMP,
    inspection_status TEXT,
    maintenance_request TEXT,
    remarks TEXT,
    updated_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (room_id) REFERENCES rooms(room_id)
);

CREATE TABLE IF NOT EXISTS staff (
    staff_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    mobile TEXT,
    department TEXT,
    designation TEXT,
    joining_date DATE,
    salary REAL DEFAULT 0,
    status TEXT DEFAULT 'Active'
);

CREATE TABLE IF NOT EXISTS attendance (
    attendance_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    staff_id TEXT,
    date DATE DEFAULT CURRENT_DATE,
    status TEXT DEFAULT 'Present',
    in_time TEXT,
    out_time TEXT,
    FOREIGN KEY (staff_id) REFERENCES staff(staff_id)
);

CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    name TEXT,
    mobile TEXT,
    address TEXT
);

CREATE TABLE IF NOT EXISTS inventory (
    item_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    category TEXT,
    unit TEXT,
    opening_stock REAL DEFAULT 0,
    current_stock REAL DEFAULT 0,
    minimum_stock REAL DEFAULT 0,
    supplier_id TEXT,
    FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id)
);

CREATE TABLE IF NOT EXISTS purchases (
    purchase_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    item_id TEXT,
    quantity REAL,
    rate REAL,
    total REAL,
    supplier_id TEXT,
    purchase_date DATE DEFAULT CURRENT_DATE,
    FOREIGN KEY (item_id) REFERENCES inventory(item_id)
);

CREATE TABLE IF NOT EXISTS stock_movements (
    movement_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    item_id TEXT,
    movement_type TEXT,
    quantity REAL,
    date TIMESTAMP DEFAULT NOW(),
    remarks TEXT,
    FOREIGN KEY (item_id) REFERENCES inventory(item_id)
);

CREATE TABLE IF NOT EXISTS expenses (
    expense_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    date DATE DEFAULT CURRENT_DATE,
    category TEXT,
    description TEXT,
    amount REAL DEFAULT 0,
    payment_mode TEXT DEFAULT 'Cash',
    vendor TEXT,
    remarks TEXT,
    created_by TEXT
);

CREATE TABLE IF NOT EXISTS notifications (
    notification_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    type TEXT,
    message TEXT,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS whatsapp_logs (
    message_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    booking_id TEXT,
    guest_id TEXT,
    mobile_number TEXT,
    message_type TEXT,
    message_text TEXT,
    date DATE DEFAULT CURRENT_DATE,
    time TEXT,
    sent_by TEXT,
    status TEXT DEFAULT 'Initiated'
);

CREATE TABLE IF NOT EXISTS audit_logs (
    log_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    "user" TEXT,
    date DATE DEFAULT CURRENT_DATE,
    time TEXT,
    action TEXT,
    module TEXT,
    record_id TEXT
);

CREATE TABLE IF NOT EXISTS app_flags (
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    flag_key TEXT NOT NULL,
    flag_value TEXT,
    PRIMARY KEY (tenant_id, flag_key)
);

CREATE TABLE IF NOT EXISTS clock_watermark (
    tenant_id TEXT PRIMARY KEY REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    last_seen DATE
);

CREATE INDEX IF NOT EXISTS idx_reservations_tenant ON reservations(tenant_id);
CREATE INDEX IF NOT EXISTS idx_reservations_room_dates ON reservations(tenant_id, room_id, checkin_date, checkout_date);
CREATE INDEX IF NOT EXISTS idx_reservations_status ON reservations(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_payments_tenant ON payments(tenant_id);
CREATE INDEX IF NOT EXISTS idx_payments_booking ON payments(tenant_id, booking_id);
CREATE INDEX IF NOT EXISTS idx_guests_tenant ON guests(tenant_id);
CREATE INDEX IF NOT EXISTS idx_guests_mobile ON guests(tenant_id, mobile);
CREATE INDEX IF NOT EXISTS idx_rooms_tenant ON rooms(tenant_id);
CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_expenses_tenant ON expenses(tenant_id, date);
CREATE INDEX IF NOT EXISTS idx_audit_tenant ON audit_logs(tenant_id, date);
"""


def init_db():
    conn = get_connection()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def create_tenant(tenant_name: str, is_demo: bool = False) -> str:
    """Creates a new, fully isolated tenant (resort) and its resort_profile
    + INACTIVE licence row. Returns the new tenant_id."""
    tenant_id = new_id("TEN-")
    installation_id = new_id("INST-")
    conn = get_connection()
    conn.execute(
        "INSERT INTO tenants (tenant_id, tenant_name, is_demo) VALUES (?, ?, ?)",
        (tenant_id, tenant_name, is_demo),
    )
    conn.execute(
        """INSERT INTO resort_profile
           (tenant_id, resort_name, currency_symbol, tax_percent, date_format,
            invoice_prefix, whatsapp_country_code, installation_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (tenant_id, tenant_name, "\u20b9", 12.0, "%d-%m-%Y", "INV", "+91", installation_id),
    )
    conn.execute(
        "INSERT INTO licence (tenant_id, installation_id, status) VALUES (?, ?, 'INACTIVE')",
        (tenant_id, installation_id),
    )
    conn.commit()
    conn.close()
    return tenant_id


def is_demo_tenant(tenant_id: str) -> bool:
    conn = get_connection()
    row = conn.execute("SELECT is_demo FROM tenants WHERE tenant_id = ?", (tenant_id,)).fetchone()
    conn.close()
    return bool(row and row["is_demo"])
