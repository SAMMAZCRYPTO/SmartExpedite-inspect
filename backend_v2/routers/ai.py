import json
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from backend_v2.core.config import settings
from backend_v2.core.security import require_roles
from backend_v2.routers.storage import resolve_local_upload_bytes
from python_app import ai_service

router = APIRouter(prefix="/api/v2/ai", tags=["Server-Side AI Extraction"])

_AI_ALLOWED_ROLES = (
    "admin",
    "qc_manager",
    "inspection_engineer",
    "inspector",
    "inspection_agency",
    "expediting_manager",
    "expeditor",
    "field_expeditor",
    "doc_expeditor",
    "vendor",
)


def _safe_filename(name: Optional[str], default: str = "document.pdf") -> str:
    clean = "".join(c if c.isalnum() or c in "._-" else "_" for c in Path(name or default).name)
    return clean[:120] or default


@router.post("/extract-notification")
def extract_notification_endpoint(
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(require_roles(*_AI_ALLOWED_ROLES)),
):
    file_url = str(payload.get("file_url") or "").strip()
    filename = _safe_filename(payload.get("file_name"), "notification.pdf")
    pdf_bytes = resolve_local_upload_bytes(file_url, current_user=current_user)
    if not pdf_bytes:
        raise HTTPException(
            status_code=404,
            detail="Could not locate uploaded notification PDF in local storage",
        )
    try:
        output = ai_service.extract_inspection_notification(pdf_bytes, filename=filename)
        return {"status": "success", "output": output}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI notification extraction error: {exc}")


@router.post("/extract-report")
def extract_report_endpoint(
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(require_roles("admin", "qc_manager", "inspection_engineer", "inspector", "inspection_agency")),
):
    file_url = str(payload.get("file_url") or "").strip()
    filename = _safe_filename(payload.get("file_name"), "report.pdf")
    report_type = str(payload.get("report_type") or "Flash")[:40]
    pdf_bytes = resolve_local_upload_bytes(file_url, current_user=current_user)
    if not pdf_bytes:
        raise HTTPException(
            status_code=404,
            detail="Could not locate uploaded report PDF in local storage",
        )
    try:
        output = ai_service.extract_inspection_report(
            pdf_bytes, filename=filename, report_type=report_type
        )
        return {"status": "success", "output": output}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI report extraction error: {exc}")


@router.post("/invoke")
def invoke_llm_with_document(
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(require_roles(*_AI_ALLOWED_ROLES)),
):
    """Server-side replacement for browser InvokeLLM (enforces tenant doc AuthZ and protects GEMINI_API_KEY)."""
    file_urls = payload.get("file_urls") or []
    prompt = str(payload.get("prompt") or "").strip()
    schema = payload.get("response_json_schema")
    if not file_urls or not prompt:
        raise HTTPException(status_code=400, detail="file_urls and prompt are required")

    pdf_bytes = resolve_local_upload_bytes(file_urls[0], current_user=current_user)
    if not pdf_bytes:
        raise HTTPException(status_code=404, detail="Referenced uploaded PDF not found in storage")

    final_prompt = prompt
    if schema:
        final_prompt += f"\n\nStrictly return a JSON object matching this schema: {json.dumps(schema)}. Return ONLY valid JSON, no markdown blocks."

    try:
        return ai_service.call_gemini_with_pdf(pdf_bytes, final_prompt)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI analysis error: {exc}")


@router.post("/extract-upload")
async def extract_direct_upload(
    file: UploadFile = File(...),
    mode: str = Form("notification"),
    report_type: str = Form("Flash"),
    current_user: Dict[str, Any] = Depends(require_roles(*_AI_ALLOWED_ROLES)),
):
    pdf_bytes = await file.read(settings.upload_max_bytes + 1)
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Empty file uploaded")
    if len(pdf_bytes) > settings.upload_max_bytes:
        raise HTTPException(status_code=413, detail="Uploaded file exceeds maximum allowed size")
    safe_name = _safe_filename(file.filename, "document.pdf")
    try:
        if mode == "report":
            output = await run_in_threadpool(
                ai_service.extract_inspection_report,
                pdf_bytes,
                filename=safe_name,
                report_type=str(report_type)[:40],
            )
        else:
            output = await run_in_threadpool(
                ai_service.extract_inspection_notification,
                pdf_bytes,
                filename=safe_name,
            )
        return {"status": "success", "output": output}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI extraction failed: {exc}")
