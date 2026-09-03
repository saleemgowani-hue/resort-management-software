"""
styles.py
Custom CSS injected into the Streamlit app so it looks like a commercial
ERP product rather than a default Streamlit demo.
"""

import streamlit as st

SIDEBAR_COLORS = [
    "#2563eb", "#7c3aed", "#db2777", "#dc2626", "#ea580c",
    "#d97706", "#65a30d", "#059669", "#0891b2", "#4f46e5",
    "#0284c7", "#c026d3", "#e11d48", "#16a34a", "#0d9488",
    "#9333ea", "#ca8a04", "#0369a1", "#be123c", "#475569",
]


def inject_css():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

        html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

        /* Hide the hamburger menu, footer and Deploy/toolbar actions, but
           keep the header bar itself (it hosts the sidebar expand/collapse
           button, which is the ONLY way to open the sidebar on mobile —
           hiding the whole header used to hide that button too). */
        #MainMenu, footer, [data-testid="stToolbarActions"], [data-testid="stAppDeployButton"] {visibility: hidden;}
        header[data-testid="stHeader"] {
            background: rgba(0, 0, 0, 0);
            box-shadow: none;
        }

        /* The sidebar's expand button (shown when the sidebar is collapsed,
           which is the ONLY way back into the menu on mobile) renders as a
           faint 60%-opacity grey icon on a plain white header - easy to miss
           on a phone. Give it a solid, high-contrast pill so it reads as an
           obvious button. */
        [data-testid="stExpandSidebarButton"] {
            background: #1e3a8a !important;
            border-radius: 8px !important;
            box-shadow: 0 2px 6px rgba(0,0,0,0.3);
        }
        [data-testid="stExpandSidebarButton"] span[data-testid="stIconMaterial"],
        [data-testid="stExpandSidebarButton"] span {
            color: white !important;
            opacity: 1 !important;
        }

        .block-container { padding-top: 1.2rem; padding-bottom: 2rem; max-width: 1400px; }

        /* ---------------- Brand header ---------------- */
        .rms-topbar {
            background: linear-gradient(90deg, #0f172a 0%, #1e3a8a 100%);
            padding: 14px 24px;
            border-radius: 14px;
            color: white;
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 18px;
            box-shadow: 0 4px 14px rgba(15, 23, 42, 0.25);
        }
        .rms-topbar h1 { font-size: 20px; margin: 0; font-weight: 800; letter-spacing: 0.5px; }
        .rms-topbar .sub { font-size: 12px; opacity: 0.8; margin-top: 2px; }
        .rms-topbar .meta { text-align: right; font-size: 13px; line-height: 1.5; }

        /* ---------------- KPI cards ---------------- */
        .kpi-card {
            border-radius: 14px;
            padding: 16px 18px;
            color: white;
            box-shadow: 0 4px 10px rgba(0,0,0,0.12);
            min-height: 92px;
        }
        .kpi-card .label { font-size: 12.5px; opacity: 0.92; font-weight: 600; text-transform: uppercase; letter-spacing: 0.4px;}
        .kpi-card .value { font-size: 26px; font-weight: 800; margin-top: 6px; }

        /* ---------------- Sidebar buttons ---------------- */
        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #0f172a 0%, #111827 100%);
        }
        section[data-testid="stSidebar"] .stButton button {
            width: 100%;
            text-align: left;
            border: none;
            border-radius: 10px;
            padding: 10px 14px;
            margin-bottom: 6px;
            font-weight: 600;
            font-size: 14.5px;
            color: white;
            transition: transform 0.12s ease, filter 0.12s ease;
        }
        section[data-testid="stSidebar"] .stButton button:hover {
            filter: brightness(1.12);
            transform: translateX(2px);
        }
        section[data-testid="stSidebar"] .brand-box {
            padding: 14px 10px 18px 10px;
            text-align: center;
            border-bottom: 1px solid rgba(255,255,255,0.1);
            margin-bottom: 10px;
        }
        section[data-testid="stSidebar"] .brand-box h2 {
            color: white; font-size: 16px; margin: 0; font-weight: 800;
        }
        section[data-testid="stSidebar"] .brand-box p {
            color: #94a3b8; font-size: 11px; margin: 2px 0 0 0;
        }

        /* ---------------- Status pills ---------------- */
        .status-pill {
            display: inline-block; padding: 3px 12px; border-radius: 20px;
            font-size: 12px; font-weight: 700; color: white;
        }

        /* ---------------- Section headers ---------------- */
        .section-title {
            font-size: 20px; font-weight: 800; color: #0f172a; margin: 6px 0 14px 0;
            border-left: 5px solid #2563eb; padding-left: 10px;
        }

        /* ---------------- Trial / licence banner ---------------- */
        .licence-banner {
            padding: 10px 16px; border-radius: 10px; font-weight: 700; font-size: 13.5px;
            margin-bottom: 14px; color: white;
        }

        div[data-testid="stMetric"] {
            background: white; border: 1px solid #e5e7eb; border-radius: 12px; padding: 10px 14px;
        }

        .stDataFrame { border-radius: 10px; overflow: hidden; }

        /* ---------------- Mobile / Tablet responsiveness ---------------- */
        @media (max-width: 900px) {
            .block-container { padding-left: 0.8rem; padding-right: 0.8rem; padding-top: 0.8rem; }

            .rms-topbar {
                flex-direction: column;
                align-items: flex-start;
                gap: 8px;
                padding: 12px 16px;
            }
            .rms-topbar h1 { font-size: 17px; }
            .rms-topbar .meta { text-align: left; font-size: 12px; }

            .kpi-card { padding: 12px 14px; min-height: 76px; }
            .kpi-card .label { font-size: 11px; }
            .kpi-card .value { font-size: 20px; }

            .section-title { font-size: 17px; }

            section[data-testid="stSidebar"] .stButton button {
                font-size: 13.5px;
                padding: 9px 12px;
            }

            header[data-testid="stHeader"] {
                min-height: 2.75rem;
            }
            [data-testid="stSidebarCollapsedControl"] {
                visibility: visible !important;
                display: block !important;
            }
        }

        @media (max-width: 640px) {
            .block-container { padding-left: 0.5rem; padding-right: 0.5rem; }
            .kpi-card .value { font-size: 18px; }
            .rms-topbar h1 { font-size: 15px; }
            div[data-testid="column"] { min-width: 100% !important; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def kpi_card_html(label, value, color1, color2):
    return f"""
    <div class="kpi-card" style="background: linear-gradient(135deg, {color1}, {color2});">
        <div class="label">{label}</div>
        <div class="value">{value}</div>
    </div>
    """


def status_pill(text, color):
    return f'<span class="status-pill" style="background:{color};">{text}</span>'
