from collections import defaultdict
import re
import time
from typing import Any, Dict, List

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status

from backend_v2.core.config import settings
from backend_v2.core.security import (
    AUTH_COOKIE_NAME,
    create_access_token,
    decode_access_token,
    extract_token_from_request,
    get_current_user,
    hash_password,
    is_admin_user,
    require_roles,
)
from backend_v2.services.audit_service import record_audit_event
from python_app import database as inspectflow_db

router = APIRouter(prefix="/api/v2/auth", tags=["Authentication & Governance"])

_LOGIN_ATTEMPTS: Dict[str, List[float]] = defaultdict(list)
_LOGIN_WINDOW_SEC = 300
_LOGIN_MAX_ATTEMPTS = 10

_DEV_ROLE_META = {
    "admin": {"label": "Global Admin", "group": "Inspection & Governance", "badge": "bg-red-100 text-red-700"},
    "qc_manager": {"label": "QC / Inspection Manager", "group": "Inspection & Governance", "badge": "bg-green-100 text-green-700"},
    "inspection_engineer": {"label": "Inspection Engineer", "group": "Inspection & Governance", "badge": "bg-blue-100 text-blue-700"},
    "inspector": {"label": "Inspector (Field)", "group": "Inspection & Governance", "badge": "bg-purple-100 text-purple-700"},
    "inspection_agency": {"label": "TPI Agency", "group": "Inspection & Governance", "badge": "bg-amber-100 text-amber-700"},
    "expediting_manager": {"label": "Expediting Manager", "group": "Expediting & Vendor", "badge": "bg-indigo-100 text-indigo-700"},
    "expeditor": {"label": "Package Expeditor", "group": "Expediting & Vendor", "badge": "bg-teal-100 text-teal-700"},
    "field_expeditor": {"label": "Field Expeditor", "group": "Expediting & Vendor", "badge": "bg-orange-100 text-orange-700"},
    "doc_expeditor": {"label": "Doc Expeditor", "group": "Expediting & Vendor", "badge": "bg-cyan-100 text-cyan-700"},
    "vendor": {"label": "Vendor Portal", "group": "Expediting & Vendor", "badge": "bg-emerald-100 text-emerald-700"},
}


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=(settings.auth_mode == "production"),
        samesite="lax",
        max_age=settings.jwt_expire_hours * 3600,
        path="/",
    )


def _check_login_rate_limit(key: str) -> None:
    now = time.time()
    recent = [ts for ts in _LOGIN_ATTEMPTS[key] if now - ts < _LOGIN_WINDOW_SEC]
    _LOGIN_ATTEMPTS[key] = recent
    if len(recent) >= _LOGIN_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed sign-in attempts. Please wait a few minutes and try again.",
        )


def _record_login_failure(key: str) -> None:
    _LOGIN_ATTEMPTS[key].append(time.time())


@router.get("/config")
def get_auth_config():
    return {
        "auth_mode": settings.auth_mode,
        "dev_quick_login_enabled": settings.auth_mode == "dev",
        "oidc_enabled": bool(settings.oidc_tenant_id and settings.oidc_client_id),
    }


@router.post("/login")
def login(request: Request, response: Response, payload: Dict[str, Any] = Body(...)):
    email = str(payload.get("email") or "").strip().lower()
    password = str(payload.get("password") or "")
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required")

    ip = request.client.host if request.client else "unknown"
    rl_key = f"{ip}:{email}"
    _check_login_rate_limit(rl_key)

    user = None
    inactive_reason = None
    try:
        user = inspectflow_db.authenticate_user(email, password)
    except ValueError as exc:
        inactive_reason = str(exc)

    if not user or inactive_reason:
        _record_login_failure(rl_key)
        record_audit_event(
            "user",
            email,
            "LOGIN_FAILED",
            notes=inactive_reason or "Invalid email or password",
            ip_address=request.client.host if request.client else None,
        )
        # Uniform 401 prevents credential-validity enumeration against deactivated accounts
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password, or account is not active.",
        )

    if str(user.get("user_status") or "active").lower() != "active":
        record_audit_event(
            "user",
            user["id"],
            "LOGIN_BLOCKED_INACTIVE",
            actor=user,
            ip_address=request.client.host if request.client else None,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password, or account is not active.",
        )

    _LOGIN_ATTEMPTS.pop(rl_key, None)
    token = create_access_token(user)
    _set_auth_cookie(response, token)
    record_audit_event(
        "user",
        user["id"],
        "LOGIN_SUCCESS",
        actor=user,
        ip_address=request.client.host if request.client else None,
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "auth_mode": settings.auth_mode,
        "user": user,
    }


def _validate_strong_password(password: str) -> None:
    if (
        len(password) < 8
        or not re.search(r"[A-Za-z]", password)
        or not re.search(r"[0-9]", password)
    ):
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters long and include both letters and numbers.",
        )


@router.post("/register", status_code=201)
def register(request: Request, payload: Dict[str, Any] = Body(...)):
    email = str(payload.get("email") or "").strip().lower()
    password = str(payload.get("password") or "")
    full_name = str(payload.get("full_name") or "").strip()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Valid email address is required")
    _validate_strong_password(password)

    try:
        user = inspectflow_db.register_user(
            email=email, password=hash_password(password), full_name=full_name
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    record_audit_event(
        "user",
        user["id"],
        "USER_REGISTERED_PENDING",
        actor=user,
        ip_address=request.client.host if request.client else None,
    )
    # Fail closed: newly registered accounts start 'pending' and receive NO active JWT until approved by an Admin
    return {
        "ok": True,
        "pending_approval": True,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "full_name": user["full_name"],
            "user_status": user["user_status"],
        },
        "message": "Account registered and awaiting administrator activation and role assignment.",
    }


@router.post("/logout")
def logout(request: Request, response: Response):
    token = extract_token_from_request(request)
    if token:
        try:
            claims = decode_access_token(token)
            jti = str(claims.get("jti") or "")
            exp = int(claims.get("exp") or 0)
            if jti:
                inspectflow_db.revoke_token(jti, exp)
        except Exception:
            pass
    response.delete_cookie(key=AUTH_COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
def me(current_user: Dict[str, Any] = Depends(get_current_user)):
    sanitized = dict(current_user)
    sanitized.pop("_token_jti", None)
    sanitized.pop("_token_exp", None)
    return sanitized


@router.get("/dev-accounts")
def list_dev_accounts():
    """Returns role switcher profiles ONLY in dev testing mode (never exposes passwords)."""
    if settings.auth_mode != "dev":
        raise HTTPException(status_code=403, detail="Dev quick-login is disabled in production mode")
    users = inspectflow_db.list_users()
    accounts = []
    for u in users:
        role = str(u.get("inspection_role") or u.get("role") or "guest").lower()
        if role == "guest" or str(u.get("user_status") or "").lower() != "active":
            continue
        meta = _DEV_ROLE_META.get(role, {"label": role, "group": "Other", "badge": "bg-gray-100 text-gray-700"})
        accounts.append({
            "id": u["id"],
            "email": u["email"],
            "full_name": u["full_name"],
            "role": role,
            "role_label": meta["label"],
            "group": meta["group"],
            "badge": meta["badge"],
        })
    return {"auth_mode": settings.auth_mode, "accounts": accounts}


@router.post("/dev-login")
def dev_quick_login(request: Request, response: Response, payload: Dict[str, Any] = Body(...)):
    """Issues a real signed JWT for a selected test user ONLY when AUTH_MODE=dev."""
    if settings.auth_mode != "dev":
        raise HTTPException(status_code=403, detail="Dev quick-login is disabled in production mode")
    ident = str(payload.get("email") or payload.get("user_id") or "").strip().lower()
    if not ident:
        raise HTTPException(status_code=400, detail="email or user_id required")
    users = inspectflow_db.list_users()
    user = next(
        (u for u in users if str(u.get("email", "")).lower() == ident or str(u.get("id", "")).lower() == ident),
        None,
    )
    if not user:
        raise HTTPException(status_code=404, detail="Dev account not found")
    if str(user.get("user_status") or "active").lower() != "active":
        raise HTTPException(status_code=403, detail="Account deactivated or pending approval")

    token = create_access_token(user)
    _set_auth_cookie(response, token)
    record_audit_event(
        "user",
        user["id"],
        "DEV_QUICK_LOGIN",
        actor=user,
        ip_address=request.client.host if request.client else None,
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "auth_mode": settings.auth_mode,
        "user": user,
    }


@router.get("/users")
def list_users_secure(
    current_user: Dict[str, Any] = Depends(require_roles("admin", "expediting_manager", "qc_manager", "inspection_engineer"))
):
    users = inspectflow_db.list_users()
    if is_admin_user(current_user):
        return users
    # Scope non-admin managers/IEs to users sharing their projects (or unassigned internal/vendor staff)
    my_pids = {str(p).lower() for p in (current_user.get("project_ids") or []) if p}
    if not my_pids:
        return [u for u in users if str(u.get("id")).lower() == str(current_user.get("id")).lower()]
    return [
        u
        for u in users
        if str(u.get("id")).lower() == str(current_user.get("id")).lower()
        or any(str(pid).lower() in my_pids for pid in (u.get("project_ids") or []))
    ]


@router.put("/users/{user_id}")
def update_user_secure(
    user_id: str,
    request: Request,
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    is_admin = is_admin_user(current_user)
    is_self = str(current_user.get("id") or "").lower() == str(user_id).lower()
    if not is_admin and not is_self:
        raise HTTPException(status_code=403, detail="Only administrators can update other users")

    # Non-admins updating themselves CANNOT escalate role, user_status, project_ids, OR company_affiliation
    safe_payload = dict(payload)
    if not is_admin:
        for protected_field in (
            "role",
            "inspection_role",
            "user_status",
            "project_ids",
            "company_affiliation",
            "company",
            "token_version",
        ):
            safe_payload.pop(protected_field, None)

    if safe_payload.get("password"):
        pw_raw = str(safe_payload["password"])
        _validate_strong_password(pw_raw)
        safe_payload["password"] = hash_password(pw_raw)

    updated = inspectflow_db.update_user(user_id, safe_payload)
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")

    record_audit_event(
        "user",
        user_id,
        "USER_UPDATED",
        actor=current_user,
        after={k: v for k, v in safe_payload.items() if k != "password"},
        ip_address=request.client.host if request.client else None,
    )
    return updated
