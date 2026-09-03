# Technical Audit — SN SOFTECH SOLUTIONS Resort Management System
### (Phase 1 & 2 of the SaaS Migration — completed before any code changes)

## A. Current Architecture

**Entry point:** `app.py` — Streamlit `st.set_page_config` + custom CSS
injection, then a hand-rolled router (`route(page_key)`) dispatching to one
`render()` function per module based on `st.session_state["current_page"]`.

**Modules (one file each, all under `modules/`):** dashboard, reservations,
rooms, guests, checkin, checkout, billing, restaurant, housekeeping, staff,
attendance, inventory, expenses, reports, kpi, whatsapp_center, settings,
notifications, licence_page. Each exposes a single `render()` function
called by `app.py`'s router. No shared base class; each module imports
`database.get_connection()` directly and writes its own SQL.

**Database access pattern:** every module opens its own short-lived
`sqlite3.Connection` via `database.get_connection()`, runs one or more
`conn.execute(sql, params)` calls with `?`-style placeholders, reads rows
via `sqlite3.Row` (dict-like access), and closes the connection at the end
of the function. There is no ORM, no connection pooling, no shared
transaction scope across multiple statements in most modules (a few — e.g.
checkout — do multiple writes on one connection before a single `commit()`).

**Authentication:** `auth.py`. Bcrypt password hashing. `sign_up()` was
already restricted to run once per installation (`any_user_exists()` guard)
because the old architecture assumed one resort per installation. Staff
users are created by an ADMIN via `create_staff_user()`. Session state
(`st.session_state["authenticated"]`, `st.session_state["user"]`) holds the
logged-in user's row as a dict for the browser session's lifetime — no
server-side session store, no JWT, no cross-device session.

**Licence/subscription:** `license.py`. A single `licence` row
(`id INTEGER PRIMARY KEY CHECK (id = 1)`) per SQLite file represents "the
one resort this installation belongs to." No trial period (removed in a
prior revision). Keys are Monthly/Yearly, verified via an HMAC checksum
against a shared secret (`config.LICENCE_SIGNING_SECRET`) — this is
already offline/stateless-verification, not a lookup-table design, which
is actually SaaS-friendly (no data migration needed for key logic itself,
only for *where the subscription record lives*).

**Business logic location:** almost entirely inline inside each module's
`render()` function — form handling, validation, SQL, and the resulting
`st.dataframe`/`st.metric` rendering are interleaved in the same function.
There is no separate service/repository layer.

**Reporting:** `modules/reports.py` (ad-hoc SQL per report name, exports
via pandas `ExcelWriter` + `pdf_generator.generate_simple_report_pdf`),
`modules/kpi.py` (aggregate SQL for ADR/RevPAR/occupancy/etc.), and
`modules/dashboard.py` (live KPI cards + Plotly charts). All read directly
from SQLite with raw SQL.

**File management:** `pdf_generator.py` (ReportLab, writes to local
`data/invoices/` and `data/receipts/`), `demo_data.py` (seeds sample rows),
`assets/` (logo, bundled Unicode font, app icon) — all local filesystem
paths computed once in `config.py` from `BASE_DIR`.

## B. Database Audit — Every Existing Table

All primary keys are **application-generated TEXT ids** (e.g. `new_id("BK-")`
→ short uppercase hex strings), not database autoincrement integers — this
is actually helpful for the migration, since PostgreSQL can keep the exact
same TEXT primary keys with no ID remapping.

| Table | Key columns | PK | FKs | Notes |
|---|---|---|---|---|
| `resort_profile` | resort_name, address, mobile, email, gst_number, currency_symbol, tax_percent, invoice_prefix, whatsapp_country_code, installation_id | `id` (CHECK id=1, singleton) | — | **Must become one row per tenant**, not a singleton |
| `users` | username (UNIQUE), email (UNIQUE), mobile, full_name, password_hash, role, is_active | `user_id` | — | **Must gain `tenant_id`**; username/email uniqueness must become scoped *per tenant*, not global |
| `licence` | status, licence_key, plan_type, activation_date, licence_expiry | `id` (CHECK id=1, singleton) | — | **Must become one row per tenant** (subscription record) |
| `licence_keys` | licence_key, plan_type, status, used_date, used_by_installation | `licence_key` | — | Reuse-guard log; needs `tenant_id` so one tenant's used key doesn't block another tenant reusing the *same string* (won't happen with the checksum scheme in practice, but tenant_id is added for auditability) |
| `room_types` | name, base_tariff, weekend_tariff, extra_person_charge | `room_type_id` | — | + tenant_id |
| `rooms` | room_number, room_type_id, floor, capacity, tariff, status | `room_id` | room_type_id → room_types | + tenant_id; room_number uniqueness scoped per tenant |
| `guests` | name, mobile, email, id_proof_type, visits, last_visit | `guest_id` | — | + tenant_id |
| `reservations` | guest_id, room_id, checkin/checkout dates, tariff/discount/tax/total, status | `booking_id` | guest_id → guests, room_id → rooms | + tenant_id; double-booking check must be scoped per tenant |
| `checkins` | booking_id, guest_id, room_id, advance_payment | `checkin_id` | booking_id → reservations | + tenant_id |
| `checkouts` | booking_id, guest_id, room_id, charges/discount/tax/total | `checkout_id` | booking_id → reservations | + tenant_id |
| `invoices` | invoice_number, booking_id, guest_id, amounts, file_path | `invoice_id` | booking_id → reservations | + tenant_id; invoice_number sequence scoped per tenant |
| `payments` | booking_id, guest_id, amount, mode, type | `payment_id` | booking_id → reservations | + tenant_id |
| `restaurant_items` | name, category, rate, tax_percent | `item_id` | — | + tenant_id |
| `restaurant_orders` | room_id, booking_id, items_json, totals | `order_id` | — | + tenant_id |
| `housekeeping` | room_id, status, assigned_staff | `hk_id` | room_id → rooms | + tenant_id |
| `staff` | name, mobile, department, designation, salary | `staff_id` | — | + tenant_id |
| `attendance` | staff_id, date, status, in/out time | `attendance_id` | staff_id → staff | + tenant_id |
| `suppliers` | name, mobile, address | `supplier_id` | — | + tenant_id |
| `inventory` | name, category, unit, stock levels | `item_id` | supplier_id → suppliers | + tenant_id |
| `purchases` | item_id, quantity, rate, total | `purchase_id` | item_id → inventory | + tenant_id |
| `stock_movements` | item_id, type, quantity | `movement_id` | item_id → inventory | + tenant_id |
| `expenses` | date, category, description, amount | `expense_id` | — | + tenant_id |
| `notifications` | type, message, is_read | `notification_id` | — | + tenant_id |
| `whatsapp_logs` | booking_id, guest_id, mobile, message_type, status | `message_id` | — | + tenant_id |
| `audit_logs` | user, action, module, record_id | `log_id` | — | + tenant_id |
| `app_flags` | flag_key, flag_value | `flag_key` | — | Used only for the demo-data-seeded marker; needs `tenant_id` folded into the key or a composite PK |

**Constraints found:** `FOREIGN KEY` relations exist but are declared
without explicit `ON DELETE` behavior (defaults to `NO ACTION` in both
SQLite and PostgreSQL — acceptable, kept as-is). Several `UNIQUE`
constraints (`users.username`, `users.email`, `room_types.name`,
`rooms.room_number`, `licence_keys.licence_key`) are currently **global**
and must become **composite-unique with `tenant_id`** so two tenants can
each have a room "101" or a staff member with the same email domain
pattern, etc.

## C. Migration Audit

**Must migrate to PostgreSQL:** the entire schema above, with `tenant_id`
added to every business table and the two former "singleton" tables
(`resort_profile`, `licence`) converted to one-row-per-tenant.

**Can remain unchanged:** the business logic *inside* each module's SQL
(the actual booking-overlap logic, KPI formulas, invoice totals math) — none
of that is SQLite-specific. Report/PDF/Excel generation code is DB-agnostic
already (it consumes already-fetched Python dicts).

**Must be rewritten:** every SQL call site across all ~19 module files plus
`auth.py`, `license.py`, `demo_data.py`, `utils.py` — two mechanical
changes needed everywhere: (1) placeholder style `?` → `%s` and (2) add a
`tenant_id = %s` predicate to every tenant-scoped `SELECT`/`UPDATE`/`DELETE`
and a `tenant_id` value to every tenant-scoped `INSERT`. A small number of
SQLite-only SQL functions are used and need PostgreSQL equivalents:
`datetime('now')` → `NOW()`, `date('now')` → `CURRENT_DATE`,
`date('now','-13 days')` → `CURRENT_DATE - INTERVAL '13 days'`.

**Requires a database abstraction layer:** yes — rather than hand-editing
~150 call sites' placeholder syntax with find/replace (error-prone), this
migration introduces `db.py`, a thin compatibility layer that (a) accepts
the existing `?`-placeholder SQL text unchanged, translates it to `%s` for
psycopg2 at execute-time, and (b) returns `RealDictCursor` rows that
support the same `row["column"]` access pattern the modules already use
via `sqlite3.Row` — this made it possible to migrate ~150 call sites by
changing only 2 lines per module (the import and the `tenant_id` filter
addition) instead of hand-rewriting every SQL string's placeholder style.

**Requires transaction handling:** `checkout.py` and `reservations.py`
perform multiple related writes (reservation insert + room status update;
checkout insert + invoice insert + payment insert) that must succeed or
fail together — these are wrapped in explicit transactions in the new
`db.py` (`with db.transaction(): ...`) rather than relying on
autocommit-per-statement.

**Requires indexing:** `tenant_id` on every business table (composite with
the existing indexes on `room_id`/`booking_date`/etc.), since virtually
every query will now filter on it first.

## D. SaaS Readiness Audit

| Requirement | Status before migration | Work needed |
|---|---|---|
| Multi-tenant | ❌ single resort per SQLite file | Add `tenants` table + `tenant_id` everywhere (this migration) |
| Secure | ✅ bcrypt hashing, parameterized SQL already used | Carry forward; add tenant-scoping to prevent cross-tenant leaks |
| Scalable | ❌ SQLite, one file per customer, no pooling | PostgreSQL + SQLAlchemy pooled engine (this migration) |
| Subscription-based | ✅ Monthly/Yearly logic already exists | Re-home the single `licence` row as a per-tenant row |
| Cloud deployable | ❌ local file paths, no secrets management | `DATABASE_URL` via env/Streamlit secrets, `.gitignore`, `.streamlit/config.toml` (this migration) |
| Production ready | Partial | Everything above, plus real tenant-isolation testing (done below with a live PostgreSQL instance, not just claimed) |
