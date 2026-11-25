"""
EPC Expediting Phases 4 & 5 Workflows Router:
  - Phase 4A: Client IAP Submission (PMT) & Approval Gate (Flow Chart Steps 6-7)
  - Phase 4B: KOM / Technical / PIM Meeting Minutes (MOM) & Dossier + Auto-RAIL (Step 8, Actions #11, #13, #17)
  - Phase 4C: Client Inspection Look-Ahead Schedule (14d/28d/60d) + .xlsx Export (Documents Sheet)
  - Phase 5A: Stores MRV Receipt, Stamped Delivery Notes & MNCR Return->Rectify->Close Loop (Step 18, Action #29)
  - Phase 5B: Commercial Closeout — LD Intimation/Settlement + Waiver Memo / LD Report (.docx) + Final Invoice (Steps 19-21, Actions #26-28)
  - Phase 5C: Governance Registers (TPIA/Freight Timesheets & Invoices, TPI CV/QM/Certs Approval, Supplier Pre-Qual, Client Letters & Lessons Learnt)
"""

import io
import time
import uuid
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Response

from backend_v2.core.security import (
    effective_role,
    get_current_user,
    is_admin_user,
    is_vendor_user,
    require_roles,
    user_can_access_po,
    vendor_owns_po,
)
from backend_v2.services.audit_service import record_audit_event
from python_app import database as inspectflow_db
from python_app.expediting_erp_workflows import _compute_closeout_status
from python_app.smartexpedit_server import (
    LOCK,
    _allowed_po_record,
    _get_accessible_pids_for_user,
    _get_sx_state,
    _parse_date_safe,
    _records,
    _save_records,
    _save_sx_state,
    _who,
    sx_db,
)

router = APIRouter()


def _require_po_access(po_num: str, current_user: Dict[str, Any], allow_vendor: bool = True):
    with LOCK, sx_db() as c:
        rec = next((r for r in _records(c) if str(r.get("po")) == po_num), None)
    if not rec:
        raise HTTPException(status_code=404, detail=f"PO {po_num} not found")
    if is_vendor_user(current_user):
        if not allow_vendor or not vendor_owns_po(current_user, rec):
            raise HTTPException(status_code=403, detail=f"Not authorized for PO {po_num}")
    elif not is_admin_user(current_user) and not user_can_access_po(current_user, rec):
        raise HTTPException(status_code=403, detail=f"Not authorized for PO {po_num}")
    return rec


def _advance_schedule_act(rec: Dict[str, Any], keyword: str, done_date: str) -> None:
    sch_rows = rec.setdefault("sch", {}).setdefault("rows", [])
    for sr in sch_rows:
        if keyword in str(sr.get("act") or "").lower():
            sr["fS"] = sr.get("fS") or done_date
            sr["fE"] = done_date
            sr["pct"] = "100"


# ---------------------------------------------------------------------------
# PHASE 4A: Client IAP Submission (PMT) & Approval Gate (Steps 6-7)
# ---------------------------------------------------------------------------

@router.get("/api/v1/po/{po}/iap")
def get_po_iap_status(
    po: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    po_num = str(po or "").strip()
    if effective_role(current_user) in ("", "guest"):
        raise HTTPException(status_code=403, detail="Active role required")
    rec = _require_po_access(po_num, current_user)
    proj = inspectflow_db.get_project(rec.get("project_id")) if rec.get("project_id") else None
    requires_iap = bool(rec.get("requires_client_iap") or (proj and proj.get("requires_client_iap")))
    iap_pkg = dict(rec.get("iap_package") or {
        "doc_no": f"IAP-{po_num}-001",
        "revision": "0",
        "client_status": "NOT_SUBMITTED",
        "submitted_at": "",
        "submitted_by": "",
        "approved_at": "",
        "approved_by": "",
        "dossier_ref": "",
        "comments": "",
    })
    return {
        "ok": True,
        "po": po_num,
        "requires_client_iap": requires_iap,
        "iap_package": iap_pkg,
        "iap_cleared": (not requires_iap) or iap_pkg.get("client_status") == "APPROVED",
    }


@router.post("/api/v1/po/{po}/iap")
def update_po_iap_workflow(
    po: str,
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(
        require_roles("admin", "expediting_manager", "expeditor", "qc_manager", "inspection_engineer", "doc_expeditor")
    ),
):
    po_num = str(po or "").strip()
    action = str(payload.get("action") or "submit").strip().lower()
    if action not in ("submit", "approve", "return", "toggle_required"):
        raise HTTPException(status_code=400, detail="action must be submit, approve, return, or toggle_required")
    eff = effective_role(current_user)
    if action in ("approve", "return") and eff not in ("admin", "qc_manager", "expediting_manager", "inspection_engineer"):
        raise HTTPException(status_code=403, detail="Only Admin, QC Manager, Expediting Manager, or Inspection Engineer may record Client IAP approval/return")

    with LOCK, sx_db() as c:
        L = _records(c)
        rec = next((r for r in L if str(r.get("po")) == po_num), None)
        if not rec:
            raise HTTPException(status_code=404, detail=f"PO {po_num} not found")
        if not is_admin_user(current_user) and not user_can_access_po(current_user, rec):
            raise HTTPException(status_code=403, detail=f"Access denied for PO {po_num}")

        if "requires_client_iap" in payload:
            rec["requires_client_iap"] = bool(payload["requires_client_iap"])

        iap_pkg = rec.setdefault("iap_package", {
            "doc_no": f"IAP-{po_num}-001",
            "revision": "0",
            "client_status": "NOT_SUBMITTED",
        })
        if payload.get("doc_no"):
            iap_pkg["doc_no"] = str(payload["doc_no"]).strip()
        if payload.get("revision"):
            iap_pkg["revision"] = str(payload["revision"]).strip()
        if payload.get("dossier_ref") is not None:
            iap_pkg["dossier_ref"] = str(payload["dossier_ref"]).strip()
        if payload.get("comments") is not None:
            iap_pkg["comments"] = str(payload["comments"]).strip()

        now_s = time.strftime("%Y-%m-%d %H:%M:%S")
        actor = current_user.get("email") or "PMT"
        if action == "submit":
            iap_pkg["client_status"] = "SUBMITTED_TO_CLIENT"
            iap_pkg["submitted_at"] = now_s
            iap_pkg["submitted_by"] = actor
        elif action == "approve":
            iap_pkg["client_status"] = "APPROVED"
            iap_pkg["approved_at"] = now_s
            iap_pkg["approved_by"] = actor
        elif action == "return":
            iap_pkg["client_status"] = "COMMENTS_RETURNED"

        _save_records(c, L, _who(None, current_user), f"IAP {action.upper()} ({iap_pkg['client_status']}) on {po_num}")

    record_audit_event("iap", po_num, f"IAP_{action.upper()}", actor=current_user, after={"status": iap_pkg["client_status"]})
    return {"ok": True, "po": po_num, "requires_client_iap": bool(rec.get("requires_client_iap")), "iap_package": iap_pkg}


# ---------------------------------------------------------------------------
# PHASE 4B: KOM / Technical Clarification / PIM Meeting MOMs & Dossier
# ---------------------------------------------------------------------------

@router.get("/api/v1/po/{po}/meetings")
def list_po_meetings(
    po: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    if effective_role(current_user) in ("", "guest"):
        raise HTTPException(status_code=403, detail="Active role required")
    rec = _require_po_access(str(po or "").strip(), current_user)
    return {
        "ok": True,
        "po": po,
        "meetings": list(rec.get("meetings") or []),
        "pim_done_on": (rec.get("mfg") or {}).get("pimOn") or "",
        "kickoff_on": rec.get("kickoffOn") or "",
    }


@router.post("/api/v1/po/{po}/meetings")
def record_po_meeting(
    po: str,
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(
        require_roles("admin", "expediting_manager", "expeditor", "field_expeditor", "doc_expeditor", "qc_manager", "inspection_engineer")
    ),
):
    po_num = str(po or "").strip()
    m_type = str(payload.get("meeting_type") or "KOM").strip().upper()
    if m_type not in ("KOM", "TECH_CLARIFICATION", "PIM"):
        raise HTTPException(status_code=400, detail="meeting_type must be KOM, TECH_CLARIFICATION, or PIM")
    m_date = str(payload.get("meeting_date") or time.strftime("%Y-%m-%d"))[:10]
    mode = str(payload.get("mode") or "TEAMS").strip()
    location = str(payload.get("location") or ("MS Teams" if mode.upper() == "TEAMS" else "Vendor Works")).strip()
    attendees = str(payload.get("attendees") or "").strip()
    mom_summary = str(payload.get("mom_summary") or "").strip()
    dossier_ref = str(payload.get("dossier_ref") or "").strip()
    action_items = [str(a).strip() for a in (payload.get("action_items") or []) if str(a).strip()]
    spawn_rail = bool(payload.get("spawn_rail", True))

    if not mom_summary:
        raise HTTPException(status_code=400, detail="mom_summary is required")

    meet_id = f"MOM-{m_type}-{uuid.uuid4().hex[:6].upper()}"
    actor = current_user.get("email") or "Expeditor"
    spawned_concerns = []

    with LOCK, sx_db() as c:
        L = _records(c)
        rec = next((r for r in L if str(r.get("po")) == po_num), None)
        if not rec:
            raise HTTPException(status_code=404, detail=f"PO {po_num} not found")
        if not is_admin_user(current_user) and not user_can_access_po(current_user, rec):
            raise HTTPException(status_code=403, detail=f"Access denied for PO {po_num}")

        entry = {
            "id": meet_id,
            "meeting_type": m_type,
            "meeting_date": m_date,
            "mode": mode,
            "location": location,
            "attendees": attendees,
            "mom_summary": mom_summary,
            "dossier_ref": dossier_ref,
            "action_items": action_items,
            "recorded_by": actor,
            "recorded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        rec.setdefault("meetings", []).append(entry)

        if m_type == "KOM":
            rec["kickoffOn"] = m_date
            _advance_schedule_act(rec, "kick off", m_date)
        elif m_type == "PIM":
            mfg = rec.setdefault("mfg", {})
            mfg["pimOn"] = m_date
            mfg["pimNotes"] = f"{mom_summary} (Dossier: {dossier_ref or 'N/A'})"
            _advance_schedule_act(rec, "pre-inspection", m_date)

        if spawn_rail and action_items:
            sx_state = _get_sx_state(c)
            concerns = sx_state.setdefault("concerns", [])
            for act_txt in action_items:
                cid = f"MOM-{uuid.uuid4().hex[:6].upper()}"
                concerns.insert(0, {
                    "id": cid,
                    "no": cid,
                    "po": po_num,
                    "issue": f"[{m_type} Action] {act_txt}",
                    "by": actor,
                    "assignedTo": "VENDOR",
                    "assignedVendor": rec.get("supplierShort") or rec.get("supplier") or "Vendor",
                    "source": f"{m_type} MOM ({meet_id})",
                    "target": (date.today() + timedelta(days=7)).isoformat(),
                    "impact": "MEDIUM",
                    "status": "OPEN",
                    "history": [{"on": time.strftime("%Y-%m-%d"), "by": actor, "act": f"Raised in {m_type}", "note": act_txt}],
                })
                spawned_concerns.append(cid)
            _save_sx_state(c, sx_state, actor)

        _save_records(c, L, actor, f"Recorded {m_type} MOM ({meet_id}) on PO {po_num}")

    record_audit_event("meeting_mom", meet_id, f"{m_type}_MOM_RECORDED", actor=current_user, after={"po": po_num, "rail_spawned": len(spawned_concerns)})
    return {"ok": True, "po": po_num, "meeting": entry, "spawned_rail_ids": spawned_concerns}


# ---------------------------------------------------------------------------
# PHASE 4D: Rolling Client Inspection Look-Ahead Schedule + .xlsx Export
# ---------------------------------------------------------------------------

def _build_look_ahead_rows(project_id: Optional[str], days: int, current_user: Dict[str, Any]) -> List[Dict[str, Any]]:
    accessible_pids = _get_accessible_pids_for_user(current_user)
    today = date.today()
    horizon = today + timedelta(days=max(7, min(days, 180)))

    with LOCK, sx_db() as c:
        L = _records(c)
    allowed_recs = {
        str(r.get("po")): r for r in L
        if _allowed_po_record(r, current_user, project_id=project_id, accessible_pids=accessible_pids)
    }

    rows: List[Dict[str, Any]] = []
    seen_keys = set()

    # 1. Live InspectFlow NOIs within look-ahead horizon (or upcoming)
    for insp in inspectflow_db.list_inspections():
        po = str(insp.get("po_number") or "")
        if po not in allowed_recs:
            continue
        st = str(insp.get("status") or "").lower()
        if st in ("cancelled", "finalized"):
            continue
        dt_str = (insp.get("start_date") or "")[:10]
        dt = _parse_date_safe(dt_str)
        if dt and dt <= horizon:
            rec = allowed_recs[po]
            rows.append({
                "date": dt_str,
                "po": po,
                "supplier": insp.get("supplier_name") or rec.get("supplierShort") or "",
                "platform": rec.get("platform") or "",
                "source": "Live NOI",
                "reference": insp.get("notification_number") or insp.get("id")[:8],
                "scope": insp.get("inspection_scope") or insp.get("inspection_type") or "Witness",
                "activity": insp.get("po_description") or "Inspection Callout",
                "location": insp.get("inspection_location") or "Vendor Works",
                "inspector_tpi": insp.get("assigned_inspector_name") or insp.get("tpi_agency") or "Pending Assignment",
                "status": insp.get("status") or "received",
            })
            seen_keys.add(f"{po}:{dt_str}:{insp.get('notification_number')}")

    # 2. Forecasted PIM / Stage / Sub-Order / FAT dates from PO 9-col Schedules
    for po, rec in allowed_recs.items():
        sch_rows = (rec.get("sch") or {}).get("rows") or []
        for sr in sch_rows:
            act = str(sr.get("act") or "")
            if not any(k in act.lower() for k in ("pre-inspection", "sub-orders", "inspection", "fat", "itp", "irn")):
                continue
            dt_str = str(sr.get("fS") or sr.get("fE") or sr.get("bS") or sr.get("bE") or "")[:10]
            dt = _parse_date_safe(dt_str)
            if not dt or dt > horizon:
                continue
            if str(sr.get("pct") or "") == "100":
                continue
            key = f"{po}:{dt_str}:{act}"
            if key in seen_keys:
                continue
            rows.append({
                "date": dt_str,
                "po": po,
                "supplier": rec.get("supplierShort") or rec.get("supplier") or "",
                "platform": rec.get("platform") or "",
                "source": "Schedule Forecast",
                "reference": f"Sr.{sr.get('sr') or ''}",
                "scope": "PIM" if "pre-inspection" in act.lower() else ("FAT" if "fat" in act.lower() else "Planned Event"),
                "activity": act,
                "location": rec.get("origin") or "Vendor Works",
                "inspector_tpi": rec.get("assigned_inspection_engineer_name") or "TBD",
                "status": "Forecasted",
            })

    rows.sort(key=lambda x: (x.get("date") or "9999-99-99", x.get("po") or ""))
    return rows


@router.get("/api/v1/expediting/look-ahead")
def get_client_inspection_look_ahead(
    project_id: Optional[str] = None,
    days: int = 28,
    current_user: Dict[str, Any] = Depends(
        require_roles("admin", "expediting_manager", "expeditor", "field_expeditor", "doc_expeditor", "qc_manager", "inspection_engineer", "inspection_agency")
    ),
):
    rows = _build_look_ahead_rows(project_id, days, current_user)
    return {
        "ok": True,
        "horizon_days": days,
        "count": len(rows),
        "events": rows,
    }


@router.get("/api/v1/expediting/look-ahead/export-xlsx")
def export_look_ahead_xlsx(
    project_id: Optional[str] = None,
    days: int = 28,
    current_user: Dict[str, Any] = Depends(
        require_roles("admin", "expediting_manager", "expeditor", "field_expeditor", "doc_expeditor", "qc_manager", "inspection_engineer", "inspection_agency")
    ),
):
    import openpyxl
    from openpyxl.styles import Font, PatternFill

    rows = _build_look_ahead_rows(project_id, days, current_user)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"LookAhead_{days}d"
    headers = ["Date", "PO #", "Supplier", "Platform", "Source", "Ref #", "Scope", "Activity / Description", "Location", "Inspector / TPI", "Status"]
    ws.append(headers)
    fill = PatternFill("solid", fgColor="0F766E")
    font = Font(color="FFFFFF", bold=True, size=10)
    for i in range(1, len(headers) + 1):
        c = ws.cell(row=1, column=i)
        c.fill = fill
        c.font = font
    for r in rows:
        ws.append([r[k] for k in ("date", "po", "supplier", "platform", "source", "reference", "scope", "activity", "location", "inspector_tpi", "status")])

    buf = io.BytesIO()
    wb.save(buf)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="Client_Inspection_LookAhead_{days}d.xlsx"'},
    )


# ---------------------------------------------------------------------------
# PHASE 5A: Stores MRV / Stamped Delivery Note & MNCR Return->Rectify->Close Loop
# ---------------------------------------------------------------------------

@router.get("/api/v1/po/{po}/mncr")
def list_po_mncrs(
    po: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    if effective_role(current_user) in ("", "guest"):
        raise HTTPException(status_code=403, detail="Active role required")
    rec = _require_po_access(str(po or "").strip(), current_user)
    return {
        "ok": True,
        "po": po,
        "mncrs": list((rec.get("sx") or {}).get("mncr") or []),
        "stamped_delivery_notes": list(rec.get("stamped_delivery_notes") or []),
    }


@router.post("/api/v1/po/{po}/mncr")
def create_stores_mncr(
    po: str,
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(
        require_roles("admin", "expediting_manager", "expeditor", "field_expeditor", "qc_manager", "inspection_engineer")
    ),
):
    po_num = str(po or "").strip()
    desc = str(payload.get("description") or "").strip()
    if not desc:
        raise HTTPException(status_code=400, detail="MNCR shortage/damage description is required")

    mncr_no = str(payload.get("mncr_no") or f"MNCR-{po_num}-{uuid.uuid4().hex[:5].upper()}")
    mrv_no = str(payload.get("mrv_no") or "").strip()
    item_no = str(payload.get("item_no") or "").strip()
    stamped_dn = str(payload.get("stamped_delivery_note_ref") or "").strip()
    category = str(payload.get("category") or "SHORTAGE_DAMAGE").strip()
    actor = current_user.get("email") or "Stores / Logistics"

    with LOCK, sx_db() as c:
        L = _records(c)
        rec = next((r for r in L if str(r.get("po")) == po_num), None)
        if not rec:
            raise HTTPException(status_code=404, detail=f"PO {po_num} not found")
        if not is_admin_user(current_user) and not user_can_access_po(current_user, rec):
            raise HTTPException(status_code=403, detail=f"Access denied for PO {po_num}")

        if stamped_dn:
            rec.setdefault("stamped_delivery_notes", []).append({
                "ref": stamped_dn,
                "mrv_no": mrv_no,
                "item_no": item_no,
                "recorded_by": actor,
                "recorded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            })

        mncr_entry = {
            "id": mncr_no,
            "mncr_no": mncr_no,
            "mrv_no": mrv_no,
            "item_no": item_no,
            "category": category,
            "description": desc,
            "stamped_delivery_note_ref": stamped_dn,
            "status": "RAISED_BY_STORES",
            "raised_by": actor,
            "raised_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "history": [{"on": time.strftime("%Y-%m-%d"), "by": actor, "act": "MNCR Raised by Stores", "note": desc}],
        }
        rec.setdefault("sx", {}).setdefault("mncr", []).append(mncr_entry)

        sx_state = _get_sx_state(c)
        sx_state.setdefault("concerns", []).insert(0, {
            "id": mncr_no,
            "no": mncr_no,
            "po": po_num,
            "issue": f"[MNCR {category}] {desc}",
            "by": actor,
            "assignedTo": "PMT",
            "assignedVendor": rec.get("supplierShort") or rec.get("supplier") or "Vendor",
            "source": f"Stores MRV ({mrv_no or 'Receipt'})",
            "target": (date.today() + timedelta(days=7)).isoformat(),
            "impact": "CRITICAL",
            "status": "OPEN",
            "history": [{"on": time.strftime("%Y-%m-%d"), "by": actor, "act": "MNCR Opened", "note": desc}],
        })
        _save_sx_state(c, sx_state, actor)
        _save_records(c, L, actor, f"Stores raised {mncr_no} on PO {po_num}")

    record_audit_event("mncr", mncr_no, "MNCR_RAISED", actor=current_user, after={"po": po_num, "category": category})
    return {"ok": True, "po": po_num, "mncr": mncr_entry}


def _update_mncr_state(po_num: str, mncr_id: str, new_status: str, note: str, actor: str, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    with LOCK, sx_db() as c:
        L = _records(c)
        rec = next((r for r in L if str(r.get("po")) == po_num), None)
        if not rec:
            raise HTTPException(status_code=404, detail=f"PO {po_num} not found")
        mncrs = (rec.get("sx") or {}).get("mncr") or []
        m = next((x for x in mncrs if str(x.get("id")) == mncr_id or str(x.get("mncr_no")) == mncr_id), None)
        if not m:
            raise HTTPException(status_code=404, detail=f"MNCR '{mncr_id}' not found on PO {po_num}")
        m["status"] = new_status
        if extra:
            m.update(extra)
        m.setdefault("history", []).append({"on": time.strftime("%Y-%m-%d"), "by": actor, "act": new_status, "note": note})

        sx_state = _get_sx_state(c)
        for cn in sx_state.get("concerns", []):
            if str(cn.get("id")) == mncr_id or str(cn.get("no")) == mncr_id:
                cn["status"] = "CLOSED" if new_status == "CLOSED" else "OPEN"
                cn["assignedTo"] = "VENDOR" if new_status == "RETURNED_TO_VENDOR" else "PMT"
                cn.setdefault("history", []).append({"on": time.strftime("%Y-%m-%d"), "by": actor, "act": new_status, "note": note})
        _save_sx_state(c, sx_state, actor)
        _save_records(c, L, actor, f"MNCR {mncr_id} -> {new_status} on PO {po_num}")
        return m


@router.post("/api/v1/po/{po}/mncr/{mncr_id}/return-to-vendor")
def pmt_return_mncr_to_vendor(
    po: str,
    mncr_id: str,
    payload: Dict[str, Any] = Body({}),
    current_user: Dict[str, Any] = Depends(require_roles("admin", "expediting_manager", "expeditor", "qc_manager", "inspection_engineer")),
):
    _require_po_access(po, current_user, allow_vendor=False)
    note = str(payload.get("instructions") or "Returned defective/short item to Vendor for rectification/replacement.")
    m = _update_mncr_state(
        po, mncr_id, "RETURNED_TO_VENDOR", note, current_user.get("email") or "PMT", extra={"pmt_return_notes": note}
    )
    return {"ok": True, "mncr": m}


@router.post("/api/v1/po/{po}/mncr/{mncr_id}/vendor-rectify")
def vendor_rectify_mncr(
    po: str,
    mncr_id: str,
    payload: Dict[str, Any] = Body({}),
    current_user: Dict[str, Any] = Depends(require_roles("admin", "vendor", "expediting_manager", "expeditor")),
):
    _require_po_access(po, current_user, allow_vendor=True)
    note = str(payload.get("rectification_details") or payload.get("rectification_notes") or payload.get("note") or "").strip()
    if not note:
        raise HTTPException(status_code=400, detail="rectification_details is required")
    m = _update_mncr_state(
        po,
        mncr_id,
        "VENDOR_RECTIFIED_PENDING_PMT",
        note,
        current_user.get("email") or "Vendor",
        extra={
            "replacement_awb_ref": str(payload.get("replacement_awb_ref") or ""),
            "vendor_rectification_notes": note,
        },
    )
    return {"ok": True, "mncr": m}


@router.post("/api/v1/po/{po}/mncr/{mncr_id}/close")
def close_mncr_by_pmt(
    po: str,
    mncr_id: str,
    payload: Dict[str, Any] = Body({}),
    current_user: Dict[str, Any] = Depends(require_roles("admin", "expediting_manager", "expeditor", "qc_manager")),
):
    _require_po_access(po, current_user, allow_vendor=False)
    note = str(payload.get("closure_remarks") or "Verified rectified receipt / Stores accepted.")
    m = _update_mncr_state(po, mncr_id, "CLOSED", note, current_user.get("email") or "PMT", extra={"closed_at": time.strftime("%Y-%m-%d %H:%M:%S")})
    return {"ok": True, "mncr": m}


# ---------------------------------------------------------------------------
# PHASE 5B: Commercial Closeout — LD Waiver Memo / Full LD Report + Final Invoice
# ---------------------------------------------------------------------------

def _calc_ld_details(rec: Dict[str, Any]) -> Dict[str, Any]:
    ld = dict(rec.get("ld") or {})
    lots = rec.get("lots") or []
    today = date.today()
    max_late = 0
    for lot in lots:
        dt = _parse_date_safe(lot.get("date"))
        if dt and dt < today and str(rec.get("stage") or "") not in ("delivered", "closed"):
            max_late = max(max_late, (today - dt).days)
    rate = float(ld.get("rate") or 0)
    cap_pct = float(ld.get("cap") or 10)
    po_val = float(rec.get("value") or 0)
    gross_ld = rate * max_late
    cap_amt = (po_val * cap_pct / 100.0) if (po_val > 0 and cap_pct > 0) else gross_ld
    computed_ld = min(gross_ld, cap_amt) if cap_amt > 0 else gross_ld
    return {
        "rate_per_day": rate,
        "cap_pct": cap_pct,
        "late_days": max_late,
        "po_value": po_val,
        "ccy": rec.get("ccy") or "USD",
        "computed_ld_amount": round(computed_ld, 2),
        "mode": ld.get("mode") or "PENDING",  # FULL_LD | PARTIAL_WAIVER | FULL_WAIVER | NOT_APPLICABLE
        "settled_amount": float(ld.get("settled_amount") if ld.get("settled_amount") not in (None, "") else computed_ld),
        "waiver_justification": ld.get("waiver_justification") or "",
        "intimated_on": (ld.get("steps") or {}).get("Intimated to vendor") or "",
        "settled_on": (ld.get("steps") or {}).get("Settled with supplier") or "",
        "memo_issued_on": (ld.get("steps") or {}).get("LD memo or report issued") or "",
        "final_invoice_no": (rec.get("close") or {}).get("finalInvoiceNo") or "",
        "final_invoice_paid_on": (rec.get("close") or {}).get("finalInvoicePaidOn") or "",
    }


@router.get("/api/v1/po/{po}/closeout/ld")
def get_po_ld_and_closeout(
    po: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    if effective_role(current_user) in ("", "guest"):
        raise HTTPException(status_code=403, detail="Active role required")
    rec = _require_po_access(str(po or "").strip(), current_user)
    return {
        "ok": True,
        "po": po,
        "ld": _calc_ld_details(rec),
        "closeout": _compute_closeout_status(rec),
    }


@router.post("/api/v1/po/{po}/closeout/ld")
def update_po_ld_and_commercial_closeout(
    po: str,
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(require_roles("admin", "expediting_manager", "expeditor")),
):
    po_num = str(po or "").strip()
    mode = str(payload.get("mode") or "PENDING").strip().upper()
    if mode not in ("PENDING", "FULL_LD", "PARTIAL_WAIVER", "FULL_WAIVER", "NOT_APPLICABLE"):
        raise HTTPException(status_code=400, detail="Invalid LD settlement mode")
    if mode in ("PARTIAL_WAIVER", "FULL_WAIVER") and not str(payload.get("waiver_justification") or "").strip():
        raise HTTPException(status_code=400, detail="Justification required for LD Waiver Memo")

    actor = current_user.get("email") or "Expeditor"
    now_d = time.strftime("%Y-%m-%d")

    with LOCK, sx_db() as c:
        L = _records(c)
        rec = next((r for r in L if str(r.get("po")) == po_num), None)
        if not rec:
            raise HTTPException(status_code=404, detail=f"PO {po_num} not found")
        if not is_admin_user(current_user) and not user_can_access_po(current_user, rec):
            raise HTTPException(status_code=403, detail=f"Access denied for PO {po_num}")

        ld = rec.setdefault("ld", {})
        if payload.get("rate_per_day") is not None:
            ld["rate"] = float(payload["rate_per_day"] or 0)
        if payload.get("cap_pct") is not None:
            ld["cap"] = float(payload["cap_pct"] or 10)
        ld["mode"] = mode
        if payload.get("settled_amount") is not None:
            ld["settled_amount"] = float(payload["settled_amount"] or 0)
        if payload.get("waiver_justification") is not None:
            ld["waiver_justification"] = str(payload["waiver_justification"])

        steps = ld.setdefault("steps", {})
        if payload.get("mark_intimated"):
            steps["Intimated to vendor"] = now_d
        if payload.get("mark_settled") or mode in ("FULL_LD", "PARTIAL_WAIVER", "FULL_WAIVER", "NOT_APPLICABLE"):
            if mode != "PENDING":
                steps["Settled with supplier"] = steps.get("Settled with supplier") or now_d
                ld["waived"] = mode in ("FULL_WAIVER", "PARTIAL_WAIVER")
                ld["not_applicable"] = mode == "NOT_APPLICABLE"
        if payload.get("issue_memo"):
            steps["LD memo or report issued"] = now_d

        close = rec.setdefault("close", {})
        if payload.get("final_invoice_no") is not None:
            close["finalInvoiceNo"] = str(payload["final_invoice_no"])
        if payload.get("final_invoice_paid_on") is not None:
            close["finalInvoicePaidOn"] = str(payload["final_invoice_paid_on"])[:10]

        cs = _compute_closeout_status(rec)
        rec["close_state"] = cs
        _save_records(c, L, actor, f"Updated LD ({mode}) & Commercial Closeout ({cs['stage_label']}) on {po_num}")

    record_audit_event("commercial_closeout", po_num, "LD_CLOSEOUT_UPDATED", actor=current_user, after={"mode": mode, "stage": cs["stage_label"]})
    return {"ok": True, "po": po_num, "ld": _calc_ld_details(rec), "closeout": cs}


@router.get("/api/v1/po/{po}/closeout/ld-memo-docx")
def export_ld_memo_or_report_docx(
    po: str,
    current_user: Dict[str, Any] = Depends(require_roles("admin", "expediting_manager", "expeditor")),
):
    from docx import Document

    rec = _require_po_access(str(po or "").strip(), current_user, allow_vendor=False)
    det = _calc_ld_details(rec)
    cs = _compute_closeout_status(rec)
    title = (
        f"LIQUIDATED DAMAGES WAIVER MEMO — PO {po}"
        if det["mode"] in ("PARTIAL_WAIVER", "FULL_WAIVER")
        else f"LIQUIDATED DAMAGES APPLICABILITY REPORT — PO {po}"
    )
    doc = Document()
    doc.add_heading(title, level=1)
    doc.add_paragraph(
        f"Project: [{rec.get('project_code') or ''}] {rec.get('project') or ''}\n"
        f"Purchase Order No.: {po} | Supplier: {rec.get('supplier') or ''}\n"
        f"Contractual Delivery Date (CDD): {rec.get('cdd_date') or 'N/A'} | PO Value: {det['ccy']} {det['po_value']:,.2f}\n"
        f"Settlement Classification: {det['mode']}"
    )
    doc.add_heading("1. LD Assessment Summary", level=2)
    doc.add_paragraph(
        f"• Measured Delay Beyond Contractual Grace/Date: {det['late_days']} day(s)\n"
        f"• Daily LD Rate: {det['ccy']} {det['rate_per_day']:,.2f}/day (Cap: {det['cap_pct']}%)\n"
        f"• Computed Contractual LD: {det['ccy']} {det['computed_ld_amount']:,.2f}\n"
        f"• Final Agreed Settlement / Deduction Amount: {det['ccy']} {det['settled_amount']:,.2f}\n"
        f"• Waiver / Commercial Justification: {det['waiver_justification'] or 'Standard contractual application.'}"
    )
    doc.add_heading("2. Commercial & Technical Closeout Verification", level=2)
    doc.add_paragraph(
        f"• Site Material Receipt (MRV %): {cs['mrv_pct']}%\n"
        f"• Databook / MRB Custodian Approval: {cs['mrb_approved_on'] or 'Pending'}\n"
        f"• Final Invoice Reference: {det['final_invoice_no'] or 'Pending'} | Paid On: {det['final_invoice_paid_on'] or 'Pending'}\n"
        f"• Overall Order Status: {cs['stage_label']}"
    )

    buf = io.BytesIO()
    doc.save(buf)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{po}_LD_{det["mode"]}.docx"'},
    )


# ---------------------------------------------------------------------------
# PHASE 5C: Governance Registers (TPIA Billing/Timesheets, TPI Creds, Pre-Qual, Lessons/Letters)
# ---------------------------------------------------------------------------

_REGISTER_KEYS = {
    "tpia-billing": "tpia_billing",
    "tpi-credentials": "tpi_credentials",
    "prequalification": "supplier_prequalification",
    "lessons-letters": "lessons_and_letters",
}


@router.get("/api/v1/governance/registers/{reg_type}")
def list_governance_register(
    reg_type: str,
    project_id: Optional[str] = None,
    po: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(
        require_roles("admin", "expediting_manager", "expeditor", "qc_manager", "inspection_engineer", "inspection_agency", "doc_expeditor")
    ),
):
    key = _REGISTER_KEYS.get(reg_type)
    if not key:
        raise HTTPException(status_code=404, detail="Unknown governance register type")
    accessible_pids = _get_accessible_pids_for_user(current_user)
    with LOCK, sx_db() as c:
        sx_state = _get_sx_state(c)
        rows = list((sx_state.get("erp_registers") or {}).get(key) or [])
    if project_id and project_id != "all":
        rows = [r for r in rows if not r.get("project_id") or str(r.get("project_id")).lower() == str(project_id).lower()]
    if accessible_pids is not None:
        rows = [r for r in rows if not r.get("project_id") or str(r.get("project_id")).lower() in accessible_pids]
    if po:
        rows = [r for r in rows if str(r.get("po") or "") == po]
    return {"ok": True, "register": reg_type, "count": len(rows), "items": rows}


@router.post("/api/v1/governance/registers/{reg_type}")
def add_governance_register_entry(
    reg_type: str,
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(
        require_roles("admin", "expediting_manager", "expeditor", "qc_manager", "inspection_engineer", "inspection_agency", "doc_expeditor")
    ),
):
    key = _REGISTER_KEYS.get(reg_type)
    if not key:
        raise HTTPException(status_code=404, detail="Unknown governance register type")
    title = str(payload.get("title") or payload.get("subject") or payload.get("inspector_name") or payload.get("supplier") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title / name / subject is required")

    item_id = f"REG-{uuid.uuid4().hex[:8].upper()}"
    actor = current_user.get("email") or "User"
    entry = {
        **payload,
        "id": item_id,
        "title": title,
        "status": str(payload.get("status") or ("PENDING_APPROVAL" if reg_type in ("tpia-billing", "tpi-credentials") else "RECORDED")),
        "created_by": actor,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with LOCK, sx_db() as c:
        sx_state = _get_sx_state(c)
        regs = sx_state.setdefault("erp_registers", {})
        regs.setdefault(key, []).insert(0, entry)
        _save_sx_state(c, sx_state, actor)
    record_audit_event("governance_register", item_id, f"REGISTER_{reg_type.upper()}_ADDED", actor=current_user, after={"title": title})
    return {"ok": True, "item": entry}


@router.post("/api/v1/governance/registers/{reg_type}/{item_id}/decision")
def decide_governance_register_entry(
    reg_type: str,
    item_id: str,
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(require_roles("admin", "expediting_manager", "qc_manager", "inspection_engineer")),
):
    key = _REGISTER_KEYS.get(reg_type)
    if not key:
        raise HTTPException(status_code=404, detail="Unknown governance register type")
    decision = str(payload.get("decision") or "").strip().upper()
    if decision not in ("APPROVED", "REJECTED", "CLOSED"):
        raise HTTPException(status_code=400, detail="decision must be APPROVED, REJECTED, or CLOSED")
    actor = current_user.get("email") or "Manager"
    with LOCK, sx_db() as c:
        sx_state = _get_sx_state(c)
        rows = (sx_state.get("erp_registers") or {}).get(key) or []
        target = next((r for r in rows if str(r.get("id")) == item_id), None)
        if not target:
            raise HTTPException(status_code=404, detail="Register entry not found")
        target["status"] = decision
        target["decided_by"] = actor
        target["decided_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        target["decision_comments"] = str(payload.get("comments") or "")
        _save_sx_state(c, sx_state, actor)
    return {"ok": True, "item": target}
