"""
demo_data.py
One-click demo/sample data seeder for SN SOFTECH SOLUTIONS Resort Management
SaaS. Everything it inserts is scoped to a single tenant_id — either a real
tenant exploring the software, or the shared platform Demo tenant (see
database.create_tenant(is_demo=True) and app.py's demo-login button).

Safe to call multiple times per tenant: it checks a marker row (in
app_flags, keyed by tenant_id) before inserting so demo data is never
duplicated for that tenant. Use `demo_data_exists(tenant_id)` to check
status and `clear_demo_data(tenant_id)` to wipe that tenant's transactional
tables if they want to start over with a clean slate before going live.
"""

import datetime as dt
import json
import random

from database import get_connection, new_id

MARKER_KEY = "demo_data_seeded"


def demo_data_exists(tenant_id) -> bool:
    conn = get_connection()
    row = conn.execute("SELECT flag_value FROM app_flags WHERE tenant_id = ? AND flag_key = ?",
                       (tenant_id, MARKER_KEY)).fetchone()
    conn.close()
    return row is not None and row["flag_value"] == "1"


def _set_marker(tenant_id):
    conn = get_connection()
    conn.execute(
        """INSERT INTO app_flags (tenant_id, flag_key, flag_value) VALUES (?, ?, '1')
           ON CONFLICT (tenant_id, flag_key) DO UPDATE SET flag_value = '1'""",
        (tenant_id, MARKER_KEY),
    )
    conn.commit()
    conn.close()


def _clear_marker(tenant_id):
    conn = get_connection()
    conn.execute("DELETE FROM app_flags WHERE tenant_id = ? AND flag_key = ?", (tenant_id, MARKER_KEY))
    conn.commit()
    conn.close()


GUEST_NAMES = [
    ("Aarav Sharma", "9811122233", "Delhi"), ("Priya Nair", "9822233344", "Kochi"),
    ("Rohan Mehta", "9833344455", "Mumbai"), ("Ananya Iyer", "9844455566", "Bengaluru"),
    ("Vikram Singh", "9855566677", "Jaipur"), ("Neha Kapoor", "9866677788", "Chandigarh"),
    ("Karan Malhotra", "9877788899", "Pune"), ("Divya Reddy", "9888899900", "Hyderabad"),
    ("Arjun Rao", "9899900011", "Chennai"), ("Sneha Joshi", "9900011122", "Nagpur"),
]

STAFF_NAMES = [
    ("Suresh Yadav", "Reception", "Front Desk Executive", 18000),
    ("Meena Kumari", "Housekeeping", "Housekeeping Supervisor", 15000),
    ("Ramesh Pillai", "Kitchen", "Head Chef", 25000),
    ("Anita Desai", "Restaurant", "Restaurant Manager", 20000),
    ("Vijay Kumar", "Security", "Security Guard", 12000),
    ("Kavita Bhatt", "Management", "Assistant Manager", 30000),
]


def seed_demo_data(tenant_id, created_by: str = "system"):
    """Populates realistic sample data for ONE tenant. No-op if already seeded for that tenant."""
    if demo_data_exists(tenant_id):
        return False, "Demo data has already been added."

    conn = get_connection()
    today = dt.date.today()

    # ---------------- Room Types ----------------
    room_types = [
        ("Standard", 1800, 2200, 400),
        ("Deluxe", 2800, 3400, 500),
        ("Suite", 4500, 5200, 700),
        ("Cottage", 6000, 7000, 800),
    ]
    rt_ids = {}
    for name, base, weekend, extra in room_types:
        rt_id = new_id("RT-")
        rt_ids[name] = rt_id
        conn.execute(
            """INSERT INTO room_types (room_type_id, tenant_id, name, base_tariff, weekend_tariff,
               extra_person_charge, description) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (rt_id, tenant_id, name, base, weekend, extra, f"{name} room with modern amenities"),
        )

    # ---------------- Rooms ----------------
    room_plan = [
        ("101", "Standard", "1"), ("102", "Standard", "1"), ("103", "Standard", "1"),
        ("201", "Deluxe", "2"), ("202", "Deluxe", "2"), ("203", "Deluxe", "2"),
        ("301", "Suite", "3"), ("302", "Suite", "3"),
        ("C1", "Cottage", "Ground"), ("C2", "Cottage", "Ground"),
    ]
    room_ids = {}
    for room_number, rtype, floor in room_plan:
        room_id = new_id("RM-")
        room_ids[room_number] = room_id
        base, weekend, extra = next((b, w, e) for n, b, w, e in room_types if n == rtype)
        conn.execute(
            """INSERT INTO rooms (room_id, tenant_id, room_number, room_type_id, floor, capacity, adult_capacity,
               child_capacity, tariff, weekend_tariff, extra_person_charge, ac_type, amenities, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Available')""",
            (room_id, tenant_id, room_number, rt_ids[rtype], floor, 3, 2, 1, base, weekend, extra, "AC",
             "WiFi, TV, Hot Water, Mini Fridge"),
        )

    # ---------------- Guests ----------------
    guest_ids = {}
    for name, mobile, city in GUEST_NAMES:
        guest_id = new_id("GST-")
        guest_ids[name] = guest_id
        conn.execute(
            """INSERT INTO guests (guest_id, tenant_id, name, mobile, country_code, whatsapp_number, email, city,
               state, country, id_proof_type, id_proof_number, visits, last_visit)
               VALUES (?, ?, ?, ?, '+91', ?, ?, ?, ?, 'India', 'Aadhaar', ?, ?, ?)""",
            (guest_id, tenant_id, name, mobile, mobile, f"{name.split()[0].lower()}@example.com", city, city,
             f"XXXX-XXXX-{random.randint(1000,9999)}", random.randint(1, 4),
             (today - dt.timedelta(days=random.randint(10, 200))).isoformat()),
        )
    conn.commit()

    # ---------------- Reservations: past (checked-out), current (checked-in), future (confirmed) ----------------
    room_numbers = list(room_ids.keys())
    guest_names = list(guest_ids.keys())
    random.shuffle(room_numbers)
    random.shuffle(guest_names)

    def make_reservation(guest_name, room_number, checkin_date, checkout_date, status, tax_percent=12.0):
        room_id = room_ids[room_number]
        nights = max((checkout_date - checkin_date).days, 1)
        row = conn.execute("SELECT tariff, room_type_id FROM rooms WHERE room_id = ? AND tenant_id = ?",
                           (room_id, tenant_id)).fetchone()
        tariff = row["tariff"]
        room_tariff = tariff * nights
        discount = random.choice([0, 0, 200, 500])
        taxable = max(room_tariff - discount, 0)
        tax = round(taxable * tax_percent / 100, 2)
        total = round(taxable + tax, 2)
        advance = round(total * random.choice([0.3, 0.5, 1.0]), 2)
        balance = round(total - advance, 2)
        guest_id = guest_ids[guest_name]
        _, mobile, _ = next(g for g in GUEST_NAMES if g[0] == guest_name)

        booking_id = new_id("BK-")
        conn.execute(
            """INSERT INTO reservations (booking_id, tenant_id, booking_date, guest_id, guest_name, mobile,
               country_code, checkin_date, checkin_time, checkout_date, checkout_time, adults, children,
               room_type_id, room_id, nights, room_tariff, discount, tax, total_amount, advance_payment,
               balance, booking_source, status, created_by)
               VALUES (?, ?, ?, ?, ?, ?, '+91', ?, '12:00', ?, '11:00', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (booking_id, tenant_id, (checkin_date - dt.timedelta(days=random.randint(1, 5))).isoformat(), guest_id,
             guest_name, mobile, checkin_date.isoformat(), checkout_date.isoformat(),
             random.choice([1, 2]), random.choice([0, 0, 1]), row["room_type_id"], room_id, nights,
             room_tariff, discount, tax, total, advance, balance,
             random.choice(["Direct", "Website", "Walk-in", "Phone", "OTA"]), status, created_by),
        )
        return booking_id, room_id, guest_id, total, advance, balance, room_tariff, nights

    bookings_created = []

    # 2 past bookings -> fully checked out with invoice + payment
    for i in range(2):
        checkin = today - dt.timedelta(days=random.randint(10, 25))
        checkout = checkin + dt.timedelta(days=random.randint(1, 3))
        booking_id, room_id, guest_id, total, advance, balance, room_tariff, nights = make_reservation(
            guest_names[i], room_numbers[i], checkin, checkout, "Checked-Out"
        )
        conn.execute(
            """INSERT INTO payments (payment_id, tenant_id, booking_id, guest_id, amount, payment_mode, payment_type,
               payment_date, created_by) VALUES (?, ?, ?, ?, ?, ?, 'Final', ?, ?)""",
            (new_id("PAY-"), tenant_id, booking_id, guest_id, total, random.choice(["Cash", "UPI", "Card"]),
             checkout.isoformat() + " 11:30:00", created_by),
        )
        invoice_number = f"INV-{today.strftime('%y')}-{len(bookings_created)+1:05d}"
        conn.execute(
            """INSERT INTO invoices (invoice_id, tenant_id, invoice_number, booking_id, guest_id, invoice_type,
               subtotal, discount, tax, total_amount, created_at)
               VALUES (?, ?, ?, ?, ?, 'Final', ?, 0, ?, ?, ?)""",
            (new_id("INVID-"), tenant_id, invoice_number, booking_id, guest_id, room_tariff,
             round(total - room_tariff, 2), total, checkout.isoformat() + " 11:30:00"),
        )
        conn.execute("UPDATE rooms SET status = 'Available' WHERE room_id = ? AND tenant_id = ?",
                    (room_id, tenant_id))
        bookings_created.append(booking_id)

    # 2 current bookings -> checked in right now, occupying rooms
    for i in range(2, 4):
        checkin = today - dt.timedelta(days=1)
        checkout = today + dt.timedelta(days=random.randint(1, 3))
        booking_id, room_id, guest_id, total, advance, balance, room_tariff, nights = make_reservation(
            guest_names[i], room_numbers[i], checkin, checkout, "Checked-In"
        )
        conn.execute(
            """INSERT INTO checkins (checkin_id, tenant_id, booking_id, guest_id, room_id, id_verified, num_guests,
               advance_payment, created_by) VALUES (?, ?, ?, ?, ?, TRUE, 2, ?, ?)""",
            (new_id("CI-"), tenant_id, booking_id, guest_id, room_id, advance, created_by),
        )
        conn.execute("UPDATE rooms SET status = 'Occupied' WHERE room_id = ? AND tenant_id = ?",
                    (room_id, tenant_id))
        bookings_created.append(booking_id)

    # 2 upcoming confirmed bookings
    for i in range(4, 6):
        checkin = today + dt.timedelta(days=random.randint(2, 10))
        checkout = checkin + dt.timedelta(days=random.randint(1, 4))
        booking_id, room_id, guest_id, *_ = make_reservation(
            guest_names[i], room_numbers[i], checkin, checkout, "Confirmed"
        )
        conn.execute("UPDATE rooms SET status = 'Reserved' WHERE room_id = ? AND tenant_id = ?",
                    (room_id, tenant_id))
        bookings_created.append(booking_id)

    # 1 cancelled booking (for reports/cancellation rate)
    checkin = today + dt.timedelta(days=5)
    checkout = checkin + dt.timedelta(days=2)
    make_reservation(guest_names[6], room_numbers[6], checkin, checkout, "Cancelled")

    conn.commit()

    # ---------------- Restaurant menu + a sample order ----------------
    menu = [
        ("Masala Dosa", "Breakfast", 120, 5), ("Paneer Butter Masala", "Main Course", 260, 5),
        ("Veg Biryani", "Main Course", 220, 5), ("Butter Naan", "Breads", 40, 5),
        ("Cold Coffee", "Beverages", 90, 12), ("Gulab Jamun", "Dessert", 80, 5),
    ]
    item_ids = {}
    for name, category, rate, tax in menu:
        item_id = new_id("ITM-")
        item_ids[name] = item_id
        conn.execute(
            "INSERT INTO restaurant_items (item_id, tenant_id, name, category, rate, tax_percent) VALUES (?, ?, ?, ?, ?, ?)",
            (item_id, tenant_id, name, category, rate, tax),
        )
    conn.commit()

    if len(bookings_created) >= 3:
        sample_booking_id = bookings_created[2]  # one of the checked-in bookings
        row = conn.execute("SELECT room_id, guest_name FROM reservations WHERE booking_id = ? AND tenant_id = ?",
                           (sample_booking_id, tenant_id)).fetchone()
        order_lines = [
            {"item_id": item_ids["Paneer Butter Masala"], "name": "Paneer Butter Masala", "qty": 2,
             "rate": 260, "tax": 26, "amount": 520},
            {"item_id": item_ids["Butter Naan"], "name": "Butter Naan", "qty": 4, "rate": 40, "tax": 8, "amount": 160},
        ]
        subtotal = sum(l["amount"] for l in order_lines)
        tax_total = sum(l["tax"] for l in order_lines)
        conn.execute(
            """INSERT INTO restaurant_orders (order_id, tenant_id, room_id, booking_id, guest_name, items_json,
               subtotal, discount, tax, total_amount, payment_status, posted_to_room, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, 'Posted to Room', TRUE, ?)""",
            (new_id("ORD-"), tenant_id, row["room_id"], sample_booking_id, row["guest_name"],
             json.dumps(order_lines), subtotal, tax_total, subtotal + tax_total, created_by),
        )

    # ---------------- Housekeeping ----------------
    for room_number, room_id in list(room_ids.items())[:4]:
        conn.execute(
            "INSERT INTO housekeeping (hk_id, tenant_id, room_id, status, assigned_staff, remarks) VALUES (?, ?, ?, ?, ?, ?)",
            (new_id("HK-"), tenant_id, room_id, random.choice(["Clean", "Inspected", "Dirty"]),
             "Meena Kumari", "Routine check"),
        )

    # ---------------- Staff + Attendance ----------------
    staff_ids = []
    for name, dept, designation, salary in STAFF_NAMES:
        staff_id = new_id("STF-")
        staff_ids.append(staff_id)
        conn.execute(
            """INSERT INTO staff (staff_id, tenant_id, name, mobile, department, designation, joining_date,
               salary, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Active')""",
            (staff_id, tenant_id, name, f"98{random.randint(10000000,99999999)}", dept, designation,
             (today - dt.timedelta(days=random.randint(60, 400))).isoformat(), salary),
        )
    conn.commit()

    for staff_id in staff_ids:
        for day_offset in range(5):
            d = today - dt.timedelta(days=day_offset)
            conn.execute(
                """INSERT INTO attendance (attendance_id, tenant_id, staff_id, date, status, in_time, out_time)
                   VALUES (?, ?, ?, ?, ?, '09:00', '18:00')""",
                (new_id("ATT-"), tenant_id, staff_id, d.isoformat(),
                 random.choice(["Present", "Present", "Present", "Half Day"])),
            )

    # ---------------- Inventory ----------------
    inventory_items = [
        ("Bedsheets (King)", "Housekeeping Supplies", "pcs", 40, 10),
        ("Bath Towels", "Housekeeping Supplies", "pcs", 60, 15),
        ("Liquid Hand Soap", "Toiletries", "litre", 20, 5),
        ("Rice (Basmati)", "Kitchen Supplies", "kg", 50, 10),
        ("Cooking Oil", "Kitchen Supplies", "litre", 30, 8),
    ]
    for name, category, unit, opening, minimum in inventory_items:
        conn.execute(
            """INSERT INTO inventory (item_id, tenant_id, name, category, unit, opening_stock, current_stock,
               minimum_stock) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (new_id("INV-"), tenant_id, name, category, unit, opening, opening, minimum),
        )

    # ---------------- Expenses ----------------
    expense_rows = [
        ("Electricity", "Monthly electricity bill", 8500, "Bank Transfer", "State Electricity Board"),
        ("Salary", "Staff salary disbursal", 45000, "Bank Transfer", "-"),
        ("Food Purchase", "Vegetables & groceries", 6200, "Cash", "Local Vendor"),
        ("Maintenance", "AC servicing", 3200, "UPI", "CoolAir Services"),
        ("Marketing", "Online listing boost", 2000, "Card", "OTA Platform"),
    ]
    for category, desc, amount, mode, vendor in expense_rows:
        conn.execute(
            """INSERT INTO expenses (expense_id, tenant_id, date, category, description, amount, payment_mode,
               vendor, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (new_id("EXP-"), tenant_id, (today - dt.timedelta(days=random.randint(1, 20))).isoformat(), category,
             desc, amount, mode, vendor, created_by),
        )

    conn.commit()
    conn.close()

    _set_marker(tenant_id)
    return True, "Demo data added successfully! Explore Dashboard, Reservations, Rooms and Reports to see it."


RESET_MARKER_KEY = "demo_last_reset_at"


def reset_demo_tenant_if_stale(tenant_id, max_age_minutes: int = 60):
    """
    Keeps the shared platform Demo tenant clean: any real booking/guest/etc.
    that a visitor adds while exploring the demo is wiped and the tenant is
    restored to the fixed sample dataset at most `max_age_minutes` after the
    last reset. Cheap on every call (one SELECT) - the expensive wipe+reseed
    only runs once per window, called from app.py on every app load.
    """
    conn = get_connection()
    row = conn.execute(
        "SELECT flag_value FROM app_flags WHERE tenant_id = ? AND flag_key = ?",
        (tenant_id, RESET_MARKER_KEY),
    ).fetchone()
    conn.close()

    now = dt.datetime.utcnow()
    stale = True
    if row and row["flag_value"]:
        try:
            last_reset = dt.datetime.fromisoformat(row["flag_value"])
            stale = (now - last_reset) >= dt.timedelta(minutes=max_age_minutes)
        except ValueError:
            stale = True

    if not stale:
        return False

    clear_demo_data(tenant_id)
    seed_demo_data(tenant_id, created_by="system")

    conn = get_connection()
    conn.execute(
        """INSERT INTO app_flags (tenant_id, flag_key, flag_value) VALUES (?, ?, ?)
           ON CONFLICT (tenant_id, flag_key) DO UPDATE SET flag_value = ?""",
        (tenant_id, RESET_MARKER_KEY, now.isoformat(), now.isoformat()),
    )
    conn.commit()
    conn.close()
    return True


def clear_demo_data(tenant_id):
    """
    Wipes ALL of THIS TENANT's transactional data (bookings, guests, payments,
    invoices, staff, etc.) to give a clean slate before going live. Resort
    profile, users, and licence are kept. Never touches any other tenant.
    """
    tables_to_clear = [
        "checkouts", "checkins", "payments", "invoices", "reservations", "guests",
        "restaurant_orders", "restaurant_items", "housekeeping", "attendance", "staff",
        "purchases", "stock_movements", "inventory", "suppliers", "expenses",
        "notifications", "whatsapp_logs", "audit_logs", "rooms", "room_types",
    ]
    conn = get_connection()
    for table in tables_to_clear:
        conn.execute(f"DELETE FROM {table} WHERE tenant_id = ?", (tenant_id,))
    conn.commit()
    conn.close()
    _clear_marker(tenant_id)
    return True, "All demo/transactional data cleared. Your account, resort profile and licence are untouched."
