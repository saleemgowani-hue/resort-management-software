# SN SOFTECH SOLUTIONS — Resort Management System (Multi-Tenant SaaS)

A commercial-grade, multi-tenant Resort/Hotel Management SaaS built with
Python + Streamlit + PostgreSQL. Every resort that signs up gets a fully
isolated workspace — no customer can ever see another customer's data.

**This is a SaaS rebuild of an earlier single-tenant desktop version.** See
`TECHNICAL_AUDIT.md` for the full before/after architecture audit that was
done before any code was changed, per the migration's own review process.

---

## ⚠️ Please read before you deploy this

This build implements the full multi-tenant architecture **for real,
tested against a live PostgreSQL database** (not mocked): tenant-isolated
signup, independent per-tenant subscriptions, a shared read-only Demo
account, and every business module (rooms, guests, reservations,
check-in/out, billing, restaurant, housekeeping, staff, attendance,
inventory, expenses, reports, KPI analytics, WhatsApp messaging, settings)
scoped to `tenant_id` at the query layer — never just UI-level filtering.

`test_tenant_isolation.py` is a real, runnable test suite (Phase 19) that
creates two tenants, seeds each with data, and asserts neither can see the
other's rooms, guests, bookings, staff, expenses, or inventory — both via
the app's own query helpers and via direct raw SQL. Run it yourself before
trusting this in production:

```bash
export DATABASE_URL=postgresql://user:pass@host:5432/dbname
python3 test_tenant_isolation.py
```

**What this build has NOT had yet:** a payment gateway integration (the
subscription/licence-key system is ready to plug one into — see
`license.py`), load/concurrency testing under real multi-tenant traffic,
and a security penetration test. Treat this as a solid, verified v1
architecture — not a "ship immediately, no further review" package.

---

## 1. Architecture at a Glance

```
Platform (this app)
  └── Tenant / Resort  (tenants table — one per customer)
        └── Users        (role: ADMIN / MANAGER / RECEPTIONIST / HOUSEKEEPING / ACCOUNTANT)
              └── Roles & Permissions   (config.ROLE_MENU_ACCESS)
                    └── Resort Data     (rooms, guests, bookings, staff, ... — all tagged tenant_id)
```

- **One shared PostgreSQL database** serves every tenant.
- **Every business table has a `tenant_id` column**, and every query in
  every module filters on it. This is the actual isolation boundary — see
  `TECHNICAL_AUDIT.md` section B for the full table-by-table breakdown.
- **Usernames and emails are unique platform-wide** (not per-tenant) —
  there's a single shared login screen with no tenant subdomain/selector,
  so a user's tenant is looked up from their own account after signing in.
- **Sign Up always creates a brand-new, fully isolated tenant.** This is
  the core of the multi-tenant model — many resorts, one app, zero data
  crossover.

## 2. PostgreSQL Setup

You need a PostgreSQL 13+ database (local, or a managed provider like
Supabase, Neon, Render, or ElephantSQL — any of these work fine with
Streamlit Cloud).

```bash
# Local example (adjust for your OS):
createdb resort_saas
```

Set the connection string as an environment variable:

```bash
export DATABASE_URL="postgresql://user:password@host:5432/resort_saas"
```

The app creates its own schema automatically on first run (`database.py`'s
`init_db()`) — no manual migration step needed for a fresh database.

## 3. Running Locally

```bash
git clone <this-repo>
cd resort_management
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

export DATABASE_URL="postgresql://user:password@host:5432/resort_saas"
streamlit run app.py
```

Windows users can instead double-click **`run.bat`** after setting
`DATABASE_URL` (`set DATABASE_URL=...` in the same terminal, or via System
Environment Variables) — it handles the virtual environment and dependency
install automatically. `run_network.bat` does the same but also exposes
the app on your local network for testing from a phone/tablet. Both are
local development conveniences; production deployment is Streamlit Cloud
(below).

## 4. Streamlit Cloud Deployment

1. Push this repository to GitHub (see the `.gitignore` — secrets and
   local data are already excluded; never commit `.streamlit/secrets.toml`).
2. On [share.streamlit.io](https://share.streamlit.io), create a new app
   pointing at this repo, branch, and `app.py`.
3. In the app's **Settings → Secrets**, paste:
   ```toml
   DATABASE_URL = "postgresql://user:password@host:5432/resort_saas"
   ```
   (copy the format from `.streamlit/secrets.toml.example`)
4. Deploy. The app creates its schema automatically on first boot.

`db.py` resolves the connection string from `st.secrets["DATABASE_URL"]`
first, falling back to the `DATABASE_URL` environment variable — so the
same code works unchanged locally and on Streamlit Cloud.

## 5. GitHub Repository Structure

```
resort_management/
├── app.py                      # Entry point: auth, tenant routing, sidebar shell
├── db.py                       # PostgreSQL connection pool (psycopg2 + compatibility shim)
├── database.py                 # Multi-tenant schema (init_db, create_tenant, is_demo_tenant)
├── auth.py                     # Sign up (creates a new tenant each time) / sign in / staff users
├── license.py                  # Per-tenant subscription logic (Monthly/Yearly, checksum keys)
├── demo_data.py                # Per-tenant sample data seeder
├── config.py                   # Branding, constants, role menus, licence signing secret
├── utils.py                    # Shared helpers — all tenant_id-scoped
├── whatsapp.py                 # WhatsApp Click-to-Chat + message templates (tenant scoped)
├── pdf_generator.py            # ReportLab invoice/receipt/report PDFs (tenant scoped)
├── styles.py                   # Custom CSS for the ERP look & feel
├── requirements.txt
├── .gitignore
├── .streamlit/
│   ├── config.toml             # Theme + server settings
│   └── secrets.toml.example    # Template — copy to secrets.toml locally, never commit it
├── TECHNICAL_AUDIT.md           # Phase 1-2 audit performed before migration
├── test_tenant_isolation.py     # Phase 19 — real isolation tests against live Postgres
├── assets/                      # Fonts, icons
└── modules/                     # One file per menu item — every query tenant_id-scoped
```

## 6. Environment / Secrets Configuration

| Variable | Where | Required | Purpose |
|---|---|---|---|
| `DATABASE_URL` | Env var (local) or `st.secrets` (Cloud) | Yes | PostgreSQL connection string |

`config.LICENCE_SIGNING_SECRET` is a code-level constant (not an env var)
used to verify licence keys offline — see the comment in `config.py` for
why, and change it before selling real subscriptions.

## 7. Subscriptions (Monthly / Yearly, No Trial)

Each tenant has its own subscription row (`licence` table, keyed by
`tenant_id` — no longer a singleton like the old desktop build). Right
after Sign Up, every module is locked except the Licence page until a
Monthly or Yearly key is activated. Keys are cryptographically
checksum-verified (no lookup table needed), issued by a **separate,
private key-generator tool kept out of this repository** — see the
comment block at the top of `license.py` for the exact mechanism, and
ask for that tool separately if you don't already have it. Never commit
a real signing secret to a public repo.

## 8. Demo Account (Phase 9)

A shared, permanently-licensed Demo tenant (`SN Softech Demo Resort`) is
created automatically the first time the app boots, pre-seeded with
sample rooms/guests/bookings. On the Sign In screen, anyone can click
**"👀 Try the Live Demo"** to explore instantly without registering.

The Demo tenant is protected at the `auth.py` layer (not just hidden UI):
`create_staff_user`, `set_user_active`, and `reset_user_password` all
explicitly refuse to run against it, and `modules/settings.py` shows a
locked banner instead of the profile/settings/user-management forms. It's
fully isolated from every real tenant like any other — it just can't be
modified.

## 9. User Roles & Adding Staff Logins

| Role | Access |
|---|---|
| ADMIN | Everything |
| MANAGER | Bookings, rooms, guests, reports, billing, housekeeping, staff |
| RECEPTIONIST | Reservations, guests, check-in/out, billing, WhatsApp |
| HOUSEKEEPING | Housekeeping module only |
| ACCOUNTANT | Billing, payments, expenses, financial reports |

Add more logins for your team from **⚙️ Settings → User Management**
(ADMIN only) — they share your resort's licence and data automatically.
The public Sign Up form always creates a **new, separate** tenant, so
it's the wrong place to add staff.

## 10. Demo/Sample Data for Your Own Account

Separately from the shared platform Demo account above, any real tenant
can click **⚙️ Settings → Demo Data → ✨ Add Demo Data** to populate their
own workspace with realistic sample rooms, guests, bookings, staff,
inventory, and expenses — useful for exploring the software before
entering real data. **Clear Demo Data** wipes it again, scoped to that
tenant only.

## 11. Data Export

Because many tenants now share one database, the old desktop build's
"download the whole SQLite file" backup feature has been replaced with a
safe **per-tenant JSON export** (Settings → Data Export) that only ever
includes the signed-in tenant's own records. A platform-wide `pg_dump`
backup is an infrastructure-level task for whoever operates the Postgres
instance, not a per-tenant self-service feature (giving a tenant the raw
database would leak every other tenant's data).

## 12. WhatsApp Setup

No API keys required for the initial version — it uses WhatsApp
**Click-to-Chat**. Buttons across Reservations, Check-In, Check-Out,
Billing, and the WhatsApp Center open `wa.me` with the message pre-filled;
staff review and press Send. Logged as "Initiated," never "Delivered,"
since the app can't know if a message was actually sent without an
official WhatsApp Business API integration (the single integration point
for that is `whatsapp.py`).

## 13. Testing Checklist

**Authentication**
- [x] Sign up creates a new, isolated tenant (verified: `test_tenant_isolation.py`)
- [x] Sign in / invalid password / inactive user rejected
- [x] Staff logins scoped to the creating tenant only

**Multi-tenancy / isolation**
- [x] Two tenants' guests, rooms, bookings, staff, expenses, inventory never overlap (raw SQL + app layer)
- [x] Room number "999" can exist independently in two tenants; duplicate within one tenant is rejected
- [x] One tenant cannot fetch another's booking by ID even when explicitly requested

**Subscriptions**
- [x] New tenant starts as `LICENCE_REQUIRED`
- [x] Activating Tenant A's licence does not affect Tenant B's status
- [x] Monthly (30 days) / Yearly (365 days) durations calculate correctly
- [x] Invalid / tampered / reused keys are rejected

**Demo account**
- [x] Auto-created once, idempotently, on first app boot
- [x] Pre-seeded with sample data; permanently licensed
- [x] Settings/user-management writes are blocked at the `auth.py` layer, not just hidden in the UI

**Database**
- [x] Insert / update / delete / foreign keys / transactions (checkout.py uses `db.transaction()`)
- [x] Schema applies cleanly to a fresh PostgreSQL database

**Deployment**
- [x] Runs locally against PostgreSQL with `DATABASE_URL` set
- [ ] Streamlit Cloud live deployment (needs your GitHub repo + Cloud account — architecture is ready, actual cloud deploy step is yours to run)
- [ ] Payment gateway integration (subscription system is ready to connect one)
- [ ] Load/concurrency testing under real multi-tenant traffic

---
**Powered by SN SOFTECH SOLUTIONS**
