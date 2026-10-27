
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from app import db
from app.access import editor_required
from app.audit import record
from app.forms import ChecklistItemForm, InspectionForm
from app.models import (
    Attachment,
    ChecklistItem,
    Finding,
    Inspection,
    Project,
    Site,
    User,
    utcnow,
)

inspections_bp = Blueprint("inspections", __name__)

INSPECTION_TYPES = {"general", "safety", "quality", "environmental"}
INSPECTION_STATUSES = {"draft", "in_progress", "completed", "cancelled"}
CHECKLIST_RESULTS = {"pass", "fail", "not_applicable", "not_inspected"}

TYPE_LABELS = {
    "general": "General",
    "safety": "Safety",
    "quality": "Quality",
    "environmental": "Environmental",
}

STATUS_LABELS = {
    "draft": "Draft",
    "in_progress": "In progress",
    "completed": "Completed",
    "cancelled": "Cancelled",
}

RESULT_LABELS = {
    "pass": "Pass",
    "fail": "Fail",
    "not_applicable": "Not applicable",
    "not_inspected": "Not inspected",
}


def can_edit():
    from flask_login import current_user

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


def inspector_choices():
    people = (
        db.session.query(User)
        .filter(
            User.is_active.is_(True),
            User.role.in_(("administrator", "inspector")),
        )
        .order_by(User.full_name, User.id)
        .all()
    )
    choices = [("", "No inspector selected")]
    for person in people:
        choices.append((person.id, f"{person.full_name} ({person.role_label})"))
    return choices


def fill_inspection_form(form, project):
    sites = (
        db.session.query(Site)
        .filter_by(project_id=project.id)
        .order_by(Site.name, Site.id)
        .all()
    )
    site_choices = []
    for site in sites:
        label = f"{site.code} — {site.name}"
        if not site.is_active:
            label += " (turned off)"
        site_choices.append((site.id, label))

    form.site_id.choices = site_choices
    form.inspector_id.choices = inspector_choices()
    return sites


def apply_inspection_form(inspection, form, project, sites):
    site_ids = {site.id for site in sites}
    if form.site_id.data not in site_ids:
        return "Choose a site that belongs to this project."

    if form.inspection_type.data not in INSPECTION_TYPES:
        return "Choose a valid inspection type."

    if form.status.data not in INSPECTION_STATUSES:
        return "Choose a valid status."

    number = form.inspection_number.data
    taken = db.session.query(Inspection).filter(
        Inspection.inspection_number == number
    )
    if inspection.id is not None:
        taken = taken.filter(Inspection.id != inspection.id)

    if taken.first() is not None:
        return "That inspection number is already used."

    inspector_id = form.inspector_id.data
    if inspector_id is not None:
        inspector = db.session.get(User, inspector_id)
        if (
            inspector is None
            or not inspector.is_active
            or inspector.role not in ("administrator", "inspector")
        ):
            return "Choose an active administrator or inspector."

    title = clean_line(form.title.data)
    if not title or len(title) > 150:
        return "Enter a title of 150 characters or fewer."

    inspection.project_id = project.id
    inspection.site_id = form.site_id.data
    inspection.inspection_number = number
    inspection.title = title
    inspection.inspection_type = form.inspection_type.data
    inspection.scheduled_date = form.scheduled_date.data
    inspection.inspector_id = inspector_id
    inspection.summary = (form.summary.data or "").strip() or None

    apply_status(inspection, form.status.data)
    inspection.updated_at = utcnow()
    return None


def apply_status(inspection, new_status):
    if new_status in ("in_progress", "completed") and inspection.started_at is None:
        inspection.started_at = utcnow()

    if new_status == "completed":
        if inspection.completed_at is None:
            inspection.completed_at = utcnow()
    else:
        inspection.completed_at = None

    inspection.status = new_status


def result_counts(items):
    counts = {key: 0 for key in RESULT_LABELS}
    for item in items:
        if item.result in counts:
            counts[item.result] += 1
    return counts


@inspections_bp.route("/inspections")
@login_required
def inspection_list():
    q = (request.args.get("q") or "").strip()
    if len(q) > 100:
        q = q[:100]

    status = request.args.get("status") or "all"
    if status not in INSPECTION_STATUSES and status != "all":
        status = "all"

    query = db.session.query(Inspection)

    if status != "all":
        query = query.filter(Inspection.status == status)

    if q:
        escaped = (
            q.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        pattern = f"%{escaped}%"
        query = query.filter(
            or_(
                Inspection.title.ilike(pattern, escape="\\"),
                Inspection.inspection_number.ilike(pattern, escape="\\"),
            )
        )

    rows = query.order_by(Inspection.scheduled_date, Inspection.id).all()

    return render_template(
        "inspection_list.html",
        rows=rows,
        q=q,
        status=status,
        can_edit=can_edit(),
        status_labels=STATUS_LABELS,
        type_labels=TYPE_LABELS,
    )


@inspections_bp.route("/inspections/new", methods=["GET", "POST"])
@editor_required
def inspection_new():
    projects = db.session.query(Project).order_by(Project.name, Project.id).all()
    raw_project_id = request.values.get("project_id", type=int)
    project = db.session.get(Project, raw_project_id) if raw_project_id else None

    if raw_project_id and project is None:
        abort(404)

    form = InspectionForm()
    sites = []

    if project is not None:
        sites = fill_inspection_form(form, project)

        if request.method == "POST" and form.validate_on_submit():
            if not sites:
                flash(
                    "Add a site to this project before creating an inspection.",
                    "danger",
                )
            else:
                inspection = Inspection(
                    project_id=project.id,
                    site_id=sites[0].id,
                    title="Pending",
                    inspection_number="PENDING",
                    inspection_type="general",
                    status="draft",
                    created_by_id=request_user_id(),
                )

                error = apply_inspection_form(
                    inspection, form, project, sites
                )

                if error:
                    flash(error, "danger")
                else:
                    db.session.add(inspection)
                    try:
                        db.session.flush()
                        record(
                            "create",
                            "inspection",
                            f"Created inspection {inspection.inspection_number}: {inspection.title}.",
                            inspection.id,
                        )
                        db.session.commit()
                    except IntegrityError:
                        db.session.rollback()
                        flash(
                            "That inspection number is already used.",
                            "danger",
                        )
                    else:
                        flash("Inspection created.", "success")
                        return redirect(
                            url_for(
                                "inspections.inspection_detail",
                                inspection_id=inspection.id,
                            )
                        )

    return render_template(
        "inspection_form.html",
        form=form,
        heading="Add inspection",
        project=project,
        projects=projects,
        has_sites=bool(sites),
        cancel_url=url_for("inspections.inspection_list"),
    )


def request_user_id():
    from flask_login import current_user

    return current_user.id


@inspections_bp.route("/inspections/<int:inspection_id>")
@login_required
def inspection_detail(inspection_id):
    inspection = get_inspection_or_404(inspection_id)

    items = (
        db.session.query(ChecklistItem)
        .filter_by(inspection_id=inspection.id)
        .order_by(ChecklistItem.sort_order, ChecklistItem.id)
        .all()
    )

    findings = (
        db.session.query(Finding)
        .filter_by(inspection_id=inspection.id)
        .order_by(Finding.id)
        .all()
    )

    inspection_files = (
        db.session.query(Attachment)
        .filter_by(inspection_id=inspection.id)
        .order_by(Attachment.id)
        .all()
    )

    return render_template(
        "inspection_detail.html",
        inspection=inspection,
        items=items,
        findings=findings,
        inspection_files=inspection_files,
        counts=result_counts(items),
        add_form=ChecklistItemForm(),
        can_edit=can_edit(),
        status_labels=STATUS_LABELS,
        type_labels=TYPE_LABELS,
        result_labels=RESULT_LABELS,
    )


@inspections_bp.route(
    "/inspections/<int:inspection_id>/edit",
    methods=["GET", "POST"],
)
@editor_required
def inspection_edit(inspection_id):
    inspection = get_inspection_or_404(inspection_id)
    project = inspection.project
    form = InspectionForm(obj=inspection)
    sites = fill_inspection_form(form, project)

    if request.method == "GET":
        form.inspector_id.data = inspection.inspector_id or ""

    if form.validate_on_submit():
        error = apply_inspection_form(inspection, form, project, sites)

        if error:
            flash(error, "danger")
        else:
            try:
                record(
                    "update",
                    "inspection",
                    f"Updated inspection {inspection.inspection_number}: {inspection.title}.",
                    inspection.id,
                )
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash("That inspection number is already used.", "danger")
            else:
                flash("Inspection updated.", "success")
                return redirect(
                    url_for(
                        "inspections.inspection_detail",
                        inspection_id=inspection.id,
                    )
                )

    return render_template(
        "inspection_form.html",
        form=form,
        heading="Edit inspection",
        project=project,
        projects=[],
        has_sites=bool(sites),
        cancel_url=url_for(
            "inspections.inspection_detail",
            inspection_id=inspection.id,
        ),
    )


@inspections_bp.route(
    "/inspections/<int:inspection_id>/checklist",
    methods=["POST"],
)
@editor_required
def checklist_add(inspection_id):
    inspection = get_inspection_or_404(inspection_id)
    form = ChecklistItemForm()

    if form.validate_on_submit():
        text = clean_line(form.item_text.data)

        if not text or len(text) > 300:
            flash("Enter a checklist line of 300 characters or fewer.", "danger")
        else:
            current = (
                db.session.query(db.func.max(ChecklistItem.sort_order))
                .filter_by(inspection_id=inspection.id)
                .scalar()
            )

            item = ChecklistItem(
                inspection_id=inspection.id,
                sort_order=(current or 0) + 1,
                item_text=text,
                result="not_inspected",
            )

            db.session.add(item)
            db.session.flush()
            record(
                "create",
                "checklist_item",
                f"Added a checklist line to inspection {inspection.inspection_number}.",
                item.id,
            )
            db.session.commit()
            flash("Checklist line added.", "success")
    else:
        flash("Enter a checklist line of 300 characters or fewer.", "danger")

    return redirect(
        url_for("inspections.inspection_detail", inspection_id=inspection.id)
    )


@inspections_bp.route(
    "/inspections/<int:inspection_id>/checklist/save",
    methods=["POST"],
)
@editor_required
def checklist_save(inspection_id):
    inspection = get_inspection_or_404(inspection_id)

    ids = request.form.getlist("item_id")
    texts = request.form.getlist("item_text")
    results = request.form.getlist("result")
    notes = request.form.getlist("notes")
    orders = request.form.getlist("sort_order")

    if not ids:
        flash("There are no checklist lines to save.", "warning")
        return redirect(
            url_for("inspections.inspection_detail", inspection_id=inspection.id)
        )

    if not (len(ids) == len(texts) == len(results) == len(notes) == len(orders)):
        flash(
            "The checklist could not be read. Reload the page and try again.",
            "danger",
        )
        return redirect(
            url_for("inspections.inspection_detail", inspection_id=inspection.id)
        )

    items = {item.id: item for item in inspection.checklist_items}
    parsed = []

    for raw_id, text, result, note, raw_order in zip(
        ids, texts, results, notes, orders
    ):
        try:
            item_id = int(raw_id)
            sort_order = int(raw_order)
        except ValueError:
            flash(
                "The checklist could not be read. Reload the page and try again.",
                "danger",
            )
            return redirect(
                url_for("inspections.inspection_detail", inspection_id=inspection.id)
            )

        item = items.get(item_id)
        if item is None:
            flash("One checklist line does not belong to this inspection.", "danger")
            return redirect(
                url_for("inspections.inspection_detail", inspection_id=inspection.id)
            )

        if result not in CHECKLIST_RESULTS:
            flash("Choose Pass, Fail, Not Applicable, or Not Inspected.", "danger")
            return redirect(
                url_for("inspections.inspection_detail", inspection_id=inspection.id)
            )

        cleaned = clean_line(text)
        if not cleaned or len(cleaned) > 300:
            flash(
                "Each checklist line needs text of 300 characters or fewer.",
                "danger",
            )
            return redirect(
                url_for("inspections.inspection_detail", inspection_id=inspection.id)
            )

        if len(note or "") > 1000:
            flash("Notes must be 1000 characters or fewer.", "danger")
            return redirect(
                url_for("inspections.inspection_detail", inspection_id=inspection.id)
            )

        if sort_order < 1 or sort_order > 999:
            flash("Order must be a number from 1 to 999.", "danger")
            return redirect(
                url_for("inspections.inspection_detail", inspection_id=inspection.id)
            )

        parsed.append(
            (item, cleaned, result, (note or "").strip() or None, sort_order)
        )

    for item, cleaned, result, note, sort_order in parsed:
        item.item_text = cleaned
        item.result = result
        item.notes = note
        item.sort_order = sort_order
        item.updated_at = utcnow()

    record(
        "update",
        "checklist",
        f"Saved checklist results for inspection {inspection.inspection_number}.",
        inspection.id,
    )
    db.session.commit()
    flash("Checklist saved.", "success")

    return redirect(
        url_for("inspections.inspection_detail", inspection_id=inspection.id)
    )


@inspections_bp.route(
    "/inspections/<int:inspection_id>/checklist/<int:item_id>/delete",
    methods=["POST"],
)
@editor_required
def checklist_delete(inspection_id, item_id):
    inspection = get_inspection_or_404(inspection_id)
    item = db.session.get(ChecklistItem, item_id)

    if item is None or item.inspection_id != inspection.id:
        abort(404)

    record(
        "delete",
        "checklist_item",
        f"Removed a checklist line from inspection {inspection.inspection_number}.",
        item.id,
    )
    db.session.delete(item)
    db.session.commit()
    flash("Checklist line removed.", "success")

    return redirect(
        url_for("inspections.inspection_detail", inspection_id=inspection.id)
    )
