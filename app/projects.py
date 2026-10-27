
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from app import db
from app.access import editor_required
from app.audit import record
from app.forms import ProjectForm, SiteCreateForm, SiteEditForm
from app.models import Inspection, Project, Site, utcnow

projects_bp = Blueprint("projects", __name__)

SITE_TYPES = {"construction", "environmental", "other"}

SITE_TYPE_LABELS = {
    "construction": "Construction",
    "environmental": "Environmental",
    "other": "Other",
}


def can_edit():
    return current_user.is_authenticated and current_user.role in (
        "administrator",
        "inspector",
    )


def clean_text(value):
    text = " ".join((value or "").split())
    return text or None


def like_pattern(term):
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def get_project_or_404(project_id):
    project = db.session.get(Project, project_id)
    if project is None:
        abort(404)
    return project


def get_site_or_404(project, site_id):
    site = db.session.get(Site, site_id)
    if site is None or site.project_id != project.id:
        abort(404)
    return site


def _project_dates_problem(form):
    start = form.start_date.data
    end = form.end_date.data
    if start and end and end < start:
        return "The end date cannot be before the start date."
    return None


def _code_taken(model, code, own_id, project_id=None):
    query = db.session.query(model).filter(model.code == code)
    if project_id is not None:
        query = query.filter(model.project_id == project_id)
    if own_id is not None:
        query = query.filter(model.id != own_id)
    return query.first() is not None


def _apply_project_form(project, form):
    problem = _project_dates_problem(form)
    if problem:
        return problem

    code = form.code.data
    if _code_taken(Project, code, project.id):
        return "That project code is already used."

    project.name = clean_text(form.name.data)
    if not project.name:
        return "Enter a project name."

    project.code = code
    project.client_name = clean_text(form.client_name.data)
    project.location_summary = clean_text(form.location_summary.data)
    project.description = (form.description.data or "").strip() or None
    project.start_date = form.start_date.data
    project.end_date = form.end_date.data
    project.updated_at = utcnow()
    return None


def _apply_site_form(site, form, project):
    if form.site_type.data not in SITE_TYPES:
        return "Choose Construction, Environmental, or Other."

    code = form.code.data
    if _code_taken(Site, code, site.id, project_id=project.id):
        return "That site code is already used on this project."

    site.project_id = project.id
    site.name = clean_text(form.name.data)
    if not site.name:
        return "Enter a site name."

    site.code = code
    site.site_type = form.site_type.data
    site.address = clean_text(form.address.data)
    site.description = (form.description.data or "").strip() or None
    site.updated_at = utcnow()

    if isinstance(form, SiteEditForm):
        site.is_active = bool(form.is_active.data)

    return None


@projects_bp.route("/projects")
@login_required
def project_list():
    q = (request.args.get("q") or "").strip()
    if len(q) > 100:
        q = q[:100]

    status = request.args.get("status") or "active"
    if status not in ("active", "archived", "all"):
        status = "active"

    query = db.session.query(Project)

    if status != "all":
        query = query.filter(Project.status == status)

    if q:
        pattern = like_pattern(q)
        query = query.filter(
            or_(
                Project.name.ilike(pattern, escape="\\"),
                Project.code.ilike(pattern, escape="\\"),
                Project.client_name.ilike(pattern, escape="\\"),
                Project.location_summary.ilike(pattern, escape="\\"),
            )
        )

    rows = query.order_by(Project.name, Project.id).all()

    return render_template(
        "project_list.html",
        rows=rows,
        q=q,
        status=status,
        can_edit=can_edit(),
    )


@projects_bp.route("/projects/new", methods=["GET", "POST"])
@editor_required
def project_new():
    form = ProjectForm()

    if form.validate_on_submit():
        project = Project(status="active", created_by_id=current_user.id)
        error = _apply_project_form(project, form)

        if error:
            flash(error, "danger")
        else:
            db.session.add(project)

            try:
                db.session.flush()
                record(
                    "create",
                    "project",
                    f"Created project {project.name} ({project.code}).",
                    project.id,
                )
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash("That project code is already used.", "danger")
            else:
                flash("Project created.", "success")
                return redirect(
                    url_for("projects.project_detail", project_id=project.id)
                )

    return render_template(
        "project_form.html",
        form=form,
        heading="Add project",
        cancel_url=url_for("projects.project_list"),
    )


@projects_bp.route("/projects/<int:project_id>")
@login_required
def project_detail(project_id):
    project = get_project_or_404(project_id)

    sites = (
        db.session.query(Site)
        .filter_by(project_id=project.id)
        .order_by(Site.name, Site.id)
        .all()
    )

    inspections = (
        db.session.query(Inspection)
        .filter_by(project_id=project.id)
        .order_by(Inspection.scheduled_date, Inspection.id)
        .all()
    )

    return render_template(
        "project_detail.html",
        project=project,
        sites=sites,
        inspections=inspections,
        can_edit=can_edit(),
        site_type_labels=SITE_TYPE_LABELS,
    )


@projects_bp.route("/projects/<int:project_id>/edit", methods=["GET", "POST"])
@editor_required
def project_edit(project_id):
    project = get_project_or_404(project_id)
    form = ProjectForm(obj=project)

    if form.validate_on_submit():
        error = _apply_project_form(project, form)

        if error:
            flash(error, "danger")
        else:
            try:
                record(
                    "update",
                    "project",
                    f"Updated project {project.name} ({project.code}).",
                    project.id,
                )
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash("That project code is already used.", "danger")
            else:
                flash("Project updated.", "success")
                return redirect(
                    url_for("projects.project_detail", project_id=project.id)
                )

    return render_template(
        "project_form.html",
        form=form,
        heading="Edit project",
        cancel_url=url_for("projects.project_detail", project_id=project.id),
    )


@projects_bp.route("/projects/<int:project_id>/archive", methods=["POST"])
@editor_required
def project_archive(project_id):
    project = get_project_or_404(project_id)

    if project.status != "archived":
        project.status = "archived"
        project.updated_at = utcnow()
        record(
            "update",
            "project",
            f"Archived project {project.name} ({project.code}).",
            project.id,
        )
        db.session.commit()
        flash("Project archived. Nothing was deleted.", "success")

    return redirect(url_for("projects.project_detail", project_id=project.id))


@projects_bp.route("/projects/<int:project_id>/restore", methods=["POST"])
@editor_required
def project_restore(project_id):
    project = get_project_or_404(project_id)

    if project.status != "active":
        project.status = "active"
        project.updated_at = utcnow()
        record(
            "update",
            "project",
            f"Restored project {project.name} ({project.code}) to active.",
            project.id,
        )
        db.session.commit()
        flash("Project restored to the active list.", "success")

    return redirect(url_for("projects.project_detail", project_id=project.id))


@projects_bp.route(
    "/projects/<int:project_id>/sites/new", methods=["GET", "POST"]
)
@editor_required
def site_new(project_id):
    project = get_project_or_404(project_id)
    form = SiteCreateForm()

    if form.validate_on_submit():
        site = Site(project_id=project.id, is_active=True)
        error = _apply_site_form(site, form, project)

        if error:
            flash(error, "danger")
        else:
            db.session.add(site)

            try:
                db.session.flush()
                record(
                    "create",
                    "site",
                    f"Added site {site.name} ({site.code}) to project {project.name}.",
                    site.id,
                )
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash("That site code is already used on this project.", "danger")
            else:
                flash("Site added.", "success")
                return redirect(
                    url_for("projects.project_detail", project_id=project.id)
                )

    return render_template(
        "site_form.html",
        form=form,
        heading="Add site",
        project=project,
        show_active=False,
    )


@projects_bp.route(
    "/projects/<int:project_id>/sites/<int:site_id>/edit",
    methods=["GET", "POST"],
)
@editor_required
def site_edit(project_id, site_id):
    project = get_project_or_404(project_id)
    site = get_site_or_404(project, site_id)
    form = SiteEditForm(obj=site)

    if form.validate_on_submit():
        error = _apply_site_form(site, form, project)

        if error:
            flash(error, "danger")
        else:
            try:
                record(
                    "update",
                    "site",
                    f"Updated site {site.name} ({site.code}) in project {project.name}.",
                    site.id,
                )
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash("That site code is already used on this project.", "danger")
            else:
                flash("Site updated.", "success")
                return redirect(
                    url_for("projects.project_detail", project_id=project.id)
                )

    return render_template(
        "site_form.html",
        form=form,
        heading="Edit site",
        project=project,
        show_active=True,
    )
