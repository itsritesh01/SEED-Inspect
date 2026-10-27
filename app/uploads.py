
from pathlib import Path
from uuid import uuid4

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    request,
    send_file,
    url_for,
)
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from app import db
from app.access import editor_required
from app.audit import record
from app.models import Attachment, CorrectiveAction, Finding, Inspection

uploads_bp = Blueprint("uploads", __name__)

SIGNATURES = {
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "pdf": (b"%PDF",),
}


def read_upload(file_storage):
    if file_storage is None or not file_storage.filename:
        return None, "Choose a JPG, PNG, or PDF file."

    original = secure_filename(file_storage.filename)
    extension = Path(original).suffix.lower().lstrip(".")
    allowed = current_app.config["ALLOWED_UPLOAD_EXTENSIONS"]

    if extension not in allowed:
        return None, "Use a JPG, PNG, or PDF file. Other file types are refused."

    data = file_storage.read()

    if not data:
        return None, "The file is empty."

    if len(data) > current_app.config["MAX_UPLOAD_BYTES"]:
        return None, "The file is larger than 5 MB."

    if not data.startswith(SIGNATURES[extension]):
        return None, "The file contents do not match a JPG, PNG, or PDF."

    if not original:
        original = f"upload.{extension}"

    return {
        "data": data,
        "extension": extension,
        "original": original[:255],
    }, None


def upload_folder():
    folder = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def save_attachment(payload, inspection_id=None, finding_id=None, action_id=None):
    parents = [inspection_id, finding_id, action_id]

    if sum(parent is not None for parent in parents) != 1:
        return "The file could not be linked to a record."

    folder = upload_folder()
    stored_name = f"{uuid4().hex}.{payload['extension']}"
    path = (folder / stored_name).resolve()

    if path.parent != folder:
        return "The file could not be stored."

    path.write_bytes(payload["data"])

    attachment = Attachment(
        inspection_id=inspection_id,
        finding_id=finding_id,
        corrective_action_id=action_id,
        stored_name=stored_name,
        original_name=payload["original"],
        extension=payload["extension"],
        file_size=len(payload["data"]),
        uploaded_by_id=current_user.id,
    )

    db.session.add(attachment)

    try:
        db.session.flush()

        if inspection_id:
            where = f"inspection {attachment.inspection.inspection_number}"
        elif finding_id:
            where = f"finding {attachment.finding.title}"
        else:
            where = "a corrective action"

        record(
            "create",
            "file",
            f"Uploaded {attachment.original_name} to {where}.",
            attachment.id,
        )

        db.session.commit()

    except Exception:
        db.session.rollback()
        path.unlink(missing_ok=True)
        return "The file could not be saved."

    return None


def stored_path(attachment):
    folder = upload_folder()
    path = (folder / attachment.stored_name).resolve()

    if path.parent != folder:
        abort(404)

    return path


@uploads_bp.route(
    "/inspections/<int:inspection_id>/attachments",
    methods=["POST"],
)
@editor_required
def upload_inspection(inspection_id):
    inspection = db.session.get(Inspection, inspection_id)

    if inspection is None:
        abort(404)

    payload, error = read_upload(request.files.get("attachment"))

    if error:
        flash(error, "danger")
    else:
        error = save_attachment(payload, inspection_id=inspection.id)
        flash(
            error or "File uploaded to this inspection.",
            "danger" if error else "success",
        )

    return redirect(
        url_for(
            "inspections.inspection_detail",
            inspection_id=inspection.id,
        )
    )


@uploads_bp.route(
    "/findings/<int:finding_id>/attachments",
    methods=["POST"],
)
@editor_required
def upload_finding(finding_id):
    finding = db.session.get(Finding, finding_id)

    if finding is None:
        abort(404)

    payload, error = read_upload(request.files.get("attachment"))

    if error:
        flash(error, "danger")
    else:
        error = save_attachment(payload, finding_id=finding.id)
        flash(
            error or "File uploaded to this finding.",
            "danger" if error else "success",
        )

    return redirect(
        url_for("findings.finding_detail", finding_id=finding.id)
    )


@uploads_bp.route(
    "/findings/<int:finding_id>/actions/<int:action_id>/attachments",
    methods=["POST"],
)
@editor_required
def upload_action(finding_id, action_id):
    finding = db.session.get(Finding, finding_id)
    action = db.session.get(CorrectiveAction, action_id)

    if (
        finding is None
        or action is None
        or action.finding_id != finding.id
    ):
        abort(404)

    payload, error = read_upload(request.files.get("attachment"))

    if error:
        flash(error, "danger")
    else:
        error = save_attachment(payload, action_id=action.id)
        flash(
            error or "File uploaded to this corrective action.",
            "danger" if error else "success",
        )

    return redirect(
        url_for(
            "findings.action_detail",
            finding_id=finding.id,
            action_id=action.id,
        )
    )


@uploads_bp.route("/attachments/<int:attachment_id>/download")
@login_required
def download(attachment_id):
    attachment = db.session.get(Attachment, attachment_id)

    if attachment is None:
        abort(404)

    path = stored_path(attachment)

    if not path.is_file():
        abort(404)

    return send_file(
        path,
        as_attachment=True,
        download_name=attachment.original_name,
    )


@uploads_bp.route(
    "/attachments/<int:attachment_id>/delete",
    methods=["POST"],
)
@editor_required
def delete_attachment(attachment_id):
    attachment = db.session.get(Attachment, attachment_id)

    if attachment is None:
        abort(404)

    target = redirect_target(attachment)
    path = stored_path(attachment)
    file_name = attachment.original_name
    file_id = attachment.id

    try:
        path.unlink(missing_ok=True)
    except OSError:
        flash(
            "The file is open in another program. Close it, then remove it again.",
            "danger",
        )
        return redirect(target)

    db.session.delete(attachment)

    record(
        "delete",
        "file",
        f"Removed file {file_name}.",
        file_id,
    )

    db.session.commit()
    flash("File removed.", "success")

    return redirect(target)


def redirect_target(attachment):
    if attachment.inspection_id:
        return url_for(
            "inspections.inspection_detail",
            inspection_id=attachment.inspection_id,
        )

    if attachment.finding_id:
        return url_for(
            "findings.finding_detail",
            finding_id=attachment.finding_id,
        )

    action = db.session.get(
        CorrectiveAction,
        attachment.corrective_action_id,
    )

    if action is None:
        abort(404)

    return url_for(
        "findings.action_detail",
        finding_id=action.finding_id,
        action_id=action.id,
    )
