



from flask import Blueprint, current_app, render_template
from sqlalchemy import inspect
from sqlalchemy.exc import OperationalError

from app import db
from app.access import admin_required
from app.models import (
    Attachment,
    AuditLog,
    ChecklistItem,
    CorrectiveAction,
    Finding,
    Inspection,
    Project,
    Site,
    User,
)

main = Blueprint("main", __name__)

TABLES = [
    (User, "People who can sign in."),
    (Project, "Engineering projects. A project can be active or archived."),
    (Site, "A construction or environmental place that belongs to one project."),
    (Inspection, "One visit to a site. Its status can be draft, in progress, completed, or cancelled."),
    (ChecklistItem, "One checklist line: Pass, Fail, Not Applicable, or Not Inspected."),
    (Finding, "A problem linked to one inspection. Status can be open, in progress, resolved, or closed."),
    (CorrectiveAction, "Work to fix one finding. Status can be open, in progress, or completed."),
    (Attachment, "A JPG, PNG, or PDF linked to one inspection, finding, or corrective action."),
    (AuditLog, "A history of sign-ins and changes made after this stage. Older practice work is not copied here."),
]


@main.route("/")
def home():
    return render_template("home.html")


@main.route("/about")
def about():
    return render_template("about.html")


@main.route("/database")
@admin_required
def database_check():
    rows = []
    missing = True
    try:
        existing = set(inspect(db.engine).get_table_names())
        for model, explanation in TABLES:
            name = model.__tablename__
            if name not in existing:
                count = None
            else:
                count = db.session.query(model).count()
            rows.append({"name": name, "explanation": explanation, "count": count})
        missing = any(item["count"] is None for item in rows)
    except OperationalError:
        rows = []
        missing = True

    ready = (not missing) and bool(rows)
    return render_template(
        "database.html",
        db_file=current_app.config["DATABASE_FILE"],
        rows=rows,
        ready=ready,
        missing=missing,
    )