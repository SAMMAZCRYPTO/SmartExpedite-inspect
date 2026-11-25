"""
SmartExpedit — Procurement Expediting & Material Tracking UI Module
===================================================================
Built in pure Python (Streamlit + Altair + Pandas) and styled to match
the exact layout, look, and feel of the InspectFlow application:
- 5-column StatsCard tiles with right-aligned 56x56 colored icon badges
- White elevation-2 rounded-2xl cards (.orig-white-card)
- Pill status badges and clean data registers
"""

import io
from datetime import date, datetime, timedelta
from typing import Dict, Any, List, Optional

import altair as alt
import openpyxl
import pandas as pd
import streamlit as st

from python_app.epc_constants import (
    ROLES,
    EPC_ROLE_LABELS,
    WBS_CATEGORIES,
    WBS_CATEGORY_COLORS,
    PO_STATUS_COLORS,
    RAIL_STATUS_COLORS,
    RAIL_IMPACT_COLORS,
    APPROVAL_CODE_LABELS,
    APPROVAL_CODE_COLORS,
    INSPECTION_STATUS_COLORS,
    INSPECTION_ACTIVITY_CODES,
    INSPECTION_TYPE_LABELS,
    BULK_STAGES,
    FLOAT_BADGE,
    calc_float,
    calc_vdrl_sla,
    format_date_gb,
    days_from_now,
    build_scurve,
)
from python_app import expediting_db
from python_app.expediting_parsers import (
    parse_vendor_schedule_file,
    parse_suborder_report_file,
)


# ---------------------------------------------------------------------------
# Shared Visual Helpers (matching InspectFlow StatsCard & Badges)
# ---------------------------------------------------------------------------

def _stat_card_html(title: str, value: Any, subtitle: str, icon: str, color: str = "blue") -> str:
    return f"""
    <div class="orig-stat-card">
        <div style="flex:1; min-width:0;">
            <p class="orig-stat-title">{title}</p>
            <h3 class="orig-stat-val">{value}</h3>
            <p class="orig-stat-sub">{subtitle}</p>
        </div>
        <div class="orig-stat-icon icon-{color}">
            {icon}
        </div>
    </div>
    """


def _badge_html(text: str, bg: str, fg: str, border: str = "transparent") -> str:
    return (
        f'<span style="display:inline-flex;align-items:center;padding:2px 9px;'
        f'border-radius:9999px;font-size:0.72rem;font-weight:700;'
        f'background:{bg};color:{fg};border:1px solid {border};white-space:nowrap;">'
        f'{text}</span>'
    )


def _po_status_badge(status: str) -> str:
    st_key = (status or "ACTIVE").upper()
    c = PO_STATUS_COLORS.get(st_key, PO_STATUS_COLORS["ACTIVE"])
    return _badge_html(st_key.replace("_", " "), c["bg"], c["text"], c["border"])


def _wbs_badge(cat: str) -> str:
    c_key = (cat or "ENGINEERING").upper()
    c = WBS_CATEGORY_COLORS.get(c_key, WBS_CATEGORY_COLORS["ENGINEERING"])
    return _badge_html(c_key, c["bg"], c["text"])


def _float_badge(float_days: Optional[int], delay_status: Optional[str] = None) -> str:
    if float_days is None:
        return '<span style="color:#94a3b8;font-size:0.75rem;">—</span>'
    _, _, calc_st = calc_float(None, None)
    st_key = delay_status or ("CRITICAL_DELAY" if float_days < 0 else ("WARNING" if float_days < 14 else calc_st))
    c = FLOAT_BADGE.get(st_key, FLOAT_BADGE["ON_TRACK"])
    label = f"{float_days}d DELAY" if float_days < 0 else f"+{float_days}d float"
    return _badge_html(label, c["bg"], c["text"], c["border"])


def _progress_bar_html(pct: float, height: int = 8) -> str:
    pct_clamped = max(0.0, min(100.0, float(pct or 0.0)))
    color = "#10b981" if pct_clamped >= 80 else ("#2563eb" if pct_clamped >= 40 else "#f59e0b")
    return f"""
    <div style="display:flex;align-items:center;gap:8px;width:100%;">
        <div style="flex:1;background:#e2e8f0;border-radius:999px;height:{height}px;overflow:hidden;">
            <div style="width:{pct_clamped:.0f}%;background:{color};height:100%;border-radius:999px;"></div>
        </div>
        <span style="font-size:0.75rem;font-weight:700;color:#334155;min-width:34px;text-align:right;">{pct_clamped:.0f}%</span>
    </div>
    """


def _build_sample_schedule_excel(po_number: str) -> bytes:
    """Generates a ready-to-upload sample Excel workbook with both Activity & Cable/Tag sheets."""
    wb = openpyxl.Workbook()
    ws1 = wb.active
    ws1.title = "Level3_Schedule"
    ws1.append([
        "Activity Code", "Activity Name", "WBS Category",
        "Baseline Start", "Baseline Finish",
        "Current Start", "Current Finish",
        "Percent Complete", "Critical"
    ])
    base = date.today() - timedelta(days=30)
    sample_rows = [
        ("STD-01", "Kick-Off Meeting (KOM)", "ENGINEERING", -25, -24, -25, -24, 100, "Yes"),
        ("STD-02", "GAD & Datasheet Submission", "ENGINEERING", -20, -10, -18, -8, 100, "Yes"),
        ("STD-05", "Sub-PO Placement (Forgings & Body)", "PROCUREMENT", -10, 0, -5, 5, 90, "Yes"),
        ("STD-10", "Raw Material Receipt & Mill Cert Review (NOI)", "PROCUREMENT", 1, 8, 5, 12, 50, "Yes"),
        ("STD-11", "Machining & Body Assembly", "FABRICATION", 9, 25, 13, 30, 25, "Yes"),
        ("STD-16", "Hydrostatic & Seat Leakage Test - FAT (NOI)", "TESTING", 26, 32, 31, 37, 0, "Yes"),
        ("STD-18", "Final Inspection & Release Note - IRN (NOI)", "TESTING", 33, 38, 38, 42, 0, "Yes"),
        ("STD-22", "Ex-Works Dispatch & Shipping", "SHIPPING", 39, 48, 43, 52, 0, "Yes"),
    ]
    for code, name, cat, bs, bf, cs, cf, pct, crit in sample_rows:
        ws1.append([
            code, name, cat,
            (base + timedelta(days=bs)).isoformat(),
            (base + timedelta(days=bf)).isoformat(),
            (base + timedelta(days=cs)).isoformat(),
            (base + timedelta(days=cf)).isoformat(),
            pct, crit
        ])

    ws2 = wb.create_sheet("Cable_Tag_Status")
    ws2.append(["SAP Code", "Tag Number", "Description", "Completion Date", "Tentative Inspection Date"])
    ws2.append(["SAP-8801", f"{po_number}-TAG-01", "8-inch Ball Valve Assembly", (base + timedelta(days=20)).isoformat(), (base + timedelta(days=28)).isoformat()])
    ws2.append(["SAP-8802", f"{po_number}-TAG-02", "12-inch Check Valve Assembly", (base + timedelta(days=26)).isoformat(), (base + timedelta(days=34)).isoformat()])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Entry Point for the SmartExpedit Module inside InspectFlow
# ---------------------------------------------------------------------------

def render_expediting_module(user: Dict[str, Any]):
    """
    Main entry point rendered inside the right-hand workspace column of InspectFlow.
    Preserves the exact top navigation and left notification layout while providing
    seamless sub-navigation across all SmartExpedit screens and role previewing.
    """
    expediting_db.init_expediting_tables()

    if "epc_subpage" not in st.session_state:
        st.session_state.epc_subpage = "Executive Dashboard"
    if "epc_preview_role" not in st.session_state:
        st.session_state.epc_preview_role = ROLES["PEXM"]
    if "epc_selected_po_id" not in st.session_state:
        pos = expediting_db.get_purchase_orders()
        st.session_state.epc_selected_po_id = pos[0]["id"] if pos else None
    if "epc_project_filter" not in st.session_state:
        st.session_state.epc_project_filter = "ALL"

    active_role = st.session_state.epc_preview_role

    # Module Sub-Header Bar (matches InspectFlow white card aesthetic)
    st.markdown(
        """
        <div class="orig-white-card" style="padding:0.85rem 1.25rem; margin-bottom:1rem; background:linear-gradient(90deg, #ffffff 0%, #f8fafc 100%);">
            <div style="display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:0.75rem;">
                <div style="display:flex; align-items:center; gap:0.75rem;">
                    <div style="width:40px;height:40px;border-radius:10px;background:#eff6ff;color:#2563eb;display:flex;align-items:center;justify-content:center;font-size:1.25rem;font-weight:700;">
                        📦
                    </div>
                    <div>
                        <div style="display:flex;align-items:center;gap:8px;">
                            <span style="font-size:1.05rem;font-weight:800;color:#0f172a;">SmartExpedit</span>
                            <span style="font-size:0.7rem;font-weight:700;padding:2px 8px;border-radius:999px;background:#dbeafe;color:#1d4ed8;">EPC Material &amp; PO Expediting</span>
                        </div>
                        <p style="margin:0;font-size:0.76rem;color:#64748b;">Level-3 Schedules • Sub-Order Float • 10-Stage Bulk Routing • VDRL 14d SLA • RAIL &amp; NOI</p>
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Navigation Tabs filtered by Role (just like Layout.jsx in SmartExpedit guide §3)
    if active_role == ROLES["VENDOR"]:
        allowed_pages = ["Vendor Portal", "Module Guide"]
    else:
        allowed_pages = [
            "Executive Dashboard",
            "PO Master Register",
            "Expeditor Workbench",
            "RAIL Action Tracker",
            "Projects & Vendors",
            "Vendor Portal",
            "Module Guide",
        ]

    if st.session_state.epc_subpage not in allowed_pages:
        st.session_state.epc_subpage = allowed_pages[0]

    nav_cols = st.columns([1.3, 1.2, 1.35, 1.25, 1.25, 1.1, 1.0, 1.55])
    page_icons = {
        "Executive Dashboard": "📊 Exec Dashboard",
        "PO Master Register": "📑 PO Register",
        "Expeditor Workbench": "🛠️ Workbench",
        "RAIL Action Tracker": "⚡ RAIL Tracker",
        "Projects & Vendors": "🏗️ Projects & Vendors",
        "Vendor Portal": "🏭 Vendor Portal",
        "Module Guide": "📖 Guide",
    }

    for idx, page_name in enumerate(allowed_pages):
        with nav_cols[idx]:
            is_curr = st.session_state.epc_subpage == page_name
            if st.button(
                page_icons.get(page_name, page_name),
                key=f"epc_nav_{page_name}",
                type="primary" if is_curr else "secondary",
                use_container_width=True,
            ):
                st.session_state.epc_subpage = page_name
                st.rerun()

    # Role Switcher ("Preview as role" per §3 of guide)
    with nav_cols[-1]:
        role_options = list(EPC_ROLE_LABELS.keys())
        curr_idx = role_options.index(active_role) if active_role in role_options else 0
        chosen_role = st.selectbox(
            "Preview as role",
            options=role_options,
            index=curr_idx,
            format_func=lambda r: f"👤 {r}: {EPC_ROLE_LABELS[r].split(' ')[0]}",
            label_visibility="collapsed",
            key="epc_role_selector_widget",
        )
        if chosen_role != active_role:
            st.session_state.epc_preview_role = chosen_role
            st.rerun()

    st.markdown("<div style='height:0.35rem;'></div>", unsafe_allow_html=True)

    # Dispatch to active SmartExpedit subpage
    sub = st.session_state.epc_subpage
    if sub == "Executive Dashboard":
        render_exec_dashboard()
    elif sub == "PO Master Register":
        render_po_register()
    elif sub == "Expeditor Workbench":
        render_po_workbench()
    elif sub == "RAIL Action Tracker":
        render_rail_tracker()
    elif sub == "Projects & Vendors":
        render_projects_and_vendors()
    elif sub == "Vendor Portal":
        render_vendor_portal()
    elif sub == "Module Guide":
        render_expediting_docs()


# ---------------------------------------------------------------------------
# 6.1 Executive Dashboard
# ---------------------------------------------------------------------------

def render_exec_dashboard():
    metrics = expediting_db.get_executive_dashboard_metrics()
    pos = metrics["pos"]
    expeditors = metrics["expeditors"]
    all_activities = metrics["all_activities"]

    # 5 KPI Cards matching InspectFlow's exact 5-column StatsCard row
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.markdown(
            _stat_card_html(
                "Active POs",
                metrics["active_pos_count"],
                f"Out of {len(pos)} total POs",
                "📦",
                "blue",
            ),
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            _stat_card_html(
                "At Risk (Float < 0)",
                metrics["critical_suborders_count"],
                "Critical delay sub-orders",
                "⚠️",
                "red" if metrics["critical_suborders_count"] > 0 else "green",
            ),
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            _stat_card_html(
                "Unassigned POs",
                metrics["unassigned_pos_count"],
                "Awaiting expeditor owner",
                "👤",
                "amber" if metrics["unassigned_pos_count"] > 0 else "teal",
            ),
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            _stat_card_html(
                "Docs Past SLA",
                metrics["overdue_vdrl_count"],
                "Past 14-day EPC review SLA",
                "📄",
                "red" if metrics["overdue_vdrl_count"] > 0 else "green",
            ),
            unsafe_allow_html=True,
        )
    with c5:
        st.markdown(
            _stat_card_html(
                "Inspections (14d)",
                metrics["upcoming_inspections_14d"],
                "NOI milestones in next 14d",
                "🔍",
                "purple",
            ),
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:1rem;'></div>", unsafe_allow_html=True)

    # S-Curve Chart + Quick Portfolio Breakdown
    col_scurve, col_summary = st.columns([6.5, 3.5], gap="medium")

    with col_scurve:
        st.markdown(
            """
            <div class="orig-white-card" style="margin-bottom:0.5rem;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.5rem;">
                    <div>
                        <h3 style="margin:0;font-size:1rem;font-weight:700;color:#0f172a;">Portfolio S-Curve — Planned vs Actual Progress (%)</h3>
                        <p style="margin:0;font-size:0.76rem;color:#64748b;">12-month cumulative milestone baseline finish vs weighted actual completion across all POs</p>
                    </div>
                    <div style="display:flex;gap:12px;font-size:0.75rem;font-weight:600;">
                        <span style="color:#2563eb;">● Planned %</span>
                        <span style="color:#10b981;">● Actual %</span>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        scurve_data = build_scurve(all_activities)
        df_sc = pd.DataFrame(scurve_data)
        df_sc["order"] = range(len(df_sc))

        base_chart = alt.Chart(df_sc).encode(
            x=alt.X("month:N", sort=alt.EncodingSortField(field="order", order="ascending"), title="Month")
        )
        area_planned = base_chart.mark_area(
            opacity=0.22, color="#3b82f6", line={"color": "#2563eb", "strokeWidth": 2.5}
        ).encode(
            y=alt.Y("planned:Q", title="Cumulative %", scale=alt.Scale(domain=[0, 100])),
            tooltip=[
                alt.Tooltip("month:N", title="Month"),
                alt.Tooltip("planned:Q", title="Planned %"),
                alt.Tooltip("actual:Q", title="Actual %"),
            ],
        )
        line_actual = base_chart.mark_line(
            color="#10b981", strokeWidth=3, point=alt.OverlayMarkDef(color="#059669", size=55)
        ).encode(
            y=alt.Y("actual:Q"),
            tooltip=[
                alt.Tooltip("month:N", title="Month"),
                alt.Tooltip("planned:Q", title="Planned %"),
                alt.Tooltip("actual:Q", title="Actual %"),
            ],
        )
        st.altair_chart((area_planned + line_actual).properties(height=270), use_container_width=True)

    with col_summary:
        st.markdown(
            """
            <div class="orig-white-card" style="margin-bottom:0.75rem;">
                <h3 style="margin:0 0 0.5rem 0;font-size:1rem;font-weight:700;color:#0f172a;">Portfolio Risk Radar</h3>
                <p style="margin:0 0 0.75rem 0;font-size:0.76rem;color:#64748b;">Real-time expediting bottlenecks requiring immediate action</p>
            """,
            unsafe_allow_html=True,
        )
        at_risk_pos = [p for p in pos if p.get("overall_status") in ("AT_RISK", "DELAYED")]
        for p in at_risk_pos[:4]:
            st.markdown(
                f"""
                <div style="padding:0.6rem 0.75rem;border:1px solid #fecaca;background:#fef2f2;border-radius:0.65rem;margin-bottom:0.5rem;">
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <span style="font-weight:700;font-size:0.82rem;color:#991b1b;">PO {p['po_number']}</span>
                        {_po_status_badge(p.get('overall_status'))}
                    </div>
                    <div style="font-size:0.76rem;color:#334155;margin-top:2px;font-weight:600;">{p.get('description','')}</div>
                    <div style="font-size:0.72rem;color:#64748b;margin-top:2px;">Vendor: {p.get('vendor_name','')} • Progress: {float(p.get('progress_percent') or 0):.0f}%</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        st.markdown("</div>", unsafe_allow_html=True)

    # PO Allocation Grid
    st.markdown(
        """
        <div class="orig-white-card" style="margin-top:0.5rem;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.75rem;">
                <div>
                    <h3 style="margin:0;font-size:1.05rem;font-weight:700;color:#0f172a;">PO Allocation &amp; Expediting Status Grid</h3>
                    <p style="margin:0;font-size:0.76rem;color:#64748b;">Assign expeditors inline or open the 6-track Expeditor Workbench for any Purchase Order</p>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    exp_emails = [""] + [e["email"] for e in expeditors]
    exp_labels = {"": "— Unassigned —"}
    for e in expeditors:
        exp_labels[e["email"]] = f"{e['full_name']} ({e['email']})"

    # Header Row
    h_cols = st.columns([1.15, 2.2, 1.6, 0.9, 1.1, 1.0, 1.3, 1.6, 1.1])
    headers = ["PO Number", "Package Description", "Vendor", "Type", "Delivery", "Status", "Progress", "Assigned Expeditor", "Action"]
    for col, h_text in zip(h_cols, headers):
        col.markdown(f"<span style='font-size:0.72rem;font-weight:700;color:#64748b;text-transform:uppercase;'>{h_text}</span>", unsafe_allow_html=True)
    st.markdown("<hr style='margin:0.35rem 0;border-color:#e2e8f0;'>", unsafe_allow_html=True)

    for po in pos:
        r_cols = st.columns([1.15, 2.2, 1.6, 0.9, 1.1, 1.0, 1.3, 1.6, 1.1])
        with r_cols[0]:
            st.markdown(f"<span style='font-weight:700;color:#1e293b;font-size:0.83rem;'>{po['po_number']}</span><br><span style='font-size:0.7rem;color:#64748b;'>{po.get('project_name','')}</span>", unsafe_allow_html=True)
        with r_cols[1]:
            st.markdown(f"<span style='font-weight:600;color:#0f172a;font-size:0.82rem;'>{po.get('description','')}</span>", unsafe_allow_html=True)
        with r_cols[2]:
            st.markdown(f"<span style='font-size:0.8rem;color:#334155;'>{po.get('vendor_name','')}</span>", unsafe_allow_html=True)
        with r_cols[3]:
            t_bg = "#eff6ff" if po.get("po_type") == "PACKAGED" else "#f5f3ff"
            t_fg = "#1d4ed8" if po.get("po_type") == "PACKAGED" else "#6d28d9"
            st.markdown(_badge_html(po.get("po_type", "PACKAGED"), t_bg, t_fg), unsafe_allow_html=True)
        with r_cols[4]:
            st.markdown(
                f"<span style='font-size:0.78rem;color:#0f172a;font-weight:600;'>{format_date_gb(po.get('current_delivery_date'))}</span>"
                f"<br><span style='font-size:0.68rem;color:#64748b;'>Base: {format_date_gb(po.get('contract_delivery_date'))}</span>",
                unsafe_allow_html=True,
            )
        with r_cols[5]:
            st.markdown(_po_status_badge(po.get("overall_status", "ACTIVE")), unsafe_allow_html=True)
        with r_cols[6]:
            st.markdown(_progress_bar_html(po.get("progress_percent", 0)), unsafe_allow_html=True)
        with r_cols[7]:
            curr_exp = po.get("assigned_expeditor") or ""
            if curr_exp and curr_exp not in exp_emails:
                exp_emails.append(curr_exp)
                exp_labels[curr_exp] = curr_exp
            new_exp = st.selectbox(
                "Expeditor",
                options=exp_emails,
                index=exp_emails.index(curr_exp) if curr_exp in exp_emails else 0,
                format_func=lambda x: exp_labels.get(x, x),
                key=f"exec_exp_{po['id']}",
                label_visibility="collapsed",
            )
            if new_exp != curr_exp:
                expediting_db.update_purchase_order(po["id"], {"assigned_expeditor": new_exp})
                st.toast(f"Assigned {po['po_number']} to {new_exp or 'Unassigned'}", icon="✅")
                st.rerun()
        with r_cols[8]:
            if st.button("Workbench →", key=f"exec_wb_{po['id']}", use_container_width=True):
                st.session_state.epc_selected_po_id = po["id"]
                st.session_state.epc_subpage = "Expeditor Workbench"
                st.rerun()
        st.markdown("<hr style='margin:0.35rem 0;border-color:#f1f5f9;'>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 6.2 PO Master Register
# ---------------------------------------------------------------------------

@st.dialog("Create New Purchase Order", width="large")
def _new_po_dialog():
    projects = expediting_db.get_epc_projects()
    vendors = expediting_db.get_epc_vendors()
    expeditors = expediting_db.get_expeditors()

    with st.form("create_po_form"):
        c1, c2 = st.columns(2)
        with c1:
            po_number = st.text_input("PO Number *", placeholder="e.g. 1061009500")
            proj_opts = {p["id"]: f"{p['code']} — {p['name']}" for p in projects}
            proj_id = st.selectbox("Project *", options=list(proj_opts.keys()), format_func=lambda k: proj_opts[k])
            po_type = st.selectbox("PO Type *", options=["PACKAGED", "BULK"])
            contract_date = st.date_input("Contract Delivery Date", value=date.today() + timedelta(days=120))
        with c2:
            vend_opts = {v["id"]: f"{v['name']} ({v['country']})" for v in vendors}
            vendor_id = st.selectbox("Vendor / Supplier *", options=list(vend_opts.keys()), format_func=lambda k: vend_opts[k])
            exp_opts = [""] + [e["email"] for e in expeditors]
            assigned_exp = st.selectbox("Assigned Expeditor", options=exp_opts, format_func=lambda x: x or "— Unassigned —")
            ras_date = st.date_input("Required-at-Site (RAS) Date", value=date.today() + timedelta(days=150))
            incoterm = st.selectbox("Incoterm", options=["CIF", "FOB", "EXW", "DDP", "FCA"])

        description = st.text_input("Package / Material Description *", placeholder="e.g. API 610 Centrifugal Process Pumps")
        gen_baseline = st.checkbox("Automatically generate 23-activity Standard Level-3 Schedule Baseline", value=(po_type == "PACKAGED"))

        submitted = st.form_submit_button("Create Purchase Order", type="primary", use_container_width=True)
        if submitted:
            if not po_number.strip() or not description.strip():
                st.error("PO Number and Description are required.")
            else:
                sel_proj = next((p for p in projects if p["id"] == proj_id), {})
                sel_vend = next((v for v in vendors if v["id"] == vendor_id), {})
                new_po = expediting_db.create_purchase_order({
                    "po_number": po_number.strip(),
                    "project_id": proj_id,
                    "project_name": sel_proj.get("name", ""),
                    "vendor_id": vendor_id,
                    "vendor_name": sel_vend.get("name", ""),
                    "vendor_email": sel_vend.get("contact_email", ""),
                    "description": description.strip(),
                    "po_type": po_type,
                    "incoterm": incoterm,
                    "contract_delivery_date": contract_date.isoformat(),
                    "current_delivery_date": contract_date.isoformat(),
                    "required_at_site_date": ras_date.isoformat(),
                    "assigned_expeditor": assigned_exp,
                    "overall_status": "ACTIVE",
                })
                if gen_baseline:
                    expediting_db.generate_standard_baseline(new_po["id"], contract_date.isoformat())
                st.session_state.epc_selected_po_id = new_po["id"]
                st.toast(f"Created PO {new_po['po_number']}", icon="🎉")
                st.rerun()


def render_po_register():
    pos = expediting_db.get_purchase_orders()
    expeditors = expediting_db.get_expeditors()

    st.markdown(
        """
        <div class="orig-white-card" style="margin-bottom:1rem;">
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.75rem;">
                <div>
                    <h3 style="margin:0;font-size:1.1rem;font-weight:700;color:#0f172a;">PO Master Register</h3>
                    <p style="margin:0;font-size:0.78rem;color:#64748b;">Full directory of Packaged Equipment and Bulk Material Purchase Orders</p>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    f1, f2, f3, f4, f5 = st.columns([2.6, 1.4, 1.3, 1.5, 1.3])
    with f1:
        q = st.text_input("Search PO #, description, vendor, project...", placeholder="🔎 Filter by PO #, description, vendor...", label_visibility="collapsed")
    with f2:
        status_filter = st.selectbox("Status", ["ALL", "ACTIVE", "AT_RISK", "DELAYED", "COMPLETED", "ON_HOLD"], label_visibility="collapsed")
    with f3:
        type_filter = st.selectbox("Type", ["ALL", "PACKAGED", "BULK"], label_visibility="collapsed")
    with f4:
        proj_names = ["ALL"] + sorted(list({p.get("project_name", "") for p in pos if p.get("project_name")}))
        default_proj = st.session_state.get("epc_project_filter", "ALL")
        if default_proj not in proj_names:
            default_proj = "ALL"
        proj_filter = st.selectbox("Project", proj_names, index=proj_names.index(default_proj), label_visibility="collapsed")
        st.session_state.epc_project_filter = proj_filter
    with f5:
        if st.button("＋ New Purchase Order", type="primary", use_container_width=True):
            _new_po_dialog()

    filtered = []
    for p in pos:
        if status_filter != "ALL" and p.get("overall_status") != status_filter:
            continue
        if type_filter != "ALL" and p.get("po_type") != type_filter:
            continue
        if proj_filter != "ALL" and p.get("project_name") != proj_filter:
            continue
        if q:
            hay = f"{p.get('po_number','')} {p.get('description','')} {p.get('vendor_name','')} {p.get('project_name','')}".lower()
            if q.lower() not in hay:
                continue
        filtered.append(p)

    st.markdown(f"<p style='font-size:0.78rem;color:#64748b;margin:0.4rem 0;'>Showing <b>{len(filtered)}</b> of {len(pos)} Purchase Orders</p>", unsafe_allow_html=True)

    exp_emails = [""] + [e["email"] for e in expeditors]

    for po in filtered:
        with st.container():
            st.markdown(
                f"""
                <div class="orig-white-card" style="padding:1rem 1.25rem;margin-bottom:0.65rem;">
                    <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:0.75rem;">
                        <div style="flex:2;min-width:260px;">
                            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                                <span style="font-size:1rem;font-weight:800;color:#0f172a;">PO {po['po_number']}</span>
                                {_po_status_badge(po.get('overall_status'))}
                                {_badge_html(po.get('po_type','PACKAGED'), '#eff6ff', '#1d4ed8')}
                                <span style="font-size:0.75rem;color:#64748b;font-weight:600;">• {po.get('project_name','')}</span>
                            </div>
                            <div style="font-size:0.9rem;font-weight:600;color:#1e293b;margin-top:4px;">{po.get('description','')}</div>
                            <div style="font-size:0.78rem;color:#64748b;margin-top:2px;">
                                🏭 <b>{po.get('vendor_name','')}</b> ({po.get('incoterm','CIF')}) &nbsp;|&nbsp;
                                📅 Contract: <b>{format_date_gb(po.get('contract_delivery_date'))}</b> &nbsp;|&nbsp;
                                🚚 Forecast: <b>{format_date_gb(po.get('current_delivery_date'))}</b> &nbsp;|&nbsp;
                                🎯 RAS: <b>{format_date_gb(po.get('required_at_site_date'))}</b>
                            </div>
                        </div>
                        <div style="min-width:180px;">
                            <div style="font-size:0.72rem;color:#64748b;font-weight:600;margin-bottom:4px;">OVERALL PROGRESS</div>
                            {_progress_bar_html(po.get('progress_percent', 0), height=10)}
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            b_cols = st.columns([3.5, 2.0, 1.5])
            with b_cols[1]:
                curr_exp = po.get("assigned_expeditor") or ""
                if curr_exp and curr_exp not in exp_emails:
                    exp_emails.append(curr_exp)
                new_exp = st.selectbox(
                    "Assign Expeditor",
                    options=exp_emails,
                    index=exp_emails.index(curr_exp) if curr_exp in exp_emails else 0,
                    format_func=lambda x: f"👤 {x}" if x else "👤 Unassigned",
                    key=f"reg_exp_{po['id']}",
                    label_visibility="collapsed",
                )
                if new_exp != curr_exp:
                    expediting_db.update_purchase_order(po["id"], {"assigned_expeditor": new_exp})
                    st.rerun()
            with b_cols[2]:
                if st.button("Open Workbench →", key=f"reg_open_{po['id']}", type="primary", use_container_width=True):
                    st.session_state.epc_selected_po_id = po["id"]
                    st.session_state.epc_subpage = "Expeditor Workbench"
                    st.rerun()


# ---------------------------------------------------------------------------
# 6.4 Expeditor Workbench (The 6-Track Operational Hub)
# ---------------------------------------------------------------------------

def render_po_workbench():
    pos = expediting_db.get_purchase_orders()
    if not pos:
        st.info("No Purchase Orders found. Create one in the PO Master Register.")
        return

    po_map = {p["id"]: p for p in pos}
    sel_id = st.session_state.get("epc_selected_po_id")
    if not sel_id or sel_id not in po_map:
        sel_id = pos[0]["id"]
        st.session_state.epc_selected_po_id = sel_id

    # Top PO Selector Strip
    top_c1, top_c2 = st.columns([3.5, 1.5])
    with top_c1:
        chosen_id = st.selectbox(
            "Select Purchase Order for Workbench",
            options=[p["id"] for p in pos],
            index=[p["id"] for p in pos].index(sel_id),
            format_func=lambda pid: f"PO {po_map[pid]['po_number']} — {po_map[pid]['description']} ({po_map[pid]['vendor_name']}) [{po_map[pid]['po_type']}]",
            label_visibility="collapsed",
        )
        if chosen_id != sel_id:
            st.session_state.epc_selected_po_id = chosen_id
            st.rerun()

    detail = expediting_db.get_workbench_detail(st.session_state.epc_selected_po_id)
    po = detail["po"]
    activities = detail["activities"]
    sub_orders = detail["sub_orders"]
    line_items = detail["line_items"]
    bulk_steps = detail["bulk_steps"]
    vdrl_docs = detail["vdrl_docs"]
    rail_items = detail["rail_items"]
    inspections = detail["inspections"]

    with top_c2:
        new_st = st.selectbox(
            "Update PO Overall Status",
            options=["ACTIVE", "AT_RISK", "DELAYED", "COMPLETED", "ON_HOLD"],
            index=["ACTIVE", "AT_RISK", "DELAYED", "COMPLETED", "ON_HOLD"].index(po.get("overall_status", "ACTIVE")),
            format_func=lambda s: f"Status: {s}",
            label_visibility="collapsed",
        )
        if new_st != po.get("overall_status"):
            expediting_db.update_purchase_order(po["id"], {"overall_status": new_st})
            st.rerun()

    # Header Strip
    st.markdown(
        f"""
        <div class="orig-white-card" style="padding:1.1rem 1.35rem;margin-bottom:0.85rem;">
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:1rem;">
                <div>
                    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                        <span style="font-size:1.2rem;font-weight:800;color:#0f172a;">PO {po['po_number']}</span>
                        {_po_status_badge(po.get('overall_status'))}
                        {_badge_html(po.get('po_type','PACKAGED'), '#eff6ff', '#1d4ed8')}
                        {_badge_html(po.get('project_name','Project'), '#f1f5f9', '#334155')}
                    </div>
                    <div style="font-size:0.95rem;font-weight:700;color:#1e293b;margin-top:4px;">{po.get('description','')}</div>
                    <div style="font-size:0.78rem;color:#64748b;margin-top:4px;">
                        🏭 Vendor: <b>{po.get('vendor_name','')}</b> ({po.get('vendor_email','')}) &nbsp;•&nbsp;
                        📅 Contract Delivery: <b>{format_date_gb(po.get('contract_delivery_date'))}</b> &nbsp;•&nbsp;
                        🚚 Forecast Delivery: <b>{format_date_gb(po.get('current_delivery_date'))}</b> &nbsp;•&nbsp;
                        🎯 Required at Site: <b>{format_date_gb(po.get('required_at_site_date'))}</b>
                    </div>
                </div>
                <div style="min-width:220px;">
                    <div style="font-size:0.72rem;font-weight:700;color:#64748b;margin-bottom:4px;">PO OVERALL COMPLETION</div>
                    {_progress_bar_html(po.get('progress_percent', 0), height=11)}
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 5 PO KPI Cards (§6.4 of guide)
    done_acts = sum(1 for a in activities if (a.get("percent_complete") or 0) == 100)
    crit_subs = sum(1 for s in sub_orders if s.get("delay_status") == "CRITICAL_DELAY")
    open_rails = sum(1 for r in rail_items if r.get("status") != "CLOSED")
    today_iso = date.today().isoformat()
    overdue_docs = sum(
        1 for d in vdrl_docs
        if not d.get("actual_return_date") and d.get("epc_review_due_date") and d["epc_review_due_date"] < today_iso
    )
    insp_acts = [a for a in activities if a.get("activity_code") in INSPECTION_ACTIVITY_CODES]
    insp_done = sum(1 for a in insp_acts if (a.get("percent_complete") or 0) == 100)

    k1, k2, k3, k4, k5 = st.columns(5)
    with k1:
        st.markdown(_stat_card_html("Schedule Milestones", f"{done_acts}/{len(activities)}", "Completed activities", "📅", "blue"), unsafe_allow_html=True)
    with k2:
        st.markdown(_stat_card_html("Critical Sub-Orders", crit_subs, f"Out of {len(sub_orders)} sub-orders", "⛓️", "red" if crit_subs > 0 else "green"), unsafe_allow_html=True)
    with k3:
        st.markdown(_stat_card_html("Open RAIL Items", open_rails, "Active blockers & actions", "⚡", "amber" if open_rails > 0 else "teal"), unsafe_allow_html=True)
    with k4:
        st.markdown(_stat_card_html("VDRL Overdue", overdue_docs, "Past 14-day review SLA", "📑", "red" if overdue_docs > 0 else "green"), unsafe_allow_html=True)
    with k5:
        st.markdown(_stat_card_html("Inspection Gates", f"{insp_done}/{len(insp_acts)}", f"{len(inspections)} NOI notifications", "🔍", "purple"), unsafe_allow_html=True)

    # Early-Warning Banner (§6.4 of guide)
    if crit_subs > 0 or overdue_docs > 0:
        warnings_list = []
        if crit_subs > 0:
            warnings_list.append(f"<b>{crit_subs} sub-order(s)</b> have negative float against the Required-at-Workshop (RAW) date")
        if overdue_docs > 0:
            warnings_list.append(f"<b>{overdue_docs} VDRL engineering document(s)</b> have exceeded the 14-day EPC review SLA")
        st.markdown(
            f"""
            <div style="margin:0.85rem 0;padding:0.75rem 1.1rem;border-radius:0.75rem;background:#fef2f2;border:1px solid #fecaca;color:#991b1b;font-size:0.82rem;display:flex;align-items:center;gap:10px;">
                <span style="font-size:1.2rem;">🚨</span>
                <div><b>Early-Warning Bottleneck Alert:</b> {"; and ".join(warnings_list)}.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown("<div style='height:0.65rem;'></div>", unsafe_allow_html=True)

    # Adaptive Workbench Tabs (shows all tracks so expeditor can inspect anything, with primary track highlighted)
    is_bulk = po.get("po_type") == "BULK"
    if is_bulk:
        tab_labels = [
            "🏭 Bulk Routing Matrix (10-Stage)",
            "📅 Level-3 Schedule",
            "📑 VDRL Documents (14d SLA)",
            "⚡ RAIL & Actions",
            "🔍 Inspections (NOI)",
            "⛓️ Sub-Orders & Float",
        ]
    else:
        tab_labels = [
            "📅 Level-3 Schedule",
            "⛓️ Sub-Orders & Float",
            "📑 VDRL Documents (14d SLA)",
            "⚡ RAIL & Actions",
            "🔍 Inspections (NOI)",
            "🏭 Bulk Routing Matrix",
        ]

    tabs = st.tabs(tab_labels)
    if is_bulk:
        with tabs[0]:
            _render_wb_bulk_tab(po, line_items, bulk_steps)
        with tabs[1]:
            _render_wb_schedule_tab(po, activities)
        with tabs[2]:
            _render_wb_vdrl_tab(po, vdrl_docs)
        with tabs[3]:
            _render_wb_rail_tab(po, rail_items)
        with tabs[4]:
            _render_wb_inspections_tab(po, inspections, activities)
        with tabs[5]:
            _render_wb_suborders_tab(po, sub_orders)
    else:
        with tabs[0]:
            _render_wb_schedule_tab(po, activities)
        with tabs[1]:
            _render_wb_suborders_tab(po, sub_orders)
        with tabs[2]:
            _render_wb_vdrl_tab(po, vdrl_docs)
        with tabs[3]:
            _render_wb_rail_tab(po, rail_items)
        with tabs[4]:
            _render_wb_inspections_tab(po, inspections, activities)
        with tabs[5]:
            _render_wb_bulk_tab(po, line_items, bulk_steps)


# ---------------------------------------------------------------------------
# 7.1 & 7.2 Schedule Tab (Gantt Chart, 2-Tier Table, Timeline, Baseline Gen, Excel/PDF Parser)
# ---------------------------------------------------------------------------

def _render_wb_schedule_tab(po: Dict[str, Any], activities: List[Dict[str, Any]], read_only: bool = False):
    tb1, tb2, tb3, tb4 = st.columns([2.2, 1.5, 1.4, 1.4])
    with tb1:
        view_mode = st.radio(
            "Schedule View",
            options=["Gantt Chart", "Table View (2-Tier)", "Timeline View"],
            horizontal=True,
            key=f"sched_view_{po['id']}_{read_only}",
            label_visibility="collapsed",
        )
    if not read_only:
        with tb2:
            wbs_filter = st.selectbox(
                "Filter Phase",
                options=["ALL"] + WBS_CATEGORIES,
                key=f"sched_wbs_{po['id']}",
                label_visibility="collapsed",
            )
        with tb3:
            if st.button("⚙️ Generate 23-Milestone Baseline", key=f"gen_base_{po['id']}", use_container_width=True):
                expediting_db.generate_standard_baseline(po["id"], po.get("contract_delivery_date"))
                st.toast("Generated 23 standard Level-3 milestones!", icon="✅")
                st.rerun()
        with tb4:
            sample_bytes = _build_sample_schedule_excel(po["po_number"])
            st.download_button(
                "📥 Sample Schedule .xlsx",
                data=sample_bytes,
                file_name=f"Sample_Schedule_{po['po_number']}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"dl_sample_{po['id']}",
                use_container_width=True,
            )
    else:
        wbs_filter = "ALL"

    # Upload Schedule Expander (Deterministic Excel first, AI PDF second)
    if not read_only:
        with st.expander("📤 Upload Revised Vendor Schedule (.xlsx / .pdf) — Idempotent Upsert on (PO, Activity Code)", expanded=False):
            up_file = st.file_uploader(
                "Upload Vendor Schedule Workbook (.xlsx) or PDF Schedule (.pdf)",
                type=["xlsx", "xlsm", "pdf"],
                key=f"sched_up_{po['id']}",
            )
            if up_file is not None:
                if st.button("🚀 Parse & Upsert Schedule Milestones", key=f"run_parse_{po['id']}", type="primary"):
                    with st.spinner("Parsing schedule (deterministic Excel engine / Gemini AI fallback)..."):
                        res = parse_vendor_schedule_file(up_file.getvalue(), up_file.name, po["id"], dry_run=False)
                    st.success(f"Upserted **{res['count']}** schedule milestones for PO {po['po_number']}.")
                    if res.get("sheetSummary"):
                        st.json(res["sheetSummary"])
                    for w in res.get("warnings", []):
                        st.warning(w)
                    st.rerun()

    filtered_acts = [
        a for a in activities
        if wbs_filter == "ALL" or a.get("wbs_category") == wbs_filter
    ]

    if not filtered_acts:
        st.info("No schedule activities found. Click **Generate 23-Milestone Baseline** or upload an Excel/PDF schedule.")
        return

    # 1. GANTT CHART VIEW
    if view_mode == "Gantt Chart":
        gantt_rows = []
        for a in filtered_acts:
            bs = a.get("baseline_start") or date.today().isoformat()
            bf = a.get("baseline_finish") or bs
            cs = a.get("current_start") or bs
            cf = a.get("current_finish") or bf
            # Ensure finish >= start + 1 day for visual bar thickness
            if bf <= bs:
                bf = (date.fromisoformat(bs[:10]) + timedelta(days=2)).isoformat()
            if cf <= cs:
                cf = (date.fromisoformat(cs[:10]) + timedelta(days=2)).isoformat()

            pct = int(a.get("percent_complete") or 0)
            delayed = cf > bf and pct < 100
            status_label = "Completed (100%)" if pct == 100 else ("Delayed vs Baseline" if delayed else "On Track")

            label = f"{a.get('activity_code','')} — {a.get('activity_name','')[:36]}"
            gantt_rows.append({
                "Task": label,
                "seq": a.get("sequence", 1),
                "Track": "1. Baseline",
                "Start": bs[:10],
                "Finish": bf[:10],
                "Status": "Baseline Plan",
                "Percent": pct,
                "Category": a.get("wbs_category", "ENGINEERING"),
            })
            gantt_rows.append({
                "Task": label,
                "seq": a.get("sequence", 1),
                "Track": "2. Current Forecast",
                "Start": cs[:10],
                "Finish": cf[:10],
                "Status": status_label,
                "Percent": pct,
                "Category": a.get("wbs_category", "ENGINEERING"),
            })

        df_g = pd.DataFrame(gantt_rows)
        chart_height = max(360, len(filtered_acts) * 28)

        bars = alt.Chart(df_g).mark_bar(cornerRadius=3, height=9).encode(
            x=alt.X("Start:T", title="Timeline"),
            x2="Finish:T",
            y=alt.Y("Task:N", sort=alt.EncodingSortField(field="seq", order="ascending"), title=None, axis=alt.Axis(labelLimit=260)),
            yOffset=alt.YOffset("Track:N"),
            color=alt.Color(
                "Status:N",
                scale=alt.Scale(
                    domain=["Baseline Plan", "Completed (100%)", "On Track", "Delayed vs Baseline"],
                    range=["#cbd5e1", "#10b981", "#2563eb", "#ef4444"],
                ),
                legend=alt.Legend(orient="top", title="Schedule Track & Status"),
            ),
            tooltip=[
                alt.Tooltip("Task:N", title="Milestone"),
                alt.Tooltip("Track:N", title="Bar"),
                alt.Tooltip("Category:N", title="WBS Phase"),
                alt.Tooltip("Start:T", title="Start"),
                alt.Tooltip("Finish:T", title="Finish"),
                alt.Tooltip("Percent:Q", title="% Complete"),
            ],
        )

        today_df = pd.DataFrame([{"today": date.today().isoformat()}])
        today_rule = alt.Chart(today_df).mark_rule(color="#dc2626", strokeDash=[5, 4], strokeWidth=2).encode(
            x="today:T"
        )

        st.altair_chart((bars + today_rule).properties(height=chart_height), use_container_width=True)

    # 2. TWO-TIER TABLE VIEW (Expandable WBS Phase Groups + Inline Edit)
    elif view_mode == "Table View (2-Tier)":
        for cat in WBS_CATEGORIES:
            cat_acts = [a for a in filtered_acts if a.get("wbs_category") == cat]
            if not cat_acts:
                continue
            avg_cat_pct = sum(float(a.get("percent_complete") or 0) for a in cat_acts) / len(cat_acts)
            with st.expander(f"📂 {cat} Phase ({len(cat_acts)} activities • {avg_cat_pct:.0f}% complete)", expanded=True):
                for a in cat_acts:
                    bf = a.get("baseline_finish") or ""
                    cf = a.get("current_finish") or ""
                    slip_days = 0
                    if bf and cf:
                        try:
                            slip_days = (date.fromisoformat(cf[:10]) - date.fromisoformat(bf[:10])).days
                        except Exception:
                            slip_days = 0
                    slip_badge = (
                        _badge_html(f"+{slip_days}d slip", "#fee2e2", "#991b1b")
                        if slip_days > 0 and (a.get("percent_complete") or 0) < 100
                        else (_badge_html("On Baseline", "#dcfce7", "#166534"))
                    )
                    crit_badge = _badge_html("CRITICAL", "#fef2f2", "#dc2626", "#fecaca") if a.get("is_critical_path") else ""
                    noi_badge = _badge_html("NOI GATE", "#f3e8ff", "#6b21a8") if a.get("activity_code") in INSPECTION_ACTIVITY_CODES else ""

                    c1, c2, c3, c4, c5 = st.columns([2.6, 1.5, 1.5, 1.4, 1.1])
                    with c1:
                        st.markdown(
                            f"<span style='font-weight:700;font-size:0.82rem;color:#0f172a;'>{a.get('activity_code')} — {a.get('activity_name')}</span> "
                            f"{crit_badge} {noi_badge}",
                            unsafe_allow_html=True,
                        )
                    with c2:
                        st.markdown(
                            f"<span style='font-size:0.74rem;color:#64748b;'>Baseline: <b>{format_date_gb(a.get('baseline_start'))} → {format_date_gb(a.get('baseline_finish'))}</b></span>",
                            unsafe_allow_html=True,
                        )
                    with c3:
                        st.markdown(
                            f"<span style='font-size:0.74rem;color:#1e293b;'>Forecast: <b>{format_date_gb(a.get('current_start'))} → {format_date_gb(a.get('current_finish'))}</b></span> {slip_badge}",
                            unsafe_allow_html=True,
                        )
                    with c4:
                        st.markdown(_progress_bar_html(a.get("percent_complete", 0)), unsafe_allow_html=True)
                    with c5:
                        if not read_only:
                            with st.popover("✏️ Edit"):
                                new_cf = st.date_input(
                                    "Forecast Finish",
                                    value=date.fromisoformat((a.get("current_finish") or date.today().isoformat())[:10]),
                                    key=f"ed_cf_{a['id']}",
                                )
                                new_pct = st.slider(
                                    "% Complete",
                                    0, 100, int(a.get("percent_complete") or 0), step=5,
                                    key=f"ed_pct_{a['id']}",
                                )
                                new_crit = st.checkbox(
                                    "Critical Path",
                                    value=bool(a.get("is_critical_path")),
                                    key=f"ed_crit_{a['id']}",
                                )
                                if st.button("Save Milestone", key=f"sv_act_{a['id']}", type="primary", use_container_width=True):
                                    expediting_db.update_schedule_activity(a["id"], {
                                        "current_finish": new_cf.isoformat(),
                                        "percent_complete": new_pct,
                                        "is_critical_path": new_crit,
                                        "actual_finish": date.today().isoformat() if new_pct == 100 else None,
                                    })
                                    st.rerun()

    # 3. VERTICAL TIMELINE VIEW
    else:
        for a in filtered_acts:
            pct = int(a.get("percent_complete") or 0)
            dot_color = "#10b981" if pct == 100 else ("#2563eb" if pct > 0 else "#94a3b8")
            st.markdown(
                f"""
                <div style="display:flex;gap:14px;align-items:flex-start;margin-bottom:0.65rem;">
                    <div style="display:flex;flex-direction:column;align-items:center;margin-top:4px;">
                        <div style="width:14px;height:14px;border-radius:999px;background:{dot_color};border:3px solid #e2e8f0;"></div>
                        <div style="width:2px;height:38px;background:#e2e8f0;"></div>
                    </div>
                    <div class="orig-white-card" style="flex:1;padding:0.7rem 1rem;">
                        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;">
                            <div>
                                <span style="font-weight:800;font-size:0.84rem;color:#0f172a;">{a.get('activity_code')} — {a.get('activity_name')}</span>
                                {_wbs_badge(a.get('wbs_category'))}
                            </div>
                            <span style="font-size:0.78rem;font-weight:700;color:#334155;">Forecast: {format_date_gb(a.get('current_finish'))} ({pct}%)</span>
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


# ---------------------------------------------------------------------------
# 7.3 Sub-Orders & Float Tab (Float Register, Timeline Chart, Unpriced PO Upload)
# ---------------------------------------------------------------------------

def _render_wb_suborders_tab(po: Dict[str, Any], sub_orders: List[Dict[str, Any]]):
    c_top1, c_top2 = st.columns([3, 2])
    with c_top1:
        st.markdown(
            """
            <div style="margin-bottom:0.5rem;">
                <h4 style="margin:0;font-size:0.98rem;font-weight:700;color:#0f172a;">Tier-2 Sub-Vendor Float &amp; Bottleneck Tracker</h4>
                <p style="margin:0;font-size:0.76rem;color:#64748b;">Float = Required-at-Workshop (RAW) Date − Sub-Vendor ETA Date. Negative float triggers Critical Delay.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with st.expander("➕ Add Sub-Order / Upload Sub-Order Report (.xlsx / .pdf)", expanded=False):
        tab_manual, tab_upload = st.tabs(["✍️ Manual Entry", "📤 Upload Sub-Order Report (Excel/PDF)"])
        with tab_manual:
            with st.form(f"add_suborder_{po['id']}"):
                sc1, sc2, sc3 = st.columns(3)
                with sc1:
                    sub_po_no = st.text_input("Sub-PO Number *", placeholder="e.g. SUB-FZ-003")
                    sub_vendor = st.text_input("Sub-Vendor Name *", placeholder="e.g. Forgings Italia S.p.A.")
                with sc2:
                    mat_desc = st.text_input("Material Description *", placeholder="e.g. Forged Body Rings ASTM A182 F316")
                    country = st.text_input("Country of Origin", value="Italy")
                with sc3:
                    raw_d = st.date_input("Required at Workshop (RAW) Date *", value=date.today() + timedelta(days=30))
                    eta_d = st.date_input("Sub-Vendor Current ETA Date *", value=date.today() + timedelta(days=25))
                if st.form_submit_button("Save Sub-Order & Calculate Float", type="primary"):
                    if sub_po_no and sub_vendor and mat_desc:
                        expediting_db.save_suborder({
                            "po_id": po["id"],
                            "po_number": po["po_number"],
                            "main_vendor": po.get("vendor_name", ""),
                            "sub_po_number": sub_po_no,
                            "sub_vendor_name": sub_vendor,
                            "material_description": mat_desc,
                            "country_of_origin": country,
                            "required_at_workshop_date": raw_d.isoformat(),
                            "sub_vendor_eta_date": eta_d.isoformat(),
                        })
                        st.toast("Sub-order saved and float calculated!", icon="✅")
                        st.rerun()
        with tab_upload:
            sub_file = st.file_uploader("Upload Sub-Order Status Report (.xlsx or .pdf)", type=["xlsx", "pdf"], key=f"sub_rep_{po['id']}")
            if sub_file and st.button("Parse Sub-Order Report", key=f"btn_sub_rep_{po['id']}", type="primary"):
                res = parse_suborder_report_file(sub_file.getvalue(), sub_file.name, po["id"], po["po_number"], po.get("vendor_name", ""))
                st.success(f"Extracted and saved {res['count']} sub-orders!")
                st.rerun()

    if not sub_orders:
        st.info("No sub-orders registered for this PO yet.")
        return

    # Sub-Order Delivery Timeline Chart (§7.3 of guide)
    tl_rows = []
    today_str = date.today().isoformat()
    for s in sub_orders:
        eta = s.get("sub_vendor_eta_date") or today_str
        raw = s.get("required_at_workshop_date") or eta
        start_d = today_str if today_str < eta else (date.fromisoformat(eta[:10]) - timedelta(days=15)).isoformat()
        tl_rows.append({
            "SubOrder": f"{s.get('sub_po_number')} ({s.get('sub_vendor_name')[:18]})",
            "Material": s.get("material_description", ""),
            "Start": start_d,
            "ETA": eta[:10],
            "RAW": raw[:10],
            "FloatDays": s.get("float_days", 0),
            "Status": s.get("delay_status", "ON_TRACK"),
        })
    df_tl = pd.DataFrame(tl_rows)
    bar_eta = alt.Chart(df_tl).mark_bar(cornerRadius=4, height=16).encode(
        x=alt.X("Start:T", title="Sub-Order Delivery Horizon (Bars = Sub-Vendor ETA, ◆ Diamond = Required at Workshop Date)"),
        x2="ETA:T",
        y=alt.Y("SubOrder:N", title=None, axis=alt.Axis(labelLimit=220)),
        color=alt.Color(
            "Status:N",
            scale=alt.Scale(
                domain=["ON_TRACK", "WARNING", "CRITICAL_DELAY"],
                range=["#10b981", "#f59e0b", "#ef4444"],
            ),
            legend=alt.Legend(orient="top", title="Float Risk Classification"),
        ),
        tooltip=["SubOrder:N", "Material:N", "ETA:T", "RAW:T", "FloatDays:Q", "Status:N"],
    )
    raw_points = alt.Chart(df_tl).mark_point(shape="diamond", size=130, filled=True, color="#0f172a").encode(
        x="RAW:T",
        y="SubOrder:N",
        tooltip=[alt.Tooltip("RAW:T", title="Required at Workshop (RAW) Date")],
    )
    st.altair_chart((bar_eta + raw_points).properties(height=max(200, len(sub_orders) * 48)), use_container_width=True)

    # Sub-Order Table Register
    for s in sub_orders:
        c1, c2, c3, c4, c5 = st.columns([2.2, 2.3, 1.8, 1.3, 1.3])
        with c1:
            st.markdown(
                f"<span style='font-weight:700;font-size:0.84rem;color:#0f172a;'>{s.get('sub_po_number')}</span> "
                f"<span style='font-size:0.75rem;color:#64748b;'>({s.get('country_of_origin','')})</span><br>"
                f"<span style='font-size:0.8rem;color:#1e293b;font-weight:600;'>{s.get('sub_vendor_name')}</span>",
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(f"<span style='font-size:0.8rem;color:#334155;'>{s.get('material_description')}</span>", unsafe_allow_html=True)
        with c3:
            st.markdown(
                f"<span style='font-size:0.76rem;color:#64748b;'>RAW Need: <b>{format_date_gb(s.get('required_at_workshop_date'))}</b></span><br>"
                f"<span style='font-size:0.76rem;color:#0f172a;'>Sub ETA: <b>{format_date_gb(s.get('sub_vendor_eta_date'))}</b></span>",
                unsafe_allow_html=True,
            )
        with c4:
            st.markdown(_float_badge(s.get("float_days"), s.get("delay_status")), unsafe_allow_html=True)
        with c5:
            with st.popover("✏️ Update Dates"):
                u_raw = st.date_input("RAW Date", value=date.fromisoformat(s["required_at_workshop_date"][:10]), key=f"s_raw_{s['id']}")
                u_eta = st.date_input("Sub-Vendor ETA", value=date.fromisoformat(s["sub_vendor_eta_date"][:10]), key=f"s_eta_{s['id']}")
                if st.button("Recalculate Float", key=f"s_sv_{s['id']}", type="primary", use_container_width=True):
                    s_copy = dict(s)
                    s_copy["required_at_workshop_date"] = u_raw.isoformat()
                    s_copy["sub_vendor_eta_date"] = u_eta.isoformat()
                    expediting_db.save_suborder(s_copy)
                    st.rerun()
        st.markdown("<hr style='margin:0.35rem 0;border-color:#f1f5f9;'>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 7.4 Bulk Manufacturing Routing Matrix (10-Stage Interactive Grid)
# ---------------------------------------------------------------------------

def _render_wb_bulk_tab(po: Dict[str, Any], line_items: List[Dict[str, Any]], bulk_steps: List[Dict[str, Any]]):
    st.markdown(
        """
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.65rem;">
            <div>
                <h4 style="margin:0;font-size:0.98rem;font-weight:700;color:#0f172a;">10-Stage Bulk Manufacturing Routing Matrix</h4>
                <p style="margin:0;font-size:0.76rem;color:#64748b;">Click any stage pill to toggle completion (100% ↔ 0%). Line item progress and overall BULK PO progress recalculate automatically.</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("➕ Add Bulk PO Line Item (Auto-seeds 10 Manufacturing Stages)", expanded=False):
        with st.form(f"add_bulk_li_{po['id']}"):
            bc1, bc2, bc3 = st.columns(3)
            with bc1:
                item_no = st.text_input("Item Number *", placeholder="e.g. 0040")
                tag_no = st.text_input("Tag / Spool Number *", placeholder="e.g. SP-2201-04")
            with bc2:
                heat_no = st.text_input("Heat / Lot Number", placeholder="e.g. HT-99415-D")
                qty = st.number_input("Quantity", min_value=1.0, value=10.0)
            with bc3:
                uom = st.selectbox("UOM", ["EA", "M", "TON", "LOT"])
                desc = st.text_input("Line Item Description *", placeholder="e.g. 16-inch Sch 80 Super Duplex Spool")
            if st.form_submit_button("Create Line Item & 10 Stages", type="primary"):
                if item_no and tag_no and desc:
                    expediting_db.create_bulk_line_item({
                        "po_id": po["id"],
                        "po_number": po["po_number"],
                        "item_number": item_no,
                        "tag_number": tag_no,
                        "heat_lot_number": heat_no,
                        "description": desc,
                        "quantity": qty,
                        "uom": uom,
                    })
                    st.rerun()

    if not line_items:
        st.info("No bulk line items registered for this PO. Add a line item above to initialize the 10-stage routing matrix.")
        return

    steps_by_li: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for stp in bulk_steps:
        steps_by_li.setdefault(stp["line_item_id"], {})[stp["stage_name"]] = stp

    for li in line_items:
        li_steps = steps_by_li.get(li["id"], {})
        done_count = sum(1 for stp in li_steps.values() if stp.get("status") == "COMPLETED")
        st.markdown(
            f"""
            <div class="orig-white-card" style="padding:0.9rem 1.15rem;margin-bottom:0.5rem;">
                <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.5rem;">
                    <div>
                        <span style="font-weight:800;font-size:0.88rem;color:#0f172a;">Item {li.get('item_number')} • Tag: {li.get('tag_number')}</span>
                        {_badge_html(f"Heat/Lot: {li.get('heat_lot_number','N/A')}", '#f1f5f9', '#334155')}
                        <span style="font-size:0.8rem;color:#334155;font-weight:600;margin-left:6px;">{li.get('description')} ({li.get('quantity')} {li.get('uom')})</span>
                    </div>
                    <div style="min-width:190px;">
                        {_progress_bar_html((done_count / 10.0) * 100.0)}
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        stage_cols = st.columns(10)
        for idx, stg in enumerate(BULK_STAGES):
            stp_rec = li_steps.get(stg["name"])
            is_done = stp_rec and stp_rec.get("status") == "COMPLETED"
            btn_label = f"{'✅' if is_done else '⬜'} {idx + 1}. {stg['label']}"
            with stage_cols[idx]:
                if st.button(
                    btn_label,
                    key=f"bulk_btn_{li['id']}_{stg['name']}",
                    type="primary" if is_done else "secondary",
                    use_container_width=True,
                ):
                    expediting_db.toggle_bulk_stage(
                        po_id=po["id"],
                        po_number=po["po_number"],
                        line_item_id=li["id"],
                        tag_number=li.get("tag_number", ""),
                        stage_name=stg["name"],
                        stage_sequence=stg["sequence"],
                    )
                    st.rerun()


# ---------------------------------------------------------------------------
# 7.5 VDRL Document Register (14-Day Review SLA & Approval Codes)
# ---------------------------------------------------------------------------

def _render_wb_vdrl_tab(po: Dict[str, Any], vdrl_docs: List[Dict[str, Any]], read_only: bool = False):
    st.markdown(
        """
        <div style="margin-bottom:0.65rem;">
            <h4 style="margin:0;font-size:0.98rem;font-weight:700;color:#0f172a;">Vendor Document Requirement List (VDRL) &amp; 14-Day EPC Review SLA</h4>
            <p style="margin:0;font-size:0.76rem;color:#64748b;">EPC Review Due Date = Actual Submission Date + 14 calendar days. Overdue unreturned documents highlight in red.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not read_only:
        with st.expander("➕ Add / Update VDRL Engineering Document", expanded=False):
            with st.form(f"vdrl_form_{po['id']}"):
                vc1, vc2, vc3 = st.columns(3)
                with vc1:
                    doc_code = st.text_input("Document Number *", placeholder="e.g. VDRL-005-WPS")
                    doc_title = st.text_input("Document Title *", placeholder="e.g. Welding Procedure Specification (WPS/PQR)")
                    discipline = st.selectbox("Discipline", ["MECHANICAL", "PIPING", "QA/QC", "PROCESS", "ELECTRICAL", "INSTRUMENTATION"])
                with vc2:
                    rev = st.text_input("Revision", value="Rev 0")
                    plan_sub = st.date_input("Planned Submission Date", value=date.today() - timedelta(days=10))
                    act_sub_enabled = st.checkbox("Submitted by Vendor?", value=True)
                    act_sub = st.date_input("Actual Submission Date", value=date.today() - timedelta(days=7))
                with vc3:
                    ret_enabled = st.checkbox("Returned by EPC Reviewer?", value=False)
                    act_ret = st.date_input("Actual Return Date", value=date.today())
                    app_code = st.selectbox("Approval Code", options=list(APPROVAL_CODE_LABELS.keys()), format_func=lambda k: APPROVAL_CODE_LABELS[k])
                if st.form_submit_button("Save VDRL Document", type="primary"):
                    if doc_code and doc_title:
                        expediting_db.save_vdrl_document({
                            "po_id": po["id"],
                            "po_number": po["po_number"],
                            "document_code": doc_code,
                            "document_title": doc_title,
                            "discipline": discipline,
                            "revision": rev,
                            "planned_submission_date": plan_sub.isoformat(),
                            "actual_submission_date": act_sub.isoformat() if act_sub_enabled else None,
                            "actual_return_date": act_ret.isoformat() if ret_enabled else None,
                            "approval_code": app_code,
                        })
                        st.rerun()

    if not vdrl_docs:
        st.info("No VDRL documents registered for this PO.")
        return

    today_iso = date.today().isoformat()
    for d in vdrl_docs:
        due = d.get("epc_review_due_date")
        ret = d.get("actual_return_date")
        is_overdue = bool(due and not ret and due < today_iso)
        app_key = d.get("approval_code") or "PENDING"
        app_c = APPROVAL_CODE_COLORS.get(app_key, APPROVAL_CODE_COLORS["PENDING"])

        delay_d = int(d.get("review_delay_days") or 0)
        delay_html = (
            f"<span style='color:#dc2626;font-weight:700;'>+{delay_d}d late</span>"
            if delay_d > 0
            else "<span style='color:#16a34a;font-weight:600;'>On time</span>"
        )

        row_border = "#fecaca" if is_overdue else "#e2e8f0"
        row_bg = "#fff5f5" if is_overdue else "#ffffff"

        st.markdown(
            f"""
            <div style="background:{row_bg};border:1px solid {row_border};border-radius:0.75rem;padding:0.8rem 1.1rem;margin-bottom:0.5rem;">
                <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.5rem;">
                    <div>
                        <span style="font-weight:800;font-size:0.85rem;color:#0f172a;">{d.get('document_code')}</span>
                        {_badge_html(d.get('revision','Rev 0'), '#f1f5f9', '#334155')}
                        {_badge_html(d.get('discipline','MECHANICAL'), '#eff6ff', '#1d4ed8')}
                        <span style="font-weight:600;font-size:0.85rem;color:#1e293b;margin-left:6px;">{d.get('document_title')}</span>
                    </div>
                    <div style="display:flex;align-items:center;gap:8px;">
                        {_badge_html('OVERDUE > 14d SLA', '#fee2e2', '#991b1b') if is_overdue else ''}
                        {_badge_html(APPROVAL_CODE_LABELS.get(app_key, app_key), app_c['bg'], app_c['text'])}
                    </div>
                </div>
                <div style="font-size:0.75rem;color:#64748b;margin-top:6px;display:flex;gap:18px;flex-wrap:wrap;">
                    <span>Planned Submit: <b>{format_date_gb(d.get('planned_submission_date'))}</b></span>
                    <span>Actual Submit: <b>{format_date_gb(d.get('actual_submission_date'))}</b></span>
                    <span>14d Review SLA Due: <b style="color:{'#dc2626' if is_overdue else '#0f172a'};">{format_date_gb(due)}</b></span>
                    <span>Actual Return: <b>{format_date_gb(ret)}</b></span>
                    <span>Review SLA Variance: {delay_html}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# 7.6 RAIL Board (Kanban + List View, OPEN -> PENDING_REVIEW -> CLOSED)
# ---------------------------------------------------------------------------

def _render_wb_rail_tab(po: Optional[Dict[str, Any]], rail_items: List[Dict[str, Any]], cross_po: bool = False):
    rc1, rc2 = st.columns([2.5, 2.5])
    with rc1:
        view_mode = st.radio(
            "RAIL View",
            ["Kanban Board (3 Columns)", "List Register"],
            horizontal=True,
            key=f"rail_vw_{po['id'] if po else 'all'}",
            label_visibility="collapsed",
        )

    with st.expander("➕ Log New RAIL Action Item", expanded=False):
        pos_list = [po] if po else expediting_db.get_purchase_orders()
        with st.form(f"rail_add_{po['id'] if po else 'all'}"):
            f1, f2, f3 = st.columns(3)
            with f1:
                if po:
                    sel_po = po
                    st.text_input("Purchase Order", value=f"PO {po['po_number']}", disabled=True)
                else:
                    po_opts = {p["id"]: f"PO {p['po_number']} — {p['vendor_name']}" for p in pos_list}
                    pid = st.selectbox("Purchase Order *", options=list(po_opts.keys()), format_func=lambda k: po_opts[k])
                    sel_po = next((p for p in pos_list if p["id"] == pid), pos_list[0])
                owner = st.text_input("Action Owner *", value="expeditor@inspectflow.io")
            with f2:
                impact = st.selectbox("Schedule Impact Severity", ["HIGH", "MEDIUM", "LOW"])
                due_d = st.date_input("Due Date *", value=date.today() + timedelta(days=7))
            with f3:
                desc = st.text_area("Action / Blocker Description *", placeholder="Describe the technical or material bottleneck and required action...")
            if st.form_submit_button("Create RAIL Item", type="primary"):
                if desc.strip():
                    expediting_db.create_rail_item({
                        "po_id": sel_po["id"],
                        "po_number": sel_po["po_number"],
                        "action_description": desc.strip(),
                        "owner_name": owner.strip(),
                        "due_date": due_d.isoformat(),
                        "impact": impact,
                        "status": "OPEN",
                    })
                    st.rerun()

    if view_mode == "Kanban Board (3 Columns)":
        cols = st.columns(3, gap="medium")
        statuses = [("OPEN", "🔴 OPEN BLOCKERS"), ("PENDING_REVIEW", "🟡 PENDING REVIEW"), ("CLOSED", "🟢 CLOSED")]
        for col, (st_code, st_title) in zip(cols, statuses):
            col_items = [r for r in rail_items if r.get("status") == st_code]
            with col:
                st.markdown(
                    f"<div style='font-size:0.82rem;font-weight:800;color:#334155;margin-bottom:0.5rem;padding:0.4rem 0.75rem;background:#f1f5f9;border-radius:0.5rem;'>{st_title} ({len(col_items)})</div>",
                    unsafe_allow_html=True,
                )
                for r in col_items:
                    imp_c = RAIL_IMPACT_COLORS.get(r.get("impact", "MEDIUM"), RAIL_IMPACT_COLORS["MEDIUM"])
                    st.markdown(
                        f"""
                        <div class="orig-white-card" style="padding:0.8rem 0.95rem;margin-bottom:0.55rem;">
                            <div style="display:flex;justify-content:space-between;align-items:center;">
                                <span style="font-size:0.74rem;font-weight:800;color:#475569;">{r.get('item_number')}</span>
                                {_badge_html(r.get('impact','MEDIUM'), imp_c['bg'], imp_c['text'])}
                            </div>
                            <div style="font-size:0.82rem;font-weight:600;color:#0f172a;margin:6px 0;">{r.get('action_description')}</div>
                            <div style="font-size:0.72rem;color:#64748b;">
                                PO: <b>{r.get('po_number')}</b> • Owner: <b>{r.get('owner_name')}</b><br>
                                Due: <b>{format_date_gb(r.get('due_date'))}</b>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    if st_code != "CLOSED":
                        next_lbl = "→ Send to Review" if st_code == "OPEN" else "✓ Close Action"
                        if st.button(next_lbl, key=f"adv_rail_{r['id']}_{cross_po}", use_container_width=True):
                            expediting_db.advance_rail_item(r["id"])
                            st.rerun()
    else:
        for r in rail_items:
            st_c = RAIL_STATUS_COLORS.get(r.get("status", "OPEN"), RAIL_STATUS_COLORS["OPEN"])
            imp_c = RAIL_IMPACT_COLORS.get(r.get("impact", "MEDIUM"), RAIL_IMPACT_COLORS["MEDIUM"])
            l1, l2, l3 = st.columns([4.5, 2.0, 1.2])
            with l1:
                st.markdown(
                    f"<b>{r.get('item_number')}</b> ({r.get('po_number')}) — {r.get('action_description')}",
                    unsafe_allow_html=True,
                )
            with l2:
                st.markdown(
                    f"{_badge_html(r.get('status','OPEN'), st_c['bg'], st_c['text'])} "
                    f"{_badge_html(r.get('impact','MEDIUM'), imp_c['bg'], imp_c['text'])} "
                    f"<span style='font-size:0.75rem;color:#64748b;'>Due {format_date_gb(r.get('due_date'))}</span>",
                    unsafe_allow_html=True,
                )
            with l3:
                if r.get("status") != "CLOSED":
                    if st.button("→ Advance", key=f"lst_adv_{r['id']}_{cross_po}", use_container_width=True):
                        expediting_db.advance_rail_item(r["id"])
                        st.rerun()


# ---------------------------------------------------------------------------
# 7.7 Inspection Notifications Board (NOI for STD-10, STD-12, STD-16, STD-17, STD-18)
# ---------------------------------------------------------------------------

def _render_wb_inspections_tab(po: Dict[str, Any], inspections: List[Dict[str, Any]], activities: List[Dict[str, Any]], is_vendor: bool = False):
    st.markdown(
        """
        <div style="margin-bottom:0.65rem;">
            <h4 style="margin:0;font-size:0.98rem;font-weight:700;color:#0f172a;">Inspection Notifications (NOI) — ITP Hold &amp; Witness Gates</h4>
            <p style="margin:0;font-size:0.76rem;color:#64748b;">Linked to critical ITP schedule milestones: STD-10 (Raw Material), STD-12 (Fit-up/NDT), STD-16 (FAT/Hydrotest), STD-17 (Painting), STD-18 (Final Release IRN).</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    insp_milestones = [a for a in activities if a.get("activity_code") in INSPECTION_ACTIVITY_CODES]
    if not insp_milestones:
        insp_milestones = [
            {"activity_code": "STD-10", "activity_name": "Raw Material Receipt & Mill Cert Review (NOI)"},
            {"activity_code": "STD-12", "activity_name": "Fit-Up, Welding & NDT Intermediate Inspection (NOI)"},
            {"activity_code": "STD-16", "activity_name": "Hydrostatic / Performance Witness Test - FAT (NOI)"},
            {"activity_code": "STD-17", "activity_name": "Surface Preparation, Painting & Coating Inspection (NOI)"},
            {"activity_code": "STD-18", "activity_name": "Final Inspection & Release Note - IRN (NOI)"},
        ]

    with st.expander("➕ Raise Notice of Inspection (NOI)", expanded=is_vendor):
        with st.form(f"raise_noi_{po['id']}_{is_vendor}"):
            ic1, ic2, ic3 = st.columns(3)
            with ic1:
                act_opts = {a["activity_code"]: f"{a['activity_code']} — {a['activity_name']}" for a in insp_milestones}
                chosen_code = st.selectbox("Inspection Milestone *", options=list(act_opts.keys()), format_func=lambda k: act_opts[k])
                default_type = "HOLD" if chosen_code in ("STD-16", "STD-18") else "WITNESS"
                insp_type = st.selectbox("ITP Point Type *", options=["HOLD", "WITNESS", "REVIEW"], index=["HOLD", "WITNESS", "REVIEW"].index(default_type))
            with ic2:
                prop_date = st.date_input("Proposed Inspection Date *", value=date.today() + timedelta(days=7))
                loc = st.text_input("Workshop Location *", value=f"{po.get('vendor_name','Vendor')} Main Works")
            with ic3:
                contact = st.text_input("Vendor QA Contact", value=po.get("vendor_email", "qa@vendor.com"))
                notes = st.text_input("Inspection Scope / ITP Clause Notes", placeholder="e.g. ITP Clause 6.2 Witness Hydrotest")
            if st.form_submit_button("Submit Notice of Inspection (NOI)", type="primary"):
                expediting_db.create_epc_inspection_notification({
                    "po_id": po["id"],
                    "po_number": po["po_number"],
                    "vendor_name": po.get("vendor_name", ""),
                    "activity_code": chosen_code,
                    "activity_name": act_opts[chosen_code].split(" — ", 1)[-1],
                    "inspection_type": insp_type,
                    "proposed_date": prop_date.isoformat(),
                    "location": loc,
                    "contact_person": contact,
                    "notes": notes,
                    "status": "PENDING",
                })
                st.toast("Notice of Inspection raised!", icon="🔍")
                st.rerun()

    if not inspections:
        st.info("No Notices of Inspection raised for this PO yet.")
        return

    for ins in inspections:
        st_key = ins.get("status", "PENDING")
        st_c = INSPECTION_STATUS_COLORS.get(st_key, INSPECTION_STATUS_COLORS["PENDING"])
        n1, n2, n3 = st.columns([4.2, 1.8, 1.8])
        with n1:
            st.markdown(
                f"""
                <div class="orig-white-card" style="padding:0.8rem 1rem;margin-bottom:0.5rem;">
                    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                        <span style="font-weight:800;font-size:0.86rem;color:#0f172a;">{ins.get('activity_code')} — {ins.get('activity_name')}</span>
                        {_badge_html(INSPECTION_TYPE_LABELS.get(ins.get('inspection_type','HOLD'), 'HOLD'), '#f3e8ff', '#6b21a8')}
                        {_badge_html(st_key, st_c['bg'], st_c['text'])}
                    </div>
                    <div style="font-size:0.76rem;color:#64748b;margin-top:4px;">
                        📅 Proposed Date: <b>{format_date_gb(ins.get('proposed_date'))}</b> &nbsp;•&nbsp;
                        📍 Location: <b>{ins.get('location')}</b> &nbsp;•&nbsp;
                        👤 Contact: <b>{ins.get('contact_person')}</b>
                    </div>
                    <div style="font-size:0.76rem;color:#334155;margin-top:2px;">{ins.get('notes') or ''}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        if not is_vendor:
            with n2:
                if st_key == "PENDING":
                    if st.button("✓ Acknowledge NOI", key=f"ack_noi_{ins['id']}", use_container_width=True):
                        expediting_db.update_epc_inspection_status(ins["id"], "ACKNOWLEDGED")
                        st.rerun()
            with n3:
                if st_key in ("PENDING", "ACKNOWLEDGED"):
                    if st.button("✅ Mark Completed", key=f"cmp_noi_{ins['id']}", type="primary", use_container_width=True):
                        expediting_db.update_epc_inspection_status(ins["id"], "COMPLETED")
                        st.rerun()


# ---------------------------------------------------------------------------
# 6.5 Cross-PO RAIL Action Tracker
# ---------------------------------------------------------------------------

def render_rail_tracker():
    pos = expediting_db.get_purchase_orders()
    rail_items = expediting_db.get_rail_items()

    st.markdown(
        """
        <div class="orig-white-card" style="margin-bottom:0.85rem;">
            <h3 style="margin:0;font-size:1.1rem;font-weight:700;color:#0f172a;">Global RAIL Action Tracker (Rolling Action Item List)</h3>
            <p style="margin:0;font-size:0.78rem;color:#64748b;">Cross-PO blocker resolution board across all active packages and vendors</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    f1, f2 = st.columns([2, 3])
    with f1:
        po_opts = ["ALL"] + [p["po_number"] for p in pos]
        po_filt = st.selectbox("Filter by PO", options=po_opts, format_func=lambda x: "All Purchase Orders" if x == "ALL" else f"PO {x}")
    with f2:
        q = st.text_input("Search action description or owner...", placeholder="🔎 Filter by keyword or owner...")

    filtered = [
        r for r in rail_items
        if (po_filt == "ALL" or r.get("po_number") == po_filt)
        and (not q or q.lower() in f"{r.get('action_description','')} {r.get('owner_name','')} {r.get('item_number','')}".lower())
    ]

    _render_wb_rail_tab(None, filtered, cross_po=True)


# ---------------------------------------------------------------------------
# 6.3 Projects & Vendors Directories
# ---------------------------------------------------------------------------

def render_projects_and_vendors():
    tab_proj, tab_vend = st.tabs(["🏗️ EPC Projects Directory", "🏭 Approved Vendors Directory"])
    pos = expediting_db.get_purchase_orders()

    with tab_proj:
        projects = expediting_db.get_epc_projects()
        with st.expander("➕ Create New EPC Project", expanded=False):
            with st.form("new_epc_proj_form"):
                c1, c2 = st.columns(2)
                with c1:
                    name = st.text_input("Project Name *")
                    code = st.text_input("Project Code *")
                    client = st.text_input("Client Name")
                with c2:
                    loc = st.text_input("Location")
                    mgr = st.text_input("Project Expediting Manager")
                    val = st.number_input("Contract Value ($M)", min_value=0.0, value=250.0)
                if st.form_submit_button("Save Project", type="primary") and name and code:
                    expediting_db.create_epc_project({
                        "name": name, "code": code, "client_name": client,
                        "location": loc, "project_manager": mgr, "contract_value_usd": val * 1_000_000,
                    })
                    st.rerun()

        p_cols = st.columns(2, gap="medium")
        for idx, prj in enumerate(projects):
            prj_pos = [p for p in pos if p.get("project_id") == prj["id"] or p.get("project_name") == prj["name"]]
            avg_prog = (sum(float(p.get("progress_percent") or 0) for p in prj_pos) / len(prj_pos)) if prj_pos else 0.0
            with p_cols[idx % 2]:
                st.markdown(
                    f"""
                    <div class="orig-white-card" style="margin-bottom:0.85rem;">
                        <div style="display:flex;justify-content:space-between;align-items:center;">
                            <span style="font-size:1.02rem;font-weight:800;color:#0f172a;">{prj.get('name')}</span>
                            {_badge_html(prj.get('code','PRJ'), '#dbeafe', '#1d4ed8')}
                        </div>
                        <div style="font-size:0.78rem;color:#64748b;margin:6px 0;">
                            🏢 Client: <b>{prj.get('client_name')}</b> &nbsp;•&nbsp; 📍 {prj.get('location')}<br>
                            👤 PEXM: <b>{prj.get('project_manager')}</b> &nbsp;•&nbsp; 📦 Active POs: <b>{len(prj_pos)}</b>
                        </div>
                        <div style="margin-top:8px;">
                            <div style="font-size:0.7rem;font-weight:700;color:#64748b;margin-bottom:3px;">AVERAGE PO COMPLETION</div>
                            {_progress_bar_html(avg_prog)}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button(f"View {len(prj_pos)} POs in Register →", key=f"prj_go_{prj['id']}", use_container_width=True):
                    st.session_state.epc_project_filter = prj["name"]
                    st.session_state.epc_subpage = "PO Master Register"
                    st.rerun()

    with tab_vend:
        vendors = expediting_db.get_epc_vendors()
        with st.expander("➕ Register New Approved Vendor", expanded=False):
            with st.form("new_epc_vendor_form"):
                v1, v2 = st.columns(2)
                with v1:
                    v_name = st.text_input("Vendor Legal Name *")
                    v_code = st.text_input("Vendor Code *", placeholder="e.g. VND-109")
                    v_country = st.text_input("Country", value="Italy")
                with v2:
                    v_contact = st.text_input("Primary Contact Person")
                    v_email = st.text_input("Contact Email")
                    v_cats = st.text_input("Supply Categories", placeholder="Valves, Pumps, Vessels")
                if st.form_submit_button("Register Vendor", type="primary") and v_name and v_code:
                    expediting_db.create_epc_vendor({
                        "name": v_name, "vendor_code": v_code, "country": v_country,
                        "contact_person": v_contact, "contact_email": v_email, "categories": v_cats,
                    })
                    st.rerun()

        v_cols = st.columns(3, gap="medium")
        for idx, v in enumerate(vendors):
            v_pos = [p for p in pos if p.get("vendor_id") == v["id"] or p.get("vendor_name") == v["name"]]
            stars = "⭐" * int(round(float(v.get("rating") or 4.5)))
            with v_cols[idx % 3]:
                st.markdown(
                    f"""
                    <div class="orig-white-card" style="margin-bottom:0.85rem;">
                        <div style="display:flex;justify-content:space-between;align-items:center;">
                            <span style="font-size:0.92rem;font-weight:800;color:#0f172a;">{v.get('name')}</span>
                            {_badge_html(v.get('vendor_code','VND'), '#f1f5f9', '#334155')}
                        </div>
                        <div style="font-size:0.75rem;color:#64748b;margin-top:6px;">
                            🌍 {v.get('country')} &nbsp;•&nbsp; {stars}<br>
                            👤 {v.get('contact_person')} ({v.get('contact_email')})<br>
                            🏷️ {v.get('categories')} &nbsp;•&nbsp; <b>{len(v_pos)} PO(s)</b>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


# ---------------------------------------------------------------------------
# 6.6 Vendor Portal (5 Supplier Self-Service Tabs)
# ---------------------------------------------------------------------------

def render_vendor_portal():
    pos = expediting_db.get_purchase_orders()
    if not pos:
        st.info("No Purchase Orders available.")
        return

    po_map = {p["id"]: p for p in pos}
    sel_id = st.session_state.get("epc_selected_po_id") or pos[0]["id"]
    if sel_id not in po_map:
        sel_id = pos[0]["id"]

    chosen_id = st.selectbox(
        "Active Supplier Purchase Order",
        options=[p["id"] for p in pos],
        index=[p["id"] for p in pos].index(sel_id),
        format_func=lambda pid: f"PO {po_map[pid]['po_number']} — {po_map[pid]['description']} ({po_map[pid]['vendor_name']})",
    )
    if chosen_id != sel_id:
        st.session_state.epc_selected_po_id = chosen_id
        st.rerun()

    detail = expediting_db.get_workbench_detail(chosen_id)
    po = detail["po"]

    # Dark/Indigo Supplier Portal Banner (§6.6 of guide)
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg, #0f172a 0%, #1e3a8a 100%);color:#ffffff;padding:1.25rem 1.5rem;border-radius:1rem;margin-bottom:1rem;box-shadow:0 4px 12px rgba(15,23,42,0.18);">
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:1rem;">
                <div>
                    <span style="font-size:0.72rem;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;color:#93c5fd;">Supplier Self-Service Portal</span>
                    <h3 style="margin:2px 0 4px 0;font-size:1.25rem;font-weight:800;color:#ffffff;">PO {po['po_number']} — {po.get('description')}</h3>
                    <div style="font-size:0.8rem;color:#cbd5e1;">
                        Supplier: <b>{po.get('vendor_name')}</b> &nbsp;•&nbsp;
                        Project: <b>{po.get('project_name')}</b> &nbsp;•&nbsp;
                        Contract Delivery: <b>{format_date_gb(po.get('contract_delivery_date'))}</b>
                    </div>
                </div>
                <div style="background:rgba(255,255,255,0.12);padding:0.65rem 1rem;border-radius:0.75rem;min-width:170px;text-align:center;">
                    <div style="font-size:0.7rem;color:#cbd5e1;font-weight:700;">REPORTED PROGRESS</div>
                    <div style="font-size:1.45rem;font-weight:800;color:#38bdf8;">{float(po.get('progress_percent') or 0):.0f}%</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    v_tabs = st.tabs([
        "📤 1. Schedule & Report Uploads",
        "⛓️ 2. Sub-Order POs",
        "📅 3. My Schedule",
        "📑 4. Document Status (VDRL)",
        "🔍 5. Inspection Notifications (NOI)",
    ])

    with v_tabs[0]:
        u1, u2 = st.columns(2, gap="medium")
        with u1:
            st.markdown("#### Upload Level-3 Schedule (.xlsx / .pdf)")
            st.caption("Deterministic Excel parser updates milestones by `(po_id, activity_code)` without duplicating rows.")
            s_file = st.file_uploader("Select Schedule File", type=["xlsx", "xlsm", "pdf"], key=f"vp_sch_{po['id']}")
            if s_file and st.button("Upload & Sync Schedule", key=f"vp_btn_sch_{po['id']}", type="primary"):
                res = parse_vendor_schedule_file(s_file.getvalue(), s_file.name, po["id"], dry_run=False)
                st.success(f"Synced {res['count']} schedule milestones!")
                st.rerun()
        with u2:
            st.markdown("#### Upload Sub-Order Status Report (.xlsx / .pdf)")
            st.caption("Automatically extracts Tier-2 sub-orders and computes workshop float.")
            so_file = st.file_uploader("Select Sub-Order Report", type=["xlsx", "pdf"], key=f"vp_so_{po['id']}")
            if so_file and st.button("Upload & Calculate Float", key=f"vp_btn_so_{po['id']}", type="primary"):
                res = parse_suborder_report_file(so_file.getvalue(), so_file.name, po["id"], po["po_number"], po.get("vendor_name", ""))
                st.success(f"Processed {res['count']} sub-orders!")
                st.rerun()

    with v_tabs[1]:
        _render_wb_suborders_tab(po, detail["sub_orders"])

    with v_tabs[2]:
        _render_wb_schedule_tab(po, detail["activities"], read_only=True)

    with v_tabs[3]:
        _render_wb_vdrl_tab(po, detail["vdrl_docs"], read_only=True)

    with v_tabs[4]:
        _render_wb_inspections_tab(po, detail["inspections"], detail["activities"], is_vendor=True)


# ---------------------------------------------------------------------------
# 6.8 In-App Project Documentation
# ---------------------------------------------------------------------------

def render_expediting_docs():
    doc_md = """# SmartExpedit — Procurement Expediting & Material Tracking Guide

### 1. Five Parallel Expediting Tracks per Purchase Order
- **Level-3 Schedule**: 23 standard Oil & Gas EPC milestones (`STD-01` to `STD-23`), interactive Gantt / 2-Tier Table / Timeline views, and deterministic Excel (`.xlsx`) + AI PDF schedule parsing with idempotent `(po_id, activity_code)` upsert.
- **Sub-Orders / Workshop Float**: Measures Tier-2 sub-vendor delivery risk (`float_days = Required_at_Workshop_Date - Sub_Vendor_ETA_Date`). Classifies into `ON_TRACK` (>= 14d), `WARNING` (0..13d), or `CRITICAL_DELAY` (< 0d).
- **Bulk Manufacturing Routing**: 10-stage per-tag interactive progress matrix (`RAW_MATERIAL` through `FINAL_INSPECTION`) for `BULK` POs.
- **VDRL Engineering Documents**: Enforces the **14-day EPC review SLA** (`epc_review_due_date = actual_submission_date + 14 days`) and tracks Approval Codes (`CODE 1` to `CODE 4`).
- **RAIL & Inspection Notifications (NOI)**: 3-stage Kanban blocker board (`OPEN → PENDING_REVIEW → CLOSED`) and supplier Notices of Inspection on `STD-10, STD-12, STD-16, STD-17, STD-18`.
"""
    st.markdown('<div class="orig-white-card">', unsafe_allow_html=True)
    st.markdown(doc_md)
    st.download_button(
        "📥 Download SmartExpedit Technical Guide (.md)",
        data=doc_md.encode("utf-8"),
        file_name="SmartExpedit_Functional_Technical_Guide.md",
        mime="text/markdown",
    )
    st.markdown("</div>", unsafe_allow_html=True)

