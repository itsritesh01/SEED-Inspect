
from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app import db


ROLE_LABELS = {
    "administrator": "Administrator",
    "inspector": "Inspector",
    "viewer": "Viewer",
}


def utcnow():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=utcnow, onupdate=utcnow
    )

    __table_args__ = (
        db.CheckConstraint(
            "role IN ('administrator', 'inspector', 'viewer')",
            name="ck_users_role",
        ),
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def role_label(self):
        return ROLE_LABELS.get(self.role, self.role.title())


class Project(db.Model):
    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, index=True)
    code = db.Column(db.String(40), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    client_name = db.Column(db.String(150), nullable=True)
    location_summary = db.Column(db.String(200), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="active", index=True)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=utcnow, onupdate=utcnow
    )

    created_by = db.relationship("User", foreign_keys=[created_by_id])
    sites = db.relationship("Site", back_populates="project", order_by="Site.name")
    inspections = db.relationship(
        "Inspection", back_populates="project", order_by="Inspection.id"
    )

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_projects_status",
        ),
    )


class Site(db.Model):
    __tablename__ = "sites"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(
        db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True
    )
    name = db.Column(db.String(150), nullable=False)
    code = db.Column(db.String(40), nullable=False)
    address = db.Column(db.String(255), nullable=True)
    site_type = db.Column(db.String(40), nullable=False, default="construction")
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=utcnow, onupdate=utcnow
    )

    project = db.relationship("Project", back_populates="sites")
    inspections = db.relationship(
        "Inspection", back_populates="site", order_by="Inspection.id"
    )

    __table_args__ = (
        db.UniqueConstraint("project_id", "code", name="uq_sites_project_code"),
        db.CheckConstraint(
            "site_type IN ('construction', 'environmental', 'other')",
            name="ck_sites_type",
        ),
    )


class Inspection(db.Model):
    __tablename__ = "inspections"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(
        db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True
    )
    site_id = db.Column(
        db.Integer, db.ForeignKey("sites.id"), nullable=False, index=True
    )
    title = db.Column(db.String(150), nullable=False)
    inspection_number = db.Column(db.String(40), unique=True, nullable=False)
    inspection_type = db.Column(db.String(40), nullable=False, default="general")
    status = db.Column(db.String(20), nullable=False, default="draft", index=True)
    scheduled_date = db.Column(db.Date, nullable=True)
    started_at = db.Column(db.DateTime(timezone=True), nullable=True)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    inspector_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    summary = db.Column(db.Text, nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=utcnow, onupdate=utcnow
    )

    project = db.relationship("Project", back_populates="inspections")
    site = db.relationship("Site", back_populates="inspections")
    inspector = db.relationship("User", foreign_keys=[inspector_id])
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    checklist_items = db.relationship(
        "ChecklistItem",
        back_populates="inspection",
        order_by="ChecklistItem.sort_order",
    )
    findings = db.relationship(
        "Finding", back_populates="inspection", order_by="Finding.id"
    )
    attachments = db.relationship(
        "Attachment",
        back_populates="inspection",
        foreign_keys="Attachment.inspection_id",
    )

    __table_args__ = (
        db.CheckConstraint(
            "inspection_type IN ('general', 'safety', 'quality', 'environmental')",
            name="ck_inspections_type",
        ),
        db.CheckConstraint(
            "status IN ('draft', 'in_progress', 'completed', 'cancelled')",
            name="ck_inspections_status",
        ),
    )


class ChecklistItem(db.Model):
    __tablename__ = "checklist_items"

    id = db.Column(db.Integer, primary_key=True)
    inspection_id = db.Column(
        db.Integer, db.ForeignKey("inspections.id"), nullable=False, index=True
    )
    sort_order = db.Column(db.Integer, nullable=False, default=1)
    item_text = db.Column(db.String(300), nullable=False)
    result = db.Column(db.String(20), nullable=False, default="not_inspected")
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=utcnow, onupdate=utcnow
    )

    inspection = db.relationship("Inspection", back_populates="checklist_items")

    __table_args__ = (
        db.CheckConstraint(
            "result IN ('pass', 'fail', 'not_applicable', 'not_inspected')",
            name="ck_checklist_result",
        ),
    )


class Finding(db.Model):
    __tablename__ = "findings"

    id = db.Column(db.Integer, primary_key=True)
    inspection_id = db.Column(
        db.Integer, db.ForeignKey("inspections.id"), nullable=False, index=True
    )
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    severity = db.Column(db.String(20), nullable=False, default="medium", index=True)
    status = db.Column(db.String(20), nullable=False, default="open", index=True)
    evidence_note = db.Column(db.Text, nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=utcnow, onupdate=utcnow
    )

    inspection = db.relationship("Inspection", back_populates="findings")
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    corrective_actions = db.relationship(
        "CorrectiveAction",
        back_populates="finding",
        order_by="CorrectiveAction.due_date",
    )
    attachments = db.relationship(
        "Attachment",
        back_populates="finding",
        foreign_keys="Attachment.finding_id",
    )

    __table_args__ = (
        db.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_findings_severity",
        ),
        db.CheckConstraint(
            "status IN ('open', 'in_progress', 'resolved', 'closed')",
            name="ck_findings_status",
        ),
    )


class CorrectiveAction(db.Model):
    __tablename__ = "corrective_actions"

    id = db.Column(db.Integer, primary_key=True)
    finding_id = db.Column(
        db.Integer, db.ForeignKey("findings.id"), nullable=False, index=True
    )
    action_text = db.Column(db.Text, nullable=False)
    responsible_name = db.Column(db.String(120), nullable=False)
    responsible_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    due_date = db.Column(db.Date, nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="open", index=True)
    progress_note = db.Column(db.Text, nullable=True)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=utcnow, onupdate=utcnow
    )

    finding = db.relationship("Finding", back_populates="corrective_actions")
    responsible_user = db.relationship(
        "User", foreign_keys=[responsible_user_id]
    )
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    attachments = db.relationship(
        "Attachment",
        back_populates="corrective_action",
        foreign_keys="Attachment.corrective_action_id",
    )

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('open', 'in_progress', 'completed')",
            name="ck_actions_status",
        ),
    )


class Attachment(db.Model):
    __tablename__ = "attachments"

    id = db.Column(db.Integer, primary_key=True)
    inspection_id = db.Column(
        db.Integer, db.ForeignKey("inspections.id"), nullable=True, index=True
    )
    finding_id = db.Column(
        db.Integer, db.ForeignKey("findings.id"), nullable=True, index=True
    )
    corrective_action_id = db.Column(
        db.Integer, db.ForeignKey("corrective_actions.id"), nullable=True, index=True
    )
    stored_name = db.Column(db.String(255), nullable=False, unique=True)
    original_name = db.Column(db.String(255), nullable=False)
    extension = db.Column(db.String(10), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    inspection = db.relationship(
        "Inspection", back_populates="attachments",
        foreign_keys=[inspection_id]
    )
    finding = db.relationship(
        "Finding", back_populates="attachments",
        foreign_keys=[finding_id]
    )
    corrective_action = db.relationship(
        "CorrectiveAction", back_populates="attachments",
        foreign_keys=[corrective_action_id]
    )
    uploaded_by = db.relationship("User", foreign_keys=[uploaded_by_id])

    __table_args__ = (
        db.CheckConstraint(
            "(inspection_id IS NOT NULL) + (finding_id IS NOT NULL) + "
            "(corrective_action_id IS NOT NULL) = 1",
            name="ck_attachments_one_parent",
        ),
        db.CheckConstraint(
            "extension IN ('jpg', 'jpeg', 'png', 'pdf')",
            name="ck_attachments_extension",
        ),
        db.CheckConstraint(
            "file_size > 0 AND file_size <= 5242880",
            name="ck_attachments_size",
        ),
    )


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(40), nullable=False)
    entity_type = db.Column(db.String(40), nullable=False)
    entity_id = db.Column(db.Integer, nullable=True)
    message = db.Column(db.String(500), nullable=False)

    user = db.relationship("User", foreign_keys=[user_id])
