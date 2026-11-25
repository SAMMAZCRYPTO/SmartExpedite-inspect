"""
Modular EPC Expediting ERP Workflows (Option B: Phases 1, 2 & 3):
  - Phase 1: 9-Column Minimum Schedule Requirements (23 rows + server baseline freeze + ITP W/H + sub-order expansion + .xlsx export)
  - Phase 2A: Unified Vendor Portal endpoints (PO Acknowledgement, Sub-Orders & Unpriced POs, 7-Section NMDC Progress Report + .docx/.pdf export, MRB/SPIR Two-Stage Closeout)
  - Phase 2B: Project-Wide Consolidated Weekly MSSR & Critical Management Log (.json + 4-sheet .xlsx)
  - Phase 3: AI Agents for PO/MR Review (Workflow Action #2) & First Expediting Contact (Workflow Action #3)
"""

import io
import json
import re
import time
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool

from backend_v2.core.config import settings
from backend_v2.core.database import SessionLocal
from backend_v2.core.security import (
    effective_role,
    get_current_user,
    is_admin_user,
    is_vendor_user,
    require_roles,
    user_can_access_po,
    vendor_owns_po,
)
from backend_v2.models.epc_models import ItpBaselineStep, ItpDocument
from backend_v2.services.audit_service import record_audit_event
from python_app import ai_service
from python_app import database as inspectflow_db
from python_app.smartexpedit_server import (
    LOCK,
    _allowed_po_record,
    _ensure_vdrl_docs,
    _get_accessible_pids_for_user,
    _get_sx_state,
    _infer_procurement_class,
    _normalize_suborder_row,
    _parse_date_safe,
    _records,
    _save_records,
    _save_sx_state,
    _who,
    sx_db,
)

router = APIRouter()

MINIMUM_SCHEDULE_23_ACTIVITIES: List[str] = [
    "PO date",
    "PO acknowledgement",
    "Drg, Datasheet, ITP, SVL, Schedule submission",
    "Kick off meeting",
    "Drg, Datasheet, ITP, SVL approval",
    "Pre-inspection meeting",
    "Sub-orders placement",
    "Sub-orders manufacturing",
    "Sub-orders delivery",
    "Start Fabrication",
    "End Fabrication",
    "Assembly",
    "Internal Testing",
    "Inspection notification",
    "FAT / Inspection",
    "Punch point closure",
    "IRN issuance",
    "Exw readiness",
    "FOB Port of dispatch (for FOB orders)",
    "CFR Port of arrival (for CFR orders)",
    "Delivered at destination (for DDP/DDU/DAP)",
    "SPIR submission (if applicable)",
    "MRB submission",
]

SCHEDULE_RULES_NOTES: List[str] = [
    "1. The above rows and columns must be incorporated in any schedule, as a minimum.",
    "2. The Duration, Baseline start and end dates are the dates considered to meet the contractual date, and shall not change throughout the execution of the order.",
    "3. The sub-orders' related activities shall be expanded separately for each critical sub-order.",
    "4. All Witness and HOLD points of the ITP must be included as these activities impact the schedule.",
    "5. Schedule in excel format is acceptable.",
]

NMDC_13_ENGINEERING_DOC_CATS: List[str] = [
    "General",
    "Foundation",
    "GA Drawing",
    "P&ID",
    "Data Sheets",
    "Process Control",
    "Performance Curves",
    "Quality",
    "Utilities List",
    "Calculations",
    "Test Reports",
    "Parts List",
    "Others as per SDR List",
]


def _days_between(start_str: Any, end_str: Any) -> Optional[int]:
    d1 = _parse_date_safe(start_str)
    d2 = _parse_date_safe(end_str)
    if d1 and d2:
        return max(0, (d2 - d1).days)
    return None


def _build_synchronized_9col_schedule(rec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merges PO minimum 23 activities + ITP Witness/Hold steps (Note 4) + Critical Sub-Orders (Note 3)
    into the 9-column standard schedule shape.
    """
    po_num = str(rec.get("po") or "")
    sch = rec.setdefault("sch", {})
    existing_rows = list(sch.get("rows") or [])
    by_act = {str(r.get("act") or "").strip().lower(): dict(r) for r in existing_rows if isinstance(r, dict)}
    by_id = {str(r.get("id") or ""): dict(r) for r in existing_rows if isinstance(r, dict) and r.get("id")}

    incoterm = str(rec.get("incoterm") or "").upper()
    lots = [l for l in (rec.get("lots") or []) if isinstance(l, dict) and l.get("date")]
    cdd = str(rec.get("cdd_date") or (lots[-1]["date"] if lots else "") or "")[:10]
    issued_on = str(rec.get("issuedOn") or time.strftime("%Y-%m-%d"))[:10]

    out_rows: List[Dict[str, Any]] = []
    seen_ids = set()
    seen_acts = set()

    def _norm_row(raw: Dict[str, Any], default_act: str, source_kind: str, ref_id: str = "") -> Dict[str, Any]:
        rid = str(raw.get("id") or ref_id or f"row-{len(out_rows)+1}")
        bS = str(raw.get("bS") or "")[:10]
        bE = str(raw.get("bE") or "")[:10]
        fS = str(raw.get("fS") or "")[:10]
        fE = str(raw.get("fE") or "")[:10]
        dur = raw.get("duration_days")
        if dur in (None, ""):
            dur = raw.get("dur")
        if dur in (None, "") and bS and bE:
            dcalc = _days_between(bS, bE)
            dur = dcalc if dcalc is not None else ""
        return {
            "id": rid,
            "act": str(raw.get("act") or default_act).strip(),
            "duration_days": "" if dur in (None, "") else str(dur),
            "bS": bS,
            "bE": bE,
            "fS": fS,
            "fE": fE,
            "dependency": str(raw.get("dependency") or raw.get("dep") or ""),
            "pct": "" if raw.get("pct") in (None, "") else str(raw.get("pct")).replace("%", ""),
            "na": bool(raw.get("na")),
            "remarks": str(raw.get("remarks") or ""),
            "source_kind": str(raw.get("source_kind") or source_kind),
            "ref_id": str(raw.get("ref_id") or ref_id),
        }

    # 1. All 23 Minimum Activities (Note 1)
    for idx, act_name in enumerate(MINIMUM_SCHEDULE_23_ACTIVITIES, 1):
        # Match flexibly (e.g. 'Drg,Datasheet' vs 'Drg, Datasheet')
        norm_key = re.sub(r"[^a-z0-9]+", " ", act_name.lower()).strip()
        matched = by_act.get(act_name.lower())
        if not matched:
            for k_act, r_val in by_act.items():
                if re.sub(r"[^a-z0-9]+", " ", k_act).strip() == norm_key:
                    matched = r_val
                    break
        raw = dict(matched or {})
        if idx == 1 and not raw.get("bS"):
            raw.setdefault("bS", issued_on)
            raw.setdefault("bE", issued_on)
            raw.setdefault("fS", issued_on)
            raw.setdefault("fE", issued_on)
            raw.setdefault("pct", "100")
            raw.setdefault("duration_days", "0")
        if act_name.startswith("Delivered at destination") and cdd and not raw.get("bE") and any(t in incoterm for t in ("DDP", "DDU", "DAP", "DPU")):
            raw["bE"] = cdd
        if act_name.startswith("Exw readiness") and cdd and not raw.get("bE") and any(t in incoterm for t in ("EXW", "FCA")):
            raw["bE"] = cdd
        if act_name.startswith("FOB Port") and cdd and not raw.get("bE") and "FOB" in incoterm:
            raw["bE"] = cdd
        if act_name.startswith("CFR Port") and cdd and not raw.get("bE") and any(t in incoterm for t in ("CFR", "CIF")):
            raw["bE"] = cdd
        row_obj = _norm_row(raw, act_name, "minimum", f"min-{idx}")
        out_rows.append(row_obj)
        seen_ids.add(row_obj["id"])
        seen_acts.add(re.sub(r"[^a-z0-9]+", " ", row_obj["act"].lower()).strip())

    # 2. Expand Critical Sub-Orders (Note 3)
    sub_rows = [_normalize_suborder_row(r) for r in ((rec.get("plan") or {}).get("rows") or []) if isinstance(r, dict) and not r.get("deleted")]
    for sr in sub_rows:
        is_crit = bool(sr.get("critical"))
        req_dt = _parse_date_safe(sr.get("req_delivery"))
        fc_dt = _parse_date_safe(sr.get("forecast_delivery"))
        has_neg_float = bool(req_dt and fc_dt and fc_dt > req_dt)
        if not (is_crit or has_neg_float or sr.get("sub_po_no")):
            continue
        ref = f"sub-{sr.get('id') or sr.get('sub_po_no') or sr.get('material')}"
        label = f"[Sub-Order] {sr.get('vendor') or 'Sub-Vendor'} — {sr.get('material') or sr.get('sub_po_no') or 'Critical Sub-Order'}"
        existing_sub = by_id.get(ref) or next((r for r in existing_rows if r.get("ref_id") == ref), None) or {}
        if not existing_sub.get("bE") and sr.get("req_delivery"):
            existing_sub["bE"] = str(sr["req_delivery"])[:10]
        if not existing_sub.get("fE") and sr.get("forecast_delivery"):
            existing_sub["fE"] = str(sr["forecast_delivery"])[:10]
        if not existing_sub.get("bS") and sr.get("order_date"):
            existing_sub["bS"] = str(sr["order_date"])[:10]
        row_obj = _norm_row(existing_sub, label, "suborder", ref)
        if row_obj["id"] not in seen_ids:
            out_rows.append(row_obj)
            seen_ids.add(row_obj["id"])
            seen_acts.add(re.sub(r"[^a-z0-9]+", " ", row_obj["act"].lower()).strip())

    # 3. Expand ITP Witness (W) & Hold (H) Steps (Note 4)
    try:
        with SessionLocal() as sdb:
            itp_docs = sdb.query(ItpDocument).filter(ItpDocument.po_number == po_num).all()
            doc_ids = [d.id for d in itp_docs]
            if doc_ids:
                itp_steps = sdb.query(ItpBaselineStep).filter(ItpBaselineStep.itp_document_id.in_(doc_ids)).all()
                for st in itp_steps:
                    pts = [str(x or "-").upper() for x in (st.vendor_point, st.subvendor_point, st.contractor_tpi_point, st.company_tpa_point)]
                    has_wh = st.is_hold_point or any(p in ("W", "H", "W/H", "HOLD", "WITNESS") for p in pts)
                    if not has_wh:
                        continue
                    ref = f"itp-{st.id}"
                    tag = "H" if (st.is_hold_point or "H" in pts) else "W"
                    label = f"[ITP {tag} Step {st.step_no}] {st.activity_description}"
                    existing_itp = by_id.get(ref) or next((r for r in existing_rows if r.get("ref_id") == ref), None) or {}
                    if st.execution_status == "VERIFIED_PASS" and not existing_itp.get("pct"):
                        existing_itp["pct"] = "100"
                    existing_itp.setdefault("remarks", f"ITP Status: {st.execution_status}")
                    row_obj = _norm_row(existing_itp, label, "itp_witness_hold", ref)
                    if row_obj["id"] not in seen_ids:
                        out_rows.append(row_obj)
                        seen_ids.add(row_obj["id"])
                        seen_acts.add(re.sub(r"[^a-z0-9]+", " ", row_obj["act"].lower()).strip())
    except Exception:
        pass

    # 4. Keep any custom uploaded rows (e.g. from Gemini/OCR imports)
    for r in existing_rows:
        if not isinstance(r, dict):
            continue
        rid = str(r.get("id") or "")
        act_norm = re.sub(r"[^a-z0-9]+", " ", str(r.get("act") or "").lower()).strip()
        if rid in seen_ids or (act_norm and act_norm in seen_acts) or not act_norm:
            continue
        out_rows.append(_norm_row(r, r.get("act") or "Custom Milestone", str(r.get("source_kind") or "custom"), rid))

    for sr_num, r in enumerate(out_rows, 1):
        r["sr"] = sr_num

    return {
        "rows": out_rows,
        "frozen": bool(sch.get("frozen")),
        "frozen_at": sch.get("frozen_at") or "",
        "frozen_by": sch.get("frozen_by") or "",
        "rebase": list(sch.get("rebase") or []),
    }


def _compute_closeout_status(rec: Dict[str, Any]) -> Dict[str, Any]:
    close = dict(rec.get("close") or {})
    ld = dict(rec.get("ld") or {})
    clr = rec.get("clr") or {}
    items = [it for it in (rec.get("items") or []) if not it.get("is_split_parent")]
    tot_ord = sum(float(it.get("qty") or 0) for it in items)
    tot_mrv = sum(float((clr.get(str(it.get("item") or "")) or {}).get("mrv") or 0) for it in items)
    mrv_complete = tot_ord > 0 and tot_mrv >= tot_ord
    mrb_approved = bool(close.get("mrbApprOn"))
    technically_closed = bool(mrv_complete and mrb_approved)
    ld_steps = ld.get("steps") or {}
    ld_settled = bool(ld_steps.get("Settled with supplier") or ld_steps.get("LD memo or report issued") or ld.get("waived") or ld.get("not_applicable"))
    final_invoice_paid = bool(close.get("finalInvoicePaidOn"))
    commercially_closed = bool(technically_closed and ld_settled and final_invoice_paid)
    return {
        "mrb_submitted_on": close.get("mrbSubOn") or "",
        "mrb_approved_on": close.get("mrbApprOn") or "",
        "spir_submitted_on": close.get("spirSubOn") or "",
        "mrv_complete": mrv_complete,
        "mrv_pct": int(round((tot_mrv / tot_ord) * 100)) if tot_ord else 0,
        "ld_settled": ld_settled,
        "final_invoice_paid": final_invoice_paid,
        "final_invoice_paid_on": close.get("finalInvoicePaidOn") or "",
        "technically_closed": technically_closed,
        "commercially_closed": commercially_closed,
        "stage_label": "Commercially Closed" if commercially_closed else ("Technically Closed" if technically_closed else "Open"),
    }


# ---------------------------------------------------------------------------
# PHASE 1: 9-Column Minimum Schedule & Server Baseline Freeze
# ---------------------------------------------------------------------------

@router.get("/api/v1/po/{po}/schedule")
def get_po_9col_schedule(
    po: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    po_num = str(po or "").strip()
    if effective_role(current_user) in ("", "guest"):
        raise HTTPException(status_code=403, detail="Active role required")
    with LOCK, sx_db() as c:
        rec = next((r for r in _records(c) if str(r.get("po")) == po_num), None)
        if not rec:
            raise HTTPException(status_code=404, detail=f"PO {po_num} not found")
        if not user_can_access_po(current_user, rec):
            raise HTTPException(status_code=403, detail=f"Access denied for PO {po_num}")
        synced = _build_synchronized_9col_schedule(rec)
    return {
        "ok": True,
        "po": po_num,
        "procurement_class": _infer_procurement_class(rec),
        "incoterm": rec.get("incoterm") or "",
        "neas": {
            "cdd_date": rec.get("cdd_date") or "",
            "ros_date": rec.get("ros_date") or "",
            "platform": rec.get("platform") or "",
            "despatch_location": rec.get("despatch_location") or rec.get("deliveryPoint") or "",
        },
        "notes": SCHEDULE_RULES_NOTES,
        **synced,
    }


@router.post("/api/v1/po/{po}/schedule")
def save_po_9col_schedule(
    po: str,
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(
        require_roles("admin", "expediting_manager", "expeditor", "field_expeditor", "vendor")
    ),
):
    po_num = str(po or "").strip()
    incoming_rows = payload.get("rows") or []
    freeze_baseline = payload.get("freeze_baseline")
    rebaseline_reason = str(payload.get("rebaseline_reason") or "").strip()
    eff = effective_role(current_user)
    actor = current_user.get("email") or "User"

    with LOCK, sx_db() as c:
        L = _records(c)
        rec = next((r for r in L if str(r.get("po")) == po_num), None)
        if not rec:
            raise HTTPException(status_code=404, detail=f"PO {po_num} not found")
        if not user_can_access_po(current_user, rec):
            raise HTTPException(status_code=403, detail=f"Access denied for PO {po_num}")

        current_sync = _build_synchronized_9col_schedule(rec)
        existing_map = {str(r["id"]): r for r in current_sync["rows"]}
        is_frozen = current_sync["frozen"]

        sch = rec.setdefault("sch", {})
        if freeze_baseline is True:
            if eff not in ("admin", "expediting_manager", "expeditor"):
                raise HTTPException(status_code=403, detail="Only Admin, Expediting Manager, or Expeditor may freeze the schedule baseline")
            sch["frozen"] = True
            sch["frozen_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            sch["frozen_by"] = actor
            is_frozen = True

        if rebaseline_reason and eff not in ("admin", "expediting_manager"):
            raise HTTPException(status_code=403, detail="Only Admin or Expediting Manager may authorize a signed re-baseline")

        # Validate Note 2 baseline freeze: no unauthorized baseline/duration edits once frozen
        merged_by_id = dict(existing_map)
        for upd in incoming_rows:
            if not isinstance(upd, dict):
                continue
            rid = str(upd.get("id") or "").strip()
            if not rid:
                rid = f"custom-{uuid.uuid4().hex[:8]}"
            prev = merged_by_id.get(rid)
            if prev and is_frozen and not rebaseline_reason:
                for bkey in ("bS", "bE", "duration_days"):
                    if bkey in upd and str(upd.get(bkey) or "")[:10] != str(prev.get(bkey) or "")[:10]:
                        raise HTTPException(
                            status_code=400,
                            detail=(
                                f"Baseline Freeze Violation on '{prev['act']}': Duration and Baseline Start/End "
                                "dates cannot be changed once frozen (Rule 2). Submit an Expediting Manager re-baseline approval."
                            ),
                        )
            merged_by_id[rid] = {
                **(prev or {}),
                "id": rid,
                "act": str(prev["act"]) if (prev and prev.get("source_kind") == "minimum") else str(upd.get("act") or (prev or {}).get("act") or "Activity"),
                "duration_days": str(upd.get("duration_days") if "duration_days" in upd else (prev or {}).get("duration_days", "")),
                "bS": str(upd.get("bS") if "bS" in upd else (prev or {}).get("bS", ""))[:10],
                "bE": str(upd.get("bE") if "bE" in upd else (prev or {}).get("bE", ""))[:10],
                "fS": str(upd.get("fS") if "fS" in upd else (prev or {}).get("fS", ""))[:10],
                "fE": str(upd.get("fE") if "fE" in upd else (prev or {}).get("fE", ""))[:10],
                "dependency": str(upd.get("dependency") if "dependency" in upd else (prev or {}).get("dependency", "")),
                "pct": str(upd.get("pct") if "pct" in upd else (prev or {}).get("pct", "")).replace("%", ""),
                "na": bool(upd.get("na") if "na" in upd else (prev or {}).get("na", False)),
                "remarks": str(upd.get("remarks") if "remarks" in upd else (prev or {}).get("remarks", "")),
                "source_kind": (prev or {}).get("source_kind") or "custom",
                "ref_id": (prev or {}).get("ref_id") or "",
            }

        if rebaseline_reason:
            sch.setdefault("rebase", []).append({
                "on": time.strftime("%Y-%m-%d %H:%M:%S"),
                "by": actor,
                "reason": rebaseline_reason,
            })

        sch["rows"] = list(merged_by_id.values())
        rec["sch"] = sch
        _save_records(c, L, actor, f"Updated 9-col Schedule for PO {po_num}" + (" [Frozen]" if freeze_baseline else ""))

    record_audit_event("schedule", po_num, "SCHEDULE_9COL_SAVED", actor=current_user, after={"frozen": is_frozen, "rows": len(merged_by_id)})
    with LOCK, sx_db() as c:
        rec_after = next(r for r in _records(c) if str(r.get("po")) == po_num)
        return {"ok": True, "po": po_num, **_build_synchronized_9col_schedule(rec_after)}


@router.get("/api/v1/po/{po}/schedule/export-xlsx")
def export_po_schedule_xlsx(
    po: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill

    po_num = str(po or "").strip()
    if effective_role(current_user) in ("", "guest"):
        raise HTTPException(status_code=403, detail="Active role required")
    with LOCK, sx_db() as c:
        rec = next((r for r in _records(c) if str(r.get("po")) == po_num), None)
        if not rec:
            raise HTTPException(status_code=404, detail=f"PO {po_num} not found")
        if not user_can_access_po(current_user, rec):
            raise HTTPException(status_code=403, detail=f"Access denied for PO {po_num}")
        synced = _build_synchronized_9col_schedule(rec)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Minimum Schedule"

    headers = [
        "Sr.",
        "Activity",
        "Duration (days)",
        "Baseline Start Date",
        "Baseline End Date",
        "Forecast / Actual Start Date",
        "Forecast/Actual End Date",
        "Dependency",
        "Percentage complete",
    ]
    ws.append([f"PO: {po_num}", f"Supplier: {rec.get('supplier', '')}", f"Class: { _infer_procurement_class(rec).upper() }", f"Frozen: {'Yes' if synced['frozen'] else 'No'}"])
    ws.append(headers)

    hdr_fill = PatternFill("solid", fgColor="1E293B")
    hdr_font = Font(color="FFFFFF", bold=True, size=10)
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=2, column=col_idx)
        cell.fill = hdr_fill
        cell.font = hdr_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for r in synced["rows"]:
        ws.append([
            r.get("sr"),
            r.get("act"),
            r.get("duration_days"),
            r.get("bS"),
            r.get("bE"),
            r.get("fS"),
            r.get("fE"),
            r.get("dependency"),
            f"{r.get('pct')}%" if str(r.get("pct") or "") != "" else "",
        ])

    ws.append([])
    ws.append(["", "Notes :"])
    for note in SCHEDULE_RULES_NOTES:
        ws.append(["", note])

    widths = [6, 46, 15, 18, 18, 24, 22, 16, 18]
    for idx, w in enumerate(widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(idx)].width = w

    buf = io.BytesIO()
    wb.save(buf)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{po_num}_Schedule_9Col.xlsx"'},
    )


def _norm_act_key(text: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def _parse_csv_schedule_rows(file_bytes: bytes) -> Dict[str, Any]:
    import csv
    from python_app.expediting_parsers import _norm_header, parse_flexible_date

    decoded = None
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            decoded = file_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if decoded is None:
        decoded = file_bytes.decode("utf-8", errors="replace")

    raw_rows = list(csv.reader(io.StringIO(decoded)))
    if not raw_rows:
        return {"mode": "EMPTY", "activities": [], "item_updates": [], "warnings": ["CSV file is empty"]}

    hdr_idx = None
    hdr_map: Dict[str, int] = {}
    mode = None
    for idx, r in enumerate(raw_rows[:25]):
        nm = {_norm_header(c): c_i for c_i, c in enumerate(r) if _norm_header(c)}
        if any(k in nm for k in ("activity", "activityname", "taskname", "activitydescription", "milestonename")):
            hdr_idx = idx
            hdr_map = nm
            mode = "ACTIVITY"
            break
        if any(k in nm for k in ("item", "itemno", "itemnumber")) and ("forecastdate" in nm or "baselinedate" in nm):
            hdr_idx = idx
            hdr_map = nm
            mode = "ITEM_CSV"
            break

    if hdr_idx is None:
        return {"mode": "UNKNOWN", "activities": [], "item_updates": [], "warnings": ["No 'Activity' or 'Item #' header found in first 25 CSV rows"]}

    activities: List[Dict[str, Any]] = []
    item_updates: List[Dict[str, Any]] = []
    if mode == "ACTIVITY":
        name_c = hdr_map.get("activity") or hdr_map.get("activityname") or hdr_map.get("taskname") or hdr_map.get("activitydescription") or hdr_map.get("milestonename")
        dur_c = hdr_map.get("durationdays") or hdr_map.get("duration") or hdr_map.get("dur")
        bs_c = hdr_map.get("baselinestartdate") or hdr_map.get("baselinestart") or hdr_map.get("plannedstart")
        be_c = hdr_map.get("baselineenddate") or hdr_map.get("baselinefinish") or hdr_map.get("baselineend")
        fs_c = hdr_map.get("forecastactualstartdate") or hdr_map.get("forecaststart") or hdr_map.get("currentstart")
        fe_c = hdr_map.get("forecastactualenddate") or hdr_map.get("forecastfinish") or hdr_map.get("forecastend") or hdr_map.get("currentfinish")
        dep_c = hdr_map.get("dependency") or hdr_map.get("dep")
        pct_c = hdr_map.get("percentagecomplete") or hdr_map.get("percentcomplete") or hdr_map.get("progress") or hdr_map.get("complete") or hdr_map.get("pct")
        rem_c = hdr_map.get("remarks") or hdr_map.get("notes")
        for r in raw_rows[hdr_idx + 1:]:
            if name_c is None or name_c >= len(r):
                continue
            act_name = str(r[name_c]).strip()
            if not act_name or act_name.lower() in ("notes", "notes :") or re.match(r"^\d+\.\s*the\s+", act_name.lower()):
                continue
            pct_str = ""
            if pct_c is not None and pct_c < len(r) and str(r[pct_c]).strip() != "":
                pct_str = str(r[pct_c]).replace("%", "").strip()
            activities.append({
                "act": act_name,
                "duration_days": str(r[dur_c]).strip() if dur_c is not None and dur_c < len(r) else "",
                "bS": (parse_flexible_date(r[bs_c]) if bs_c is not None and bs_c < len(r) else None) or "",
                "bE": (parse_flexible_date(r[be_c]) if be_c is not None and be_c < len(r) else None) or "",
                "fS": (parse_flexible_date(r[fs_c]) if fs_c is not None and fs_c < len(r) else None) or "",
                "fE": (parse_flexible_date(r[fe_c]) if fe_c is not None and fe_c < len(r) else None) or "",
                "dependency": str(r[dep_c]).strip() if dep_c is not None and dep_c < len(r) else "",
                "pct": pct_str,
                "remarks": str(r[rem_c]).strip() if rem_c is not None and rem_c < len(r) else "",
            })
    elif mode == "ITEM_CSV":
        item_c = hdr_map.get("item") or hdr_map.get("itemno") or hdr_map.get("itemnumber")
        fc_c = hdr_map.get("forecastdate")
        dr_c = hdr_map.get("delayreason") or hdr_map.get("delayreasoncode")
        rp_c = hdr_map.get("recoveryplan")
        for r in raw_rows[hdr_idx + 1:]:
            if item_c is None or item_c >= len(r) or not str(r[item_c]).strip():
                continue
            fc = (parse_flexible_date(r[fc_c]) if fc_c is not None and fc_c < len(r) else None) or ""
            item_updates.append({
                "item_id": str(r[item_c]).strip(),
                "forecast_date": fc,
                "delay_reason_code": str(r[dr_c]).strip() if dr_c is not None and dr_c < len(r) else "",
                "recovery_plan": str(r[rp_c]).strip() if rp_c is not None and rp_c < len(r) else "",
            })
    return {"mode": mode, "activities": activities, "item_updates": item_updates, "warnings": []}


@router.post("/api/v1/po/{po}/schedule/upload")
async def upload_and_parse_po_schedule(
    po: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(
        require_roles("admin", "vendor", "expediting_manager", "expeditor", "field_expeditor")
    ),
):
    """
    Unified schedule upload & parser for Vendors and Expeditors (.xlsx, .csv, .pdf with OCR/AI fallback).
    Parses the uploaded schedule, matches/updates the PO's 9-Column Minimum Schedule while
    strictly enforcing Rule 2 Baseline Freeze, and persists directly to the PO record.
    """
    from python_app.expediting_parsers import _is_excel_bytes, parse_excel_schedule
    from python_app.pdf_ocr import extract_pdf_with_ocr

    po_num = str(po or "").strip()
    form = await request.form()
    up = form.get("file") or form.get("schedule") or form.get("pdf")
    if up is None or not hasattr(up, "read"):
        raise HTTPException(status_code=400, detail="Schedule file upload ('file') is required")

    file_bytes = await up.read(settings.upload_max_bytes + 1)
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded schedule file is empty")
    if len(file_bytes) > settings.upload_max_bytes:
        raise HTTPException(status_code=413, detail="Uploaded file exceeds maximum allowed size")

    filename = str(getattr(up, "filename", None) or "schedule.xlsx")
    lower_fn = filename.lower()

    with LOCK, sx_db() as c:
        rec = next((r for r in _records(c) if str(r.get("po")) == po_num), None)
        if not rec:
            raise HTTPException(status_code=404, detail=f"PO {po_num} not found")
        if is_vendor_user(current_user) and not vendor_owns_po(current_user, rec):
            raise HTTPException(status_code=403, detail=f"Not authorized for PO {po_num}")
        if not is_admin_user(current_user) and not user_can_access_po(current_user, rec):
            raise HTTPException(status_code=403, detail=f"Not authorized for PO {po_num}")
        proc_cls = _infer_procurement_class(rec)

    parsed_acts: List[Dict[str, Any]] = []
    item_updates: List[Dict[str, Any]] = []
    warnings: List[str] = []
    target_delivery = None
    file_kind = "unknown"
    engine = "unknown"

    try:
        if lower_fn.endswith(".pdf") or file_bytes.lstrip()[:5].startswith(b"%PDF-"):
            file_kind = "pdf"
            if ai_service.get_gemini_api_key():
                ai_out = await run_in_threadpool(
                    ai_service.extract_schedule_with_gemini,
                    file_bytes,
                    filename=filename,
                    procurement_class=proc_cls,
                )
                target_delivery = ai_out.get("target_delivery")
                for a in (ai_out.get("activities") or []):
                    parsed_acts.append({
                        "act": a.get("act") or "",
                        "duration_days": a.get("duration_days") or "",
                        "bS": a.get("bS") or "",
                        "bE": a.get("bE") or "",
                        "fS": a.get("fS") or "",
                        "fE": a.get("fE") or "",
                        "dependency": a.get("dependency") or "",
                        "pct": a.get("pct") or "",
                        "remarks": "",
                    })
                engine = "gemini-2.5-flash"

            if not parsed_acts:
                ocr_res = await run_in_threadpool(extract_pdf_with_ocr, file_bytes, max_pages=60)
                engine = f"ocr:{ocr_res.get('engine') or 'pdf'}"
                for ln in (ocr_res.get("lines") or []):
                    txt = str(ln.get("text") or "").strip() if isinstance(ln, dict) else str(ln).strip()
                    dates = re.findall(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b", txt)
                    if txt and dates:
                        parsed_acts.append({
                            "act": re.sub(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", "", txt).strip(" -|:\t")[:120] or txt[:80],
                            "duration_days": "",
                            "bS": dates[0] if len(dates) >= 1 else "",
                            "bE": dates[1] if len(dates) >= 2 else dates[0],
                            "fS": dates[2] if len(dates) >= 3 else "",
                            "fE": dates[3] if len(dates) >= 4 else (dates[-1] if dates else ""),
                            "dependency": "",
                            "pct": "",
                            "remarks": "Parsed via OCR text fallback",
                        })

        elif lower_fn.endswith(".csv"):
            file_kind = "csv"
            engine = "csv-parser"
            csv_out = _parse_csv_schedule_rows(file_bytes)
            parsed_acts = csv_out.get("activities") or []
            item_updates = csv_out.get("item_updates") or []
            warnings.extend(csv_out.get("warnings") or [])

        else:
            file_kind = "excel"
            engine = "openpyxl"
            _is_excel_bytes(file_bytes, filename)
            xl_out = await run_in_threadpool(parse_excel_schedule, file_bytes)
            warnings.extend(xl_out.get("warnings") or [])
            for a in (xl_out.get("activities") or []):
                parsed_acts.append({
                    "act": a.get("activity_name") or "",
                    "duration_days": a.get("duration_days") or "",
                    "bS": a.get("raw_bS") if "raw_bS" in a else (a.get("baseline_start") or ""),
                    "bE": a.get("raw_bE") if "raw_bE" in a else (a.get("baseline_finish") or ""),
                    "fS": a.get("raw_fS") if "raw_fS" in a else (a.get("current_start") or ""),
                    "fE": a.get("raw_fE") if "raw_fE" in a else (a.get("current_finish") or ""),
                    "dependency": a.get("dependency") or "",
                    "pct": a.get("raw_pct") if "raw_pct" in a else str(a.get("percent_complete") or ""),
                    "remarks": a.get("remarks") or "",
                })
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed parsing uploaded schedule '{filename}': {exc}")

    if not parsed_acts and not item_updates:
        raise HTTPException(
            status_code=400,
            detail=(
                f"No recognizable schedule activities or dates found in '{filename}'. "
                "Include an 'Activity' column (with Baseline/Forecast dates) or use the 9-Col Excel template."
            ),
        )

    matched_count = 0
    added_count = 0
    baseline_locked_skips = 0
    actor = current_user.get("email") or "Schedule Upload"

    with LOCK, sx_db() as c:
        L = _records(c)
        target = next((r for r in L if str(r.get("po")) == po_num), None)
        if not target:
            raise HTTPException(status_code=404, detail=f"PO {po_num} not found")

        sync = _build_synchronized_9col_schedule(target)
        is_frozen = sync["frozen"]
        rows = list(sync["rows"])
        by_norm = {_norm_act_key(r["act"]): r for r in rows}

        for pa in parsed_acts:
            act_label = str(pa.get("act") or "").strip()
            if not act_label:
                continue
            nk = _norm_act_key(act_label)
            existing_row = by_norm.get(nk)
            if not existing_row:
                # Try substring/token overlap match against existing minimum/ITP/suborder rows
                existing_row = next(
                    (
                        r for r in rows
                        if nk and (_norm_act_key(r["act"]) in nk or nk in _norm_act_key(r["act"]))
                    ),
                    None,
                )
            if existing_row:
                matched_count += 1
                if not is_frozen:
                    if pa.get("bS"):
                        existing_row["bS"] = str(pa["bS"])[:10]
                    if pa.get("bE"):
                        existing_row["bE"] = str(pa["bE"])[:10]
                    if str(pa.get("duration_days") or "") != "":
                        existing_row["duration_days"] = str(pa["duration_days"])
                else:
                    if (pa.get("bS") and existing_row.get("bS") and str(pa["bS"])[:10] != str(existing_row["bS"])[:10]) or (
                        pa.get("bE") and existing_row.get("bE") and str(pa["bE"])[:10] != str(existing_row["bE"])[:10]
                    ):
                        baseline_locked_skips += 1
                if pa.get("fS"):
                    existing_row["fS"] = str(pa["fS"])[:10]
                if pa.get("fE"):
                    existing_row["fE"] = str(pa["fE"])[:10]
                if pa.get("dependency"):
                    existing_row["dependency"] = str(pa["dependency"])
                if str(pa.get("pct") or "") != "":
                    existing_row["pct"] = str(pa["pct"]).replace("%", "")
                if pa.get("remarks"):
                    existing_row["remarks"] = str(pa["remarks"])
            else:
                added_count += 1
                new_r = {
                    "id": f"imp-{uuid.uuid4().hex[:8]}",
                    "sr": len(rows) + 1,
                    "act": act_label,
                    "duration_days": str(pa.get("duration_days") or ""),
                    "bS": "" if is_frozen else str(pa.get("bS") or "")[:10],
                    "bE": "" if is_frozen else str(pa.get("bE") or "")[:10],
                    "fS": str(pa.get("fS") or pa.get("bS") or "")[:10],
                    "fE": str(pa.get("fE") or pa.get("bE") or "")[:10],
                    "dependency": str(pa.get("dependency") or ""),
                    "pct": str(pa.get("pct") or "").replace("%", ""),
                    "na": False,
                    "remarks": str(pa.get("remarks") or f"Imported from {filename}"),
                    "source_kind": "imported",
                    "ref_id": "",
                }
                rows.append(new_r)
                by_norm[nk] = new_r

        # Also apply item-level forecast updates from CSV or target_delivery
        for iu in item_updates:
            for itm in (target.get("items") or []):
                if str(itm.get("item")) == iu.get("item_id"):
                    if iu.get("forecast_date"):
                        itm["forecast_date"] = iu["forecast_date"]
                    if iu.get("delay_reason_code"):
                        itm["delay_reason"] = iu["delay_reason_code"]
                    if iu.get("recovery_plan"):
                        itm["recovery_plan"] = iu["recovery_plan"]

        if not target_delivery and rows:
            deliv_row = next(
                (r for r in rows if any(k in r["act"].lower() for k in ("exw", "fob", "cfr", "delivered at destination")) and r.get("fE")),
                None,
            )
            if deliv_row:
                target_delivery = deliv_row.get("fE")

        sch = target.setdefault("sch", {})
        sch["rows"] = rows
        target["sch"] = sch
        _save_records(c, L, actor, f"Parsed & imported schedule '{filename}' ({matched_count} matched, {added_count} added)")
        final_sync = _build_synchronized_9col_schedule(target)

    if baseline_locked_skips:
        warnings.append(
            f"Rule 2 Baseline Freeze active: kept frozen Baseline dates on {baseline_locked_skips} row(s) and updated Forecast/Actuals only."
        )
    record_audit_event(
        "schedule",
        po_num,
        "SCHEDULE_FILE_UPLOADED",
        actor=current_user,
        after={"filename": filename, "engine": engine, "matched": matched_count, "added": added_count},
    )
    return {
        "ok": True,
        "po": po_num,
        "filename": filename,
        "file_kind": file_kind,
        "engine": engine,
        "parsed_count": len(parsed_acts) + len(item_updates),
        "matched_count": matched_count,
        "added_count": added_count,
        "warnings": warnings,
        "target_delivery": target_delivery,
        **final_sync,
    }


# ---------------------------------------------------------------------------
# PHASE 2A: Unified Vendor Portal (PO Ack, Sub-Orders, 7-Sec Progress Report, MRB/SPIR)
# ---------------------------------------------------------------------------

@router.post("/api/v1/vendor/po-acknowledgement")
def submit_po_acknowledgement(
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(require_roles("admin", "vendor", "expediting_manager", "expeditor")),
):
    po_num = str(payload.get("po_number") or payload.get("po") or "").strip()
    ack_status = str(payload.get("status") or "").strip()
    open_points = str(payload.get("open_points") or payload.get("comments") or "").strip()
    ack_date = str(payload.get("ack_date") or time.strftime("%Y-%m-%d"))[:10]
    buyer_settled = bool(payload.get("buyer_settled"))
    if ack_status not in ("Pending", "With comments", "Unconditional"):
        raise HTTPException(status_code=400, detail="status must be 'Pending', 'With comments', or 'Unconditional'")
    if ack_status == "With comments" and not open_points:
        raise HTTPException(status_code=400, detail="Open points description is required when acknowledging with comments")

    with LOCK, sx_db() as c:
        L = _records(c)
        rec = next((r for r in L if str(r.get("po")) == po_num), None)
        if not rec:
            raise HTTPException(status_code=404, detail=f"PO {po_num} not found")
        if is_vendor_user(current_user) and not vendor_owns_po(current_user, rec):
            raise HTTPException(status_code=403, detail=f"Not authorized for PO {po_num}")
        if not is_admin_user(current_user) and not user_can_access_po(current_user, rec):
            raise HTTPException(status_code=403, detail=f"Not authorized for PO {po_num}")

        if buyer_settled and not is_vendor_user(current_user):
            ack_status = "Unconditional"

        needs_buyer = ack_status == "With comments"
        rec["ackx"] = {
            "st": ack_status,
            "pts": open_points,
            "ack_date": ack_date,
            "buyer_escalation_required": needs_buyer,
            "updated_by": current_user.get("email"),
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        if ack_status == "Unconditional":
            rec["ackDate"] = ack_date
            sch_rows = rec.setdefault("sch", {}).setdefault("rows", [])
            for sr in sch_rows:
                if "acknowledg" in str(sr.get("act") or "").lower():
                    sr["fS"] = sr.get("fS") or ack_date
                    sr["fE"] = ack_date
                    sr["pct"] = "100"
        _save_records(c, L, _who(None, current_user), f"PO {po_num} Acknowledgement -> {ack_status}")

    record_audit_event("po_ack", po_num, "PO_ACKNOWLEDGEMENT_UPDATED", actor=current_user, after={"status": ack_status, "buyer_escalation": needs_buyer})
    return {"ok": True, "po": po_num, "ack": rec["ackx"]}


@router.post("/api/v1/vendor/sub-orders")
def upsert_vendor_suborder(
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(require_roles("admin", "vendor", "expediting_manager", "expeditor", "field_expeditor")),
):
    po_num = str(payload.get("po_number") or payload.get("po") or "").strip()
    vendor_name = str(payload.get("vendor") or "").strip()
    material = str(payload.get("material") or "").strip()
    if not po_num or not vendor_name or not material:
        raise HTTPException(status_code=400, detail="po_number, vendor, and material are required")

    sub_id = str(payload.get("id") or f"SUB-{uuid.uuid4().hex[:8].upper()}")
    with LOCK, sx_db() as c:
        L = _records(c)
        rec = next((r for r in L if str(r.get("po")) == po_num), None)
        if not rec:
            raise HTTPException(status_code=404, detail=f"PO {po_num} not found")
        if is_vendor_user(current_user) and not vendor_owns_po(current_user, rec):
            raise HTTPException(status_code=403, detail=f"Not authorized for PO {po_num}")
        if not is_admin_user(current_user) and not user_can_access_po(current_user, rec):
            raise HTTPException(status_code=403, detail=f"Not authorized for PO {po_num}")

        plan = rec.setdefault("plan", {"rows": [], "extra": []})
        rows = plan.setdefault("rows", [])
        sub_po_no = str(payload.get("sub_po_no") or "").strip()
        ord_dt = str(payload.get("order_date") or "")[:10]
        req_del = str(payload.get("req_delivery") or "")[:10]
        fc_del = str(payload.get("forecast_delivery") or req_del)[:10]
        entry = {
            "id": sub_id,
            "item_ref": str(payload.get("item_ref") or ""),
            "sub_po_no": sub_po_no,
            "no": sub_po_no,
            "vendor": vendor_name,
            "sub": vendor_name,
            "material": material,
            "item": material,
            "loc": str(payload.get("location") or ""),
            "critical": bool(payload.get("critical", True)),
            "order_date": ord_dt,
            "aPlace": ord_dt,
            "req_delivery": req_del,
            "raw": req_del,
            "forecast_delivery": fc_del,
            "clear": fc_del,
            "unpriced_po_ref": str(payload.get("unpriced_po_ref") or ""),
            "status": str(payload.get("status") or ("Placed" if sub_po_no else "Enquiry")),
            "updated_by": current_user.get("email"),
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "deleted": False,
        }
        idx = next((i for i, x in enumerate(rows) if str(x.get("id")) == sub_id), None)
        if idx is not None:
            rows[idx] = {**rows[idx], **entry}
        else:
            rows.append(entry)
        _save_records(c, L, _who(None, current_user), f"Updated sub-order {vendor_name} / {material} on {po_num}")

    return {"ok": True, "po": po_num, "sub_order": entry}


@router.delete("/api/v1/vendor/sub-orders/{sub_id}")
def delete_vendor_suborder(
    sub_id: str,
    po: str,
    reason: str = "Removed by user",
    current_user: Dict[str, Any] = Depends(require_roles("admin", "vendor", "expediting_manager", "expeditor")),
):
    with LOCK, sx_db() as c:
        L = _records(c)
        rec = next((r for r in L if str(r.get("po")) == po), None)
        if not rec:
            raise HTTPException(status_code=404, detail=f"PO {po} not found")
        if is_vendor_user(current_user) and not vendor_owns_po(current_user, rec):
            raise HTTPException(status_code=403, detail=f"Not authorized for PO {po}")
        for row in (rec.get("plan") or {}).get("rows") or []:
            if str(row.get("id")) == sub_id:
                row["deleted"] = True
                row["delete_reason"] = reason
                _save_records(c, L, _who(None, current_user), f"Removed sub-order {sub_id} on {po}")
                return {"ok": True, "sub_id": sub_id}
    raise HTTPException(status_code=404, detail="Sub-order not found")


def _default_eng_13_docs(rec: Dict[str, Any]) -> List[Dict[str, Any]]:
    docs = _ensure_vdrl_docs(rec)
    out = []
    for idx, cat in enumerate(NMDC_13_ENGINEERING_DOC_CATS, 1):
        cat_l = cat.lower()
        sub_cnt = 0
        for d in docs:
            title_l = str(d.get("title") or "").lower()
            if (cat_l == "ga drawing" and ("ga" in title_l or "drawing" in title_l)) or (
                cat_l == "data sheets" and "data" in title_l
            ) or (cat_l == "quality" and ("itp" in title_l or "quality" in title_l or "wps" in title_l)) or (
                cat_l in title_l
            ):
                if d.get("submitted") or d.get("actual_date") or d.get("code") in ("Code 1", "Code 2"):
                    sub_cnt += 1
        out.append({"sr": idx, "category": cat, "submitted_qty": sub_cnt, "remarks": ""})
    return out


@router.get("/api/v1/po/{po}/progress-reports")
def list_po_progress_reports(
    po: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    po_num = str(po or "").strip()
    if effective_role(current_user) in ("", "guest"):
        raise HTTPException(status_code=403, detail="Active role required")
    with LOCK, sx_db() as c:
        rec = next((r for r in _records(c) if str(r.get("po")) == po_num), None)
        if not rec:
            raise HTTPException(status_code=404, detail=f"PO {po_num} not found")
        if not user_can_access_po(current_user, rec):
            raise HTTPException(status_code=403, detail=f"Access denied for PO {po_num}")
        sx_state = _get_sx_state(c)

    concerns = [cn for cn in (sx_state.get("concerns") or []) if str(cn.get("po")) == po_num and cn.get("status") != "CLOSED"]
    reports = list(rec.get("vpr_reports") or [])
    items_delivery_template = [
        {
            "item": str(it.get("item") or ""),
            "desc": str(it.get("desc") or ""),
            "ros_date": str(it.get("ros_date") or rec.get("ros_date") or ""),
            "planned_delivery": str(it.get("baseline_date") or rec.get("cdd_date") or ""),
            "actual_delivery": str(it.get("actual_date") or ""),
            "platform": str(it.get("platform") or rec.get("platform") or ""),
            "despatch_location": str(it.get("despatch_location") or rec.get("despatch_location") or rec.get("deliveryPoint") or ""),
        }
        for it in (rec.get("items") or [])
        if not it.get("is_split_parent")
    ]
    return {
        "ok": True,
        "po": po_num,
        "reports": reports,
        "template_defaults": {
            "contract_no": rec.get("contract_no") or "",
            "budget_no": rec.get("budget_no") or "",
            "project_no": rec.get("project_code") or "",
            "project_name": rec.get("project") or "",
            "equipment_material": rec.get("head") or "",
            "vendor_name": rec.get("supplierShort") or rec.get("supplier") or "",
            "engineering_docs_13": _default_eng_13_docs(rec),
            "delivery_items": items_delivery_template,
            "open_concerns_summary": "; ".join(f"[{c_i.get('no') or c_i.get('id')}] {c_i.get('issue')}" for c_i in concerns[:5]),
        },
    }


@router.post("/api/v1/po/{po}/progress-reports")
def save_or_submit_progress_report(
    po: str,
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(
        require_roles("admin", "vendor", "expediting_manager", "expeditor", "field_expeditor")
    ),
):
    po_num = str(po or "").strip()
    submit = bool(payload.get("submit", True))
    attachments = dict(payload.get("attachments") or {})
    if submit and not (attachments.get("schedule_attached") and attachments.get("suborder_status_attached")):
        raise HTTPException(
            status_code=400,
            detail="Section 7 Mandatory Attachments: Both Vendor Schedule and Sub-Order Status annexure must be attached/confirmed before submitting the Progress Report.",
        )

    rep_id = str(payload.get("id") or f"VPR-{po_num}-{uuid.uuid4().hex[:6].upper()}")
    with LOCK, sx_db() as c:
        L = _records(c)
        rec = next((r for r in L if str(r.get("po")) == po_num), None)
        if not rec:
            raise HTTPException(status_code=404, detail=f"PO {po_num} not found")
        if is_vendor_user(current_user) and not vendor_owns_po(current_user, rec):
            raise HTTPException(status_code=403, detail=f"Not authorized for PO {po_num}")
        if not is_admin_user(current_user) and not user_can_access_po(current_user, rec):
            raise HTTPException(status_code=403, detail=f"Not authorized for PO {po_num}")

        reports = rec.setdefault("vpr_reports", [])
        existing = next((r for r in reports if str(r.get("id")) == rep_id), None)
        next_no = str(payload.get("report_no") or f"{len(reports)+1:02d}")
        report_obj = {
            "id": rep_id,
            "report_no": next_no,
            "round": (int(existing.get("round") or 1) + (1 if existing and existing.get("status") == "Returned" else 0)) if existing else 1,
            "status": "Submitted" if submit else "Draft",
            "contract_no": payload.get("contract_no") or rec.get("contract_no") or "",
            "budget_no": payload.get("budget_no") or rec.get("budget_no") or "",
            "project_no": payload.get("project_no") or rec.get("project_code") or "",
            "equipment_material": payload.get("equipment_material") or rec.get("head") or "",
            "vendor_name": payload.get("vendor_name") or rec.get("supplierShort") or rec.get("supplier") or "",
            "period_from": str(payload.get("period_from") or "")[:10],
            "period_to": str(payload.get("period_to") or "")[:10],
            "po_summary": payload.get("po_summary") or {},
            "achievements_this_month": payload.get("achievements_this_month") or {},
            "planned_next_month": payload.get("planned_next_month") or {},
            "areas_of_concern": str(payload.get("areas_of_concern") or ""),
            "engineering_detail": payload.get("engineering_detail") or {"docs_13": _default_eng_13_docs(rec)},
            "procurement_detail": payload.get("procurement_detail") or {},
            "manufacturing_detail": payload.get("manufacturing_detail") or {},
            "delivery_detail": payload.get("delivery_detail") or {},
            "attachments": attachments,
            "submitted_by": current_user.get("email"),
            "submitted_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "reviewer_comments": existing.get("reviewer_comments", "") if existing else "",
        }
        if existing:
            idx = reports.index(existing)
            reports[idx] = report_obj
        else:
            reports.append(report_obj)
        _save_records(c, L, _who(None, current_user), f"Progress Report #{next_no} ({report_obj['status']}) on PO {po_num}")

    record_audit_event("progress_report", rep_id, "VPR_SUBMITTED" if submit else "VPR_SAVED", actor=current_user, after={"po": po_num, "no": next_no})
    return {"ok": True, "po": po_num, "report": report_obj}


@router.post("/api/v1/po/{po}/progress-reports/{report_id}/review")
def review_progress_report(
    po: str,
    report_id: str,
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(require_roles("admin", "expediting_manager", "expeditor")),
):
    decision = str(payload.get("decision") or "").strip()
    if decision not in ("Agreed", "Returned"):
        raise HTTPException(status_code=400, detail="decision must be 'Agreed' or 'Returned'")
    comments = str(payload.get("comments") or "").strip()
    with LOCK, sx_db() as c:
        L = _records(c)
        rec = next((r for r in L if str(r.get("po")) == po), None)
        if not rec:
            raise HTTPException(status_code=404, detail=f"PO {po} not found")
        if not user_can_access_po(current_user, rec):
            raise HTTPException(status_code=403, detail=f"Access denied for PO {po}")
        rep = next((r for r in (rec.get("vpr_reports") or []) if str(r.get("id")) == report_id), None)
        if not rep:
            raise HTTPException(status_code=404, detail="Progress report not found")
        rep["status"] = decision
        rep["reviewer_comments"] = comments
        rep["reviewed_by"] = current_user.get("email")
        rep["reviewed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _save_records(c, L, _who(None, current_user), f"Progress Report #{rep.get('report_no')} {decision} on PO {po}")
    return {"ok": True, "report": rep}


def _find_progress_report_for_export(po: str, report_id: str, current_user: Dict[str, Any]):
    with LOCK, sx_db() as c:
        rec = next((r for r in _records(c) if str(r.get("po")) == po), None)
        if not rec:
            raise HTTPException(status_code=404, detail=f"PO {po} not found")
        if not user_can_access_po(current_user, rec):
            raise HTTPException(status_code=403, detail=f"Access denied for PO {po}")
        rep = next((r for r in (rec.get("vpr_reports") or []) if str(r.get("id")) == report_id), None)
        if not rep:
            raise HTTPException(status_code=404, detail="Progress report not found")
        sub_rows = [_normalize_suborder_row(x) for x in ((rec.get("plan") or {}).get("rows") or []) if isinstance(x, dict) and not x.get("deleted")]
        return rec, rep, sub_rows


@router.get("/api/v1/po/{po}/progress-reports/{report_id}/export-docx")
def export_progress_report_docx(
    po: str,
    report_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    from docx import Document

    rec, rep, sub_rows = _find_progress_report_for_export(po, report_id, current_user)
    doc = Document()
    doc.add_heading(f"PROGRESS REPORT — No. {rep.get('report_no', '')}", level=1)
    p = doc.add_paragraph()
    p.add_run(
        f"Project: [{rep.get('project_no') or rec.get('project_code') or ''}] {rec.get('project') or ''}  |  "
        f"Contract No.: {rep.get('contract_no') or 'N/A'}  |  Budget No.: {rep.get('budget_no') or 'N/A'}\n"
        f"Purchase Order No.: {po}  |  Equipment / Material: {rep.get('equipment_material') or ''}\n"
        f"Vendor Name: {rep.get('vendor_name') or ''}  |  "
        f"Reporting Period: {rep.get('period_from') or '—'} to {rep.get('period_to') or '—'}  |  Status: {rep.get('status')}"
    )

    doc.add_heading("1. PO SUMMARY", level=2)
    sum_d = rep.get("po_summary") or {}
    t1 = doc.add_table(rows=1, cols=3)
    t1.style = "Table Grid"
    t1.rows[0].cells[0].text, t1.rows[0].cells[1].text, t1.rows[0].cells[2].text = "Discipline", "Planned %", "Actual %"
    for key, label in [("engineering", "Engineering (Item 3)"), ("procurement", "Procurement (Item 4)"), ("manufacturing", "Manufacturing (Item 5)"), ("delivery", "Delivery (Item 6)"), ("overall", "Overall Progress")]:
        row = t1.add_row().cells
        row[0].text = label
        row[1].text = f"{(sum_d.get(key) or {}).get('planned', 0)}%"
        row[2].text = f"{(sum_d.get(key) or {}).get('actual', 0)}%"

    ach = rep.get("achievements_this_month") or {}
    nxt = rep.get("planned_next_month") or {}
    doc.add_paragraph(
        "Achievements This Month:\n"
        + "\n".join(f"• {k.title()}: {ach.get(k) or '—'}" for k in ("engineering", "procurement", "manufacturing", "delivery"))
    )
    doc.add_paragraph(
        "Planned Activities Next Month:\n"
        + "\n".join(f"• {k.title()}: {nxt.get(k) or '—'}" for k in ("engineering", "procurement", "manufacturing", "delivery"))
    )

    doc.add_heading("2. AREAS OF CONCERN", level=2)
    doc.add_paragraph(rep.get("areas_of_concern") or "None reported.")

    doc.add_heading("3. ENGINEERING DETAIL REPORT", level=2)
    eng = rep.get("engineering_detail") or {}
    doc.add_paragraph(
        f"Planned (This Month / Accumulated): {eng.get('planned_month', 0)}% / {eng.get('planned_cum', sum_d.get('engineering', {}).get('planned', 0))}%\n"
        f"Actual (This Month / Accumulated): {eng.get('actual_month', 0)}% / {eng.get('actual_cum', sum_d.get('engineering', {}).get('actual', 0))}%"
    )
    t3 = doc.add_table(rows=1, cols=4)
    t3.style = "Table Grid"
    t3.rows[0].cells[0].text, t3.rows[0].cells[1].text, t3.rows[0].cells[2].text, t3.rows[0].cells[3].text = "Sr.", "Description (SDR Category)", "Submitted Qty", "Remarks"
    for item in eng.get("docs_13") or _default_eng_13_docs(rec):
        rw = t3.add_row().cells
        rw[0].text = str(item.get("sr", ""))
        rw[1].text = str(item.get("category", ""))
        rw[2].text = str(item.get("submitted_qty", 0))
        rw[3].text = str(item.get("remarks", ""))

    doc.add_heading("4. PROCUREMENT DETAIL REPORT (Sub-Order Status)", level=2)
    proc = rep.get("procurement_detail") or {}
    doc.add_paragraph(f"Procurement Progress: Planned {sum_d.get('procurement', {}).get('planned', 0)}% | Actual {sum_d.get('procurement', {}).get('actual', 0)}% — {proc.get('notes', '')}")
    if sub_rows:
        t4 = doc.add_table(rows=1, cols=5)
        t4.style = "Table Grid"
        for i, h in enumerate(["Sub-Vendor", "Material", "Sub-PO #", "Req Delivery", "Forecast"]):
            t4.rows[0].cells[i].text = h
        for sr in sub_rows:
            rw = t4.add_row().cells
            rw[0].text, rw[1].text, rw[2].text, rw[3].text, rw[4].text = (
                str(sr.get("vendor", "")), str(sr.get("material", "")), str(sr.get("sub_po_no", "")),
                str(sr.get("req_delivery", "")), str(sr.get("forecast_delivery", ""))
            )

    doc.add_heading("5. MANUFACTURING DETAIL REPORT", level=2)
    mfg = rep.get("manufacturing_detail") or {}
    doc.add_paragraph(f"Planned: {sum_d.get('manufacturing', {}).get('planned', 0)}% | Actual: {sum_d.get('manufacturing', {}).get('actual', 0)}%\nStatus Notes: {mfg.get('status_notes') or 'Per shop schedule.'}")

    doc.add_heading("6. DELIVERY DETAIL REPORT", level=2)
    d6 = (rep.get("delivery_detail") or {}).get("items") or []
    t6 = doc.add_table(rows=1, cols=6)
    t6.style = "Table Grid"
    for i, h in enumerate(["PO Item", "ROS Date", "Planned Delivery", "Actual Delivery", "Platform", "Despatch Location"]):
        t6.rows[0].cells[i].text = h
    for it in d6:
        rw = t6.add_row().cells
        rw[0].text = str(it.get("item", ""))
        rw[1].text = str(it.get("ros_date", ""))
        rw[2].text = str(it.get("planned_delivery", ""))
        rw[3].text = str(it.get("actual_delivery", ""))
        rw[4].text = str(it.get("platform", ""))
        rw[5].text = str(it.get("despatch_location", ""))

    doc.add_heading("7. ATTACHMENTS", level=2)
    att = rep.get("attachments") or {}
    doc.add_paragraph(
        f"• Vendor 9-Column Execution Schedule Attached: {'YES' if att.get('schedule_attached') else 'NO'}\n"
        f"• Sub-Order Status Annexure Attached: {'YES' if att.get('suborder_status_attached') else 'NO'}\n"
        f"• Supporting Reference: {att.get('notes') or 'N/A'}"
    )

    buf = io.BytesIO()
    doc.save(buf)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{po}_Progress_Report_{rep.get("report_no", "01")}.docx"'},
    )


@router.get("/api/v1/po/{po}/progress-reports/{report_id}/export-pdf")
def export_progress_report_pdf(
    po: str,
    report_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    rec, rep, sub_rows = _find_progress_report_for_export(po, report_id, current_user)
    buf = io.BytesIO()
    c_pdf = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    y = h - 42

    def _draw(text: str, bold: bool = False, size: int = 9, step: int = 13):
        nonlocal y
        if y < 48:
            c_pdf.showPage()
            y = h - 42
        c_pdf.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c_pdf.drawString(36, y, text[:110])
        y -= step

    _draw(f"PROGRESS REPORT No. {rep.get('report_no', '')} — PO {po}", bold=True, size=13, step=18)
    _draw(f"Project: {rec.get('project') or ''} | Contract: {rep.get('contract_no') or 'N/A'} | Vendor: {rep.get('vendor_name') or ''}", size=9)
    _draw(f"Period: {rep.get('period_from') or '-'} to {rep.get('period_to') or '-'} | Status: {rep.get('status')}", size=9, step=16)

    sum_d = rep.get("po_summary") or {}
    _draw("1. PO SUMMARY (Planned vs Actual)", bold=True, size=10, step=15)
    for k in ("engineering", "procurement", "manufacturing", "delivery", "overall"):
        _draw(f"   - {k.title()}: Planned {(sum_d.get(k) or {}).get('planned', 0)}% | Actual {(sum_d.get(k) or {}).get('actual', 0)}%")
    _draw("2. AREAS OF CONCERN", bold=True, size=10, step=15)
    _draw(f"   {rep.get('areas_of_concern') or 'None reported.'}")
    _draw("3. ENGINEERING DETAIL (13 SDR Categories)", bold=True, size=10, step=15)
    for item in (rep.get("engineering_detail") or {}).get("docs_13") or _default_eng_13_docs(rec):
        _draw(f"   {item.get('sr')}. {item.get('category')}: {item.get('submitted_qty', 0)} docs | {item.get('remarks', '')}", size=8, step=11)
    _draw(f"4. PROCUREMENT SUB-ORDERS ({len(sub_rows)} tracked)", bold=True, size=10, step=15)
    for sr in sub_rows[:12]:
        _draw(f"   - {sr.get('vendor')}: {sr.get('material')} ({sr.get('sub_po_no') or 'Enquiry'}) FC: {sr.get('forecast_delivery') or '-'}", size=8, step=11)
    _draw("5. MANUFACTURING STATUS", bold=True, size=10, step=15)
    _draw(f"   {(rep.get('manufacturing_detail') or {}).get('status_notes') or 'Per shop schedule.'}")
    _draw("6. DELIVERY STATUS & 7. ATTACHMENTS", bold=True, size=10, step=15)
    att = rep.get("attachments") or {}
    _draw(f"   Schedule Attached: {'YES' if att.get('schedule_attached') else 'NO'} | Sub-Order Annexure: {'YES' if att.get('suborder_status_attached') else 'NO'}")

    c_pdf.save()
    return Response(
        content=buf.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{po}_Progress_Report_{rep.get("report_no", "01")}.pdf"'},
    )


@router.post("/api/v1/vendor/mrb-spir")
def update_mrb_spir_and_closeout(
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(
        require_roles("admin", "vendor", "expediting_manager", "expeditor", "doc_expeditor", "qc_manager")
    ),
):
    po_num = str(payload.get("po_number") or payload.get("po") or "").strip()
    if not po_num:
        raise HTTPException(status_code=400, detail="po_number required")
    eff = effective_role(current_user)
    with LOCK, sx_db() as c:
        L = _records(c)
        rec = next((r for r in L if str(r.get("po")) == po_num), None)
        if not rec:
            raise HTTPException(status_code=404, detail=f"PO {po_num} not found")
        if is_vendor_user(current_user) and not vendor_owns_po(current_user, rec):
            raise HTTPException(status_code=403, detail=f"Not authorized for PO {po_num}")
        if not is_admin_user(current_user) and not user_can_access_po(current_user, rec):
            raise HTTPException(status_code=403, detail=f"Not authorized for PO {po_num}")

        close = rec.setdefault("close", {})
        if payload.get("mrb_submitted_on"):
            close["mrbSubOn"] = str(payload["mrb_submitted_on"])[:10]
        if payload.get("spir_submitted_on"):
            close["spirSubOn"] = str(payload["spir_submitted_on"])[:10]
        if not is_vendor_user(current_user):
            if payload.get("mrb_approved_on"):
                close["mrbApprOn"] = str(payload["mrb_approved_on"])[:10]
            if payload.get("final_invoice_paid_on") and eff in ("admin", "expediting_manager", "expeditor"):
                close["finalInvoicePaidOn"] = str(payload["final_invoice_paid_on"])[:10]
            if payload.get("ld_settled") and eff in ("admin", "expediting_manager"):
                ld = rec.setdefault("ld", {})
                ld.setdefault("steps", {})["Settled with supplier"] = time.strftime("%Y-%m-%d")

        cs = _compute_closeout_status(rec)
        rec["close_state"] = cs
        _save_records(c, L, _who(None, current_user), f"Updated MRB/SPIR Closeout ({cs['stage_label']}) on {po_num}")
    return {"ok": True, "po": po_num, "closeout": cs}


# ---------------------------------------------------------------------------
# PHASE 2B: Consolidated Project-Wide Weekly MSSR & Critical Management Export
# ---------------------------------------------------------------------------

def _collect_consolidated_mssr(project_id: Optional[str], current_user: Dict[str, Any]) -> Dict[str, Any]:
    accessible_pids = _get_accessible_pids_for_user(current_user)
    today = date.today()
    with LOCK, sx_db() as c:
        L = _records(c)
        sx_state = _get_sx_state(c)

    filtered = [
        rec for rec in L
        if _allowed_po_record(rec, current_user, project_id=project_id, accessible_pids=accessible_pids)
    ]
    concerns = sx_state.get("concerns") or []
    po_rows = []
    slip_rows = []
    aoc_rows = []
    neas_items = []

    for rec in filtered:
        po = str(rec.get("po") or "")
        sync = _build_synchronized_9col_schedule(rec)
        docs = _ensure_vdrl_docs(rec)
        overdue_docs = sum(
            1 for d in docs
            if d.get("code") == "Code 3" or (
                _parse_date_safe(d.get("planned_date")) and _parse_date_safe(d.get("planned_date")) < today
                and not d.get("actual_date") and d.get("code") not in ("Code 1", "Code 2")
            )
        )
        crit_subs = sum(
            1 for raw_sr in ((rec.get("plan") or {}).get("rows") or [])
            if isinstance(raw_sr, dict) and not raw_sr.get("deleted") and (
                (sr := _normalize_suborder_row(raw_sr)).get("critical")
                or (_parse_date_safe(sr.get("forecast_delivery")) and _parse_date_safe(sr.get("req_delivery"))
                    and _parse_date_safe(sr.get("forecast_delivery")) > _parse_date_safe(sr.get("req_delivery")))
            )
        )
        slipped = [
            r for r in sync["rows"]
            if r.get("fE") and r.get("bE") and str(r["fE"])[:10] > str(r["bE"])[:10]
        ]
        for sr in slipped:
            slip_rows.append({
                "po": po,
                "supplier": rec.get("supplierShort") or rec.get("supplier") or "",
                "activity": sr.get("act"),
                "baseline_end": sr.get("bE"),
                "forecast_end": sr.get("fE"),
                "slip_days": _days_between(sr.get("bE"), sr.get("fE")) or 0,
            })

        po_concerns = [cn for cn in concerns if str(cn.get("po")) == po and cn.get("status") != "CLOSED"]
        for cn in po_concerns:
            aoc_rows.append({
                "po": po,
                "supplier": rec.get("supplierShort") or rec.get("supplier") or "",
                "ref": cn.get("no") or cn.get("id"),
                "impact": cn.get("impact") or "MEDIUM",
                "issue": cn.get("issue") or "",
                "status": cn.get("status") or "OPEN",
            })

        ack = rec.get("ackx") or {}
        ack_st = ack.get("st") or ("Unconditional" if rec.get("ackDate") else "Pending")
        vprs = rec.get("vpr_reports") or []
        latest_vpr = vprs[-1] if vprs else None
        closeout = _compute_closeout_status(rec)

        clr = rec.get("clr") or {}
        for it in (rec.get("items") or []):
            if it.get("is_split_parent"):
                continue
            ik = str(it.get("item") or "")
            ce = clr.get(ik) or {}
            neas_items.append({
                "po": po,
                "item": ik,
                "desc": it.get("desc") or "",
                "qty": it.get("qty") or 0,
                "unit": it.get("unit") or "EA",
                "cdd_date": it.get("cdd_date") or rec.get("cdd_date") or "",
                "ros_date": it.get("ros_date") or rec.get("ros_date") or "",
                "platform": it.get("platform") or rec.get("platform") or "",
                "despatch_location": it.get("despatch_location") or rec.get("despatch_location") or rec.get("deliveryPoint") or "",
                "irn_qty": ce.get("irn") or 0,
                "ship_qty": ce.get("ship") or 0,
                "mrv_qty": ce.get("mrv") or 0,
            })

        po_rows.append({
            "po": po,
            "project_code": rec.get("project_code") or "",
            "supplier": rec.get("supplierShort") or rec.get("supplier") or "",
            "head": rec.get("head") or "",
            "procurement_class": _infer_procurement_class(rec),
            "platform": rec.get("platform") or "",
            "despatch_location": rec.get("despatch_location") or rec.get("deliveryPoint") or "",
            "cdd_date": rec.get("cdd_date") or "",
            "ros_date": rec.get("ros_date") or "",
            "ack_status": ack_st,
            "buyer_escalation": bool(ack.get("buyer_escalation_required")),
            "slipped_tasks": len(slipped),
            "critical_suborders": crit_subs,
            "overdue_docs": overdue_docs,
            "open_concerns": len(po_concerns),
            "latest_vpr": f"#{latest_vpr.get('report_no')} ({latest_vpr.get('status')})" if latest_vpr else "None",
            "closeout_stage": closeout["stage_label"],
            "mrv_pct": closeout["mrv_pct"],
            "ai_reviewed": bool(rec.get("ai_mr_review")),
        })

    return {
        "ok": True,
        "generated_at": time.strftime("%Y-%m-%d %H:%M"),
        "kpis": {
            "total_pos": len(po_rows),
            "pos_with_slips": sum(1 for r in po_rows if r["slipped_tasks"] > 0),
            "open_concerns": len(aoc_rows),
            "buyer_ack_escalations": sum(1 for r in po_rows if r["buyer_escalation"]),
            "technically_closed": sum(1 for r in po_rows if r["closeout_stage"] in ("Technically Closed", "Commercially Closed")),
        },
        "po_rows": po_rows,
        "slip_rows": slip_rows,
        "aoc_rows": aoc_rows,
        "neas_items": neas_items,
    }


@router.get("/api/v1/expediting/mssr/consolidated")
def get_consolidated_weekly_mssr(
    project_id: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(
        require_roles("admin", "expediting_manager", "expeditor", "field_expeditor", "doc_expeditor", "qc_manager", "inspection_engineer")
    ),
):
    return _collect_consolidated_mssr(project_id, current_user)


@router.get("/api/v1/expediting/mssr/export-xlsx")
def export_consolidated_mssr_xlsx(
    project_id: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(
        require_roles("admin", "expediting_manager", "expeditor", "field_expeditor", "doc_expeditor", "qc_manager", "inspection_engineer")
    ),
):
    import openpyxl
    from openpyxl.styles import Font, PatternFill

    data = _collect_consolidated_mssr(project_id, current_user)
    wb = openpyxl.Workbook()

    def _write_sheet(ws, title: str, headers: List[str], rows: List[List[Any]]):
        ws.title = title
        ws.append(headers)
        fill = PatternFill("solid", fgColor="1E3A8A")
        font = Font(color="FFFFFF", bold=True, size=10)
        for i in range(1, len(headers) + 1):
            c = ws.cell(row=1, column=i)
            c.fill = fill
            c.font = font
        for r in rows:
            ws.append(r)

    _write_sheet(
        wb.active,
        "Executive MSSR Summary",
        ["PO #", "Project", "Supplier", "Class", "Platform", "Despatch Location", "CDD", "ROS Date", "PO Ack", "Slips", "Crit Sub-Orders", "Overdue Docs", "Open AOC", "Latest VPR", "MRV %", "Closeout"],
        [
            [r["po"], r["project_code"], r["supplier"], r["procurement_class"], r["platform"], r["despatch_location"], r["cdd_date"], r["ros_date"], r["ack_status"], r["slipped_tasks"], r["critical_suborders"], r["overdue_docs"], r["open_concerns"], r["latest_vpr"], f"{r['mrv_pct']}%", r["closeout_stage"]]
            for r in data["po_rows"]
        ],
    )
    _write_sheet(
        wb.create_sheet(),
        "Critical Schedule Slips",
        ["PO #", "Supplier", "Activity", "Baseline Finish", "Forecast Finish", "Slip (days)"],
        [[s["po"], s["supplier"], s["activity"], s["baseline_end"], s["forecast_end"], s["slip_days"]] for s in data["slip_rows"]],
    )
    _write_sheet(
        wb.create_sheet(),
        "Areas of Concern",
        ["PO #", "Supplier", "Ref", "Impact", "Issue Description", "Status"],
        [[a["po"], a["supplier"], a["ref"], a["impact"], a["issue"], a["status"]] for a in data["aoc_rows"]],
    )
    _write_sheet(
        wb.create_sheet(),
        "NEAS Item Delivery Matrix",
        ["PO #", "Item #", "Description", "Qty", "Unit", "CDD", "ROS Date", "Platform", "Despatch Location", "Released (IRN)", "Shipped", "MRV"],
        [[n["po"], n["item"], n["desc"], n["qty"], n["unit"], n["cdd_date"], n["ros_date"], n["platform"], n["despatch_location"], n["irn_qty"], n["ship_qty"], n["mrv_qty"]] for n in data["neas_items"]],
    )

    buf = io.BytesIO()
    wb.save(buf)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="Consolidated_Weekly_MSSR_{time.strftime("%Y%m%d")}.xlsx"'},
    )


# ---------------------------------------------------------------------------
# PHASE 3: AI Agents (Action #2 PO/MR Review & Action #3 First Expediting Contact)
# ---------------------------------------------------------------------------

@router.post("/api/v1/po/{po}/ai-review-mr")
async def ai_review_po_and_mr(
    po: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(
        require_roles("admin", "expediting_manager", "expeditor", "doc_expeditor", "qc_manager", "inspection_engineer")
    ),
):
    po_num = str(po or "").strip()
    ctype = (request.headers.get("content-type") or "").lower()
    pdf_bytes: Optional[bytes] = None
    filename = f"{po_num}_PO_MR.pdf"
    extra_notes = ""

    if "multipart/form-data" in ctype:
        form = await request.form()
        up = form.get("file") or form.get("pdf")
        extra_notes = str(form.get("notes") or "")
        if up is not None and hasattr(up, "read"):
            pdf_bytes = await up.read(settings.upload_max_bytes + 1)
            if len(pdf_bytes) > settings.upload_max_bytes:
                raise HTTPException(status_code=413, detail="Uploaded PDF exceeds maximum size limit")
            filename = getattr(up, "filename", None) or filename
    else:
        try:
            body = await request.json()
            if isinstance(body, dict):
                extra_notes = str(body.get("notes") or body.get("mr_text") or "")
        except Exception:
            pass

    with LOCK, sx_db() as c:
        rec = next((r for r in _records(c) if str(r.get("po")) == po_num), None)
        if not rec:
            raise HTTPException(status_code=404, detail=f"PO {po_num} not found")
        if not user_can_access_po(current_user, rec):
            raise HTTPException(status_code=403, detail=f"Access denied for PO {po_num}")

    context_summary = json.dumps({
        "po": po_num,
        "head": rec.get("head"),
        "supplier": rec.get("supplier"),
        "mr_ref": rec.get("mrRef"),
        "incoterm": rec.get("incoterm"),
        "cdd_date": rec.get("cdd_date"),
        "ros_date": rec.get("ros_date"),
        "platform": rec.get("platform"),
        "despatch_location": rec.get("despatch_location"),
        "pbg_required": rec.get("pbg_required"),
        "lc_required": rec.get("lc_required"),
        "items": (rec.get("items") or [])[:25],
        "expeditor_notes": extra_notes,
    }, indent=2)

    review = await run_in_threadpool(
        ai_service.analyze_po_and_mr,
        pdf_bytes=pdf_bytes,
        filename=filename,
        po_context_text=context_summary,
        po_number=po_num,
        mr_ref=str(rec.get("mrRef") or ""),
    )
    review["reviewed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    review["reviewed_by"] = current_user.get("email")

    with LOCK, sx_db() as c:
        L = _records(c)
        target = next((r for r in L if str(r.get("po")) == po_num), None)
        if target:
            target["ai_mr_review"] = review
            mrx = target.setdefault("mrx", {})
            for k, val in (review.get("checklist_flags") or {}).items():
                if val:
                    mrx[k] = True
            _save_records(c, L, _who(None, current_user), f"AI Agent PO/MR Review completed on {po_num}")

    record_audit_event("po", po_num, "AI_PO_MR_REVIEW", actor=current_user, after={"engine": review.get("engine")})
    return {"ok": True, "po": po_num, "review": review}


@router.post("/api/v1/po/{po}/ai-first-contact")
async def ai_generate_first_contact(
    po: str,
    payload: Dict[str, Any] = Body({}),
    current_user: Dict[str, Any] = Depends(
        require_roles("admin", "expediting_manager", "expeditor", "doc_expeditor")
    ),
):
    po_num = str(po or "").strip()
    mark_sent = bool(payload.get("mark_sent"))
    issue_vdms_access = bool(payload.get("issue_vdms_access"))

    with LOCK, sx_db() as c:
        rec = next((r for r in _records(c) if str(r.get("po")) == po_num), None)
        if not rec:
            raise HTTPException(status_code=404, detail=f"PO {po_num} not found")
        if not user_can_access_po(current_user, rec):
            raise HTTPException(status_code=403, detail=f"Access denied for PO {po_num}")

    proj = inspectflow_db.get_project(rec.get("project_id")) if rec.get("project_id") else None
    draft = await run_in_threadpool(
        ai_service.draft_first_expediting_contact,
        rec,
        rec.get("ai_mr_review"),
        proj,
        current_user.get("full_name") or current_user.get("email") or "Package Expeditor",
    )
    if payload.get("subject"):
        draft["subject"] = str(payload["subject"])
    if payload.get("body"):
        draft["body"] = str(payload["body"])

    with LOCK, sx_db() as c:
        L = _records(c)
        target = next((r for r in L if str(r.get("po")) == po_num), None)
        if target:
            target["first_contact_draft"] = draft
            if mark_sent:
                now_d = time.strftime("%Y-%m-%d")
                target["intro"] = {
                    "sentOn": now_d,
                    "by": current_user.get("email"),
                    "subject": draft["subject"],
                    "body": draft["body"],
                }
                target["kickoffOn"] = target.get("kickoffOn") or now_d
            if issue_vdms_access:
                target["dc"] = {
                    "on": time.strftime("%Y-%m-%d"),
                    "by": current_user.get("email"),
                }
            _save_records(c, L, _who(None, current_user), f"AI First Expediting Contact {'Sent' if mark_sent else 'Drafted'} on {po_num}")

    record_audit_event("po", po_num, "AI_FIRST_CONTACT", actor=current_user, after={"sent": mark_sent, "vdms_issued": issue_vdms_access})
    return {"ok": True, "po": po_num, "draft": draft, "sent": mark_sent, "vdms_issued": issue_vdms_access}
