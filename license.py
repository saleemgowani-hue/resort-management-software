"""
license.py
Per-tenant subscription logic for SN SOFTECH SOLUTIONS Resort Management
SaaS.

No free trial: a newly signed-up tenant requires a valid licence key
(Monthly or Yearly) before any module besides the Licence page is usable.
Every function here takes an explicit `tenant_id` — there is no more
"the one installation's licence," since one shared database now serves
every tenant on the platform.

Anti-rollback note:
A fully tamper-proof expiry system still isn't achievable without an
online licence-activation server. We keep a per-tenant `last_seen_date`
watermark: if the OS-reported date is EARLIER than the last date seen for
this tenant, we treat the licence as still bound to the later date. This
is a deterrent against trivially editing a database row's date, not a
cryptographic guarantee.
"""

import datetime as dt
import hashlib
import secrets

from database import get_connection

DATE_FMT = "%Y-%m-%d"


def _today() -> dt.date:
    return dt.date.today()


def _as_date(value):
    """PostgreSQL DATE columns come back as datetime.date objects already;
    this also accepts a plain ISO string for safety."""
    if value is None:
        return None
    if isinstance(value, dt.date):
        return value
    return dt.datetime.strptime(str(value)[:10], DATE_FMT).date()


def _get_licence_row(tenant_id: str):
    conn = get_connection()
    row = conn.execute("SELECT * FROM licence WHERE tenant_id = ?", (tenant_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def _effective_today(tenant_id: str) -> dt.date:
    """Return the later of (system date, this tenant's last-seen watermark)."""
    conn = get_connection()
    sys_today = _today()
    row = conn.execute("SELECT last_seen FROM clock_watermark WHERE tenant_id = ?", (tenant_id,)).fetchone()

    if row is None:
        conn.execute("INSERT INTO clock_watermark (tenant_id, last_seen) VALUES (?, ?)",
                     (tenant_id, sys_today.isoformat()))
        conn.commit()
        conn.close()
        return sys_today

    watermark = _as_date(row["last_seen"])
    effective = max(sys_today, watermark)
    if effective != watermark:
        conn.execute("UPDATE clock_watermark SET last_seen = ? WHERE tenant_id = ?",
                    (effective.isoformat(), tenant_id))
        conn.commit()
    conn.close()
    return effective


def initialize_licence_record(tenant_id: str):
    """Idempotent - database.create_tenant() already inserts an INACTIVE
    licence row for every new tenant, so this is a safety net only."""
    conn = get_connection()
    existing = conn.execute("SELECT 1 FROM licence WHERE tenant_id = ?", (tenant_id,)).fetchone()
    if existing:
        conn.close()
        return
    conn.execute("INSERT INTO licence (tenant_id, status) VALUES (?, 'INACTIVE')", (tenant_id,))
    conn.commit()
    conn.close()


def get_status(tenant_id: str):
    """
    Returns a dict describing this tenant's current access state:
    {
        state: 'LICENCE_REQUIRED' | 'ACTIVE' | 'LICENCE_EXPIRING' | 'LICENCE_EXPIRED' | 'NONE',
        days_remaining: int,
        can_access: bool,
        message: str
    }
    """
    from config import LICENCE_WARNING_DAYS_LEFT

    row = _get_licence_row(tenant_id)
    today = _effective_today(tenant_id)

    if row is None:
        return {"state": "NONE", "days_remaining": 0, "can_access": False,
                "message": "No licence found."}

    if row["status"] == "ACTIVE" and row["licence_expiry"]:
        expiry = _as_date(row["licence_expiry"])
        days_remaining = (expiry - today).days
        if days_remaining < 0:
            return {"state": "LICENCE_EXPIRED", "days_remaining": 0, "can_access": False,
                    "message": "Your licence has expired. Please renew to continue."}
        elif days_remaining <= LICENCE_WARNING_DAYS_LEFT:
            return {"state": "LICENCE_EXPIRING", "days_remaining": days_remaining, "can_access": True,
                    "message": f"Licence expiring soon - {days_remaining} day(s) remaining."}
        else:
            return {"state": "ACTIVE", "days_remaining": days_remaining, "can_access": True,
                    "message": f"Licence Active - Valid until {expiry.strftime('%d-%m-%Y')}."}

    return {"state": "LICENCE_REQUIRED", "days_remaining": 0, "can_access": False,
            "message": "Please activate your licence key to start using the software."}


PLAN_DURATION_DAYS = {"Monthly": 30, "Yearly": 365}
_PLAN_PREFIX = {"Monthly": "SNM", "Yearly": "SNY"}
_PREFIX_TO_PLAN = {v: k for k, v in _PLAN_PREFIX.items()}


def _checksum(prefix: str, random_part: str) -> str:
    """4-hex-char HMAC-based checksum, so a key's authenticity can be verified
    without any lookup table — see LICENCE_SIGNING_SECRET in config.py."""
    from config import LICENCE_SIGNING_SECRET

    digest = hashlib.sha256(f"{LICENCE_SIGNING_SECRET}:{prefix}:{random_part}".encode()).hexdigest().upper()
    return digest[:4]


def _generate_key_string(plan_type: str) -> str:
    prefix = _PLAN_PREFIX.get(plan_type, "SNY")
    random_part = secrets.token_hex(6).upper()  # 12 hex chars -> 3 groups of 4
    checksum = _checksum(prefix, random_part)
    groups = [random_part[0:4], random_part[4:8], random_part[8:12], checksum]
    return f"{prefix}RMS-" + "-".join(groups)


def _parse_and_verify_key(licence_key: str):
    """Verifies a key's signature (no database lookup needed). Returns
    (is_valid, plan_type_or_None)."""
    key = (licence_key or "").strip().upper()
    parts = key.split("-")
    if len(parts) != 5:
        return False, None

    prefix_group, g1, g2, g3, checksum = parts
    if not prefix_group.endswith("RMS"):
        return False, None
    prefix = prefix_group[:-3]
    plan_type = _PREFIX_TO_PLAN.get(prefix)
    if plan_type is None:
        return False, None
    if any(len(g) != 4 for g in (g1, g2, g3, checksum)):
        return False, None

    random_part = g1 + g2 + g3
    expected_checksum = _checksum(prefix, random_part)
    if checksum != expected_checksum:
        return False, None

    return True, plan_type


def generate_key_batch(plan_type: str, count: int):
    """
    Generates `count` cryptographically-signed licence keys. STATELESS —
    does not touch any database. Intended for SN SOFTECH SOLUTIONS' private
    key-issuing tool (kept out of the customer/tenant-facing app).
    """
    if plan_type not in PLAN_DURATION_DAYS:
        return []
    seen = set()
    keys = []
    while len(keys) < count:
        key = _generate_key_string(plan_type)
        if key in seen:
            continue
        seen.add(key)
        keys.append(key)
    return keys


def activate_licence(tenant_id: str, licence_key: str):
    """
    Verifies the key's signature, rejects it if already used by ANY tenant
    on the platform (licence_keys.licence_key is globally unique), and
    activates a subscription for this tenant for the duration matching its
    plan_type. Returns (success, message).
    """
    licence_key = (licence_key or "").strip().upper()
    if not licence_key:
        return False, "Please enter a licence key."

    is_valid, plan_type = _parse_and_verify_key(licence_key)
    if not is_valid:
        return False, "This licence key is invalid. Please check it and try again."

    conn = get_connection()
    already_used = conn.execute(
        "SELECT 1 FROM licence_keys WHERE licence_key = ?", (licence_key,)
    ).fetchone()
    if already_used:
        conn.close()
        return False, "This licence key has already been used."

    duration_days = PLAN_DURATION_DAYS.get(plan_type, 365)
    today = _effective_today(tenant_id)
    expiry = today + dt.timedelta(days=duration_days)

    profile = conn.execute("SELECT installation_id FROM resort_profile WHERE tenant_id = ?",
                           (tenant_id,)).fetchone()
    installation_id = profile["installation_id"] if profile else None

    conn.execute(
        """UPDATE licence SET status = 'ACTIVE', licence_key = ?, plan_type = ?,
           activation_date = ?, licence_expiry = ? WHERE tenant_id = ?""",
        (licence_key, plan_type, today.isoformat(), expiry.isoformat(), tenant_id),
    )
    conn.execute(
        """INSERT INTO licence_keys (licence_key, tenant_id, plan_type, status, used_date, used_by_installation)
           VALUES (?, ?, ?, 'Used', ?, ?)""",
        (licence_key, tenant_id, plan_type, today.isoformat(), installation_id),
    )
    conn.commit()
    conn.close()
    return True, f"{plan_type} licence activated successfully! Valid until {expiry.strftime('%d-%m-%Y')}."


def get_licence_details(tenant_id: str):
    row = _get_licence_row(tenant_id)
    return row or {}
