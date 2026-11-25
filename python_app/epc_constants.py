from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

ROLES = {
    "PEXM": "PEXM",
    "EXPEDITOR": "EXPEDITOR",
    "DOC_EXPEDITOR": "DOC_EXPEDITOR",
    "VENDOR": "VENDOR",
}

EPC_ROLE_LABELS = {
    "PEXM": "Project Expediting Manager",
    "EXPEDITOR": "Package & Document Expeditor",
    "DOC_EXPEDITOR": "Document Expeditor",
    "VENDOR": "Vendor / Supplier",
}

WBS_CATEGORIES = [
    "PROCUREMENT",
    "ENGINEERING",
    "FABRICATION",
    "ASSEMBLY",
    "TESTING",
    "DELIVERY",
    "CLOSEOUT",
]

STANDARD_ACTIVITIES: List[Dict[str, str]] = [
    {"code": "STD-01", "name": "PO Date / Formal Award", "category": "PROCUREMENT"},
    {"code": "STD-02", "name": "PO Acceptance & Acknowledgment", "category": "PROCUREMENT"},
    {"code": "STD-03", "name": "Submission of Key Drawings / Datasheets", "category": "ENGINEERING"},
    {"code": "STD-04", "name": "Submission of Inspection & Test Plan (ITP)", "category": "ENGINEERING"},
    {"code": "STD-05", "name": "Submission of Sub-Vendor List (SVL)", "category": "PROCUREMENT"},
    {"code": "STD-06", "name": "Submission of Manufacturing & Delivery Schedule", "category": "ENGINEERING"},
    {"code": "STD-07", "name": "Kick-Off Meeting (KOM)", "category": "ENGINEERING"},
    {"code": "STD-08", "name": "Approval of Drawings & Datasheets", "category": "ENGINEERING"},
    {"code": "STD-09", "name": "Approval of ITP & Quality Procedures", "category": "ENGINEERING"},
    {"code": "STD-10", "name": "Pre-Inspection Meeting (PIM)", "category": "ENGINEERING"},
    {"code": "STD-11", "name": "Placement of Major Sub-Orders / Raw Material POs", "category": "PROCUREMENT"},
    {"code": "STD-12", "name": "Receipt of Raw Materials & Components", "category": "PROCUREMENT"},
    {"code": "STD-13", "name": "Start of Fabrication / Manufacturing", "category": "FABRICATION"},
    {"code": "STD-14", "name": "Completion of Prefabrication / Sub-Assemblies", "category": "FABRICATION"},
    {"code": "STD-15", "name": "Mechanical Assembly & Integration", "category": "ASSEMBLY"},
    {"code": "STD-16", "name": "FAT / Hydrotest", "category": "TESTING"},
    {"code": "STD-17", "name": "Punch Point / Defect Closure", "category": "TESTING"},
    {"code": "STD-18", "name": "Inspection Release Note (IRN)", "category": "TESTING"},
    {"code": "STD-19", "name": "Ex-Works Readiness & Packing", "category": "DELIVERY"},
    {"code": "STD-20", "name": "Dispatch / Port Delivery", "category": "DELIVERY"},
    {"code": "STD-21", "name": "Material Arrival at Site / Yard (ROS)", "category": "DELIVERY"},
    {"code": "STD-22", "name": "SPIR Approval", "category": "CLOSEOUT"},
    {"code": "STD-23", "name": "Final MRB Approval", "category": "CLOSEOUT"},
]

CRITICAL_BASELINE_SEQUENCES = {10, 11, 12, 15, 16, 18, 20}

INSPECTION_ACTIVITY_CODES = ["STD-10", "STD-12", "STD-16", "STD-17", "STD-18"]

BULK_STAGES: List[Dict[str, Any]] = [
    {"name": "RAW_MATERIAL_RECEIPT", "label": "Raw Material", "sequence": 1},
    {"name": "ROUGH_MACHINING", "label": "Rough Mach.", "sequence": 2},
    {"name": "TRIM_MACHINING", "label": "Trim Mach.", "sequence": 3},
    {"name": "FINAL_MACHINING", "label": "Final Mach.", "sequence": 4},
    {"name": "ASSEMBLY", "label": "Assembly", "sequence": 5},
    {"name": "NDE_FERRITE_PMI", "label": "NDE / PMI", "sequence": 6},
    {"name": "HYDROTEST", "label": "Hydrotest", "sequence": 7},
    {"name": "SURFACE_PREP", "label": "Coating", "sequence": 8},
    {"name": "CERT_32_ISSUANCE", "label": "3.2 Cert", "sequence": 9},
    {"name": "DISPATCH", "label": "Dispatch", "sequence": 10},
]

INSPECTION_TYPE_LABELS = {
    "HOLD": "Hold Point (H)",
    "WITNESS": "Witness Point (W)",
    "REVIEW": "Document Review (R)",
}

WBS_CATEGORY_COLORS = {
    "PROCUREMENT": {"bg": "#dbeafe", "text": "#1d4ed8"},
    "ENGINEERING": {"bg": "#e0e7ff", "text": "#4338ca"},
    "FABRICATION": {"bg": "#fef3c7", "text": "#b45309"},
    "ASSEMBLY": {"bg": "#fae8ff", "text": "#86198f"},
    "TESTING": {"bg": "#f3e8ff", "text": "#6b21a8"},
    "DELIVERY": {"bg": "#dcfce7", "text": "#15803d"},
    "SHIPPING": {"bg": "#dcfce7", "text": "#15803d"},
    "CLOSEOUT": {"bg": "#f1f5f9", "text": "#334155"},
}

PO_STATUS_COLORS = {
    "ACTIVE": {"bg": "#dbeafe", "text": "#1d4ed8", "border": "#bfdbfe"},
    "AT_RISK": {"bg": "#fef3c7", "text": "#b45309", "border": "#fde68a"},
    "DELAYED": {"bg": "#fee2e2", "text": "#b91c1c", "border": "#fecaca"},
    "COMPLETED": {"bg": "#dcfce7", "text": "#15803d", "border": "#bbf7d0"},
    "ON_HOLD": {"bg": "#f1f5f9", "text": "#475569", "border": "#e2e8f0"},
}

RAIL_STATUS_COLORS = {
    "OPEN": {"bg": "#fee2e2", "text": "#b91c1c"},
    "PENDING_REVIEW": {"bg": "#fef3c7", "text": "#b45309"},
    "CLOSED": {"bg": "#dcfce7", "text": "#15803d"},
}

RAIL_IMPACT_COLORS = {
    "CRITICAL": {"bg": "#fee2e2", "text": "#991b1b"},
    "HIGH": {"bg": "#fee2e2", "text": "#991b1b"},
    "MAJOR": {"bg": "#ffedd5", "text": "#9a3412"},
    "MEDIUM": {"bg": "#fef3c7", "text": "#92400e"},
    "MINOR": {"bg": "#f1f5f9", "text": "#475569"},
    "LOW": {"bg": "#f1f5f9", "text": "#475569"},
    "NO_IMPACT": {"bg": "#dcfce7", "text": "#166534"},
}

APPROVAL_CODE_LABELS = {
    "UNDER_REVIEW": "Under Review",
    "PENDING": "Pending Review",
    "CODE_1": "Code 1 — Approved",
    "CODE_2": "Code 2 — Approved w/ Comments",
    "CODE_3_REJECTED": "Code 3 — Revise & Resubmit",
    "APPROVED": "Approved (Final)",
}

APPROVAL_CODE_COLORS = {
    "UNDER_REVIEW": {"bg": "#fef3c7", "text": "#92400e"},
    "PENDING": {"bg": "#f1f5f9", "text": "#475569"},
    "CODE_1": {"bg": "#dcfce7", "text": "#166534"},
    "CODE_2": {"bg": "#dbeafe", "text": "#1e40af"},
    "CODE_3_REJECTED": {"bg": "#fee2e2", "text": "#991b1b"},
    "APPROVED": {"bg": "#dcfce7", "text": "#15803d"},
}

INSPECTION_STATUS_COLORS = {
    "SUBMITTED": {"bg": "#fef3c7", "text": "#b45309"},
    "PENDING": {"bg": "#fef3c7", "text": "#b45309"},
    "ACKNOWLEDGED": {"bg": "#dbeafe", "text": "#1d4ed8"},
    "COMPLETED": {"bg": "#dcfce7", "text": "#15803d"},
    "CANCELLED": {"bg": "#f1f5f9", "text": "#64748b"},
}

FLOAT_BADGE = {
    "ON_TRACK": {"bg": "#dcfce7", "text": "#15803d", "border": "#bbf7d0"},
    "WARNING": {"bg": "#fef3c7", "text": "#b45309", "border": "#fde68a"},
    "CRITICAL_DELAY": {"bg": "#fee2e2", "text": "#b91c1c", "border": "#fecaca"},
}

DISCIPLINES = [
    "MECHANICAL",
    "ELECTRICAL",
    "INSTRUMENTATION",
    "STRUCTURAL",
    "PROCESS",
    "CIVIL",
]

RAIL_CATEGORIES = ["ENGINEERING", "PROCUREMENT", "QUALITY", "SUB_VENDOR", "COMMERCIAL"]
RAIL_ACTION_BY = ["VENDOR", "EPC_EXPEDITOR", "ENGINEERING", "CLIENT"]
RAIL_IMPACTS = ["CRITICAL", "MAJOR", "MINOR", "NO_IMPACT"]
RAIL_STATUSES = ["OPEN", "PENDING_REVIEW", "CLOSED"]


def parse_iso_date(val: Any) -> Optional[date]:
    if not val:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    s = str(val).strip()
    if not s or s == "—":
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def format_date_gb(val: Any) -> str:
    d = parse_iso_date(val)
    if not d:
        return "—"
    return d.strftime("%d %b %Y")


def days_from_now(val: Any) -> Optional[int]:
    d = parse_iso_date(val)
    if not d:
        return None
    return (d - date.today()).days


def calc_float(
    forecast_delivery_date: Any, transit_time_days: Any = 0, raw_date: Any = None
) -> Tuple[Optional[int], Optional[str], str]:
    """
    Returns (float_days, expected_arrival_workshop_iso, delay_status).
    Rules from §8.1:
      arrival = forecast_delivery_date + transit_time_days
      float   = round((raw_date - arrival) / 1 day)
      < 0     -> CRITICAL_DELAY
      0..14   -> WARNING
      > 14    -> ON_TRACK
      null    -> ON_TRACK
    """
    f_date = parse_iso_date(forecast_delivery_date)
    r_date = parse_iso_date(raw_date)
    try:
        t_days = int(transit_time_days or 0)
    except Exception:
        t_days = 0

    arrival_date = (f_date + timedelta(days=t_days)) if f_date else None
    arrival_iso = arrival_date.isoformat() if arrival_date else None

    if not arrival_date or not r_date:
        return None, arrival_iso, "ON_TRACK"

    flt = (r_date - arrival_date).days
    if flt < 0:
        status = "CRITICAL_DELAY"
    elif flt <= 14:
        status = "WARNING"
    else:
        status = "ON_TRACK"
    return flt, arrival_iso, status


def calc_vdrl_sla(
    actual_submission_date: Any,
    planned_submission_date: Any,
    epc_review_due_date: Any,
    actual_return_date: Any,
) -> Tuple[str, int, bool]:
    """
    Contractual review window = 14 days from submission (§8.2).
    Returns (due_date_iso, delay_days, is_overdue).
    """
    today = date.today()
    sub_d = parse_iso_date(actual_submission_date) or parse_iso_date(planned_submission_date) or today
    due_d = parse_iso_date(epc_review_due_date) or (sub_d + timedelta(days=14))
    ret_d = parse_iso_date(actual_return_date)

    is_overdue = (ret_d is None) and (due_d < today)
    if not ret_d:
        delay_days = max(0, (today - due_d).days) if due_d < today else 0
    else:
        delay_days = max(0, (ret_d - due_d).days)

    return due_d.isoformat(), delay_days, is_overdue


def build_scurve(activities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    S-Curve calculation (§6.1):
    Bucket every activity by the month of its baseline_finish;
    add 100 to planned and percent_complete to actual;
    accumulate and divide by total activities.
    """
    valid = [a for a in activities if parse_iso_date(a.get("baseline_finish"))]
    if not valid:
        return []

    total = len(valid)
    months: Dict[str, Dict[str, float]] = {}
    for a in valid:
        bf = parse_iso_date(a.get("baseline_finish"))
        if not bf:
            continue
        key = bf.strftime("%Y-%m")
        if key not in months:
            months[key] = {"planned": 0.0, "actual": 0.0}
        months[key]["planned"] += 100.0
        months[key]["actual"] += float(a.get("percent_complete") or 0.0)

    cum_p = 0.0
    cum_a = 0.0
    series = []
    for key in sorted(months.keys()):
        m = months[key]
        cum_p += m["planned"] / total
        cum_a += m["actual"] / total
        series.append(
            {
                "month": key,
                "planned": round(min(100.0, cum_p), 1),
                "actual": round(min(100.0, cum_a), 1),
                "Month": key,
                "Planned %": round(min(100.0, cum_p), 1),
                "Actual %": round(min(100.0, cum_a), 1),
            }
        )
    return series
