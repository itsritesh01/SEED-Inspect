from datetime import date

from flask import Blueprint, render_template, request, url_for
from flask_login import login_required
from sqlalchemy import or_

from app import db
from app.models import (
    Attachment,
    ChecklistItem,
    CorrectiveAction,
    Finding,
    Inspection,
    Project,
    Site,
)

dashboard_bp = Blueprint("dashboard", __name__)

ACTION_STATUSES = {"open", "in_progress", "completed"}
ACTION_STATUS_LABELS = {
    "open": "Open",
    "in_progress": "In progress",
    "completed": "Completed",
}


def like_pattern(value):
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def search_rows(model, columns, pattern):
    query = db.session.query(model).filter(
        or_(*(column.ilike(pattern, escape="\\") for column in columns))
    )
    return query.order_by(model.id).limit(21).all()


def limited(rows):
    return rows[:20], len(rows) > 20


@dashboard_bp.route("/dashboard")
@login_required
def dashboard():
    today = date.today()
    open_findings = ("open", "in_progress")
    open_actions = ("open", "in_progress")

    counts = {
        "active_projects": db.session.query(Project).filter_by(status="active").count(),
        "active_sites": db.session.query(Site).filter_by(is_active=True).count(),
        "inspections_in_progress": (
            db.session.query(Inspection).filter_by(status="in_progress").count()
        ),
        "open_findings": (
            db.session.query(Finding).filter(Finding.status.in_(open_findings)).count()
        ),
        "open_actions": (
            db.session.query(CorrectiveAction)
            .filter(CorrectiveAction.status.in_(open_actions))
            .count()
        ),
        "past_due_actions": (
            db.session.query(CorrectiveAction)
            .filter(
                CorrectiveAction.status != "completed",
                CorrectiveAction.due_date < today,
            )
            .count()
        ),
        "fail_lines": (
            db.session.query(ChecklistItem).filter_by(result="fail").count()
        ),
        "files": db.session.query(Attachment).count(),
    }

    recent_inspections = (
        db.session.query(Inspection).order_by(Inspection.id.desc()).limit(5).all()
    )
    recent_findings = (
        db.session.query(Finding).order_by(Finding.id.desc()).limit(5).all()
    )

    return render_template(
        "dashboard.html",
        counts=counts,
        today=today,
        recent_inspections=recent_inspections,
        recent_findings=recent_findings,
    )


@dashboard_bp.route("/search")
@login_required
def search():
    q = (request.args.get("q") or "").strip()[:100]
    groups = []

    if len(q) >= 2:
        pattern = like_pattern(q)

        project_rows, project_more = limited(
            search_rows(
                Project,
                [
                    Project.name,
                    Project.code,
                    Project.client_name,
                    Project.location_summary,
                ],
                pattern,
            )
        )

        site_rows, site_more = limited(
            search_rows(Site, [Site.name, Site.code, Site.address], pattern)
        )

        inspection_rows, inspection_more = limited(
            search_rows(
                Inspection,
                [Inspection.title, Inspection.inspection_number, Inspection.summary],
                pattern,
            )
        )

        finding_rows, finding_more = limited(
            search_rows(Finding, [Finding.title, Finding.description], pattern)
        )

        action_rows, action_more = limited(
            search_rows(
                CorrectiveAction,
                [CorrectiveAction.action_text, CorrectiveAction.responsible_name],
                pattern,
            )
        )

        groups = [
            {
                "title": "Projects",
                "more": project_more,
                "rows": [
                    {
                        "label": f"{row.code} — {row.name}",
                        "url": url_for(
                            "projects.project_detail", project_id=row.id
                        ),
                    }
                    for row in project_rows
                ],
            },
            {
                "title": "Sites",
                "more": site_more,
                "rows": [
                    {
                        "label": f"{row.code} — {row.name}",
                        "url": url_for(
                            "projects.project_detail", project_id=row.project_id
                        ),
                    }
                    for row in site_rows
                ],
            },
            {
                "title": "Inspections",
                "more": inspection_more,
                "rows": [
                    {
                        "label": f"{row.inspection_number} — {row.title}",
                        "url": url_for(
                            "inspections.inspection_detail", inspection_id=row.id
                        ),
                    }
                    for row in inspection_rows
                ],
            },
            {
                "title": "Findings",
                "more": finding_more,
                "rows": [
                    {
                        "label": row.title,
                        "url": url_for(
                            "findings.finding_detail", finding_id=row.id
                        ),
                    }
                    for row in finding_rows
                ],
            },
            {
                "title": "Corrective actions",
                "more": action_more,
                "rows": [
                    {
                        "label": row.action_text,
                        "url": url_for(
                            "findings.action_detail",
                            finding_id=row.finding_id,
                            action_id=row.id,
                        ),
                    }
                    for row in action_rows
                ],
            },
        ]

    return render_template("search.html", q=q, groups=groups)


@dashboard_bp.route("/actions")
@login_required
def action_list():
    today = date.today()
    status = request.args.get("status") or "all"
    due = request.args.get("due") or "all"

    if status not in ACTION_STATUSES and status not in ("all", "unfinished"):
        status = "all"

    if due not in ("all", "past", "not_past"):
        due = "all"

    query = db.session.query(CorrectiveAction)

    if status == "unfinished":
        query = query.filter(
            CorrectiveAction.status.in_(("open", "in_progress"))
        )
    elif status != "all":
        query = query.filter(CorrectiveAction.status == status)

    if due == "past":
        query = query.filter(
            CorrectiveAction.status != "completed",
            CorrectiveAction.due_date < today,
        )
    elif due == "not_past":
        query = query.filter(
            or_(
                CorrectiveAction.status == "completed",
                CorrectiveAction.due_date >= today,
            )
        )

    rows = query.order_by(CorrectiveAction.due_date, CorrectiveAction.id).all()

    return render_template(
        "action_list.html",
        rows=rows,
        status=status,
        due=due,
        today=today,
        status_labels=ACTION_STATUS_LABELS,
    )