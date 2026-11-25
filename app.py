import json
from datetime import datetime
from typing import Any, Dict, List, Optional

import altair as alt
import pandas as pd
import pydeck as pdk
import streamlit as st

from python_app import ai_service as ai
from python_app import database as db
from python_app.expediting_ui import render_expediting_module

st.set_page_config(
    page_title="Base44 APP — InspectFlow",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="collapsed",
)

db.init_db()

# ── Original Layout.jsx + Tailwind + Material Elevation CSS ──────────────────
st.markdown(
    """
    <style>
    /* Hide default Streamlit chrome & sidebar to match original Layout.jsx */
    #MainMenu {visibility: hidden;}
    header[data-testid="stHeader"] {display: none;}
    section[data-testid="stSidebar"] {display: none;}
    footer {visibility: hidden;}

    .stApp {
        background-color: #f9fafb !important;
        font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    .block-container {
        padding-top: 0rem !important;
        padding-bottom: 2rem !important;
        padding-left: 1.5rem !important;
        padding-right: 1.5rem !important;
        max-width: 1600px !important;
    }

    :root {
        --md-elevation-1: 0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.24);
        --md-elevation-2: 0 3px 6px rgba(0,0,0,0.15), 0 2px 4px rgba(0,0,0,0.12);
        --md-elevation-3: 0 10px 20px rgba(0,0,0,0.15), 0 3px 6px rgba(0,0,0,0.10);
    }

    /* Top App Bar (matches Layout.jsx header) */
    .orig-topbar {
        background: #ffffff;
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -2px rgba(0,0,0,0.1);
        padding: 0.75rem 1.5rem;
        margin: 0 -1.5rem 1.25rem -1.5rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
        border-bottom: 1px solid #e5e7eb;
    }
    .orig-logo-box {
        width: 40px;
        height: 40px;
        background: linear-gradient(135deg, #4f46e5, #4338ca);
        border-radius: 0.5rem;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        color: white;
        font-size: 1.25rem;
        box-shadow: 0 4px 6px rgba(79, 70, 229, 0.25);
    }
    .orig-user-pill {
        display: inline-flex;
        align-items: center;
        gap: 0.75rem;
        padding: 0.4rem 0.9rem;
        background: #f9fafb;
        border-radius: 0.5rem;
        border: 1px solid #f3f4f6;
    }
    .orig-role-badge {
        padding: 0.15rem 0.6rem;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .role-admin { background: #fee2e2; color: #991b1b; border: 1px solid #fecaca; }
    .role-inspection_engineer { background: #dbeafe; color: #1e40af; border: 1px solid #bfdbfe; }
    .role-qc_manager { background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }
    .role-inspector { background: #f3e8ff; color: #6b21a8; border: 1px solid #e9d5ff; }
    .role-inspection_agency { background: #fef3c7; color: #92400e; border: 1px solid #fde68a; }

    /* StatsCard.jsx exact look */
    .orig-stat-card {
        background: #ffffff;
        border-radius: 1rem;
        padding: 1.5rem;
        box-shadow: var(--md-elevation-2);
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        height: 100%;
    }
    .orig-stat-title {
        font-size: 0.82rem;
        font-weight: 600;
        color: #4b5563;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        margin-bottom: 0.4rem;
    }
    .orig-stat-value {
        font-size: 2.25rem;
        font-weight: 700;
        color: #111827;
        line-height: 1.1;
        margin-bottom: 0.25rem;
    }
    .orig-stat-trend {
        font-size: 0.85rem;
        color: #6b7280;
    }
    .orig-stat-icon {
        width: 56px;
        height: 56px;
        border-radius: 1rem;
        display: flex;
        align-items: center;
        justify-content: center;
        color: #ffffff;
        font-size: 1.5rem;
        box-shadow: var(--md-elevation-1);
        flex-shrink: 0;
    }

    /* White Elevation-2 Container (Search card, Table card, Agency card) */
    .orig-white-card {
        background: #ffffff;
        border-radius: 1rem;
        padding: 1.5rem;
        box-shadow: var(--md-elevation-2);
        margin-bottom: 1.25rem;
    }

    /* Notifications Panel Card */
    .orig-noti-card {
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 0.5rem;
        padding: 0.75rem;
        margin-bottom: 0.5rem;
        border-left: 3px solid #4f46e5;
    }

    /* Status Badges */
    .status-pill {
        display: inline-block;
        padding: 0.15rem 0.55rem;
        border-radius: 9999px;
        font-size: 0.72rem;
        font-weight: 600;
    }
    .status-received { background: #f3f4f6; color: #1f2937; border: 1px solid #e5e7eb; }
    .status-scheduled { background: #dbeafe; color: #1e40af; border: 1px solid #bfdbfe; }
    .status-in_progress { background: #e0e7ff; color: #3730a3; border: 1px solid #c7d2fe; }
    .status-completed { background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }
    .status-finalized { background: #f3e8ff; color: #6b21a8; border: 1px solid #e9d5ff; }

    /* Footer */
    .orig-footer {
        background: #ffffff;
        border-top: 1px solid #e5e7eb;
        padding: 1.25rem;
        text-align: center;
        color: #6b7280;
        font-size: 0.875rem;
        margin-top: 3rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

ROLE_LABELS = {
    "admin": "Admin",
    "inspection_engineer": "Inspection Engineer",
    "qc_manager": "QC Manager",
    "inspector": "Inspector",
    "inspection_agency": "Inspection Agency",
}


def render_stat_card(title: str, value: Any, trend: str, bg_hex: str, icon_char: str) -> None:
    st.markdown(
        f"""
        <div class="orig-stat-card">
            <div>
                <div class="orig-stat-title">{title}</div>
                <div class="orig-stat-value">{value}</div>
                <div class="orig-stat-trend">{trend}</div>
            </div>
            <div class="orig-stat-icon" style="background-color: {bg_hex};">
                {icon_char}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Session State ────────────────────────────────────────────────────────────
if "user" not in st.session_state:
    users = db.list_users()
    st.session_state.user = users[0] if users else None
if "current_page" not in st.session_state:
    st.session_state.current_page = "Dashboard"
if "selected_project_id" not in st.session_state:
    st.session_state.selected_project_id = None
if "notifications_expanded" not in st.session_state:
    st.session_state.notifications_expanded = False
if "filter_ncrs" not in st.session_state:
    st.session_state.filter_ncrs = False
if "filter_findings" not in st.session_state:
    st.session_state.filter_findings = False
if "filter_pending" not in st.session_state:
    st.session_state.filter_pending = False
if "active_view" not in st.session_state:
    st.session_state.active_view = "table"
if "chat_open" not in st.session_state:
    st.session_state.chat_open = False
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = [
        {"role": "assistant", "content": "Hi! I'm the InspectFlow AI Assistant. How can I help you today?"}
    ]


# ── Modal Dialogs (matching Dashboard.jsx Dialogs) ───────────────────────────

@st.dialog("Upload Notifications", width="large")
def open_upload_modal(user: Dict[str, Any]) -> None:
    st.caption("Upload PDF Inspection Notifications to extract data automatically with Gemini AI.")
    files = st.file_uploader("Drag & drop PDF files here, or click to select", type=["pdf"], accept_multiple_files=True)
    if files and st.button("Extract & Process Notifications", type="primary", use_container_width=True):
        existing = db.list_inspections()
        results = []
        for f in files:
            with st.spinner(f"Uploading & extracting {f.name}..."):
                pdf_bytes = f.read()
                url = db.save_uploaded_file(pdf_bytes, f.name)
                extracted = ai.extract_inspection_notification(pdf_bytes, f.name)
                dup = next(
                    (
                        x
                        for x in existing
                        if x.get("po_number") == extracted.get("po_number")
                        and x.get("notification_number") == extracted.get("notification_number")
                    ),
                    None,
                )
                extracted["document_url"] = url
                extracted["fileName"] = f.name
                extracted["isDuplicate"] = dup is not None
                results.append(extracted)
        st.session_state["modal_extracted_list"] = results

    extracted_list = st.session_state.get("modal_extracted_list", [])
    for idx, data in enumerate(extracted_list):
        st.markdown(f"#### {data.get('notification_number') or data.get('fileName')} (PO: {data.get('po_number') or 'N/A'})")
        if data.get("isDuplicate"):
            st.warning("⚠️ Duplicate PO & Notification Number detected.")
        with st.form(f"modal_review_form_{idx}"):
            c1, c2, c3 = st.columns(3)
            po = c1.text_input("PO Number", value=data.get("po_number") or "")
            notif = c2.text_input("Notification Number", value=data.get("notification_number") or "")
            rev = c3.text_input("Revision", value=data.get("notification_revision") or "00")

            c4, c5, c6 = st.columns(3)
            sup = c4.text_input("Supplier Name", value=data.get("supplier_name") or "")
            cntry = c5.text_input("Country", value=data.get("country") or "")
            sdate = c6.text_input("Start Date", value=data.get("start_date") or "")

            desc = st.text_input("PO Description", value=data.get("po_description") or "")
            notes = st.text_area("Notes", value=data.get("notes") or "")
            if st.form_submit_button("Save Inspection", type="primary"):
                db.create_inspection(
                    {
                        **data,
                        "po_number": po,
                        "notification_number": notif,
                        "notification_revision": rev,
                        "supplier_name": sup,
                        "country": cntry,
                        "start_date": sdate,
                        "po_description": desc,
                        "notes": notes,
                        "project_id": st.session_state.selected_project_id,
                        "status": "received",
                        "created_by": user.get("email"),
                    }
                )
                st.session_state["modal_extracted_list"].pop(idx)
                st.rerun()


@st.dialog("Edit Inspection Details", width="large")
def open_edit_inspection_modal(insp: Dict[str, Any]) -> None:
    inspectors = db.list_inspectors()
    agencies = db.list_agencies()
    with st.form(f"dlg_edit_{insp['id']}"):
        c1, c2, c3, c4 = st.columns(4)
        po = c1.text_input("PO #", value=insp.get("po_number") or "")
        notif = c2.text_input("Notification #", value=insp.get("notification_number") or "")
        rev = c3.text_input("Revision #", value=insp.get("notification_revision") or "")
        rec_dt = c4.text_input("Receipt Date", value=insp.get("notification_receipt_date") or "")

        c5, c6, c7 = st.columns(3)
        sup = c5.text_input("Supplier Name", value=insp.get("supplier_name") or "")
        subsup = c6.text_input("Sub-Supplier Name", value=insp.get("subsupplier_name") or "")
        cntry = c7.text_input("Country", value=insp.get("country") or "")

        c8, c9, c10, c11 = st.columns(4)
        loc = c8.text_input("Location", value=insp.get("inspection_location") or "")
        sdate = c9.text_input("Start Date", value=insp.get("start_date") or "")
        edate = c10.text_input("End Date", value=insp.get("end_date") or "")
        itime = c11.text_input("Time", value=insp.get("inspection_time") or "")

        c12, c13, c14 = st.columns(3)
        vname = c12.text_input("Vendor Contact", value=insp.get("vendor_contact_name") or "")
        vphone = c13.text_input("Vendor Phone", value=insp.get("vendor_contact_phone") or "")
        vemail = c14.text_input("Vendor Email", value=insp.get("vendor_contact_email") or "")

        c15, c16, c17 = st.columns(3)
        ag_map = {"-- None --": None, **{a["name"]: a["id"] for a in agencies}}
        cur_ag = next((k for k, v in ag_map.items() if v == insp.get("tpi_agency_id")), "-- None --")
        sel_ag = c15.selectbox("TPI Agency", list(ag_map.keys()), index=list(ag_map.keys()).index(cur_ag))

        ins_map = {"-- Unassigned --": None, **{f"{i['full_name']} ({i['email']})": i["id"] for i in inspectors}}
        cur_ins = next((k for k, v in ins_map.items() if v == insp.get("assigned_inspector_id")), "-- Unassigned --")
        sel_ins = c16.selectbox("Assigned Inspector", list(ins_map.keys()), index=list(ins_map.keys()).index(cur_ins))

        st_opts = ["received", "scheduled", "in_progress", "completed", "finalized"]
        cur_st = insp.get("status") if insp.get("status") in st_opts else "received"
        sel_st = c17.selectbox("Status", st_opts, index=st_opts.index(cur_st))

        desc = st.text_input("PO Description", value=insp.get("po_description") or "")
        notes = st.text_area("Notes", value=insp.get("notes") or "")

        st.markdown("**Items Being Offered**")
        items_df = pd.DataFrame(insp.get("items_being_offered") or [{"itemNumber": "1", "description": "", "quantity": ""}])
        ed_items = st.data_editor(items_df, num_rows="dynamic", use_container_width=True, key=f"dlg_items_{insp['id']}")

        st.markdown("**Inspection Activities (ITP)**")
        acts_df = pd.DataFrame(
            insp.get("inspection_activities")
            or [{"date": "", "time": "", "itp_step": "", "activity": "", "supplier": "W", "contractor": "W", "company_tpa": "W", "remarks": ""}]
        )
        ed_acts = st.data_editor(acts_df, num_rows="dynamic", use_container_width=True, key=f"dlg_acts_{insp['id']}")

        if st.form_submit_button("Save Changes", type="primary", use_container_width=True):
            db.update_inspection(
                insp["id"],
                {
                    "po_number": po,
                    "notification_number": notif,
                    "notification_revision": rev,
                    "notification_receipt_date": rec_dt or None,
                    "supplier_name": sup,
                    "subsupplier_name": subsup,
                    "country": cntry,
                    "location_address": loc,
                    "start_date": sdate or None,
                    "end_date": edate or None,
                    "inspection_time": itime,
                    "vendor_contact_name": vname,
                    "vendor_contact_phone": vphone,
                    "vendor_contact_email": vemail,
                    "tpi_agency_id": ag_map[sel_ag],
                    "assigned_inspector_id": ins_map[sel_ins],
                    "status": sel_st,
                    "po_description": desc,
                    "notes": notes,
                    "items_being_offered": ed_items.to_dict(orient="records"),
                    "inspection_activities": ed_acts.to_dict(orient="records"),
                },
            )
            st.rerun()


@st.dialog("Findings — Reports & Release | Actions", width="large")
def open_reports_findings_modal(insp: Dict[str, Any], user: Dict[str, Any]) -> None:
    fresh = db.get_inspection(insp["id"]) or insp
    open_cnt = sum(
        sum(1 for f in (r.get("findings") or []) if (f.get("closure_status") or f.get("status") or "open").lower() != "closed")
        for r in (fresh.get("inspection_reports") or [])
    )
    t_rep, t_act = st.tabs(["📄 Reports & Release", f"⚡ Actions ({open_cnt} Open)"])

    with t_rep:
        with st.expander("➕ Upload New Report or Release Note", expanded=False):
            u1, u2 = st.columns(2)
            with u1:
                rname = st.text_input("Report Name", key=f"rname_{fresh['id']}")
                rtype = st.selectbox("Report Type", ["Flash", "Interim", "Final"], key=f"rtype_{fresh['id']}")
                rfile = st.file_uploader("Report PDF", type=["pdf"], key=f"rfile_{fresh['id']}")
                if st.button("Upload & Extract Findings", type="primary", key=f"ubtn_{fresh['id']}") and rfile:
                    b = rfile.read()
                    url = db.save_uploaded_file(b, rfile.name)
                    findings = []
                    try:
                        parsed = ai.extract_inspection_report(b, rfile.name, rtype)
                        findings = parsed.get("findings") or []
                    except Exception:
                        pass
                    reps = list(fresh.get("inspection_reports") or [])
                    reps.append(
                        {
                            "name": rname or rfile.name,
                            "url": url,
                            "uploaded_by": user.get("email"),
                            "uploaded_date": db.now_iso(),
                            "report_type": rtype,
                            "is_final_report": rtype == "Final",
                            "approval_status": "pending",
                            "findings": findings,
                        }
                    )
                    db.update_inspection(fresh["id"], {"inspection_reports": reps})
                    st.rerun()
            with u2:
                rn_name = st.text_input("Release Note Name", key=f"rnname_{fresh['id']}")
                rn_file = st.file_uploader("Release Note PDF", type=["pdf"], key=f"rnfile_{fresh['id']}")
                if st.button("Upload Release Note", key=f"rnbtn_{fresh['id']}") and rn_file:
                    url = db.save_uploaded_file(rn_file.read(), rn_file.name)
                    rns = list(fresh.get("release_notes") or [])
                    rns.append({"name": rn_name or rn_file.name, "url": url, "uploaded_by": user.get("email"), "uploaded_date": db.now_iso()})
                    db.update_inspection(fresh["id"], {"release_notes": rns})
                    st.rerun()

        reports = list(fresh.get("inspection_reports") or [])
        if not reports:
            st.info("No inspection reports uploaded yet.")
        for idx, r in enumerate(reports):
            c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
            c1.markdown(
                f"**{r.get('name')}** (`{r.get('report_type', 'Flash')}`) — "
                f"Status: **{(r.get('approval_status') or 'pending').upper()}** — [Open PDF]({r.get('url', '#')})"
            )
            if c2.button("Approve", key=f"ap_{fresh['id']}_{idx}"):
                reports[idx]["approval_status"] = "approved"
                db.update_inspection(fresh["id"], {"inspection_reports": reports})
                st.rerun()
            if c3.button("Reject", key=f"rj_{fresh['id']}_{idx}"):
                reports[idx]["approval_status"] = "rejected"
                db.update_inspection(fresh["id"], {"inspection_reports": reports})
                st.rerun()
            if c4.button("Delete", key=f"dl_{fresh['id']}_{idx}"):
                reports.pop(idx)
                db.update_inspection(fresh["id"], {"inspection_reports": reports})
                st.rerun()

    with t_act:
        reports = list(fresh.get("inspection_reports") or [])
        any_f = False
        for r_idx, r in enumerate(reports):
            for f_idx, f in enumerate(r.get("findings") or []):
                any_f = True
                closed = (f.get("closure_status") or f.get("status") or "open").lower() == "closed"
                st.markdown(
                    f"{'🟢 CLOSED' if closed else '🔴 OPEN'} — **{f.get('type', 'Finding')}** "
                    f"(`{f.get('severity', 'Major')}`) — Ref: `{f.get('item_reference', '-')}`  \n"
                    f"{f.get('description', '')}"
                )
                if not closed:
                    jc1, jc2 = st.columns([3, 1])
                    just = jc1.text_input("Closure Justification", key=f"mjust_{fresh['id']}_{r_idx}_{f_idx}")
                    if jc2.button("Close Finding", key=f"mcls_{fresh['id']}_{r_idx}_{f_idx}", type="primary"):
                        reports[r_idx]["findings"][f_idx]["status"] = "Closed"
                        reports[r_idx]["findings"][f_idx]["closure_status"] = "closed"
                        reports[r_idx]["findings"][f_idx]["closure_justification"] = just or "Closed"
                        reports[r_idx]["findings"][f_idx]["closed_by"] = user.get("email")
                        reports[r_idx]["findings"][f_idx]["closed_date"] = db.now_iso()
                        db.update_inspection(fresh["id"], {"inspection_reports": reports})
                        st.rerun()
                st.divider()
        if not any_f:
            st.info("No findings recorded for this inspection.")


@st.dialog("Attendance & Location Verification", width="large")
def open_attendance_modal(insp: Dict[str, Any], user: Dict[str, Any]) -> None:
    att_list = db.list_attendances(inspection_id=insp["id"])
    inspectors = db.list_inspectors()
    my_prof = next((i for i in inspectors if i.get("email") == user.get("email")), inspectors[0] if inspectors else None)

    c1, c2 = st.columns(2)
    lat = c1.number_input("Latitude", value=float(insp.get("location_latitude") or 24.49887), format="%.6f")
    lng = c2.number_input("Longitude", value=float(insp.get("location_longitude") or 54.36676), format="%.6f")

    open_rec = next((a for a in att_list if not a.get("check_out_time")), None)
    if not open_rec:
        if st.button("📍 Check In Now", type="primary", use_container_width=True) and my_prof:
            db.create_attendance(
                {
                    "inspection_id": insp["id"],
                    "inspector_id": my_prof["id"],
                    "check_in_time": db.now_iso(),
                    "check_in_latitude": lat,
                    "check_in_longitude": lng,
                    "location_verified": True,
                    "check_in_notes": "Checked in via Dashboard",
                }
            )
            st.rerun()
    else:
        if st.button("🏁 Check Out Now", type="primary", use_container_width=True):
            db.update_attendance(
                open_rec["id"],
                {
                    "check_out_time": db.now_iso(),
                    "check_out_latitude": lat,
                    "check_out_longitude": lng,
                    "check_out_notes": "Checked out via Dashboard",
                },
            )
            st.rerun()

    if att_list:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Inspector": a.get("inspector_name") or "-",
                        "Check In": a.get("check_in_time"),
                        "Check Out": a.get("check_out_time") or "On Site",
                        "Coordinates": a.get("check_in_coordinates_text") or "-",
                        "Verified": "Yes" if a.get("location_verified") else "No",
                    }
                    for a in att_list
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )


# ── Top Navigation Bar (Matches Layout.jsx 1:1) ─────────────────────────────
def render_top_navbar(user: Dict[str, Any]) -> None:
    projects = db.list_projects()
    role = user.get("inspection_role") or user.get("role") or "admin"
    is_admin = role == "admin"
    is_qc = role == "qc_manager"
    is_eng = role == "inspection_engineer"
    is_insp = role == "inspector"
    is_agency = role == "inspection_agency"

    st.markdown(
        f"""
        <div class="orig-topbar">
            <div style="display:flex;align-items:center;gap:0.75rem;">
                <div class="orig-logo-box">📄</div>
                <span style="font-size:1.25rem;font-weight:700;color:#111827;">InspectFlow</span>
            </div>
            <div class="orig-user-pill">
                <div style="text-align:right;line-height:1.2;">
                    <div style="font-size:0.875rem;font-weight:600;color:#111827;">{user.get('full_name')}</div>
                    <div style="font-size:0.75rem;color:#6b7280;">{user.get('email')}</div>
                </div>
                <span class="orig-role-badge role-{role}">{ROLE_LABELS.get(role, 'User')}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Navigation Bar Row: Project Selector + Account Switcher + Original Nav Items
    nav_items = []
    if is_admin or is_eng or is_qc or is_insp:
        nav_items.append(("My Inspections" if is_insp else "Dashboard", "Dashboard"))
        nav_items.append(("📦 Expediting", "Expediting"))
        nav_items.append(("IR & IRC", "Reports"))
    else:
        nav_items.append(("📦 Expediting", "Expediting"))
    if is_admin or is_eng or is_qc or is_agency:
        nav_items.append(("Inspectors", "Inspectors"))
    if is_admin:
        nav_items.append(("Agencies", "TPIAgencies"))
    if is_admin or is_qc:
        nav_items.append(("Performance", "TPIPerformance"))
    if is_admin:
        nav_items.append(("Admin", "UserManagement"))
    if is_insp:
        nav_items.append(("My Profile", "Profile"))

    cols = st.columns([1.6, 1.8] + [1] * len(nav_items) + [0.8])

    # Project Selector
    proj_options = {"All Projects": None, **{f"{p['name']} ({p['code']})": p["id"] for p in projects}}
    cur_p = next((k for k, v in proj_options.items() if v == st.session_state.selected_project_id), "All Projects")
    sel_p = cols[0].selectbox("Project", list(proj_options.keys()), index=list(proj_options.keys()).index(cur_p), label_visibility="collapsed")
    st.session_state.selected_project_id = proj_options[sel_p]

    # Quick Role/User Switcher
    all_users = db.list_users()
    u_map = {f"👤 {u['full_name']} ({ROLE_LABELS.get(u.get('inspection_role'), 'User')})": u for u in all_users}
    cur_u = next((k for k, v in u_map.items() if v["email"] == user["email"]), list(u_map.keys())[0])
    sel_u = cols[1].selectbox("User", list(u_map.keys()), index=list(u_map.keys()).index(cur_u), label_visibility="collapsed")
    if u_map[sel_u]["email"] != user["email"]:
        st.session_state.user = u_map[sel_u]
        st.session_state.current_page = "Dashboard"
        st.rerun()

    for idx, (label, page_key) in enumerate(nav_items):
        is_active = st.session_state.current_page == page_key
        if cols[idx + 2].button(
            label,
            key=f"nav_{page_key}",
            type="primary" if is_active else "secondary",
            use_container_width=True,
        ):
            st.session_state.current_page = page_key
            st.rerun()

    if cols[-1].button("Sign Out", key="nav_signout", use_container_width=True):
        st.session_state.user = None
        st.rerun()

    st.markdown("<div style='height: 0.75rem;'></div>", unsafe_allow_html=True)


# ── Dashboard Page (Matches Dashboard.jsx 1:1) ──────────────────────────────
def render_dashboard_page(user: Dict[str, Any]) -> None:
    inspections = db.list_inspections()
    inspectors = db.list_inspectors()
    projects = db.list_projects()

    role = user.get("inspection_role") or user.get("role") or "admin"
    is_admin = role == "admin"
    is_qc = role == "qc_manager"
    is_eng = role == "inspection_engineer"
    is_insp = role == "inspector"
    is_agency = role == "inspection_agency"

    if is_admin or is_qc:
        role_filtered = inspections
    elif is_eng:
        role_filtered = [i for i in inspections if i.get("created_by") == user.get("email")]
    elif is_agency:
        ag_name = (user.get("company") or user.get("company_affiliation") or "").lower()
        role_filtered = [i for i in inspections if (i.get("tpi_agency") or "").lower() == ag_name]
    elif is_insp:
        prof = next((ins for ins in inspectors if ins.get("email") == user.get("email")), None)
        pid = prof["id"] if prof else None
        role_filtered = [
            i
            for i in inspections
            if i.get("assigned_inspector_email") == user.get("email") or (pid and i.get("assigned_inspector_id") == pid)
        ]
    else:
        role_filtered = inspections

    sel_pid = st.session_state.selected_project_id
    current_project = next((p for p in projects if p["id"] == sel_pid), None) if sel_pid else None
    project_filtered = (
        [i for i in role_filtered if not i.get("project_id") or i.get("project_id") == sel_pid]
        if sel_pid
        else role_filtered
    )

    # Header with Title & Upload Button (Dashboard.jsx lines 612-626)
    project_prefix = f"{current_project['name']} - " if current_project else ""
    if is_insp:
        dash_title = f"{project_prefix}My Assigned Inspections"
        dash_desc = "View and track inspections assigned to you for this project"
    elif is_eng:
        dash_title = f"{project_prefix}My Inspection Notifications"
        dash_desc = "Manage your inspection notifications for this project"
    elif is_qc:
        dash_title = f"{project_prefix}Project Oversight"
        dash_desc = "Monitor and manage all inspection notifications for this project"
    else:
        dash_title = f"{project_prefix}Dashboard"
        dash_desc = "Manage and track all inspection notifications for this project"

    h_left, h_right = st.columns([4, 1])
    with h_left:
        st.markdown(
            f"""
            <div style="margin-bottom: 1rem;">
                <h1 style="font-size:2.25rem;font-weight:700;color:#111827;margin:0 0 0.35rem 0;">{dash_title}</h1>
                <p style="color:#4b5563;font-size:1rem;margin:0;">{dash_desc}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with h_right:
        if is_admin or is_eng or is_qc:
            st.markdown("<div style='height:0.5rem;'></div>", unsafe_allow_html=True)
            if st.button("⬆️ Upload Notification", type="primary", use_container_width=True):
                open_upload_modal(user)

    # 5 Stats Cards (Dashboard.jsx lines 629-665)
    stats_total = len(role_filtered)
    stats_received = sum(1 for i in role_filtered if i.get("status") == "received")
    stats_scheduled = sum(1 for i in role_filtered if i.get("status") == "scheduled")
    stats_completed = sum(1 for i in role_filtered if i.get("status") == "completed")
    stats_finalized = sum(1 for i in role_filtered if i.get("status") == "finalized")

    sc1, sc2, sc3, sc4, sc5 = st.columns(5)
    with sc1:
        render_stat_card(
            "My Inspections" if is_insp else "Total Inspections",
            stats_total,
            "Assigned to me" if is_insp else ("Your notifications" if is_eng else "All notifications"),
            "#4f46e5",
            "📄",
        )
    with sc2:
        render_stat_card("Received", stats_received, "Not yet assigned", "#4b5563", "📥")
    with sc3:
        render_stat_card("Scheduled", stats_scheduled, "Inspector assigned", "#2563eb", "🕒")
    with sc4:
        render_stat_card("Completed", stats_completed, "Event finished", "#16a34a", "✅")
    with sc5:
        render_stat_card("Finalized", stats_finalized, "Report uploaded", "#9333ea", "🏅")

    st.markdown("<div style='height: 1.25rem;'></div>", unsafe_allow_html=True)

    # White Search & Quick Filters Card (Dashboard.jsx lines 668-747)
    with st.container():
        search_q = st.text_input(
            "Search",
            placeholder="🔍 Search by PO number, notification number, location, supplier, country...",
            label_visibility="collapsed",
        )
        qf1, qf2, qf3, qf4, qf5, _ = st.columns([0.9, 1.1, 1.1, 1.2, 0.9, 4])
        qf1.markdown("<div style='padding-top:0.4rem;font-size:0.875rem;color:#4b5563;font-weight:500;'>⚡ Quick Filters:</div>", unsafe_allow_html=True)
        if qf2.button(
            f"⚠️ NCRs Only {'✕' if st.session_state.filter_ncrs else ''}",
            type="primary" if st.session_state.filter_ncrs else "secondary",
            use_container_width=True,
        ):
            st.session_state.filter_ncrs = not st.session_state.filter_ncrs
            st.rerun()
        if qf3.button(
            f"📋 Findings Only {'✕' if st.session_state.filter_findings else ''}",
            type="primary" if st.session_state.filter_findings else "secondary",
            use_container_width=True,
        ):
            st.session_state.filter_findings = not st.session_state.filter_findings
            st.rerun()
        if qf4.button(
            f"⏳ Pending Reports {'✕' if st.session_state.filter_pending else ''}",
            type="primary" if st.session_state.filter_pending else "secondary",
            use_container_width=True,
        ):
            st.session_state.filter_pending = not st.session_state.filter_pending
            st.rerun()
        if st.session_state.filter_ncrs or st.session_state.filter_findings or st.session_state.filter_pending:
            if qf5.button("Clear All", use_container_width=True):
                st.session_state.filter_ncrs = False
                st.session_state.filter_findings = False
                st.session_state.filter_pending = False
                st.rerun()

    # Apply Search & Quick Filters
    filtered = []
    for insp in project_filtered:
        if search_q.strip():
            q = search_q.strip().lower()
            hay = " ".join(
                str(insp.get(k) or "")
                for k in (
                    "po_number",
                    "notification_number",
                    "inspection_location",
                    "inspection_type",
                    "vendor_contact_name",
                    "supplier_name",
                    "subsupplier_name",
                    "country",
                )
            ).lower()
            if q not in hay:
                continue
        if st.session_state.filter_ncrs and insp.get("open_ncrs_count", 0) == 0:
            continue
        if st.session_state.filter_findings and insp.get("total_findings_count", 0) == 0:
            continue
        if st.session_state.filter_pending:
            has_pend = any((r.get("approval_status") or "pending") == "pending" for r in (insp.get("inspection_reports") or []))
            if not has_pend:
                continue
        filtered.append(insp)

    # Centered View Toggle: Table View | Calendar View (Dashboard.jsx lines 750-760)
    _, vt1, vt2, _ = st.columns([2.5, 1.2, 1.2, 2.5])
    if vt1.button(
        "📋 Table View",
        type="primary" if st.session_state.active_view == "table" else "secondary",
        use_container_width=True,
    ):
        st.session_state.active_view = "table"
        st.rerun()
    if vt2.button(
        "📅 Calendar View",
        type="primary" if st.session_state.active_view == "calendar" else "secondary",
        use_container_width=True,
    ):
        st.session_state.active_view = "calendar"
        st.rerun()

    # ── Table View (Matches InspectionTable.jsx) ──
    if st.session_state.active_view == "table":
        st.markdown("<div style='height:0.5rem;'></div>", unsafe_allow_html=True)
        th_l, th_r = st.columns([4, 1])
        th_l.markdown(f"### Inspection Notifications ({len(filtered)})")

        if filtered:
            table_rows = []
            for i in filtered:
                table_rows.append(
                    {
                        "PO #": i.get("po_number") or "-",
                        "Notification #": i.get("notification_number") or "-",
                        "Revision #": i.get("notification_revision") or "00",
                        "Receipt Date": i.get("notification_receipt_date") or "-",
                        "Supplier Name": i.get("supplier_name") or "-",
                        "Sub-Supplier Name": i.get("subsupplier_name") or "-",
                        "Country": i.get("country") or "-",
                        "Location": i.get("inspection_location") or "-",
                        "Date": i.get("start_date") or "-",
                        "Time": i.get("inspection_time") or "Full Day",
                        "PO Description": i.get("po_description") or "-",
                        "Vendor Contact": i.get("vendor_contact_name") or "-",
                        "Vendor Phone": i.get("vendor_contact_phone") or "-",
                        "Vendor Email": i.get("vendor_contact_email") or "-",
                        "TPI Agency": i.get("tpi_agency") or "-",
                        "Inspector Name": i.get("assigned_inspector_name") or "Unassigned",
                        "Inspector Phone": i.get("assigned_inspector_phone") or "-",
                        "Inspector Email": i.get("assigned_inspector_email") or "-",
                        "Status": (i.get("status") or "received").upper(),
                    }
                )
            df_table = pd.DataFrame(table_rows)
            th_r.download_button(
                "📊 Export to Excel (CSV)",
                data=df_table.to_csv(index=False).encode("utf-8"),
                file_name=f"inspections_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True,
            )
            st.dataframe(df_table, use_container_width=True, hide_index=True)

            # Row Action Bar (Edit, Reports & Findings, Attendance/GPS, Delete)
            st.markdown("##### Quick Row Actions")
            for i in filtered:
                rc1, rc2, rc3, rc4, rc5 = st.columns([3.5, 1, 1.2, 1.2, 0.8])
                rc1.markdown(
                    f"**{i.get('notification_number')}** — PO `{i.get('po_number')}` | "
                    f"{i.get('supplier_name')} ({i.get('country') or '-'}) &nbsp; "
                    f"<span class='status-pill status-{i.get('status', 'received')}'>{i.get('status', 'received').upper()}</span>",
                    unsafe_allow_html=True,
                )
                if rc2.button("✏️ Edit", key=f"row_ed_{i['id']}", use_container_width=True):
                    open_edit_inspection_modal(i)
                if rc3.button(
                    f"📑 Reports ({len(i.get('inspection_reports') or [])})",
                    key=f"row_rp_{i['id']}",
                    use_container_width=True,
                ):
                    open_reports_findings_modal(i, user)
                if rc4.button("📍 Check-In / GPS", key=f"row_at_{i['id']}", use_container_width=True):
                    open_attendance_modal(i, user)
                if rc5.button("🗑️", key=f"row_dl_{i['id']}", use_container_width=True):
                    db.delete_inspection(i["id"])
                    st.rerun()
        else:
            st.info("No inspection notifications found.")

    # ── Calendar View (Matches CalendarView.jsx) ──
    else:
        sched = [i for i in filtered if i.get("start_date")]
        if not sched:
            st.info("No scheduled inspection dates to display on the calendar.")
        else:
            cal_df = pd.DataFrame(
                [
                    {
                        "Notification": i.get("notification_number"),
                        "Supplier": i.get("supplier_name"),
                        "Start": i.get("start_date"),
                        "End": i.get("end_date") or i.get("start_date"),
                        "Status": (i.get("status") or "received").upper(),
                    }
                    for i in sched
                ]
            )
            chart = (
                alt.Chart(cal_df)
                .mark_bar(cornerRadius=6, height=24)
                .encode(
                    x=alt.X("Start:T", title="Date"),
                    x2="End:T",
                    y=alt.Y("Notification:N", title="Notification #"),
                    color="Status:N",
                    tooltip=["Notification", "Supplier", "Start", "End", "Status"],
                )
                .properties(height=300)
            )
            st.altair_chart(chart, use_container_width=True)

    # Bottom AI Chat Widget (Matches ChatWidget.jsx)
    if is_admin or is_qc or is_eng:
        with st.expander("💬 InspectFlow AI Chat Assistant", expanded=st.session_state.chat_open):
            for m in st.session_state.chat_messages:
                with st.chat_message(m["role"]):
                    st.markdown(m["content"])
            q_chat = st.chat_input("Ask InspectFlow AI about inspections, NCRs, suppliers, or inspectors...")
            if q_chat:
                st.session_state.chat_open = True
                st.session_state.chat_messages.append({"role": "user", "content": q_chat})
                reply = ai.chat_with_assistant(q_chat, inspections, inspectors, db.list_agencies())
                st.session_state.chat_messages.append({"role": "assistant", "content": reply})
                st.rerun()


# ── Other Pages Matching Original JSX Layouts ────────────────────────────────
def render_reports_page(user: Dict[str, Any]) -> None:
    inspections = db.list_inspections()
    st.markdown(
        """
        <div style="margin-bottom:1.5rem;">
            <h1 style="font-size:2.25rem;font-weight:700;color:#111827;margin:0 0 0.35rem 0;">Reports & Release</h1>
            <p style="color:#4b5563;margin:0;">View and manage all inspection reports and release notes</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    ir_rows, rn_rows = [], []
    for i in inspections:
        for r in i.get("inspection_reports") or []:
            ir_rows.append(
                {
                    "Report Name": r.get("name") or "-",
                    "Notification #": i.get("notification_number"),
                    "PO Number": i.get("po_number"),
                    "Supplier": i.get("supplier_name"),
                    "Findings": len(r.get("findings") or []),
                    "Approval": (r.get("approval_status") or "pending").upper(),
                    "Uploaded By": r.get("uploaded_by") or "-",
                    "Upload Date": str(r.get("uploaded_date") or "")[:16],
                    "URL": r.get("url") or "",
                }
            )
        for rn in i.get("release_notes") or []:
            rn_rows.append(
                {
                    "Report Name": rn.get("name") or "-",
                    "Notification Number": i.get("notification_number"),
                    "PO Number": i.get("po_number"),
                    "Supplier": i.get("supplier_name"),
                    "Uploaded By": rn.get("uploaded_by") or "-",
                    "Upload Date": str(rn.get("uploaded_date") or "")[:16],
                    "URL": rn.get("url") or "",
                }
            )
    c1, c2 = st.columns(2)
    with c1:
        render_stat_card("Inspection Reports", len(ir_rows), "Uploaded Flash, Interim & Final reports", "#4f46e5", "📄")
    with c2:
        render_stat_card("Release Notes", len(rn_rows), "Issued Inspection Release Certificates", "#16a34a", "📜")

    st.markdown("<div style='height:1rem;'></div>", unsafe_allow_html=True)
    t1, t2 = st.tabs([f"Inspection Reports ({len(ir_rows)})", f"Release Notes ({len(rn_rows)})"])
    with t1:
        if ir_rows:
            st.dataframe(
                pd.DataFrame(ir_rows),
                column_config={"URL": st.column_config.LinkColumn("Document", display_text="Open PDF")},
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No inspection reports uploaded yet.")
    with t2:
        if rn_rows:
            st.dataframe(
                pd.DataFrame(rn_rows),
                column_config={"URL": st.column_config.LinkColumn("Document", display_text="Open PDF")},
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No release notes uploaded yet.")


def render_inspectors_page() -> None:
    inspectors = db.list_inspectors()
    agencies = db.list_agencies()
    hl, hr = st.columns([4, 1])
    hl.markdown(
        """
        <div style="margin-bottom:1.5rem;">
            <h1 style="font-size:2.25rem;font-weight:700;color:#111827;margin:0 0 0.35rem 0;">Inspector Management</h1>
            <p style="color:#4b5563;margin:0;">Manage inspector profiles, qualifications, and certifications</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_stat_card("Total Inspectors", len(inspectors), "All registered", "#4f46e5", "👥")
    with c2:
        render_stat_card("Active", sum(1 for i in inspectors if i.get("status") == "active"), "Available", "#16a34a", "✅")
    with c3:
        render_stat_card("Inactive", sum(1 for i in inspectors if i.get("status") == "inactive"), "Not active", "#4b5563", "⏸️")
    with c4:
        render_stat_card("On Leave", sum(1 for i in inspectors if i.get("status") == "suspended"), "Unavailable", "#d97706", "🗓️")

    st.markdown("<div style='height:1rem;'></div>", unsafe_allow_html=True)
    with st.expander("➕ Add Inspector"):
        with st.form("new_insp_form"):
            f1, f2, f3 = st.columns(3)
            fn = f1.text_input("Full Name *")
            em = f2.text_input("Email *")
            ph = f3.text_input("Phone")
            f4, f5, f6 = st.columns(3)
            ag_map = {"-- None --": None, **{a["name"]: a["id"] for a in agencies}}
            ag = f4.selectbox("Company / Agency", list(ag_map.keys()))
            sp = f5.text_input("Specialization")
            ex = f6.number_input("Years of Experience", min_value=0, value=5)
            if st.form_submit_button("Save Inspector", type="primary") and fn and em:
                db.create_inspector(
                    {
                        "full_name": fn,
                        "email": em,
                        "phone": ph,
                        "tpi_agency_id": ag_map[ag],
                        "specialization": sp,
                        "experience_years": ex,
                        "status": "active",
                    }
                )
                st.rerun()

    grid = st.columns(3)
    for idx, ins in enumerate(inspectors):
        with grid[idx % 3]:
            st.markdown(
                f"""
                <div class="orig-white-card">
                    <h3 style="margin:0 0 0.25rem 0;color:#111827;">{ins['full_name']}</h3>
                    <p style="margin:0 0 0.5rem 0;color:#6b7280;font-size:0.875rem;">{ins['email']}</p>
                    <span class="status-pill status-completed">{ins.get('status', 'active').upper()}</span>
                    <hr style="margin:0.75rem 0;border-color:#f3f4f6;"/>
                    <p style="margin:0.2rem 0;font-size:0.875rem;"><strong>Agency:</strong> {ins.get('company') or '-'}</p>
                    <p style="margin:0.2rem 0;font-size:0.875rem;"><strong>Specialization:</strong> {ins.get('specialization') or '-'}</p>
                    <p style="margin:0.2rem 0;font-size:0.875rem;"><strong>Phone:</strong> {ins.get('phone') or '-'}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("🗑️ Delete", key=f"del_i_{ins['id']}", use_container_width=True):
                db.delete_inspector(ins["id"])
                st.rerun()


def render_agencies_page() -> None:
    agencies = db.list_agencies()
    st.markdown(
        """
        <div style="margin-bottom:1.5rem;">
            <h1 style="font-size:2.25rem;font-weight:700;color:#111827;margin:0 0 0.35rem 0;">TPI Agencies</h1>
            <p style="color:#4b5563;margin:0;">Manage Third Party Inspection agencies (Admin Only)</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.expander("➕ Add Agency"):
        with st.form("new_ag_form"):
            c1, c2 = st.columns(2)
            nm = c1.text_input("Agency Name *")
            st_v = c2.selectbox("Status", ["active", "inactive"])
            m1, m2, m3 = st.columns(3)
            mn = m1.text_input("Manager Name")
            me = m2.text_input("Manager Email")
            mp = m3.text_input("Manager Phone")
            ad = st.text_input("Address")
            if st.form_submit_button("Add Agency", type="primary") and nm:
                db.create_agency({"name": nm, "status": st_v, "manager_name": mn, "manager_email": me, "manager_phone": mp, "address": ad})
                st.rerun()

    grid = st.columns(3)
    for idx, a in enumerate(agencies):
        with grid[idx % 3]:
            st.markdown(
                f"""
                <div class="orig-white-card">
                    <h3 style="margin:0 0 0.35rem 0;color:#111827;">{a['name']}</h3>
                    <span class="status-pill status-completed">{a.get('status', 'active')}</span>
                    <div style="background:#eef2ff;border-radius:0.5rem;padding:0.75rem;margin-top:0.75rem;">
                        <div style="font-size:0.72rem;font-weight:700;color:#312e81;text-transform:uppercase;">Manager Details</div>
                        <div style="font-size:0.85rem;color:#374151;margin-top:0.25rem;"><strong>Name:</strong> {a.get('manager_name') or '-'}</div>
                        <div style="font-size:0.85rem;color:#374151;"><strong>Email:</strong> {a.get('manager_email') or '-'}</div>
                        <div style="font-size:0.85rem;color:#374151;"><strong>Phone:</strong> {a.get('manager_phone') or '-'}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("🗑️ Delete Agency", key=f"del_a_{a['id']}", use_container_width=True):
                db.delete_agency(a["id"])
                st.rerun()


def render_performance_page() -> None:
    perf = db.get_tpi_performance()
    st.markdown(
        """
        <div style="margin-bottom:1.5rem;">
            <h1 style="font-size:2.25rem;font-weight:700;color:#111827;margin:0 0 0.35rem 0;">TPI Performance Evaluation</h1>
            <p style="color:#4b5563;margin:0;">Monitor and evaluate Third-Party Inspection agency performance based on KPIs</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if not perf:
        st.info("No TPI Agencies found.")
        return
    p = perf[0]
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_stat_card("Overall Score", f"{p['avg_overall_score']}%", p["agency_name"], "#4f46e5", "🏆")
    with c2:
        render_stat_card("Quality Score", f"{p['avg_quality_score']}%", "Report quality", "#2563eb", "📋")
    with c3:
        render_stat_card("Timeliness", f"{p['avg_timeliness_score']}%", "SLA compliance", "#16a34a", "⏱️")
    with c4:
        render_stat_card("Communication", f"{p['avg_communication_score']}%", "Responsiveness", "#9333ea", "💬")
    st.markdown("<div style='height:1rem;'></div>", unsafe_allow_html=True)
    st.dataframe(pd.DataFrame(perf), use_container_width=True, hide_index=True)


def render_admin_page() -> None:
    users = db.list_users()
    projects = db.list_projects()
    st.markdown(
        """
        <div style="margin-bottom:1.5rem;">
            <h1 style="font-size:2.25rem;font-weight:700;color:#111827;margin:0 0 0.35rem 0;">User Management</h1>
            <p style="color:#4b5563;margin:0;">Assign roles and permissions to users in the system</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    t_u, t_p = st.tabs(["Users", "Projects"])
    with t_u:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Full Name": u["full_name"],
                        "Email": u["email"],
                        "Role": ROLE_LABELS.get(u.get("inspection_role"), "Unassigned"),
                        "Company": u.get("company_affiliation") or "-",
                        "Status": u.get("user_status", "active"),
                    }
                    for u in users
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
    with t_p:
        with st.form("adm_proj_form"):
            c1, c2, c3 = st.columns(3)
            pn = c1.text_input("Project Name *")
            pc = c2.text_input("Project Code *")
            pd_txt = c3.text_input("Description")
            if st.form_submit_button("Add Project", type="primary") and pn and pc:
                db.create_project({"name": pn, "code": pc, "description": pd_txt, "status": "active"})
                st.rerun()
        if projects:
            st.dataframe(pd.DataFrame(projects), use_container_width=True, hide_index=True)


def render_profile_page(user: Dict[str, Any]) -> None:
    st.markdown(
        f"""
        <div class="orig-white-card">
            <h2 style="margin:0;">👤 {user.get('full_name')}</h2>
            <p style="color:#6b7280;margin:0.25rem 0 0.5rem 0;">{user.get('email')}</p>
            <span class="orig-role-badge role-inspector">Inspector</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    cv = st.file_uploader("Upload CV / Resume (PDF)", type=["pdf"])
    cert = st.file_uploader("Upload Qualifications / Certificates", type=["pdf", "png", "jpg"])
    if st.button("Save Uploaded Documents", type="primary") and (cv or cert):
        st.success("Profile documents updated!")


# ── Main Layout Wrapper (Top Bar + Left Collapsible Notifications + Main Area) ─
def main() -> None:
    if st.query_params.get("ui") != "streamlit":
        st.markdown(
            """
            <style>
            .block-container {
                padding: 0 !important;
                margin: 0 !important;
                max-width: 100vw !important;
            }
            iframe {
                position: fixed !important;
                top: 0 !important;
                left: 0 !important;
                width: 100vw !important;
                height: 100vh !important;
                border: none !important;
                margin: 0 !important;
                padding: 0 !important;
                z-index: 999999 !important;
            }
            </style>
            <iframe src="http://localhost:5214" allow="geolocation; clipboard-write"></iframe>
            """,
            unsafe_allow_html=True,
        )
        return

    user = st.session_state.user
    if not user:
        st.markdown("<div style='height:3rem;'></div>", unsafe_allow_html=True)
        _, col, _ = st.columns([1, 1.2, 1])
        with col:
            st.markdown("<div class='orig-white-card'><h2>Sign In to InspectFlow</h2></div>", unsafe_allow_html=True)
            with st.form("login"):
                em = st.text_input("Email", value="admin@inspectflow.com")
                pw = st.text_input("Password", type="password", value="Admin@123")
                if st.form_submit_button("Sign In", type="primary", use_container_width=True):
                    u = db.authenticate_user(em, pw)
                    if u:
                        st.session_state.user = u
                        st.rerun()
                    else:
                        st.error("Invalid credentials")
        return

    render_top_navbar(user)

    # Left Collapsible Notifications Panel + Main Content Area (Matches Layout.jsx lines 244-254)
    inspections = db.list_inspections()
    active_count = sum(1 for i in inspections if i.get("status") != "finalized")

    if st.session_state.notifications_expanded:
        col_noti, col_main = st.columns([1.15, 4.85])
        with col_noti:
            nh1, nh2 = st.columns([3, 1])
            nh1.markdown(f"**🔔 Notifications ({active_count})**")
            if nh2.button("◀", key="collapse_noti", help="Collapse Notifications Panel"):
                st.session_state.notifications_expanded = False
                st.rerun()
            nq = st.text_input("Search PO...", key="noti_q", placeholder="Search by PO, supplier...", label_visibility="collapsed")
            for n in inspections:
                if nq and nq.lower() not in f"{n.get('po_number', '')} {n.get('supplier_name', '')}".lower():
                    continue
                st.markdown(
                    f"""
                    <div class="orig-noti-card">
                        <div style="display:flex;justify-content:space-between;align-items:center;">
                            <strong style="font-size:0.78rem;">PO: {n.get('po_number')}</strong>
                            <span class="status-pill status-{n.get('status', 'received')}">{n.get('status', 'received')}</span>
                        </div>
                        <div style="font-size:0.72rem;color:#6b7280;margin-top:0.2rem;">📄 {n.get('notification_number')}</div>
                        <div style="font-size:0.72rem;color:#374151;margin-top:0.25rem;display:flex;justify-content:space-between;">
                            <span>{str(n.get('supplier_name', ''))[:20]}</span>
                            <span style="color:#9ca3af;">{n.get('start_date') or ''}</span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
    else:
        col_noti, col_main = st.columns([0.28, 5.72])
        with col_noti:
            if st.button(f"🔔\n{active_count}", key="expand_noti", help="Expand Notifications Panel", use_container_width=True):
                st.session_state.notifications_expanded = True
                st.rerun()

    with col_main:
        page = st.session_state.current_page
        if page == "Dashboard":
            render_dashboard_page(user)
        elif page == "Expediting":
            render_expediting_module(user)
        elif page == "Reports":
            render_reports_page(user)
        elif page == "Inspectors":
            render_inspectors_page()
        elif page == "TPIAgencies":
            render_agencies_page()
        elif page == "TPIPerformance":
            render_performance_page()
        elif page == "UserManagement":
            render_admin_page()
        elif page == "Profile":
            render_profile_page(user)

    st.markdown(
        """
        <div class="orig-footer">
            © 2025 InspectFlow. Streamline your inspection notifications.
        </div>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
