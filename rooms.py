import streamlit as st
import pandas as pd

from config import ROOM_STATUSES, ROOM_STATUS_COLORS
from database import get_connection, new_id
from styles import status_pill
from utils import currency, log_audit
import auth


def _get_room_types(tenant_id):
    conn = get_connection()
    rows = conn.execute("SELECT * FROM room_types WHERE tenant_id = ? ORDER BY name", (tenant_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _get_rooms(tenant_id):
    conn = get_connection()
    rows = conn.execute("""
        SELECT r.*, rt.name as room_type_name
        FROM rooms r LEFT JOIN room_types rt ON r.room_type_id = rt.room_type_id
        WHERE r.is_active = TRUE AND r.tenant_id = ?
        ORDER BY r.room_number
    """, (tenant_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def render():
    st.markdown('<div class="section-title">🛏️ Room Management</div>', unsafe_allow_html=True)
    user = st.session_state.get("user", {})
    tenant_id = auth.current_tenant_id()

    tab1, tab2, tab3 = st.tabs(["Room Status Board", "Room Master", "Room Types"])

    # ---------------- Room Status Board ----------------
    with tab1:
        rooms = _get_rooms(tenant_id)
        if not rooms:
            st.info("No rooms added yet. Go to 'Room Master' tab to add your first room.")
        else:
            cols = st.columns(4)
            for i, room in enumerate(rooms):
                color = ROOM_STATUS_COLORS.get(room["status"], "#6b7280")
                with cols[i % 4]:
                    st.markdown(
                        f"""
                        <div style="border:1px solid #e5e7eb;border-left:6px solid {color};
                                    border-radius:10px;padding:12px 14px;margin-bottom:12px;background:white;">
                            <div style="font-weight:800;font-size:16px;">Room {room['room_number']}</div>
                            <div style="font-size:12.5px;color:#64748b;">{room.get('room_type_name') or '-'} | Floor {room.get('floor') or '-'}</div>
                            <div style="margin-top:6px;">{status_pill(room['status'], color)}</div>
                            <div style="font-size:12.5px;margin-top:6px;">{currency(tenant_id, room['tariff'])}/night</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

    # ---------------- Room Master ----------------
    with tab2:
        with st.expander("➕ Add New Room", expanded=len(_get_rooms(tenant_id)) == 0):
            room_types = _get_room_types(tenant_id)
            rt_options = {rt["name"]: rt["room_type_id"] for rt in room_types}
            with st.form("add_room_form", clear_on_submit=True):
                c1, c2, c3 = st.columns(3)
                room_number = c1.text_input("Room Number *")
                floor = c2.text_input("Floor")
                ac_type = c3.selectbox("AC / Non-AC", ["AC", "Non-AC"])

                c4, c5, c6 = st.columns(3)
                room_type_name = c4.selectbox("Room Type", list(rt_options.keys()) or ["-- add a room type first --"])
                capacity = c5.number_input("Capacity", min_value=1, value=2)
                adult_cap = c6.number_input("Adult Capacity", min_value=1, value=2)

                c7, c8, c9 = st.columns(3)
                child_cap = c7.number_input("Child Capacity", min_value=0, value=1)
                tariff = c8.number_input("Tariff (₹)", min_value=0.0, value=2000.0, step=100.0)
                weekend_tariff = c9.number_input("Weekend Tariff (₹)", min_value=0.0, value=2500.0, step=100.0)

                c10, c11 = st.columns(2)
                extra_person = c10.number_input("Extra Person Charge (₹)", min_value=0.0, value=500.0, step=50.0)
                amenities = c11.text_input("Amenities (comma separated)", value="WiFi, TV, Hot Water")

                submitted = st.form_submit_button("Save Room", type="primary")
                if submitted:
                    if not room_number:
                        st.error("Room Number is required.")
                    else:
                        conn = get_connection()
                        exists = conn.execute("SELECT 1 FROM rooms WHERE tenant_id = ? AND room_number = ?",
                                              (tenant_id, room_number)).fetchone()
                        if exists:
                            st.error(f"Room {room_number} already exists.")
                            conn.close()
                        else:
                            room_id = new_id("RM-")
                            conn.execute(
                                """INSERT INTO rooms (room_id, tenant_id, room_number, room_type_id, floor, capacity,
                                   adult_capacity, child_capacity, tariff, weekend_tariff, extra_person_charge,
                                   ac_type, amenities, status)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Available')""",
                                (room_id, tenant_id, room_number, rt_options.get(room_type_name), floor, capacity,
                                 adult_cap, child_cap, tariff, weekend_tariff, extra_person, ac_type, amenities),
                            )
                            conn.commit()
                            conn.close()
                            log_audit(tenant_id, user.get("username", ""), "Room created", "rooms", room_id)
                            st.success(f"Room {room_number} added successfully.")
                            st.rerun()

        rooms = _get_rooms(tenant_id)
        if rooms:
            df = pd.DataFrame(rooms)[["room_number", "room_type_name", "floor", "capacity", "tariff",
                                       "weekend_tariff", "ac_type", "status"]]
            df.columns = ["Room No", "Type", "Floor", "Capacity", "Tariff", "Weekend Tariff", "AC", "Status"]
            st.dataframe(df, use_container_width=True, hide_index=True)

            st.markdown("##### Update Room Status")
            room_map = {f"{r['room_number']} ({r['status']})": r["room_id"] for r in rooms}
            selected = st.selectbox("Select Room", list(room_map.keys()))
            new_status = st.selectbox("New Status", ROOM_STATUSES)
            if st.button("Update Status"):
                conn = get_connection()
                conn.execute("UPDATE rooms SET status = ? WHERE room_id = ? AND tenant_id = ?",
                            (new_status, room_map[selected], tenant_id))
                conn.commit()
                conn.close()
                log_audit(tenant_id, user.get("username", ""), f"Room status changed to {new_status}",
                          "rooms", room_map[selected])
                st.success("Room status updated.")
                st.rerun()

    # ---------------- Room Types ----------------
    with tab3:
        with st.form("add_room_type_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            name = c1.text_input("Room Type Name *", placeholder="e.g. Deluxe, Suite, Cottage")
            base_tariff = c2.number_input("Base Tariff (₹)", min_value=0.0, value=2000.0, step=100.0)
            weekend_tariff = c3.number_input("Weekend Tariff (₹)", min_value=0.0, value=2500.0, step=100.0)
            extra_charge = st.number_input("Extra Person Charge (₹)", min_value=0.0, value=500.0, step=50.0)
            description = st.text_area("Description")
            if st.form_submit_button("Save Room Type", type="primary"):
                if not name:
                    st.error("Room type name is required.")
                else:
                    conn = get_connection()
                    exists = conn.execute("SELECT 1 FROM room_types WHERE tenant_id = ? AND name = ?",
                                          (tenant_id, name)).fetchone()
                    if exists:
                        st.error(f"Room type '{name}' already exists.")
                        conn.close()
                    else:
                        conn.execute(
                            """INSERT INTO room_types (room_type_id, tenant_id, name, base_tariff, weekend_tariff,
                               extra_person_charge, description) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                            (new_id("RT-"), tenant_id, name, base_tariff, weekend_tariff, extra_charge, description),
                        )
                        conn.commit()
                        conn.close()
                        st.success(f"Room type '{name}' added.")
                        st.rerun()

        room_types = _get_room_types(tenant_id)
        if room_types:
            df = pd.DataFrame(room_types)[["name", "base_tariff", "weekend_tariff", "extra_person_charge"]]
            df.columns = ["Room Type", "Base Tariff", "Weekend Tariff", "Extra Person Charge"]
            st.dataframe(df, use_container_width=True, hide_index=True)
