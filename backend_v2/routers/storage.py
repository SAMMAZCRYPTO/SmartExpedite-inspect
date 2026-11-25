import hashlib
import mimetypes
from pathlib import Path
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from backend_v2.core.config import settings
from backend_v2.core.database import SessionLocal
from backend_v2.core.security import (
    effective_role,
    get_current_user,
    is_admin_user,
    is_vendor_user,
    user_can_access_po,
    vendor_owns_po,
)
from backend_v2.models.epc_models import DocumentRecord
from backend_v2.services.audit_service import record_audit_event

router = APIRouter(prefix="/api/v2/storage", tags=["Protected Document Storage"])

_BUCKET_ALIASES = {
    "inspection-documents",
    "inspector-cvs",
    "avatars",
    "itp-baselines",
    "ncr-evidence",
    "logistics",
    "inspection-reports",
}


def _validate_magic_bytes(ext: str, file_bytes: bytes) -> None:
    head = file_bytes[:16]
    if ext == ".pdf":
        if not file_bytes.lstrip()[:5].startswith(b"%PDF-"):
            raise HTTPException(status_code=400, detail="File content is not a valid PDF document")
    elif ext == ".png":
        if not head.startswith(b"\x89PNG\r\n\x1a\n"):
            raise HTTPException(status_code=400, detail="File content is not a valid PNG image")
    elif ext in (".jpg", ".jpeg"):
        if not head.startswith(b"\xff\xd8\xff"):
            raise HTTPException(status_code=400, detail="File content is not a valid JPEG image")
    elif ext == ".webp":
        if not (head.startswith(b"RIFF") and head[8:12] == b"WEBP"):
            raise HTTPException(status_code=400, detail="File content is not a valid WEBP image")
    elif ext in (".xlsx", ".docx"):
        if not head.startswith(b"PK\x03\x04"):
            raise HTTPException(status_code=400, detail=f"File content is not a valid {ext} Office archive")
    elif ext in (".xls", ".doc"):
        if not (head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1") or head.startswith(b"PK\x03\x04")):
            raise HTTPException(status_code=400, detail=f"File content is not a valid {ext} document")
    elif ext in (".csv", ".txt"):
        if b"\x00" in file_bytes[:4096]:
            raise HTTPException(status_code=400, detail="Binary content is not allowed in text/CSV uploads")


def _sanitize_rel_path(raw_path: Optional[str], filename: str) -> str:
    safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in (filename or "document.pdf"))
    unique_prefix = uuid.uuid4().hex[:12]
    if raw_path:
        cleaned = str(raw_path).replace("\\", "/").lstrip("/")
        if ".." in cleaned or cleaned.startswith("/") or ":" in cleaned:
            raise HTTPException(status_code=400, detail="Invalid storage path")
        sub_ext = Path(cleaned).suffix.lower()
        if sub_ext not in settings.allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Target path extension '{sub_ext or 'none'}' is not permitted.",
            )
        parts = ["".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in p) for p in cleaned.split("/") if p]
        if parts:
            parts[-1] = f"{unique_prefix}_{parts[-1]}"
            return "/".join(parts)
    return f"uploads/{unique_prefix}_{safe_name}"


def save_validated_upload(
    file_bytes: bytes,
    filename: str,
    bucket: str = "inspection-documents",
    subpath: Optional[str] = None,
    uploaded_by: Optional[str] = None,
    po_number: Optional[str] = None,
    inspection_id: Optional[str] = None,
    classification: str = "general",
    content_type: Optional[str] = None,
) -> Dict[str, Any]:
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file uploads are not permitted")
    if len(file_bytes) > settings.upload_max_bytes:
        mb = settings.upload_max_bytes // (1024 * 1024)
        raise HTTPException(status_code=413, detail=f"File exceeds maximum allowed upload size of {mb} MB")

    safe_bucket = "".join(c if c.isalnum() or c in "-_" else "_" for c in (bucket or "inspection-documents"))
    ext = Path(filename or "").suffix.lower()
    if ext not in settings.allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File extension '{ext or 'none'}' is not permitted. Allowed: {', '.join(sorted(settings.allowed_extensions))}",
        )
    if subpath:
        sub_ext = Path(str(subpath).replace("\\", "/")).suffix.lower()
        if sub_ext and sub_ext != ext:
            raise HTTPException(status_code=400, detail="Target path extension must match uploaded filename extension")

    _validate_magic_bytes(ext, file_bytes)

    rel_path = _sanitize_rel_path(subpath, filename or "document.pdf")
    target_path = (settings.storage_root / safe_bucket / rel_path).resolve()
    root_resolved = settings.storage_root.resolve()
    if root_resolved not in target_path.parents:
        raise HTTPException(status_code=400, detail="Invalid target path outside storage root")
    if target_path.exists():
        raise HTTPException(status_code=409, detail="Target upload path already exists")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(file_bytes)

    sha256_hex = hashlib.sha256(file_bytes).hexdigest()
    guessed_mime = mimetypes.guess_type(filename or "")[0] or "application/octet-stream"
    doc_id = uuid.uuid4().hex

    with SessionLocal() as db:
        rec = DocumentRecord(
            id=doc_id,
            bucket=safe_bucket,
            rel_path=rel_path,
            original_filename=filename or Path(rel_path).name,
            mime_type=guessed_mime,
            size_bytes=len(file_bytes),
            sha256_hash=sha256_hex,
            po_number=(str(po_number).strip() or None) if po_number else None,
            inspection_id=(str(inspection_id).strip() or None) if inspection_id else None,
            classification=classification,
            uploaded_by=uploaded_by,
        )
        db.add(rec)
        db.commit()

    return {
        "doc_id": doc_id,
        "url": f"/uploads/{safe_bucket}/{rel_path}",
        "secure_download_url": f"/api/v2/storage/files/{doc_id}/download",
        "sha256": sha256_hex,
        "size_bytes": len(file_bytes),
        "mime_type": guessed_mime,
    }


def _authorize_document_record(current_user: Optional[Dict[str, Any]], rec: DocumentRecord) -> None:
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if is_admin_user(current_user):
        return
    eff = effective_role(current_user)
    if eff in ("", "guest"):
        raise HTTPException(status_code=403, detail="Active role required to access documents")

    user_email = str(current_user.get("email") or "").strip().lower()
    if rec.uploaded_by and user_email and str(rec.uploaded_by).strip().lower() == user_email:
        return

    if is_vendor_user(current_user):
        if not rec.po_number:
            raise HTTPException(status_code=403, detail="Vendor cannot access unlinked system documents")
        from python_app.smartexpedit_server import LOCK, sx_db, _records
        with LOCK, sx_db() as c:
            po_rec = next((r for r in _records(c) if str(r.get("po")) == str(rec.po_number)), None)
        if not po_rec or not vendor_owns_po(current_user, po_rec):
            raise HTTPException(status_code=403, detail="Vendor cannot access documents for unassigned PO")
        return

    if rec.po_number:
        from python_app.smartexpedit_server import LOCK, sx_db, _records
        with LOCK, sx_db() as c:
            po_rec = next((r for r in _records(c) if str(r.get("po")) == str(rec.po_number)), None)
        if po_rec and not user_can_access_po(current_user, po_rec):
            raise HTTPException(status_code=403, detail="Access denied: PO belongs to another project")
    if rec.inspection_id:
        from python_app import database as inspectflow_db
        insp = inspectflow_db.get_inspection(rec.inspection_id)
        if insp:
            from backend_v2.core.security import user_can_access_project_id
            pid = insp.get("project_id")
            if pid and not user_can_access_project_id(current_user, pid):
                raise HTTPException(status_code=403, detail="Access denied: inspection belongs to another project")


def _authorize_legacy_path(current_user: Optional[Dict[str, Any]], bucket: str, rel_path: str) -> None:
    """Checks DocumentRecord or inspection/PO association for /uploads/{bucket}/{file_path} access."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if is_admin_user(current_user):
        return
    eff = effective_role(current_user)
    if eff in ("", "guest"):
        raise HTTPException(status_code=403, detail="Active role required to access uploaded files")

    with SessionLocal() as db:
        rec = (
            db.query(DocumentRecord)
            .filter(DocumentRecord.bucket == bucket, DocumentRecord.rel_path == rel_path)
            .order_by(DocumentRecord.created_at.desc())
            .first()
        )
    if rec:
        _authorize_document_record(current_user, rec)
        return

    # Fallback check for legacy files referenced in Inspections (without a DocumentRecord row)
    target_suffix = f"/uploads/{bucket}/{rel_path}"
    from python_app import database as inspectflow_db
    if is_vendor_user(current_user):
        from python_app.smartexpedit_server import LOCK, sx_db, _records
        with LOCK, sx_db() as c:
            owned_pos = {str(r.get("po")) for r in _records(c) if vendor_owns_po(current_user, r)}
        for insp in inspectflow_db.list_inspections():
            if str(insp.get("po_number") or "") not in owned_pos:
                continue
            blobs = [
                insp.get("document_url") or "",
                *(str(r.get("url") or "") for r in (insp.get("inspection_reports") or []) if isinstance(r, dict)),
                *(str(r.get("url") or "") for r in (insp.get("release_notes") or []) if isinstance(r, dict)),
                *(str(r.get("url") or "") for r in (insp.get("test_reports") or []) if isinstance(r, dict)),
            ]
            if any(target_suffix in u for u in blobs):
                return
        raise HTTPException(status_code=403, detail="Vendor cannot access unowned or system upload")


@router.post("/upload")
async def upload_protected_file(
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
            raise HTTPException(status_code=403, detail="Cannot upload file to unassigned PO or project")

    content = await file.read(settings.upload_max_bytes + 1)
    if len(content) > settings.upload_max_bytes:
        raise HTTPException(status_code=413, detail="File exceeds maximum upload size")

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
    return meta


@router.get("/files/{doc_id}/download")
def download_document_by_id(
    doc_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    with SessionLocal() as db:
        rec = db.get(DocumentRecord, doc_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Document not found")

    _authorize_document_record(current_user, rec)

    file_path = (settings.storage_root / rec.bucket / rec.rel_path).resolve()
    if settings.storage_root.resolve() not in file_path.parents or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Stored file missing from disk")
    safe_fname = (rec.original_filename or "document.pdf").replace('"', "").replace("\r", "").replace("\n", "")
    disp = "inline" if rec.mime_type in ("application/pdf", "image/png", "image/jpeg", "image/webp") else "attachment"
    return FileResponse(
        path=str(file_path),
        media_type=rec.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'{disp}; filename="{safe_fname}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


def resolve_local_upload_bytes(file_url: str, current_user: Optional[Dict[str, Any]] = None) -> Optional[bytes]:
    """Safely resolves a local /uploads/... or /api/v2/storage/files/... reference with tenant authorization."""
    if not file_url:
        return None
    s = str(file_url).strip()
    if "/api/v2/storage/files/" in s:
        doc_id = s.split("/api/v2/storage/files/")[1].split("/")[0].split("?")[0]
        with SessionLocal() as db:
            rec = db.get(DocumentRecord, doc_id)
        if rec:
            if current_user is not None:
                _authorize_document_record(current_user, rec)
            p = (settings.storage_root / rec.bucket / rec.rel_path).resolve()
            if settings.storage_root.resolve() in p.parents and p.is_file():
                return p.read_bytes()
    if "/uploads/" in s:
        rel = s.split("/uploads/", 1)[1].split("?")[0].lstrip("/")
        if ".." in rel or "\\" in rel:
            return None
        parts = rel.split("/", 1)
        if len(parts) == 2 and current_user is not None:
            _authorize_legacy_path(current_user, parts[0], parts[1])
        candidate = (settings.storage_root / rel).resolve()
        if settings.storage_root.resolve() in candidate.parents and candidate.is_file():
            return candidate.read_bytes()
    return None
