import json
import logging
from typing import Any, Dict, Optional

from backend_v2.core.database import SessionLocal
from backend_v2.models.epc_models import AuditEvent

logger = logging.getLogger("inspectflow.audit")


def record_audit_event(
    entity_type: str,
    entity_id: str,
    action: str,
    actor: Optional[Dict[str, Any]] = None,
    before: Any = None,
    after: Any = None,
    notes: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> None:
    """Append an immutable compliance audit record to audit_events."""
    try:
        with SessionLocal() as db:
            ev = AuditEvent(
                entity_type=str(entity_type),
                entity_id=str(entity_id),
                action=str(action),
                actor_id=str(actor.get("id")) if actor and actor.get("id") else None,
                actor_email=str(actor.get("email")) if actor and actor.get("email") else None,
                actor_role=str(
                    actor.get("effective_role") or actor.get("inspection_role") or actor.get("role")
                ) if actor else "system",
                before_json=json.dumps(before, default=str) if before is not None else None,
                after_json=json.dumps(after, default=str) if after is not None else None,
                notes=notes,
                ip_address=ip_address,
            )
            db.add(ev)
            db.commit()
    except Exception:
        logger.exception("Failed to write audit event %s on %s/%s", action, entity_type, entity_id)
