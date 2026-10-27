import json

from flask import request
from flask_login import current_user

from ..extensions import db
from ..models import AuditLog


def client_ip():
    fwd = request.headers.get("X-Forwarded-For", "")
    return (fwd.split(",")[0].strip() or request.remote_addr or "")[:45]


def audit(action, target=None, brand_id=None, actor_label=None, **details):
    """Record an audit entry in the current session (caller commits)."""
    user = current_user if current_user and current_user.is_authenticated else None
    if brand_id is None:
        brand_id = getattr(target, "brand_id", None) or (user.brand_id if user else None)
    entry = AuditLog(
        actor_id=user.id if user else None,
        actor_label=actor_label or (user.email if user else "customer"),
        actor_role=user.role if user else "customer",
        brand_id=brand_id,
        action=action,
        target_type=type(target).__name__ if target is not None else None,
        target_id=getattr(target, "id", None),
        details=json.dumps(details, default=str) if details else None,
        ip_address=client_ip(),
    )
    db.session.add(entry)
    return entry
