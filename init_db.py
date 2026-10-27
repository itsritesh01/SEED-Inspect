from sqlalchemy import inspect

from app import create_app, db
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

MODELS = [
    User,
    Project,
    Site,
    Inspection,
    ChecklistItem,
    Finding,
    CorrectiveAction,
    Attachment,
    AuditLog,
]

app = create_app()

with app.app_context():
    db.create_all()
    names = sorted(inspect(db.engine).get_table_names())
    print("Database file:")
    print(app.config["DATABASE_FILE"])
    print("Tables:")
    for name in names:
        print(" -", name)
    print("Records in each table:")
    for model in MODELS:
        count = db.session.query(model).count()
        print(f" - {model.__tablename__}: {count}")
    expected = sorted(model.__tablename__ for model in MODELS)
    if names != expected:
        print("Unexpected table list. Compare it with the guide.")
    else:
        print("Database file is ready. Existing records were kept.")