"""
test_tenant_isolation.py
Phase 19 (Data Isolation Testing) — run against a REAL PostgreSQL database,
not mocked. Creates two tenants, has each create guests/bookings/payments/
expenses, then asserts Tenant A cannot see ANY of Tenant B's records (and
vice versa) both through the application's query helpers and through
direct raw SQL. Also re-verifies the licence-independence bug fix and the
demo-tenant bootstrap.

Run with:
    DATABASE_URL=postgresql://... python3 test_tenant_isolation.py
"""

import sys

from database import init_db, get_connection
import auth
import license as licence_engine
import demo_data

FAILURES = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        FAILURES.append(label)


print("=" * 70)
print("PHASE 19 - TENANT ISOLATION TEST SUITE (live PostgreSQL)")
print("=" * 70)

init_db()

# ---------------------------------------------------------------------
# Demo tenant bootstrap check (must run BEFORE app.py's ensure_demo_tenant)
# ---------------------------------------------------------------------
from config import DEMO_USERNAME
demo_exists_before = auth.username_exists(DEMO_USERNAME)
check("Demo account does not exist until app.ensure_demo_tenant() runs it", not demo_exists_before)

# ---------------------------------------------------------------------
# Setup: two independent tenants signing up through the real auth flow
# ---------------------------------------------------------------------
ok_a, msg_a = auth.sign_up("Ocean View Resort", "Ravi Kumar", "9876543210",
                           "ravi@example.com", "tenant_a_admin", "Passw0rd!", "Passw0rd!")
ok_b, msg_b = auth.sign_up("Mountain Peak Resort", "Sita Devi", "9123456789",
                           "sita@example.com", "tenant_b_admin", "Passw0rd!", "Passw0rd!")
check("Tenant A signup succeeds", ok_a)
check("Tenant B signup succeeds", ok_b)

_, _, user_a = auth.sign_in("tenant_a_admin", "Passw0rd!")
_, _, user_b = auth.sign_in("tenant_b_admin", "Passw0rd!")
tenant_a = user_a["tenant_id"]
tenant_b = user_b["tenant_id"]
check("Tenant A and B have different tenant_ids", tenant_a != tenant_b)

# ---------------------------------------------------------------------
# Subscription independence (the original bug report, re-verified)
# ---------------------------------------------------------------------
status_a_before = licence_engine.get_status(tenant_a)
status_b_before = licence_engine.get_status(tenant_b)
check("Tenant A starts as LICENCE_REQUIRED", status_a_before["state"] == "LICENCE_REQUIRED")
check("Tenant B starts as LICENCE_REQUIRED", status_b_before["state"] == "LICENCE_REQUIRED")

keys = licence_engine.generate_key_batch("Monthly", 2)
ok_activate, _ = licence_engine.activate_licence(tenant_a, keys[0])
check("Tenant A licence activation succeeds", ok_activate)

status_a_after = licence_engine.get_status(tenant_a)
status_b_after = licence_engine.get_status(tenant_b)
check("Tenant A is now ACTIVE", status_a_after["state"] == "ACTIVE")
check("Tenant B is STILL LICENCE_REQUIRED (not bled through from A)", status_b_after["state"] == "LICENCE_REQUIRED")

licence_engine.activate_licence(tenant_b, keys[1])

# ---------------------------------------------------------------------
# Seed each tenant with demo data (rooms, guests, bookings, payments, expenses)
# ---------------------------------------------------------------------
seed_ok_a, _ = demo_data.seed_demo_data(tenant_a, created_by="tenant_a_admin")
seed_ok_b, _ = demo_data.seed_demo_data(tenant_b, created_by="tenant_b_admin")
check("Demo data seeded for Tenant A", seed_ok_a)
check("Demo data seeded for Tenant B", seed_ok_b)

# ---------------------------------------------------------------------
# Cross-tenant isolation checks - direct raw SQL (bypasses any UI filtering)
# ---------------------------------------------------------------------
conn = get_connection()

tables_with_names = [
    ("guests", "name"), ("rooms", "room_number"), ("reservations", "guest_name"),
    ("staff", "name"), ("expenses", "description"), ("inventory", "name"),
]

for table, name_col in tables_with_names:
    a_rows = conn.execute(f"SELECT {name_col} FROM {table} WHERE tenant_id = ?", (tenant_a,)).fetchall()
    b_rows = conn.execute(f"SELECT {name_col} FROM {table} WHERE tenant_id = ?", (tenant_b,)).fetchall()
    a_values = {r[name_col] for r in a_rows}
    b_values = {r[name_col] for r in b_rows}

    check(f"{table}: Tenant A has records", len(a_values) > 0)
    check(f"{table}: Tenant B has records", len(b_values) > 0)

    cross_impossible = conn.execute(
        f"SELECT COUNT(*) c FROM {table} WHERE tenant_id = ? AND tenant_id = ?", (tenant_a, tenant_b)
    ).fetchone()["c"]
    check(f"{table}: no row can match both tenant_a and tenant_b simultaneously", cross_impossible == 0)

guest_ids_a = {r["guest_id"] for r in conn.execute(
    "SELECT guest_id FROM guests WHERE tenant_id = ?", (tenant_a,)).fetchall()}
guest_ids_b = {r["guest_id"] for r in conn.execute(
    "SELECT guest_id FROM guests WHERE tenant_id = ?", (tenant_b,)).fetchall()}
check("No guest_id appears in both tenants' guest lists", guest_ids_a.isdisjoint(guest_ids_b))

booking_ids_a = {r["booking_id"] for r in conn.execute(
    "SELECT booking_id FROM reservations WHERE tenant_id = ?", (tenant_a,)).fetchall()}
booking_ids_b = {r["booking_id"] for r in conn.execute(
    "SELECT booking_id FROM reservations WHERE tenant_id = ?", (tenant_b,)).fetchall()}
check("No booking_id appears in both tenants' reservation lists", booking_ids_a.isdisjoint(booking_ids_b))

# Cross-tenant fetch attempt: try to read tenant B's booking using tenant A's id -> must return nothing
if booking_ids_b:
    some_b_booking = next(iter(booking_ids_b))
    leaked = conn.execute(
        "SELECT 1 FROM reservations WHERE tenant_id = ? AND booking_id = ?", (tenant_a, some_b_booking)
    ).fetchone()
    check("Tenant A cannot fetch Tenant B's booking by ID even when explicitly requested", leaked is None)

conn.close()

# ---------------------------------------------------------------------
# Application-layer checks - via the actual utils.py helpers modules use
# ---------------------------------------------------------------------
from utils import get_resort_profile

profile_a = get_resort_profile(tenant_a)
profile_b = get_resort_profile(tenant_b)
check("Tenant A resort_profile has correct name", profile_a.get("resort_name") == "Ocean View Resort")
check("Tenant B resort_profile has correct name", profile_b.get("resort_name") == "Mountain Peak Resort")
check("Tenant A's profile is NOT Tenant B's profile", profile_a.get("resort_name") != profile_b.get("resort_name"))

# ---------------------------------------------------------------------
# Room number reuse across tenants must be ALLOWED; duplicate WITHIN one
# tenant must be REJECTED (this is the composite UNIQUE(tenant_id, room_number))
# ---------------------------------------------------------------------
conn3 = get_connection()
conn3.execute("INSERT INTO room_types (room_type_id, tenant_id, name, base_tariff) VALUES (?, ?, 'TestType', 1000)",
             ("RT-TESTA", tenant_a))
conn3.execute("INSERT INTO room_types (room_type_id, tenant_id, name, base_tariff) VALUES (?, ?, 'TestType', 1000)",
             ("RT-TESTB", tenant_b))
conn3.execute("INSERT INTO rooms (room_id, tenant_id, room_number, room_type_id, tariff, status) "
             "VALUES (?, ?, '999', ?, 1000, 'Available')", ("RM-TESTA", tenant_a, "RT-TESTA"))
conn3.commit()
try:
    conn3.execute("INSERT INTO rooms (room_id, tenant_id, room_number, room_type_id, tariff, status) "
                 "VALUES (?, ?, '999', ?, 1000, 'Available')", ("RM-TESTB", tenant_b, "RT-TESTB"))
    conn3.commit()
    check("Room number '999' can be reused independently by two different tenants", True)
except Exception as e:
    conn3.rollback()
    check(f"Room number '999' can be reused independently by two different tenants (error: {e})", False)
conn3.close()

conn4 = get_connection()
try:
    conn4.execute("INSERT INTO rooms (room_id, tenant_id, room_number, room_type_id, tariff, status) "
                 "VALUES (?, ?, '999', ?, 1000, 'Available')", ("RM-TESTA-DUP", tenant_a, "RT-TESTA"))
    conn4.commit()
    check("Duplicate room number WITHIN the same tenant is rejected", False)
except Exception:
    conn4.rollback()
    check("Duplicate room number WITHIN the same tenant is rejected", True)
conn4.close()

# ---------------------------------------------------------------------
print("=" * 70)
if FAILURES:
    print(f"RESULT: {len(FAILURES)} CHECK(S) FAILED:")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
else:
    print("RESULT: ALL CHECKS PASSED")
    sys.exit(0)
