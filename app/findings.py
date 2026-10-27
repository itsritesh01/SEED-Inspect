from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from app import db
from app.access import editor_required
from app.audit import record
from app.forms import CorrectiveActionForm, FindingForm
from app.models import Attachment, CorrectiveAction, Finding, Inspection, User, utcnow

findings_bp = Blueprint("findings", __name__)

SEVERITIES = {"low", "medium", "high", "critical"}
FINDING_STATUSES = {"open", "in_progress", "resolved", "closed"}
ACTION_STATUSES = {"open", "in_progress", "completed"}

SEVERITY_LABELS = {
    "low": "Low",
    "medium": "Medium",
    "high": "High",
    "critical": "Critical",
}
FINDING_STATUS_LABELS = {
    "open": "Open",
    "in_progress": "In progress",
    "resolved": "Resolved",
    "closed": "Closed",
}
ACTION_STATUS_LABELS = {
    "open": "Open",
    "in_progress": "In progress",
    "completed": "Completed",
}


def can_edit():
    return current_user.is_authenticated and current_user.role in (
        "administrator",
        "inspector",
    )


def clean_line(value):
    return " ".join((value or "").split())


def get_inspection_or_404(inspection_id):
    inspection = db.session.get(Inspection, inspection_id)
    if inspection is None:
        abort(404)
    return inspection


def get_finding_or_404(finding_id):
    finding = db.session.get(Finding, finding_id)
    if finding is None:
        abort(404)
    return finding


def get_action_or_404(finding, action_id):
    action = db.session.get(CorrectiveAction, action_id)
    if action is None or action.finding_id != finding.id:
        abort(404)
    return action


def user_choices():
    people = (
        db.session.query(User)
        .filter(User.is_active.is_(True))
        .order_by(User.full_name, User.id)
        .all()
    )
    choices = [("", "No account linked")]
    for person in people:
        choices.append((person.id, f"{person.full_name} ({person.role_label})"))
    return choices


def fill_action_form(form):
    form.responsible_user_id.choices = user_choices()


def apply_finding(finding, form):
    title = clean_line(form.title.data)
    description = (form.description.data or "").strip()
    evidence = (form.evidence_note.data or "").strip()
    if not title or len(title) > 150:
        return "Enter a title of 150 characters or fewer."
    if not description or len(description) > 2000:
        return "Enter a description of 2000 characters or fewer."
    if len(evidence) > 2000:
        return "Use 2000 characters or fewer for the evidence note."
    if form.severity.data not in SEVERITIES:
        return "Choose Low, Medium, High, or Critical."
    if form.status.data not in FINDING_STATUSES:
        return "Choose a valid finding status."
    finding.title = title
    finding.description = description
    finding.evidence_note = evidence or None
    finding.severity = form.severity.data
    finding.status = form.status.data
    finding.updated_at = utcnow()
    return None


def apply_action(action, form):
    text = (form.action_text.data or "").strip()
    name = clean_line(form.responsible_name.data)
    note = (form.progress_note.data or "").strip()
    if not text or len(text) > 2000:
        return "Describe the corrective action in 2000 characters or fewer."
    if not name or len(name) > 120:
        return "Enter the responsible person's name, using 120 characters or fewer."
    if len(note) > 2000:
        return "Use 2000 characters or fewer for the progress note."
    if form.status.data not in ACTION_STATUSES:
        return "Choose Open, In progress, or Completed."
    if form.due_date.data is None:
        return "Enter a due date."

    user_id = form.responsible_user_id.data
    if user_id is not None:
        person = db.session.get(User, user_id)
        if person is None or not person.is_active:
            return "Choose an active account, or leave the account blank."
    action.action_text = text
    action.responsible_name = name
    action.responsible_user_id = user_id
    action.due_date = form.due_date.data
    action.progress_note = note or None
    if form.status.data == "completed":
        if action.completed_at is None:
            action.completed_at = utcnow()
    else:
        action.completed_at = None
    action.status = form.status.data
    action.updated_at = utcnow()
    return None


@findings_bp.route("/findings")
@login_required
def finding_list():
    q = (request.args.get("q") or "").strip()[:100]
    status = request.args.get("status") or "all"
    severity = request.args.get("severity") or "all"
    if status not in FINDING_STATUSES and status not in ("all", "unfinished"):
        status = "all"
    if severity not in SEVERITIES and severity != "all":
        severity = "all"

    query = db.session.query(Finding)
    if status == "unfinished":
        query = query.filter(Finding.status.in_(("open", "in_progress")))
    elif status != "all":
        query = query.filter(Finding.status == status)
    if severity != "all":
        query = query.filter(Finding.severity == severity)
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        query = query.filter(
            or_(
                Finding.title.ilike(pattern, escape="\\"),
                Finding.description.ilike(pattern, escape="\\"),
            )
        )
    rows = query.order_by(Finding.id).all()
    return render_template(
        "finding_list.html",
        rows=rows,
        q=q,
        status=status,
        severity=severity,
        can_edit=can_edit(),
        severity_labels=SEVERITY_LABELS,
        status_labels=FINDING_STATUS_LABELS,
    )


@findings_bp.route("/inspections/<int:inspection_id>/findings/new", methods=["GET", "POST"])
@editor_required
def finding_new(inspection_id):
    inspection = get_inspection_or_404(inspection_id)
    form = FindingForm()
    if form.validate_on_submit():
        finding = Finding(
            inspection_id=inspection.id,
            title="Pending",
            description="Pending",
            severity="medium",
            status="open",
            created_by_id=current_user.id,
        )
        error = apply_finding(finding, form)
        if error:
            flash(error, "danger")
        else:
            db.session.add(finding)
            try:
                db.session.flush()
                record("create", "finding", f"Recorded finding {finding.title}.", finding.id)
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash("The finding could not be saved.", "danger")
            else:
                flash("Finding recorded. This did not change the checklist.", "success")
                return redirect(url_for("findings.finding_detail", finding_id=finding.id))
    return render_template(
        "finding_form.html",
        form=form,
        heading="Add finding",
        inspection=inspection,
        cancel_url=url_for("inspections.inspection_detail", inspection_id=inspection.id),
    )


@findings_bp.route("/findings/<int:finding_id>")
@login_required
def finding_detail(finding_id):
    finding = get_finding_or_404(finding_id)
    actions = (
        db.session.query(CorrectiveAction)
        .filter_by(finding_id=finding.id)
        .order_by(CorrectiveAction.due_date, CorrectiveAction.id)
        .all()
    )
    finding_files = (
        db.session.query(Attachment)
        .filter_by(finding_id=finding.id)
        .order_by(Attachment.id)
        .all()
    )
    return render_template(
        "finding_detail.html",
        finding=finding,
        actions=actions,
        finding_files=finding_files,
        can_edit=can_edit(),
        severity_labels=SEVERITY_LABELS,
        status_labels=FINDING_STATUS_LABELS,
        action_status_labels=ACTION_STATUS_LABELS,
    )


@findings_bp.route("/findings/<int:finding_id>/edit", methods=["GET", "POST"])
@editor_required
def finding_edit(finding_id):
    finding = get_finding_or_404(finding_id)
    form = FindingForm(obj=finding)
    if form.validate_on_submit():
        error = apply_finding(finding, form)
        if error:
            flash(error, "danger")
        else:
            record("update", "finding", f"Updated finding {finding.title}.", finding.id)
            db.session.commit()
            flash("Finding updated.", "success")
            return redirect(url_for("findings.finding_detail", finding_id=finding.id))
    return render_template(
        "finding_form.html",
        form=form,
        heading="Edit finding",
        inspection=finding.inspection,
        cancel_url=url_for("findings.finding_detail", finding_id=finding.id),
    )


@findings_bp.route("/findings/<int:finding_id>/actions/<int:action_id>")
@login_required
def action_detail(finding_id, action_id):
    finding = get_finding_or_404(finding_id)
    action = get_action_or_404(finding, action_id)
    action_files = (
        db.session.query(Attachment)
        .filter_by(corrective_action_id=action.id)
        .order_by(Attachment.id)
        .all()
    )
    return render_template(
        "action_detail.html",
        finding=finding,
        action=action,
        action_files=action_files,
        can_edit=can_edit(),
        action_status_labels=ACTION_STATUS_LABELS,
    )


@findings_bp.route("/findings/<int:finding_id>/actions/new", methods=["GET", "POST"])
@editor_required
def action_new(finding_id):
    finding = get_finding_or_404(finding_id)
    form = CorrectiveActionForm()
    fill_action_form(form)
    if form.validate_on_submit():
        action = CorrectiveAction(
            finding_id=finding.id,
            action_text="Pending",
            responsible_name="Pending",
            due_date=form.due_date.data,
            status="open",
            created_by_id=current_user.id,
        )
        error = apply_action(action, form)
        if error:
            flash(error, "danger")
        else:
            db.session.add(action)
            try:
                db.session.flush()
                record(
                    "create",
                    "action",
                    f"Added a corrective action to finding {finding.title}.",
                    action.id,
                )
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash("The corrective action could not be saved.", "danger")
            else:
                flash("Corrective action added. The finding status was not changed.", "success")
                return redirect(url_for("findings.finding_detail", finding_id=finding.id))
    return render_template(
        "action_form.html",
        form=form,
        heading="Add corrective action",
        finding=finding,
        cancel_url=url_for("findings.finding_detail", finding_id=finding.id),
    )


@findings_bp.route(
    "/findings/<int:finding_id>/actions/<int:action_id>/edit",
    methods=["GET", "POST"],
)
@editor_required
def action_edit(finding_id, action_id):
    finding = get_finding_or_404(finding_id)
    action = get_action_or_404(finding, action_id)
    form = CorrectiveActionForm(obj=action)
    fill_action_form(form)
    if request.method == "GET":
        form.responsible_user_id.data = action.responsible_user_id or ""
    if form.validate_on_submit():
        error = apply_action(action, form)
        if error:
            flash(error, "danger")
        else:
            record(
                "update",
                "action",
                f"Updated a corrective action on finding {finding.title}.",
                action.id,
            )
            db.session.commit()
            flash("Corrective action updated.", "success")
            return redirect(url_for("findings.finding_detail", finding_id=finding.id))
    return render_template(
        "action_form.html",
        form=form,
        heading="Edit corrective action",
        finding=finding,
        cancel_url=url_for("findings.finding_detail", finding_id=finding.id),
    )