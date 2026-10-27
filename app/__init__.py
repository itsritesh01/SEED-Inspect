
from pathlib import Path

from flask import Flask, render_template
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()
csrf = CSRFProtect()
login_manager = LoginManager()
login_manager.login_view = "accounts.login"
login_manager.login_message = "Please sign in to open that page."
login_manager.login_message_category = "warning"


@event.listens_for(Engine, "connect")
def _set_sqlite_foreign_keys(dbapi_connection, connection_record):
    # Make SQLite honor links between tables on every connection.
    if dbapi_connection.__class__.__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


@login_manager.user_loader
def load_user(user_id):
    from app.models import User

    try:
        user = db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None

    if user is None or not user.is_active:
        return None

    return user


def create_app():
    app = Flask(__name__)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db_file = Path(app.instance_path) / "seed_inspect.db"

    app.config["SECRET_KEY"] = "dev-only-change-in-a-later-stage"
    app.config["DATABASE_FILE"] = str(db_file)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + db_file.as_posix()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["MAX_UPLOAD_BYTES"] = 5 * 1024 * 1024
    app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024
    app.config["ALLOWED_UPLOAD_EXTENSIONS"] = {"jpg", "jpeg", "png", "pdf"}
    app.config["UPLOAD_FOLDER"] = str(Path(app.instance_path) / "uploads")
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    from app import models
    from app.accounts import accounts
    from app.audit import audit_bp
    from app.dashboard import dashboard_bp
    from app.findings import findings_bp
    from app.inspections import inspections_bp
    from app.projects import projects_bp
    from app.reports import reports_bp
    from app.routes import main
    from app.uploads import uploads_bp

    app.register_blueprint(main)
    app.register_blueprint(accounts)
    app.register_blueprint(projects_bp)
    app.register_blueprint(inspections_bp)
    app.register_blueprint(findings_bp)
    app.register_blueprint(uploads_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(audit_bp)

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("403.html"), 403

    @app.errorhandler(404)
    def missing(_error):
        return render_template("404.html"), 404

    @app.errorhandler(413)
    def too_large(_error):
        return render_template("413.html"), 413

    return app
