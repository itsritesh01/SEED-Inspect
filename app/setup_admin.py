
from email_validator import EmailNotValidError, validate_email
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import User


def clean_name(value):
    return " ".join((value or "").split())


def clean_email(value):
    text = (value or "").strip()
    if not text:
        return None
    try:
        result = validate_email(text, check_deliverability=False)
    except EmailNotValidError:
        return None
    return result.normalized.lower()


def password_problem(password, email):
    if not password:
        return "Enter a password."
    if password != password.strip():
        return "Do not start or end the password with a space."
    if len(password) < 10:
        return "Use at least 10 characters."
    if len(password) > 128:
        return "Use 128 characters or fewer."
    if email and password.lower() == email.lower():
        return "Do not use the email address as the password."
    return None


def create_first_administrator(full_name, email, password, password_repeat):
    """Create the only administrator this command is allowed to create.

    Returns (user, None) on success, or (None, error_message).
    Call this inside an application context. It never prints the password.
    """
    if "users" not in inspect(db.engine).get_table_names():
        return None, "The users table is missing. Run python init_db.py first."

    if db.session.query(User).filter_by(role="administrator").first() is not None:
        return None, (
            "An administrator account already exists. "
            "This command will not create another one. "
            "Sign in and open Users to add people."
        )

    name = clean_name(full_name)
    if not name or len(name) > 120:
        return None, "Enter a full name of 120 characters or fewer."

    mail = clean_email(email)
    if mail is None:
        return None, "Enter an email address like name@example.com."

    if password != password_repeat:
        return None, "The two passwords do not match."

    problem = password_problem(password, mail)
    if problem:
        return None, problem

    user = User(full_name=name, email=mail, role="administrator", is_active=True)
    user.set_password(password)
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return None, "That email is already used."
    return user, None
