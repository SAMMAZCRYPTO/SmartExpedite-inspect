import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend_v2.core.config import settings
from backend_v2.core.database import SessionLocal, init_v2_tables
from backend_v2.core.security import (
    effective_role,
    get_current_user,
    is_admin_user,
    is_vendor_user,
    require_roles,
    user_can_access_po,
    user_can_access_project_id,
    vendor_owns_po,
)
from backend_v2.models.epc_models import DocumentRecord
from backend_v2.routers.ai import router as ai_router
from backend_v2.routers.auth import router as auth_router
from backend_v2.routers.storage import (
    _authorize_document_record,
    _authorize_legacy_path,
    router as storage_router,
    save_validated_upload,
)
from backend_v2.services.audit_service import record_audit_event
from python_app import database as db
from python_app import expediting_db
from python_app.epc_constants import build_scurve
from python_app.expediting_parsers import (
    build_sample_schedule_excel,
    parse_suborder_report_file,
    parse_vendor_schedule_file,
)

app = FastAPI(title="InspectFlow + SmartExpedit EPC API", version="2.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


db.init_db()
init_v2_tables()
expediting_db.init_expediting_tables()

app.include_router(auth_router)
app.include_router(storage_router)
app.include_router(ai_router)

_SAFE_INLINE_UPLOAD_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}


@app.get("/uploads/{bucket}/{file_path:path}")
def serve_protected_upload(
    bucket: str,
    file_path: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    if (
        ".." in bucket
        or ".." in file_path
        or "\\" in bucket
        or "\\" in file_path
        or ":" in bucket
        or ":" in file_path
        or bucket.startswith("/")
        or file_path.startswith("/")
    ):
        raise HTTPException(status_code=400, detail="Invalid upload path")
    target = (db.UPLOADS_DIR / bucket / file_path).resolve()
    root_resolved = db.UPLOADS_DIR.resolve()
    if root_resolved not in target.parents:
        raise HTTPException(status_code=400, detail="Invalid upload path")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Uploaded file not found")

    _authorize_legacy_path(current_user, bucket, file_path)

    ext = target.suffix.lower()
    disp = "inline" if ext in _SAFE_INLINE_UPLOAD_EXTS else "attachment"
    safe_name = target.name.replace('"', "")
    return FileResponse(
        path=str(target),
        headers={
            "Content-Disposition": f'{disp}; filename="{safe_name}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


def _agency_ids_for_user(user: Dict[str, Any]) -> set[str]:
    uemail = str(user.get("email") or "").strip().lower()
    ucomp = str(user.get("company_affiliation") or user.get("company") or "").strip().lower()
    matched = set()
    for a in db.list_agencies():
        if (
            (uemail and str(a.get("manager_email") or "").strip().lower() == uemail)
            or (ucomp and str(a.get("name") or "").strip().lower() == ucomp)
        ):
            matched.add(str(a["id"]).strip().lower())
    return matched


def _filter_inspections_for_user(
    items: list, user: Dict[str, Any], project_id: Optional[str] = None
) -> list:
    if project_id and str(project_id).strip().lower() != "all":
        norm_pid = str(project_id).strip().lower()
        items = [i for i in items if str(i.get("project_id") or "").strip().lower() == norm_pid]

    eff_role = effective_role(user)
    if eff_role in ("", "guest"):
        return []
    if is_admin_user(user):
        return items

    uemail = str(user.get("email") or "").strip().lower()
    uid = str(user.get("id") or "").strip().lower()

    if is_vendor_user(user):
        from python_app.smartexpedit_server import LOCK, sx_db, _records

        with LOCK, sx_db() as c:
            po_map = {str(r.get("po")): r for r in _records(c)}
        allowed = []
        for insp in items:
            po_num = str(insp.get("po_number") or "")
            po_rec = po_map.get(po_num)
            if po_rec and vendor_owns_po(user, po_rec):
                allowed.append(insp)
            elif not po_rec and uemail and str(insp.get("created_by") or "").strip().lower() == uemail:
                allowed.append(insp)
        return allowed

    accessible_pids = {
        str(p["id"]).strip().lower()
        for p in db.list_projects()
        if db.user_has_project_access(user, p)
    }

    if eff_role == "inspector":
        my_inspector = next(
            (
                ins
                for ins in db.list_inspectors()
                if (uemail and str(ins.get("email") or "").strip().lower() == uemail)
                or (uid and str(ins.get("user_id") or "").strip().lower() == uid)
            ),
            None,
        )
        my_ins_id = str(my_inspector["id"]).strip().lower() if my_inspector else ""
        return [
            insp
            for insp in items
            if (my_ins_id and str(insp.get("assigned_inspector_id") or "").strip().lower() == my_ins_id)
            or (uemail and str(insp.get("assigned_inspector_email") or "").strip().lower() == uemail)
        ]

    if eff_role == "inspection_agency":
        aids = _agency_ids_for_user(user)
        agency_insp_ids = {
            str(ins["id"]).strip().lower()
            for ins in db.list_inspectors()
            if str(ins.get("tpi_agency_id") or "").strip().lower() in aids
        }
        return [
            insp
            for insp in items
            if (
                str(insp.get("tpi_agency_id") or "").strip().lower() in aids
                or str(insp.get("assigned_inspector_id") or "").strip().lower() in agency_insp_ids
            )
            and (not accessible_pids or str(insp.get("project_id") or "").strip().lower() in accessible_pids or not insp.get("project_id"))
        ]

    return [
        insp
        for insp in items
        if str(insp.get("project_id") or "").strip().lower() in accessible_pids
        or (uemail and str(insp.get("created_by") or "").strip().lower() == uemail)
        or (uemail and str(insp.get("assigned_inspection_engineer_email") or "").strip().lower() == uemail)
        or (uemail and str(insp.get("assigned_expeditor_email") or "").strip().lower() == uemail)
    ]


# ── Inspections ──────────────────────────────────────────────────────────────

def _validate_and_normalize_inspector(
    payload: Dict[str, Any],
    *,
    require_presence: bool = False,
) -> None:
    """Enforce that any inspector assigned to or attending an inspection is active & registered in Inspectors."""
    insp_id = str(payload.get("assigned_inspector_id") or payload.get("inspector_id") or "").strip()
    insp_email = str(payload.get("assigned_inspector_email") or payload.get("inspector_email") or "").strip().lower()
    insp_name = str(payload.get("assigned_inspector_name") or "").strip()
    has_any_ref = bool(insp_id or insp_email or insp_name)
    if not has_any_ref and not require_presence:
        return
    if not has_any_ref and require_presence:
        raise HTTPException(
            status_code=400,
            detail="Only registered active inspectors in the Inspectors directory can attend an inspection.",
        )

    all_inspectors = db.list_inspectors()
    matched = None
    if insp_id:
        matched = next(
            (i for i in all_inspectors if str(i.get("id") or "").strip().lower() == insp_id.lower()),
            None,
        )
    if not matched and insp_email:
        matched = next(
            (i for i in all_inspectors if str(i.get("email") or "").strip().lower() == insp_email),
            None,
        )
    if not matched:
        raise HTTPException(
            status_code=400,
            detail="Unregistered inspector: every inspector attending or assigned to an inspection must first be registered in the Inspectors directory.",
        )
    if str(matched.get("status") or "active").strip().lower() != "active":
        raise HTTPException(
            status_code=400,
            detail=f"Inspector '{matched.get('full_name') or matched.get('email')}' has status '{matched.get('status')}' and cannot attend or be assigned until marked active.",
        )

    canonical_name = matched.get("full_name") or matched.get("name") or matched.get("email")
    canonical_email = matched.get("email")
    canonical_phone = matched.get("phone")
    if "inspector_id" in payload or require_presence:
        payload["inspector_id"] = matched["id"]
    if (
        "assigned_inspector_id" in payload
        or "assigned_inspector_email" in payload
        or "assigned_inspector_name" in payload
        or not require_presence
    ):
        payload["assigned_inspector_id"] = matched["id"]
        payload["assigned_inspector_name"] = canonical_name
        payload["assigned_inspector_email"] = canonical_email
        if canonical_phone is not None:
            payload["assigned_inspector_phone"] = canonical_phone
        if matched.get("tpi_agency_id") and not payload.get("tpi_agency_id"):
            payload["tpi_agency_id"] = matched["tpi_agency_id"]
        if matched.get("company") and not payload.get("tpi_agency"):
            payload["tpi_agency"] = matched["company"]


@app.get("/api/Inspections")
def get_inspections(
    project_id: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    return _filter_inspections_for_user(db.list_inspections(), current_user, project_id=project_id)


@app.get("/api/Inspections/{inspection_id}")
def get_inspection(inspection_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    item = db.get_inspection(inspection_id)
    if not item:
        raise HTTPException(status_code=404, detail="Inspection not found")
    if not _filter_inspections_for_user([item], current_user):
        raise HTTPException(status_code=403, detail="Access denied: inspection is outside your scope")
    return item


@app.post("/api/Inspections", status_code=201)
def create_inspection(
    request: Request,
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(
        require_roles("admin", "qc_manager", "inspection_engineer", "expediting_manager", "expeditor", "doc_expeditor", "vendor")
    ),
):
    clean_payload = dict(payload)
    if str(clean_payload.get("project_id") or "").strip().lower() == "all":
        clean_payload["project_id"] = None
    if str(clean_payload.get("status") or "").strip().lower() == "finalized":
        raise HTTPException(status_code=400, detail="Inspections cannot be created directly as finalized; issue an IRC instead.")

    po_num = str(clean_payload.get("po_number") or "").strip()
    if is_vendor_user(current_user):
        from python_app.smartexpedit_server import LOCK, sx_db, _records

        with LOCK, sx_db() as c:
            po_rec = next((r for r in _records(c) if str(r.get("po")) == po_num), None)
        if not po_rec or not vendor_owns_po(current_user, po_rec):
            raise HTTPException(status_code=403, detail=f"Vendor is not authorized to create inspections for PO '{po_num}'")
        if not clean_payload.get("project_id") and po_rec.get("project_id"):
            clean_payload["project_id"] = po_rec.get("project_id")
    elif not is_admin_user(current_user):
        pid = clean_payload.get("project_id")
        if pid and not user_can_access_project_id(current_user, pid):
            raise HTTPException(status_code=403, detail="Access denied: target project is not assigned to you")
        if not pid and po_num:
            from python_app.smartexpedit_server import LOCK, sx_db, _records

            with LOCK, sx_db() as c:
                po_rec = next((r for r in _records(c) if str(r.get("po")) == po_num), None)
            if po_rec and not user_can_access_po(current_user, po_rec):
                raise HTTPException(status_code=403, detail="Access denied: PO belongs to an unassigned project")
            if po_rec and po_rec.get("project_id"):
                clean_payload["project_id"] = po_rec.get("project_id")

    # Validate registered active inspector if one is assigned on creation
    _validate_and_normalize_inspector(clean_payload, require_presence=False)

    # Never allow client payload to spoof created_by
    clean_payload["created_by"] = current_user.get("email")
    created = db.create_inspection(clean_payload)
    try:
        from python_app.smartexpedit_server import sync_single_inspection_to_smartexpedit

        sync_single_inspection_to_smartexpedit(created)
    except Exception as e:
        print("Auto-sync create_inspection to SmartExpedit error:", e)
    record_audit_event(
        "inspection",
        created["id"],
        "INSPECTION_CREATED",
        actor=current_user,
        after={"po_number": created.get("po_number"), "notification_number": created.get("notification_number")},
        ip_address=request.client.host if request.client else None,
    )
    return created


@app.put("/api/Inspections/{inspection_id}")
def update_inspection(
    inspection_id: str,
    request: Request,
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(
        require_roles("admin", "qc_manager", "inspection_engineer", "inspector", "inspection_agency", "expeditor", "expediting_manager")
    ),
):
    existing = db.get_inspection(inspection_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Inspection not found")
    if not _filter_inspections_for_user([existing], current_user):
        raise HTTPException(status_code=403, detail="Access denied: inspection is outside your scope")

    eff = effective_role(current_user)
    clean_payload = dict(payload)
    if str(clean_payload.get("project_id") or "").strip().lower() == "all":
        clean_payload.pop("project_id", None)
    if "project_id" in clean_payload and not is_admin_user(current_user):
        if clean_payload["project_id"] and not user_can_access_project_id(current_user, clean_payload["project_id"]):
            raise HTTPException(status_code=403, detail="Cannot reassign inspection to an unassigned project")

    # Enforce IRC gate: cannot jump directly to finalized via generic PUT unless already finalized
    if (
        str(clean_payload.get("status") or "").strip().lower() == "finalized"
        and str(existing.get("status") or "").lower() != "finalized"
    ):
        raise HTTPException(
            status_code=400,
            detail="Inspections can only become 'finalized' through the gated /api/v1/issue-irc workflow.",
        )

    # Enforce registered active inspector whenever inspector assignment fields are set
    _validate_and_normalize_inspector(clean_payload, require_presence=False)

    # Inspectors/agencies/expeditors cannot self-endorse IE approval in inspection_reports
    if "inspection_reports" in clean_payload and eff not in ("admin", "qc_manager", "inspection_engineer"):
        prev_by_url = {
            str(r.get("id") or r.get("url") or idx): r
            for idx, r in enumerate(existing.get("inspection_reports") or [])
            if isinstance(r, dict)
        }
        sanitized_reps = []
        for idx, rep in enumerate(clean_payload.get("inspection_reports") or []):
            if not isinstance(rep, dict):
                continue
            r_copy = dict(rep)
            prev = prev_by_url.get(str(rep.get("id") or rep.get("url") or idx))
            if prev and prev.get("approval_status") == "approved":
                r_copy["approval_status"] = "approved"
            elif r_copy.get("approval_status") == "approved":
                r_copy["approval_status"] = (prev or {}).get("approval_status") or "pending"
            sanitized_reps.append(r_copy)
        clean_payload["inspection_reports"] = sanitized_reps

    updated = db.update_inspection(inspection_id, clean_payload)
    if not updated:
        raise HTTPException(status_code=404, detail="Inspection not found")
    try:
        from python_app.smartexpedit_server import sync_single_inspection_to_smartexpedit

        fresh = db.get_inspection(inspection_id)
        if fresh:
            sync_single_inspection_to_smartexpedit(fresh)
    except Exception as e:
        print("Auto-sync update_inspection to SmartExpedit error:", e)
    record_audit_event(
        "inspection",
        inspection_id,
        "INSPECTION_UPDATED",
        actor=current_user,
        after={"keys": list(clean_payload.keys())},
        ip_address=request.client.host if request.client else None,
    )
    return Response(status_code=204)


@app.delete("/api/Inspections/{inspection_id}")
def delete_inspection(
    inspection_id: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_roles("admin", "qc_manager", "inspection_engineer")),
):
    existing = db.get_inspection(inspection_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Inspection not found")
    if not is_admin_user(current_user) and existing.get("project_id") and not user_can_access_project_id(current_user, existing.get("project_id")):
        raise HTTPException(status_code=403, detail="Access denied: cannot delete inspection from an unassigned project")
    if str(existing.get("status") or "").strip().lower() == "finalized":
        raise HTTPException(
            status_code=400,
            detail="Cannot delete a finalized NOI that already has an issued IRC/IRN release note. Cancel or create a revision instead.",
        )
    if not db.delete_inspection(inspection_id):
        raise HTTPException(status_code=404, detail="Inspection not found")
    try:
        from python_app.smartexpedit_server import remove_inspection_from_smartexpedit

        remove_inspection_from_smartexpedit(existing)
    except Exception as e:
        print("Auto-sync delete_inspection to SmartExpedit error:", e)
    record_audit_event(
        "inspection",
        inspection_id,
        "INSPECTION_DELETED",
        actor=current_user,
        before={"po_number": existing.get("po_number"), "notification_number": existing.get("notification_number")},
        ip_address=request.client.host if request.client else None,
    )
    return Response(status_code=204)


# ── Inspectors ───────────────────────────────────────────────────────────────

def _filter_inspectors_for_user(items: List[Dict[str, Any]], user: Dict[str, Any]) -> List[Dict[str, Any]]:
    eff = effective_role(user)
    if is_admin_user(user) or eff in ("qc_manager", "inspection_engineer", "expediting_manager", "expeditor"):
        return items
    uemail = str(user.get("email") or "").strip().lower()
    uid = str(user.get("id") or "").strip().lower()
    if eff == "inspector":
        return [
            i for i in items
            if (uemail and str(i.get("email") or "").strip().lower() == uemail)
            or (uid and str(i.get("user_id") or "").strip().lower() == uid)
        ]
    if eff == "inspection_agency":
        aids = _agency_ids_for_user(user)
        return [i for i in items if str(i.get("tpi_agency_id") or "").strip().lower() in aids]
    return []


@app.get("/api/Inspectors")
def get_inspectors(
    current_user: Dict[str, Any] = Depends(
        require_roles("admin", "qc_manager", "inspection_engineer", "inspection_agency", "inspector", "expediting_manager", "expeditor")
    )
):
    return _filter_inspectors_for_user(db.list_inspectors(), current_user)


@app.get("/api/Inspectors/{inspector_id}")
def get_inspector(
    inspector_id: str,
    current_user: Dict[str, Any] = Depends(
        require_roles("admin", "qc_manager", "inspection_engineer", "inspection_agency", "inspector", "expediting_manager", "expeditor")
    ),
):
    item = db.get_inspector(inspector_id)
    if not item:
        raise HTTPException(status_code=404, detail="Inspector not found")
    if not _filter_inspectors_for_user([item], current_user):
        raise HTTPException(status_code=403, detail="Access denied: inspector outside your scope")
    return item


@app.post("/api/Inspectors", status_code=201)
def create_inspector(
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(
        require_roles("admin", "qc_manager", "inspection_engineer", "inspection_agency", "inspector")
    ),
):
    eff = effective_role(current_user)
    clean = dict(payload)
    if eff == "inspector":
        # Field inspector may self-onboard ONLY their own inspector profile
        clean["email"] = current_user.get("email")
        clean["user_id"] = current_user.get("id")
        clean.pop("status", None)
    elif eff == "inspection_agency":
        aids = _agency_ids_for_user(current_user)
        if aids:
            clean["tpi_agency_id"] = next(iter(aids)).upper()
    return db.create_inspector(clean)


@app.put("/api/Inspectors/{inspector_id}")
def update_inspector(
    inspector_id: str,
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(
        require_roles("admin", "qc_manager", "inspection_engineer", "inspection_agency", "inspector")
    ),
):
    existing = db.get_inspector(inspector_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Inspector not found")
    eff = effective_role(current_user)
    clean = dict(payload)
    if eff == "inspector":
        uemail = str(current_user.get("email") or "").strip().lower()
        if str(existing.get("email") or "").strip().lower() != uemail and str(existing.get("user_id") or "").strip().lower() != str(current_user.get("id") or "").lower():
            raise HTTPException(status_code=403, detail="Inspectors can only update their own profile")
        clean.pop("status", None)
        clean.pop("tpi_agency_id", None)
        clean.pop("email", None)
    elif eff == "inspection_agency":
        aids = _agency_ids_for_user(current_user)
        if str(existing.get("tpi_agency_id") or "").strip().lower() not in aids:
            raise HTTPException(status_code=403, detail="Cannot edit inspector belonging to another agency")
        clean.pop("tpi_agency_id", None)

    updated = db.update_inspector(inspector_id, clean)
    if not updated:
        raise HTTPException(status_code=404, detail="Inspector not found")
    return Response(status_code=204)


@app.delete("/api/Inspectors/{inspector_id}")
def delete_inspector(
    inspector_id: str,
    current_user: Dict[str, Any] = Depends(require_roles("admin", "qc_manager", "inspection_engineer")),
):
    if not db.delete_inspector(inspector_id):
        raise HTTPException(status_code=404, detail="Inspector not found")
    return Response(status_code=204)


# ── TPI Agencies ─────────────────────────────────────────────────────────────

@app.get("/api/TpiAgencies/performance")
def get_tpi_performance(
    project_id: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(
        require_roles("admin", "qc_manager", "inspection_engineer", "inspection_agency", "expediting_manager")
    ),
):
    if project_id and str(project_id).strip().lower() != "all":
        if not is_admin_user(current_user) and not user_can_access_project_id(current_user, project_id):
            raise HTTPException(status_code=403, detail="Access denied: unassigned project")
    perf = db.get_tpi_performance(project_id=project_id)
    eff = effective_role(current_user)
    if eff == "inspection_agency":
        aids = _agency_ids_for_user(current_user)
        return [a for a in perf if str(a.get("agency_id") or "").strip().lower() in aids]
    return perf


@app.get("/api/TpiAgencies")
def get_agencies(
    current_user: Dict[str, Any] = Depends(
        require_roles("admin", "qc_manager", "inspection_engineer", "inspection_agency", "inspector", "expediting_manager", "expeditor")
    )
):
    agencies = db.list_agencies()
    if effective_role(current_user) == "inspection_agency":
        aids = _agency_ids_for_user(current_user)
        return [a for a in agencies if str(a.get("id") or "").strip().lower() in aids]
    return agencies


@app.get("/api/TpiAgencies/{agency_id}")
def get_agency(
    agency_id: str,
    current_user: Dict[str, Any] = Depends(
        require_roles("admin", "qc_manager", "inspection_engineer", "inspection_agency", "inspector")
    ),
):
    item = db.get_agency(agency_id)
    if not item:
        raise HTTPException(status_code=404, detail="Agency not found")
    if effective_role(current_user) == "inspection_agency":
        if str(item["id"]).strip().lower() not in _agency_ids_for_user(current_user):
            raise HTTPException(status_code=403, detail="Access denied: other TPI agency")
    return item


@app.post("/api/TpiAgencies", status_code=201)
def create_agency(
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(require_roles("admin", "qc_manager")),
):
    return db.create_agency(payload)


@app.put("/api/TpiAgencies/{agency_id}")
def update_agency(
    agency_id: str,
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(require_roles("admin", "qc_manager")),
):
    updated = db.update_agency(agency_id, payload)
    if not updated:
        raise HTTPException(status_code=404, detail="Agency not found")
    return Response(status_code=204)


@app.delete("/api/TpiAgencies/{agency_id}")
def delete_agency(
    agency_id: str,
    current_user: Dict[str, Any] = Depends(require_roles("admin", "qc_manager")),
):
    if not db.delete_agency(agency_id):
        raise HTTPException(status_code=404, detail="Agency not found")
    return Response(status_code=204)


# ── Projects ─────────────────────────────────────────────────────────────────

@app.get("/api/Projects")
def get_projects(current_user: Dict[str, Any] = Depends(get_current_user)):
    if effective_role(current_user) in ("", "guest"):
        return []
    all_projs = db.list_projects()
    return [p for p in all_projs if db.user_has_project_access(current_user, p)]


@app.get("/api/Projects/{project_id}")
def get_project(project_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    item = db.get_project(project_id)
    if not item:
        raise HTTPException(status_code=404, detail="Project not found")
    if not db.user_has_project_access(current_user, item):
        raise HTTPException(status_code=403, detail="Access denied: project is not assigned to your account")
    return item


@app.post("/api/Projects", status_code=201)
def create_project(
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(require_roles("admin")),
):
    from python_app.smartexpedit_server import _apply_project_governance

    res = _apply_project_governance(payload, actor=current_user)
    return res["project"]


@app.put("/api/Projects/{project_id}")
def update_project(
    project_id: str,
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(require_roles("admin")),
):
    existing = db.get_project(project_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")
    from python_app.smartexpedit_server import _apply_project_governance

    _apply_project_governance({**payload, "project_id": project_id}, actor=current_user)
    return Response(status_code=204)


@app.delete("/api/Projects/{project_id}")
def delete_project(
    project_id: str,
    current_user: Dict[str, Any] = Depends(require_roles("admin")),
):
    if not db.delete_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return Response(status_code=204)


# ── Inspection Attendances ───────────────────────────────────────────────────

@app.get("/api/InspectionAttendances")
def get_attendances(
    inspectionId: Optional[str] = None,
    inspector_id: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(
        require_roles("admin", "qc_manager", "inspection_engineer", "inspection_agency", "inspector", "expediting_manager")
    ),
):
    rows = db.list_attendances(inspection_id=inspectionId, inspector_id=inspector_id)
    if is_admin_user(current_user):
        return rows
    allowed_insp_ids = {i["id"] for i in _filter_inspections_for_user(db.list_inspections(), current_user)}
    return [r for r in rows if r.get("inspection_id") in allowed_insp_ids]


@app.get("/api/InspectionAttendances/{attendance_id}")
def get_attendance(
    attendance_id: str,
    current_user: Dict[str, Any] = Depends(
        require_roles("admin", "qc_manager", "inspection_engineer", "inspection_agency", "inspector", "expediting_manager")
    ),
):
    item = db.get_attendance(attendance_id)
    if not item:
        raise HTTPException(status_code=404, detail="Attendance not found")
    if not is_admin_user(current_user):
        insp = db.get_inspection(item.get("inspection_id") or "")
        if not insp or not _filter_inspections_for_user([insp], current_user):
            raise HTTPException(status_code=403, detail="Access denied: attendance outside your scope")
    return item


@app.post("/api/InspectionAttendances", status_code=201)
def create_attendance(
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(require_roles("admin", "qc_manager", "inspection_engineer", "inspector")),
):
    insp_id = str(payload.get("inspection_id") or "").strip()
    insp = db.get_inspection(insp_id)
    if not insp:
        raise HTTPException(status_code=404, detail="Referenced inspection not found")
    if not _filter_inspections_for_user([insp], current_user):
        raise HTTPException(status_code=403, detail="Access denied: cannot check in for inspection outside your scope")
    att_payload = dict(payload)
    if effective_role(current_user) == "inspector" and not att_payload.get("inspector_email"):
        att_payload["inspector_email"] = current_user.get("email")
    _validate_and_normalize_inspector(att_payload, require_presence=True)
    if effective_role(current_user) == "inspector":
        reg_email = str(att_payload.get("assigned_inspector_email") or "").strip().lower()
        if reg_email != str(current_user.get("email") or "").strip().lower():
            raise HTTPException(status_code=403, detail="Inspectors may only check in using their own registered Inspector profile.")
    return db.create_attendance(att_payload)


@app.put("/api/InspectionAttendances/{attendance_id}")
def update_attendance(
    attendance_id: str,
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(require_roles("admin", "qc_manager", "inspection_engineer", "inspector")),
):
    existing = db.get_attendance(attendance_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Attendance not found")
    insp = db.get_inspection(existing.get("inspection_id") or "")
    if not insp or not _filter_inspections_for_user([insp], current_user):
        raise HTTPException(status_code=403, detail="Access denied: cannot update attendance outside your scope")
    updated = db.update_attendance(attendance_id, payload)
    if not updated:
        raise HTTPException(status_code=404, detail="Attendance not found")
    return Response(status_code=204)


@app.delete("/api/InspectionAttendances/{attendance_id}")
def delete_attendance(
    attendance_id: str,
    current_user: Dict[str, Any] = Depends(require_roles("admin", "qc_manager", "inspection_engineer")),
):
    if not db.delete_attendance(attendance_id):
        raise HTTPException(status_code=404, detail="Attendance not found")
    return Response(status_code=204)


# ── Inspection Reviews ───────────────────────────────────────────────────────

@app.get("/api/InspectionReviews")
def get_reviews(
    current_user: Dict[str, Any] = Depends(
        require_roles("admin", "qc_manager", "inspection_engineer", "inspection_agency", "inspector")
    )
):
    rows = db.list_reviews()
    if is_admin_user(current_user):
        return rows
    allowed_insp_ids = {i["id"] for i in _filter_inspections_for_user(db.list_inspections(), current_user)}
    return [r for r in rows if r.get("inspection_id") in allowed_insp_ids]


@app.get("/api/InspectionReviews/{review_id}")
def get_review(
    review_id: str,
    current_user: Dict[str, Any] = Depends(
        require_roles("admin", "qc_manager", "inspection_engineer", "inspection_agency", "inspector")
    ),
):
    item = db.get_review(review_id)
    if not item:
        raise HTTPException(status_code=404, detail="Review not found")
    if not is_admin_user(current_user):
        insp = db.get_inspection(item.get("inspection_id") or "")
        if not insp or not _filter_inspections_for_user([insp], current_user):
            raise HTTPException(status_code=403, detail="Access denied: review outside your scope")
    return item


@app.post("/api/InspectionReviews", status_code=201)
def create_review(
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(require_roles("admin", "qc_manager", "inspection_engineer")),
):
    insp = db.get_inspection(str(payload.get("inspection_id") or ""))
    if not insp:
        raise HTTPException(status_code=404, detail="Inspection not found")
    if not is_admin_user(current_user) and insp.get("project_id") and not user_can_access_project_id(current_user, insp.get("project_id")):
        raise HTTPException(status_code=403, detail="Access denied: inspection belongs to another project")
    clean = dict(payload)
    clean["reviewed_by"] = current_user.get("id")
    return db.create_review(clean)


@app.put("/api/InspectionReviews/{review_id}")
def update_review(
    review_id: str,
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(require_roles("admin", "qc_manager", "inspection_engineer")),
):
    updated = db.update_review(review_id, payload)
    if not updated:
        raise HTTPException(status_code=404, detail="Review not found")
    return Response(status_code=204)


@app.delete("/api/InspectionReviews/{review_id}")
def delete_review(
    review_id: str,
    current_user: Dict[str, Any] = Depends(require_roles("admin", "qc_manager")),
):
    if not db.delete_review(review_id):
        raise HTTPException(status_code=404, detail="Review not found")
    return Response(status_code=204)


# ── Storage ──────────────────────────────────────────────────────────────────

@app.post("/api/Storage/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    bucket: str = Form("inspection-documents"),
    path: str = Form(""),
    po_number: Optional[str] = Form(None),
    inspection_id: Optional[str] = Form(None),
    classification: str = Form("general"),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    if effective_role(current_user) in ("", "guest"):
        raise HTTPException(status_code=403, detail="Active role required to upload files")
    if po_number:
        from python_app.smartexpedit_server import LOCK, sx_db, _records

        with LOCK, sx_db() as c:
            po_rec = next((r for r in _records(c) if str(r.get("po")) == str(po_number).strip()), None)
        if po_rec and not user_can_access_po(current_user, po_rec):
            raise HTTPException(status_code=403, detail="Cannot upload document to unassigned PO or project")

    content = await file.read(settings.upload_max_bytes + 1)
    if len(content) > settings.upload_max_bytes:
        raise HTTPException(status_code=413, detail="Uploaded file exceeds maximum allowed size")

    meta = save_validated_upload(
        file_bytes=content,
        filename=file.filename or "document.pdf",
        bucket=bucket,
        subpath=path or None,
        uploaded_by=current_user.get("email"),
        po_number=po_number,
        inspection_id=inspection_id,
        classification=classification,
        content_type=file.content_type,
    )
    record_audit_event(
        "document",
        meta["doc_id"],
        "DOCUMENT_UPLOADED",
        actor=current_user,
        after={"filename": file.filename, "bucket": bucket, "po_number": po_number, "sha256": meta["sha256"]},
        ip_address=request.client.host if request.client else None,
    )
    # Return same-origin relative URLs (avoid trusting raw Host header)
    return {
        "url": meta["url"],
        "secure_download_url": meta["secure_download_url"],
        "doc_id": meta["doc_id"],
        "sha256": meta["sha256"],
    }


@app.post("/api/Storage/delete")
def delete_file(
    request: Request,
    payload: Dict[str, str],
    current_user: Dict[str, Any] = Depends(require_roles("admin", "qc_manager", "inspection_engineer", "expediting_manager", "expeditor")),
):
    bucket = payload.get("bucket", "")
    rel_path = payload.get("path", "")
    if not bucket or not rel_path or ".." in rel_path or ".." in bucket or "\\" in rel_path or "\\" in bucket:
        raise HTTPException(status_code=400, detail="Invalid bucket or path")
    target = (db.UPLOADS_DIR / bucket / Path(rel_path.lstrip("/"))).resolve()
    if db.UPLOADS_DIR.resolve() not in target.parents:
        raise HTTPException(status_code=400, detail="Invalid file path")

    _authorize_legacy_path(current_user, bucket, rel_path.lstrip("/"))

    if target.exists():
        target.unlink()
        with SessionLocal() as sdb:
            sdb.query(DocumentRecord).filter(
                DocumentRecord.bucket == bucket,
                DocumentRecord.rel_path == rel_path.lstrip("/"),
            ).delete()
            sdb.commit()
        record_audit_event(
            "document",
            rel_path,
            "DOCUMENT_DELETED",
            actor=current_user,
            after={"bucket": bucket, "path": rel_path},
            ip_address=request.client.host if request.client else None,
        )
        return {"message": "File deleted successfully"}
    raise HTTPException(status_code=404, detail="File not found")


# ── SmartExpedit REST & Schedule/Sub-Order Parsing Endpoints ─────────────────

_EXP_INTERNAL_ROLES = ("admin", "expediting_manager", "expeditor", "field_expeditor", "doc_expeditor", "qc_manager", "inspection_engineer")
_EXP_WRITE_ROLES = ("admin", "expediting_manager", "expeditor", "field_expeditor", "doc_expeditor")


def _expediting_po_allowed(po_obj: Optional[Dict[str, Any]], user: Dict[str, Any]) -> bool:
    if not po_obj:
        return False
    if is_admin_user(user):
        return True
    if is_vendor_user(user):
        ucomp = str(user.get("company_affiliation") or user.get("company") or "").strip().lower()
        vname = str(po_obj.get("vendor_name") or "").strip().lower()
        return bool(ucomp and vname and ucomp == vname)
    pid = po_obj.get("project_id")
    if pid and db.get_project(pid):
        return user_can_access_project_id(user, pid)
    return True if effective_role(user) in _EXP_INTERNAL_ROLES else False


@app.get("/api/expediting/dashboard")
def api_expediting_dashboard(
    current_user: Dict[str, Any] = Depends(require_roles(*_EXP_INTERNAL_ROLES))
):
    data = expediting_db.get_executive_dashboard_metrics()
    data["scurve"] = build_scurve(data.get("all_activities", []))
    data["projects"] = expediting_db.get_epc_projects()
    data["vendors"] = expediting_db.get_epc_vendors()
    return data


@app.get("/api/expediting/pos")
def api_expediting_pos(
    current_user: Dict[str, Any] = Depends(require_roles(*_EXP_INTERNAL_ROLES, "vendor"))
):
    pos = expediting_db.get_purchase_orders()
    return [p for p in pos if _expediting_po_allowed(p, current_user)]


@app.post("/api/expediting/pos", status_code=201)
def api_create_expediting_po(
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(require_roles("admin", "expediting_manager")),
):
    po = expediting_db.create_purchase_order(payload)
    if payload.get("generate_baseline", True):
        expediting_db.generate_standard_baseline(po["id"])
    return po


@app.put("/api/expediting/pos/{po_id}")
def api_update_expediting_po(
    po_id: str,
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(require_roles("admin", "expediting_manager", "expeditor")),
):
    try:
        expediting_db.update_purchase_order(po_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"status": "ok"}


@app.get("/api/expediting/workbench/{po_id}")
def api_expediting_workbench(
    po_id: str,
    current_user: Dict[str, Any] = Depends(require_roles(*_EXP_INTERNAL_ROLES, "vendor")),
):
    po = expediting_db.get_purchase_order(po_id)
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    if not _expediting_po_allowed(po, current_user):
        raise HTTPException(status_code=403, detail="Access denied: PO is outside your scope")
    return expediting_db.get_workbench_detail(po_id)


@app.post("/api/expediting/workbench/{po_id}/baseline")
def api_expediting_generate_baseline(
    po_id: str,
    current_user: Dict[str, Any] = Depends(require_roles("admin", "expediting_manager", "expeditor")),
):
    po = expediting_db.get_purchase_order(po_id)
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    acts = expediting_db.generate_standard_baseline(po_id)
    return {"status": "ok", "count": len(acts), "activities": acts}


@app.put("/api/expediting/activities/{act_id}")
def api_update_schedule_activity(
    act_id: str,
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(require_roles("admin", "expediting_manager", "expeditor", "field_expeditor")),
):
    expediting_db.update_schedule_activity(act_id, payload)
    return {"status": "ok"}


@app.get("/api/expediting/sample_schedule/{po_number}")
def api_download_sample_schedule(
    po_number: str,
    current_user: Dict[str, Any] = Depends(require_roles(*_EXP_INTERNAL_ROLES, "vendor")),
):
    safe_po = re.sub(r"[^A-Za-z0-9._-]", "_", po_number or "PO")[:64]
    xlsx_bytes = build_sample_schedule_excel(safe_po)
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="Sample_Schedule_{safe_po}.xlsx"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.post("/api/expediting/parse_vendor_schedule")
async def api_parse_vendor_schedule(
    file: UploadFile = File(...),
    po_id: str = Form(""),
    dry_run: bool = Form(False),
    current_user: Dict[str, Any] = Depends(require_roles(*_EXP_WRITE_ROLES, "vendor")),
):
    if po_id:
        po = expediting_db.get_purchase_order(po_id)
        if po and not _expediting_po_allowed(po, current_user):
            raise HTTPException(status_code=403, detail="Access denied for target PO")
    content = await file.read(settings.upload_max_bytes + 1)
    if len(content) > settings.upload_max_bytes:
        raise HTTPException(status_code=413, detail="File exceeds maximum upload size")
    try:
        return parse_vendor_schedule_file(content, file.filename or "schedule.xlsx", po_id, dry_run=dry_run)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/expediting/suborders")
def api_save_suborder(
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(require_roles(*_EXP_WRITE_ROLES, "vendor")),
):
    po_id = str(payload.get("po_id") or "").strip()
    if po_id:
        po = expediting_db.get_purchase_order(po_id)
        if po and not _expediting_po_allowed(po, current_user):
            raise HTTPException(status_code=403, detail="Access denied for target PO")
    return expediting_db.save_suborder(payload)


@app.delete("/api/expediting/suborders/{sub_id}")
def api_delete_suborder(
    sub_id: str,
    current_user: Dict[str, Any] = Depends(require_roles("admin", "expediting_manager", "expeditor")),
):
    expediting_db.delete_suborder(sub_id)
    return {"status": "ok"}


@app.post("/api/expediting/parse_suborder_report")
async def api_parse_suborder_report(
    file: UploadFile = File(...),
    po_id: str = Form(...),
    po_number: str = Form(""),
    main_vendor: str = Form(""),
    current_user: Dict[str, Any] = Depends(require_roles(*_EXP_WRITE_ROLES, "vendor")),
):
    po = expediting_db.get_purchase_order(po_id)
    if po and not _expediting_po_allowed(po, current_user):
        raise HTTPException(status_code=403, detail="Access denied for target PO")
    content = await file.read(settings.upload_max_bytes + 1)
    if len(content) > settings.upload_max_bytes:
        raise HTTPException(status_code=413, detail="File exceeds maximum upload size")
    try:
        return parse_suborder_report_file(content, file.filename or "suborders.xlsx", po_id, po_number, main_vendor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/expediting/bulk_line_items")
def api_create_bulk_line_item(
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(require_roles("admin", "expediting_manager", "expeditor")),
):
    try:
        return expediting_db.create_bulk_line_item(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/expediting/bulk_toggle")
def api_toggle_bulk_stage(
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(require_roles("admin", "expediting_manager", "expeditor", "field_expeditor")),
):
    line_item_id = str(payload.get("line_item_id") or "").strip()
    po_id = str(payload.get("po_id") or "").strip()
    stage_name = str(payload.get("stage_name") or "").strip()
    if not line_item_id or not po_id or not stage_name:
        raise HTTPException(status_code=400, detail="line_item_id, po_id, and stage_name are required")
    try:
        expediting_db.toggle_bulk_stage(
            line_item_id=line_item_id,
            po_id=po_id,
            po_number=payload.get("po_number", ""),
            tag_number=payload.get("tag_number", ""),
            heat_lot=payload.get("heat_lot", ""),
            stage_name=stage_name,
            stage_label=payload.get("stage_label", ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "ok"}


@app.post("/api/expediting/vdrl")
def api_save_vdrl(
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(require_roles("admin", "expediting_manager", "expeditor", "doc_expeditor", "inspection_engineer")),
):
    return expediting_db.save_vdrl_document(payload)


@app.delete("/api/expediting/vdrl/{doc_id}")
def api_delete_vdrl(
    doc_id: str,
    current_user: Dict[str, Any] = Depends(require_roles("admin", "expediting_manager", "doc_expeditor")),
):
    expediting_db.delete_vdrl_document(doc_id)
    return {"status": "ok"}


@app.get("/api/expediting/rail")
def api_list_rail(
    po_id: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(require_roles(*_EXP_INTERNAL_ROLES, "vendor")),
):
    if po_id:
        po = expediting_db.get_purchase_order(po_id)
        if po and not _expediting_po_allowed(po, current_user):
            raise HTTPException(status_code=403, detail="Access denied for target PO")
        return expediting_db.get_rail_items(po_id)
    items = expediting_db.get_rail_items()
    if is_vendor_user(current_user):
        allowed_pos = {p["po_number"] for p in expediting_db.get_purchase_orders() if _expediting_po_allowed(p, current_user)}
        return [r for r in items if r.get("po_number") in allowed_pos]
    return items


@app.post("/api/expediting/rail")
def api_create_rail(
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(require_roles(*_EXP_WRITE_ROLES, "inspection_engineer", "qc_manager")),
):
    return expediting_db.create_rail_item(payload)


@app.post("/api/expediting/rail/{rail_id}/advance")
def api_advance_rail(
    rail_id: str,
    current_user: Dict[str, Any] = Depends(require_roles("admin", "expediting_manager", "expeditor", "inspection_engineer")),
):
    expediting_db.advance_rail_item(rail_id)
    return {"status": "ok"}


@app.delete("/api/expediting/rail/{rail_id}")
def api_delete_rail(
    rail_id: str,
    current_user: Dict[str, Any] = Depends(require_roles("admin", "expediting_manager")),
):
    expediting_db.delete_rail_item(rail_id)
    return {"status": "ok"}


@app.post("/api/expediting/inspections")
def api_create_epc_inspection(
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(require_roles(*_EXP_WRITE_ROLES, "vendor")),
):
    po_id = str(payload.get("po_id") or "").strip()
    if po_id:
        po = expediting_db.get_purchase_order(po_id)
        if po and not _expediting_po_allowed(po, current_user):
            raise HTTPException(status_code=403, detail="Access denied for target PO")
    return expediting_db.create_epc_inspection_notification(payload)


@app.put("/api/expediting/inspections/{notif_id}/status")
def api_update_epc_inspection_status(
    notif_id: str,
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(require_roles("admin", "qc_manager", "inspection_engineer", "expediting_manager", "expeditor")),
):
    expediting_db.update_epc_inspection_status(notif_id, payload.get("status", "ACKNOWLEDGED"))
    return {"status": "ok"}


@app.get("/api/expediting/projects")
def api_list_epc_projects(
    current_user: Dict[str, Any] = Depends(require_roles(*_EXP_INTERNAL_ROLES))
):
    return expediting_db.get_epc_projects()


@app.post("/api/expediting/projects")
def api_create_epc_project(
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(require_roles("admin", "expediting_manager")),
):
    return expediting_db.create_epc_project(payload)


@app.get("/api/expediting/vendors")
def api_list_epc_vendors(
    current_user: Dict[str, Any] = Depends(require_roles(*_EXP_INTERNAL_ROLES))
):
    return expediting_db.get_epc_vendors()


@app.post("/api/expediting/vendors")
def api_create_epc_vendor(
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(require_roles("admin", "expediting_manager")),
):
    return expediting_db.create_epc_vendor(payload)


# ── Mount Native SmartExpedit Server (/api/kv, /api/blob, /api/v1/*, /smartexpedit-app) ──
from python_app.smartexpedit_server import router as smartexpedit_router
from python_app.expediting_erp_workflows import router as erp_workflow_router
from python_app.expediting_phase45_workflows import router as erp_phase45_router

app.include_router(smartexpedit_router)
app.include_router(erp_workflow_router)
app.include_router(erp_phase45_router)


# ── Serve Original Built SPA UI directly from Python FastAPI ─────────────────
DIST_DIR = db.BASE_DIR / "dist"
if (DIST_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
def serve_spa(full_path: str):
    if full_path.startswith("api/") or full_path.startswith("uploads/"):
        raise HTTPException(status_code=404, detail="Not found")
    if full_path:
        if ".." in full_path or "\\" in full_path or ":" in full_path or full_path.startswith("/"):
            raise HTTPException(status_code=404, detail="Not found")
        dist_root = DIST_DIR.resolve()
        candidate = (dist_root / full_path).resolve()
        if dist_root in candidate.parents and candidate.is_file():
            return FileResponse(str(candidate))
    index_file = DIST_DIR / "index.html"
    if index_file.is_file():
        return FileResponse(str(index_file))
    raise HTTPException(status_code=404, detail="Frontend build not found")
