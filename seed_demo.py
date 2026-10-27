"""Add missing fictional demonstration records.

This script never deletes a record and never changes an existing password,
project, site, inspection, checklist, finding, action, or file.
Run it only while the website is stopped.
"""

from datetime import date, datetime, timezone
from io import BytesIO

from PIL import Image, ImageDraw
from reportlab.pdfgen import canvas
from sqlalchemy import inspect

from app import create_app, db
from app.audit import record
from app.models import (
    Attachment,
    ChecklistItem,
    CorrectiveAction,
    Finding,
    Inspection,
    Project,
    Site,
    User,
)
from app.setup_admin import create_first_administrator

app = create_app()


def ensure_user(full_name, email, role, password):
    person = db.session.query(User).filter_by(email=email).one_or_none()
    if person is not None:
        print(f"Left unchanged: account {email}")
        return person, False
    person = User(full_name=full_name, email=email, role=role, is_active=True)
    person.set_password(password)
    db.session.add(person)
    db.session.flush()
    print(f"Added account: {email}")
    return person, True


def ensure_project(code, **fields):
    project = db.session.query(Project).filter_by(code=code).one_or_none()
    if project is not None:
        print(f"Left unchanged: project {code}")
        return project, False
    project = Project(code=code, status="active", **fields)
    db.session.add(project)
    db.session.flush()
    print(f"Added project: {code}")
    return project, True


def ensure_site(project, code, **fields):
    site = (
        db.session.query(Site)
        .filter_by(project_id=project.id, code=code)
        .one_or_none()
    )
    if site is not None:
        print(f"Left unchanged: site {project.code} / {code}")
        return site, False
    site = Site(project_id=project.id, code=code, is_active=True, **fields)
    db.session.add(site)
    db.session.flush()
    print(f"Added site: {project.code} / {code}")
    return site, True


def fictional_png():
    image = Image.new("RGB", (640, 360), (15, 44, 76))
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 40, 600, 320), outline=(255, 255, 255), width=3)
    draw.text((70, 160), "SEED Inspect fictional photo. Not a real site.", fill=(255, 255, 255))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def fictional_pdf():
    buffer = BytesIO()
    document = canvas.Canvas(buffer)
    document.setTitle("Fictional demonstration note")
    document.drawString(72, 720, "SEED Inspect fictional note.")
    document.drawString(72, 700, "This is not a company document.")
    document.save()
    return buffer.getvalue()


def store_file(inspection, original_name, extension, data, user_id):
    from pathlib import Path
    from uuid import uuid4

    folder = Path(app.instance_path) / "uploads"
    folder.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4().hex}.{extension}"
    path = folder / stored_name
    path.write_bytes(data)
    row = Attachment(
        inspection_id=inspection.id,
        stored_name=stored_name,
        original_name=original_name,
        extension=extension,
        file_size=len(data),
        uploaded_by_id=user_id,
    )
    db.session.add(row)
    db.session.flush()
    print(f"Added file: {original_name} on {inspection.inspection_number}")
    return True


def add_inspection_pack(project, site, inspector, creator):
    inspection = Inspection(
        project_id=project.id,
        site_id=site.id,
        title="Monthly safety walk",
        inspection_number="INS-01",
        inspection_type="safety",
        status="in_progress",
        scheduled_date=date(2026, 3, 2),
        started_at=datetime(2026, 3, 2, 9, 0, tzinfo=timezone.utc),
        inspector_id=inspector.id,
        summary="Fictional safety walk at the north abutment.",
        created_by_id=creator.id,
    )
    db.session.add(inspection)
    db.session.flush()
    lines = [
        (1, "Excavation is barricaded", "fail", "Fictional gap in the barricade."),
        (2, "Workers are wearing helmets", "pass", None),
        (3, "Fire extinguisher is in date", "not_inspected", None),
        (4, "River access is blocked", "not_applicable", "No river work on this visit."),
    ]
    for order, text, result, notes in lines:
        db.session.add(
            ChecklistItem(
                inspection_id=inspection.id,
                sort_order=order,
                item_text=text,
                result=result,
                notes=notes,
            )
        )
    finding = Finding(
        inspection_id=inspection.id,
        title="Missing excavation barricade",
        description="Fictional missing barricade at the north abutment.",
        evidence_note="Seen from the site path.",
        severity="high",
        status="open",
        created_by_id=creator.id,
    )
    db.session.add(finding)
    db.session.flush()
    db.session.add(
        CorrectiveAction(
            finding_id=finding.id,
            action_text="Install barricade and warning tape.",
            responsible_name="Riya Sen",
            responsible_user_id=inspector.id,
            due_date=date(2026, 3, 9),
            status="in_progress",
            progress_note="Fictional demonstration note.",
            created_by_id=creator.id,
        )
    )
    store_file(inspection, "fictional_site.png", "png", fictional_png(), creator.id)
    print("Added inspection: INS-01")
    return 8


def add_completed_pack(project, site, inspector, creator):
    inspection = Inspection(
        project_id=project.id,
        site_id=site.id,
        title="Yard drainage check",
        inspection_number="INS-02",
        inspection_type="environmental",
        status="completed",
        scheduled_date=date(2026, 3, 12),
        started_at=datetime(2026, 3, 12, 10, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 3, 12, 11, 30, tzinfo=timezone.utc),
        inspector_id=inspector.id,
        summary="Fictional drainage check. The outlet was clear.",
        created_by_id=creator.id,
    )
    db.session.add(inspection)
    db.session.flush()
    db.session.add(
        ChecklistItem(
            inspection_id=inspection.id,
            sort_order=1,
            item_text="Storm drain is clear",
            result="pass",
            notes="Fictional clear outlet.",
        )
    )
    finding = Finding(
        inspection_id=inspection.id,
        title="Oil stain near the gate",
        description="Fictional small stain. It was cleaned during the visit.",
        evidence_note="Noted on the yard log.",
        severity="low",
        status="resolved",
        created_by_id=creator.id,
    )
    db.session.add(finding)
    db.session.flush()
    db.session.add(
        CorrectiveAction(
            finding_id=finding.id,
            action_text="Clean the stain and place a drip tray.",
            responsible_name="Riya Sen",
            responsible_user_id=inspector.id,
            due_date=date(2026, 3, 12),
            status="completed",
            progress_note="Fictional cleanup finished on the same day.",
            completed_at=datetime(2026, 3, 12, 11, 0, tzinfo=timezone.utc),
            created_by_id=creator.id,
        )
    )
    store_file(inspection, "fictional_note.pdf", "pdf", fictional_pdf(), creator.id)
    print("Added inspection: INS-02")
    return 5


with app.app_context():
    if "users" not in inspect(db.engine).get_table_names():
        raise SystemExit("The tables are missing. Run python init_db.py first.")

    added = 0
    admin = db.session.query(User).filter_by(role="administrator").first()
    if admin is None:
        admin, error = create_first_administrator(
            "Meera Nair",
            "meera.admin@example.com",
            "North-Bridge-24",
            "North-Bridge-24",
        )
        if error:
            raise SystemExit(error)
        print("Added account: meera.admin@example.com")
        added += 1
    else:
        print(f"Left unchanged: administrator {admin.email}")

    riya, created = ensure_user(
        "Riya Sen", "riya.inspector@example.com", "inspector", "Site-Visit-24"
    )
    added += int(created)
    arun, created = ensure_user(
        "Arun Das", "arun.viewer@example.com", "viewer", "Quiet-Reader-24"
    )
    added += int(created)

    harbor, created = ensure_project(
        "HPB-01",
        name="Harbor Point Bridge",
        description="Fictional bridge practice project.",
        client_name="North Civic Works",
        location_summary="Fictional harbor point",
        start_date=date(2026, 1, 6),
        created_by_id=admin.id,
    )
    added += int(created)
    depot, created = ensure_project(
        "DY-02",
        name="Depot Yard",
        description="Fictional yard practice project.",
        client_name="North Civic Works",
        location_summary="Fictional depot",
        start_date=date(2026, 2, 2),
        created_by_id=admin.id,
    )
    added += int(created)

    north, created = ensure_site(
        harbor,
        "NA-1",
        name="North Abutment",
        site_type="construction",
        address="Fictional harbor road",
        description="Fictional construction site.",
    )
    added += int(created)
    _, created = ensure_site(
        harbor,
        "SP-2",
        name="South Pier",
        site_type="construction",
        address="Fictional south bank",
        description="Fictional second site on the same project.",
    )
    added += int(created)
    yard, created = ensure_site(
        depot,
        "YD-1",
        name="Yard Gate",
        site_type="environmental",
        address="Fictional depot lane",
        description="Fictional environmental site.",
    )
    added += int(created)

    ins01 = db.session.query(Inspection).filter_by(inspection_number="INS-01").one_or_none()
    if ins01 is None:
        added += add_inspection_pack(harbor, north, riya, admin)
    else:
        print("Left unchanged: inspection INS-01")

    ins02 = db.session.query(Inspection).filter_by(inspection_number="INS-02").one_or_none()
    if ins02 is None:
        added += add_completed_pack(depot, yard, riya, admin)
    else:
        print("Left unchanged: inspection INS-02")

    if added:
        record(
            "create",
            "record",
            "Added missing fictional demonstration records. Existing records were not changed.",
            user_id=admin.id,
        )
        db.session.commit()
    else:
        db.session.rollback()

    print(f"Finished. Added {added} new records.")
    if added:
        print("Practice passwords were set only on accounts created by this run.")
        print("Meera, if created now: meera.admin@example.com / North-Bridge-24")
        print("Riya, if created now: riya.inspector@example.com / Site-Visit-24")
        print("Arun, if created now: arun.viewer@example.com / Quiet-Reader-24")