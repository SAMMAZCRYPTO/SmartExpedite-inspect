import base64
import hashlib
import hmac
import json
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from fastapi import Depends, HTTPException, Request, status

from backend_v2.core.config import settings
from backend_v2.core.passwords import hash_password, is_password_hashed, verify_password  # noqa: F401
from python_app import database as inspectflow_db

AUTH_COOKIE_NAME = "inspectflow_access_token"


def _b64url_decode(data: str) -> bytes:
    pad = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data + pad)


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def effective_role(user: Optional[Dict[str, Any]]) -> str:
    if not user:
        return ""
    return str(
        user.get("effective_role")
        or user.get("inspection_role")
        or user.get("role")
        or ""
    ).strip().lower()


def is_admin_user(user: Optional[Dict[str, Any]]) -> bool:
    if not user:
        return False
    return effective_role(user) == "admin" or str(user.get("role") or "").strip().lower() == "admin"


# ── Compact Signed JWT (HS256) ───────────────────────────────────────────────

def _sign_hs256(signing_input: bytes) -> str:
    sig = hmac.new(
        settings.jwt_secret.encode("utf-8"), signing_input, hashlib.sha256
    ).digest()
    return _b64url_encode(sig)


def create_access_token(
    user: Dict[str, Any], expires_hours: Optional[int] = None
) -> str:
    now = int(time.time())
    ttl = (expires_hours or settings.jwt_expire_hours) * 3600
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "jti": uuid.uuid4().hex,
        "sub": str(user.get("id") or ""),
        "email": user.get("email") or "",
        "full_name": user.get("full_name") or "",
        "role": user.get("inspection_role") or user.get("role") or "guest",
        "base_role": user.get("role") or "guest",
        "inspection_role": user.get("inspection_role") or user.get("role") or "guest",
        "company_affiliation": user.get("company_affiliation") or user.get("company") or "",
        "department": user.get("department") or "",
        "project_ids": user.get("project_ids") or [],
        "token_version": int(user.get("token_version") or 1),
        "iat": now,
        "exp": now + ttl,
        "mode": settings.auth_mode,
    }
    h_enc = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    p_enc = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{h_enc}.{p_enc}".encode("ascii")
    sig_enc = _sign_hs256(signing_input)
    return f"{h_enc}.{p_enc}.{sig_enc}"


def decode_access_token(token: str) -> Dict[str, Any]:
    if not token or token.count(".") != 2:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token format",
        )
    h_enc, p_enc, sig_enc = token.split(".", 2)
    signing_input = f"{h_enc}.{p_enc}".encode("ascii")
    expected_sig = _sign_hs256(signing_input)
    if not hmac.compare_digest(sig_enc, expected_sig):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token signature",
        )
    try:
        header = json.loads(_b64url_decode(h_enc).decode("utf-8"))
        if not isinstance(header, dict) or header.get("alg") != "HS256" or header.get("typ") != "JWT":
            raise ValueError("Invalid JWT header")
        payload = json.loads(_b64url_decode(p_enc).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Invalid JWT payload")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Corrupt authentication token payload",
        )
    if int(payload.get("exp") or 0) < int(time.time()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Please sign in again.",
        )
    token_mode = str(payload.get("mode") or "")
    if token_mode != settings.auth_mode:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token was issued for a different authentication mode. Please sign in again.",
        )
    jti = str(payload.get("jti") or "")
    if jti and inspectflow_db.is_token_revoked(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been signed out. Please sign in again.",
        )
    return payload


def extract_token_from_request(request: Request) -> Optional[str]:
    auth_header = request.headers.get("Authorization") or ""
    if auth_header.lower().startswith("bearer "):
        tok = auth_header[7:].strip()
        if tok:
            return tok
    cookie_tok = request.cookies.get(AUTH_COOKIE_NAME)
    if cookie_tok:
        return cookie_tok.strip()
    return None


def _enrich_live_user(claims: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve latest live user status & project assignments from DB (fail-closed)."""
    uid = claims.get("sub")
    email = claims.get("email")
    users = inspectflow_db.list_users()
    match = next(
        (
            u
            for u in users
            if (uid and str(u.get("id")).lower() == str(uid).lower())
            or (email and str(u.get("email")).lower() == str(email).lower())
        ),
        None,
    )
    if not match:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found or session invalidated. Please sign in again.",
        )
    user_status = str(match.get("user_status") or "active").lower()
    if user_status == "deactivated":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account deactivated. Contact administrator.",
        )
    if user_status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is pending administrator activation.",
        )
    claim_tv = int(claims.get("token_version") or 1)
    live_tv = int(match.get("token_version") or 1)
    if claim_tv != live_tv:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session invalidated due to account or credential update. Please sign in again.",
        )
    return {
        **match,
        "effective_role": str(
            match.get("inspection_role") or match.get("role") or "guest"
        ).lower(),
        "_token_jti": claims.get("jti"),
        "_token_exp": claims.get("exp"),
    }


def get_current_user(request: Request) -> Dict[str, Any]:
    token = extract_token_from_request(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please sign in.",
        )
    claims = decode_access_token(token)
    return _enrich_live_user(claims)


def get_optional_user(request: Request) -> Optional[Dict[str, Any]]:
    token = extract_token_from_request(request)
    if not token:
        return None
    try:
        claims = decode_access_token(token)
        return _enrich_live_user(claims)
    except HTTPException:
        return None


def require_roles(*allowed_roles: str) -> Callable[[Request], Dict[str, Any]]:
    normalized = {r.lower() for r in allowed_roles}

    def dependency(request: Request, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        eff = effective_role(user)
        base = str(user.get("role") or "").lower()
        if is_admin_user(user):
            return user
        if eff in normalized or base in normalized:
            return user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied for role '{eff}'. Required: {', '.join(sorted(normalized))}",
        )

    return dependency


def is_vendor_user(user: Optional[Dict[str, Any]]) -> bool:
    if not user:
        return False
    return effective_role(user) == "vendor"


def user_can_access_project_id(user: Dict[str, Any], project_id: Optional[str]) -> bool:
    if is_admin_user(user):
        return True
    pid = str(project_id or "").strip().lower()
    if not pid or pid == "all":
        return False
    for proj in inspectflow_db.list_projects():
        if str(proj.get("id") or "").strip().lower() == pid:
            return inspectflow_db.user_has_project_access(user, proj)
    return False


def vendor_owns_po(user: Dict[str, Any], po_rec: Dict[str, Any]) -> bool:
    if not is_vendor_user(user):
        return True
    uid = str(user.get("id") or "").strip().lower()
    uemail = str(user.get("email") or "").strip().lower()
    ucompany = str(user.get("company_affiliation") or user.get("company") or "").strip().lower()

    rec_vid = str(po_rec.get("assigned_vendor_id") or "").strip().lower()
    rec_vemail = str(po_rec.get("assigned_vendor_email") or "").strip().lower()
    rec_sup = str(po_rec.get("supplier") or "").strip().lower()
    rec_sup_short = str(po_rec.get("supplierShort") or "").strip().lower()

    if rec_vid and uid and rec_vid == uid:
        return True
    if rec_vemail and uemail and rec_vemail == uemail:
        return True
    # Only fall back to exact normalized company match if PO lacks explicit vendor assignment
    if not rec_vid and not rec_vemail and ucompany and ucompany not in ("vendor", "supplier"):
        if ucompany == rec_sup or (rec_sup_short and ucompany == rec_sup_short):
            return True
    return False


def user_can_access_po(user: Dict[str, Any], po_rec: Optional[Dict[str, Any]]) -> bool:
    """Strict tenant check for PO records across Vendors, Guests, and Internal Project Staff."""
    if not user or not po_rec:
        return False
    if is_admin_user(user):
        return True
    eff = effective_role(user)
    if eff in ("", "guest"):
        return False
    if eff == "vendor":
        return vendor_owns_po(user, po_rec)
    rec_pid = str(po_rec.get("project_id") or "").strip().lower()
    if not rec_pid:
        return False
    return user_can_access_project_id(user, rec_pid)
