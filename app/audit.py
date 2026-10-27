
from flask import Blueprint, render_template, request
from flask_login import current_user

from app import db
from app.access import admin_required
from app.models import AuditLog

audit_bp = Blueprint("audit", __name__)

ACTION_LABELS = {
    "sign_in": "Signed in",
    "sign_in_failed": "Sign-in failed",
    "sign_out": "Signed out",
    "create": "Created",
    "update": "Updated",
    "delete": "Removed",
    "download": "Downloaded",
}


def record(action, entity_type, message, entity_id=None, user_id=None):
    if user_id is None and current_user.is_authenticated:
        user_id = current_user.id

    text = " ".join((message or "").split())
    if not text:
        text = "Recorded."

    db.session.add(
        AuditLog(
            user_id=user_id,
            action=(action or "update")[:40],
            entity_type=(entity_type or "record")[:40],
            entity_id=entity_id,
            message=text[:500],
        )
    )


@audit_bp.route("/audit")
@admin_required
def audit_list():
    q = (request.args.get("q") or "").strip()[:100]
    action = request.args.get("action") or "all"

    if action not in ACTION_LABELS and action != "all":
        action = "all"

    query = db.session.query(AuditLog)

    if action != "all":
        query = query.filter(AuditLog.action == action)

    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.filter(
            AuditLog.message.ilike(f"%{escaped}%", escape="\\")
        )

    total = query.count()
    rows = query.order_by(AuditLog.id.desc()).limit(100).all()

    return render_template(
        "audit_list.html",
        rows=rows,
        total=total,
        q=q,
        action=action,
        action_labels=ACTION_LABELS,
    )
