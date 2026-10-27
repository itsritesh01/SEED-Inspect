
from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    DateField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Email, Length, Optional, Regexp

from app.models import ROLE_LABELS

CODE_MESSAGE = "Use 2 to 20 letters, numbers, and hyphens, such as HPB-01."
CODE_PATTERN = r"^[A-Z0-9]+(?:-[A-Z0-9]+)*$"

SITE_TYPE_CHOICES = [
    ("construction", "Construction"),
    ("environmental", "Environmental"),
    ("other", "Other"),
]


def uppercase_code(value):
    if value is None:
        return ""
    return value.strip().upper()


class LoginForm(FlaskForm):
    email = StringField(
        "Email",
        validators=[
            DataRequired(message="Enter an email address."),
            Email(message="Enter an email address like name@example.com."),
            Length(max=255, message="Use 255 characters or fewer."),
        ],
    )
    password = PasswordField(
        "Password",
        validators=[
            DataRequired(message="Enter a password."),
            Length(max=128, message="Use 128 characters or fewer."),
        ],
    )
    submit = SubmitField("Sign in")


class UserCreateForm(FlaskForm):
    full_name = StringField(
        "Full name",
        validators=[
            DataRequired(message="Enter the full name."),
            Length(max=120, message="Use 120 characters or fewer."),
        ],
    )
    email = StringField(
        "Email",
        validators=[
            DataRequired(message="Enter an email address."),
            Email(message="Enter an email address like name@example.com."),
            Length(max=255, message="Use 255 characters or fewer."),
        ],
    )
    role = SelectField(
        "Role",
        choices=list(ROLE_LABELS.items()),
        validators=[DataRequired(message="Choose a role.")],
    )
    password = PasswordField(
        "Temporary password",
        validators=[
            DataRequired(message="Enter a temporary password."),
            Length(max=128, message="Use 128 characters or fewer."),
        ],
    )
    password_confirm = PasswordField(
        "Repeat temporary password",
        validators=[DataRequired(message="Repeat the temporary password.")],
    )
    submit = SubmitField("Create user")


class UserEditForm(FlaskForm):
    full_name = StringField(
        "Full name",
        validators=[
            DataRequired(message="Enter the full name."),
            Length(max=120, message="Use 120 characters or fewer."),
        ],
    )
    email = StringField(
        "Email",
        validators=[
            DataRequired(message="Enter an email address."),
            Email(message="Enter an email address like name@example.com."),
            Length(max=255, message="Use 255 characters or fewer."),
        ],
    )
    role = SelectField(
        "Role",
        choices=list(ROLE_LABELS.items()),
        validators=[DataRequired(message="Choose a role.")],
    )
    is_active = BooleanField("Account is active")
    new_password = PasswordField(
        "New password",
        validators=[Length(max=128, message="Use 128 characters or fewer.")],
    )
    new_password_confirm = PasswordField("Repeat new password")
    submit = SubmitField("Save changes")


class PasswordChangeForm(FlaskForm):
    current_password = PasswordField(
        "Current password",
        validators=[
            DataRequired(message="Enter the current password."),
            Length(max=128, message="Use 128 characters or fewer."),
        ],
    )
    new_password = PasswordField(
        "New password",
        validators=[
            DataRequired(message="Enter a new password."),
            Length(max=128, message="Use 128 characters or fewer."),
        ],
    )
    new_password_confirm = PasswordField(
        "Repeat new password",
        validators=[DataRequired(message="Repeat the new password.")],
    )
    submit = SubmitField("Change password")


class ProjectForm(FlaskForm):
    name = StringField(
        "Project name",
        validators=[
            DataRequired(message="Enter the project name."),
            Length(max=150, message="Use 150 characters or fewer."),
        ],
    )
    code = StringField(
        "Project code",
        filters=[uppercase_code],
        validators=[
            DataRequired(message="Enter a project code."),
            Length(min=2, max=20, message=CODE_MESSAGE),
            Regexp(CODE_PATTERN, message=CODE_MESSAGE),
        ],
    )
    client_name = StringField(
        "Client",
        validators=[Optional(), Length(max=150, message="Use 150 characters or fewer.")],
    )
    location_summary = StringField(
        "Location",
        validators=[Optional(), Length(max=200, message="Use 200 characters or fewer.")],
    )
    description = TextAreaField(
        "Description",
        validators=[Optional(), Length(max=2000, message="Use 2000 characters or fewer.")],
    )
    start_date = DateField("Start date", format="%Y-%m-%d", validators=[Optional()])
    end_date = DateField("End date", format="%Y-%m-%d", validators=[Optional()])
    submit = SubmitField("Save project")


class SiteCreateForm(FlaskForm):
    name = StringField(
        "Site name",
        validators=[
            DataRequired(message="Enter the site name."),
            Length(max=150, message="Use 150 characters or fewer."),
        ],
    )
    code = StringField(
        "Site code",
        filters=[uppercase_code],
        validators=[
            DataRequired(message="Enter a site code."),
            Length(min=2, max=20, message=CODE_MESSAGE),
            Regexp(CODE_PATTERN, message=CODE_MESSAGE),
        ],
    )
    site_type = SelectField(
        "Site type",
        choices=SITE_TYPE_CHOICES,
        validators=[DataRequired(message="Choose a site type.")],
    )
    address = StringField(
        "Address",
        validators=[Optional(), Length(max=255, message="Use 255 characters or fewer.")],
    )
    description = TextAreaField(
        "Description",
        validators=[Optional(), Length(max=2000, message="Use 2000 characters or fewer.")],
    )
    submit = SubmitField("Save site")


class SiteEditForm(SiteCreateForm):
    is_active = BooleanField("Site is active")
    submit = SubmitField("Save site")


INSPECTION_TYPE_CHOICES = [
    ("general", "General"),
    ("safety", "Safety"),
    ("quality", "Quality"),
    ("environmental", "Environmental"),
]

INSPECTION_STATUS_CHOICES = [
    ("draft", "Draft"),
    ("in_progress", "In progress"),
    ("completed", "Completed"),
    ("cancelled", "Cancelled"),
]


def optional_int(value):
    if value is None or value == "":
        return None
    return int(value)


class InspectionForm(FlaskForm):
    site_id = SelectField(
        "Site",
        coerce=int,
        validators=[DataRequired(message="Choose a site.")],
    )
    inspection_number = StringField(
        "Inspection number",
        filters=[uppercase_code],
        validators=[
            DataRequired(message="Enter an inspection number."),
            Length(min=2, max=20, message=CODE_MESSAGE),
            Regexp(CODE_PATTERN, message=CODE_MESSAGE),
        ],
    )
    title = StringField(
        "Title",
        validators=[
            DataRequired(message="Enter a title."),
            Length(max=150, message="Use 150 characters or fewer."),
        ],
    )
    inspection_type = SelectField(
        "Inspection type",
        choices=INSPECTION_TYPE_CHOICES,
        validators=[DataRequired(message="Choose an inspection type.")],
    )
    status = SelectField(
        "Status",
        choices=INSPECTION_STATUS_CHOICES,
        validators=[DataRequired(message="Choose a status.")],
    )
    scheduled_date = DateField(
        "Scheduled date",
        format="%Y-%m-%d",
        validators=[Optional()],
    )
    inspector_id = SelectField(
        "Inspector",
        coerce=optional_int,
        validators=[Optional()],
    )
    summary = TextAreaField(
        "Summary",
        validators=[Optional(), Length(max=2000, message="Use 2000 characters or fewer.")],
    )
    submit = SubmitField("Save inspection")


class ChecklistItemForm(FlaskForm):
    item_text = StringField(
        "Checklist line",
        validators=[
            DataRequired(message="Enter the checklist line."),
            Length(max=300, message="Use 300 characters or fewer."),
        ],
    )
    submit = SubmitField("Add checklist line")


FINDING_SEVERITY_CHOICES = [
    ("low", "Low"),
    ("medium", "Medium"),
    ("high", "High"),
    ("critical", "Critical"),
]

FINDING_STATUS_CHOICES = [
    ("open", "Open"),
    ("in_progress", "In progress"),
    ("resolved", "Resolved"),
    ("closed", "Closed"),
]

ACTION_STATUS_CHOICES = [
    ("open", "Open"),
    ("in_progress", "In progress"),
    ("completed", "Completed"),
]


class FindingForm(FlaskForm):
    title = StringField(
        "Title",
        validators=[
            DataRequired(message="Enter a title."),
            Length(max=150, message="Use 150 characters or fewer."),
        ],
    )
    description = TextAreaField(
        "Description",
        validators=[
            DataRequired(message="Enter a description."),
            Length(max=2000, message="Use 2000 characters or fewer."),
        ],
    )
    severity = SelectField(
        "Severity",
        choices=FINDING_SEVERITY_CHOICES,
        validators=[DataRequired(message="Choose a severity.")],
    )
    status = SelectField(
        "Status",
        choices=FINDING_STATUS_CHOICES,
        validators=[DataRequired(message="Choose a finding status.")],
    )
    evidence_note = TextAreaField(
        "Evidence note",
        validators=[Optional(), Length(max=2000, message="Use 2000 characters or fewer.")],
    )
    submit = SubmitField("Save finding")


class CorrectiveActionForm(FlaskForm):
    action_text = TextAreaField(
        "Action",
        validators=[
            DataRequired(message="Describe the corrective action."),
            Length(max=2000, message="Use 2000 characters or fewer."),
        ],
    )
    responsible_name = StringField(
        "Responsible person",
        validators=[
            DataRequired(message="Enter the responsible person's name."),
            Length(max=120, message="Use 120 characters or fewer."),
        ],
    )
    responsible_user_id = SelectField(
        "Link to an account",
        coerce=optional_int,
        validators=[Optional()],
    )
    due_date = DateField(
        "Due date",
        format="%Y-%m-%d",
        validators=[DataRequired(message="Enter a due date.")],
    )
    status = SelectField(
        "Status",
        choices=ACTION_STATUS_CHOICES,
        validators=[DataRequired(message="Choose an action status.")],
    )
    progress_note = TextAreaField(
        "Progress note",
        validators=[Optional(), Length(max=2000, message="Use 2000 characters or fewer.")],
    )
    submit = SubmitField("Save corrective action")
