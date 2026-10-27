
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy.exc import IntegrityError

from app import db
from app.access import admin_required, safe_next
from app.audit import record
from app.forms import LoginForm, PasswordChangeForm, UserCreateForm, UserEditForm
from app.models import ROLE_LABELS, User, utcnow
from app.setup_admin import clean_email, clean_name, password_problem

accounts = Blueprint("accounts", __name__)


def _save_new_user(full_name, email, role, password, password_confirm):
    name = clean_name(full_name)
    if not name or len(name) > 120:
        return None, "Enter a full name of 120 characters or fewer."

    mail = clean_email(email)
    if mail is None:
        return None, "Enter an email address like name@example.com."

    if role not in ROLE_LABELS:
        return None, "Choose Administrator, Inspector, or Viewer."

    if password != password_confirm:
        return None, "The two passwords do not match."

    problem = password_problem(password, mail)
    if problem:
        return None, problem

    if db.session.query(User).filter_by(email=mail).first() is not None:
        return None, "That email is already used."

    user = User(full_name=name, email=mail, role=role, is_active=True)
    user.set_password(password)
    db.session.add(user)

    try:
        db.session.flush()
        record("create", "user", f"Created the account for {user.email}.", user.id)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return None, "That email is already used."

    return user, None


@accounts.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    form = LoginForm()

    if form.validate_on_submit():
        mail = clean_email(form.email.data)
        user = None

        if mail is not None:
            user = db.session.query(User).filter_by(email=mail).first()

        password_ok = (
            user is not None and user.check_password(form.password.data)
        )

        if user is None or not password_ok or not user.is_active:
            label = mail or "an unread address"

            record(
                "sign_in_failed",
                "user",
                f"Sign-in failed for {label}.",
                user.id if user else None,
                user_id=user.id if user else None,
            )
            db.session.commit()

            flash("The email or password is not correct.", "danger")
            return render_template("login.html", form=form), 401

        login_user(user)

        record(
            "sign_in",
            "user",
            f"Signed in {user.email}.",
            user.id,
            user_id=user.id,
        )
        db.session.commit()

        flash("Signed in.", "success")
        return redirect(
            safe_next(request.args.get("next")) or url_for("main.home")
        )

    return render_template("login.html", form=form)


@accounts.route("/logout", methods=["POST"])
@login_required
def logout():
    record(
        "sign_out",
        "user",
        f"Signed out {current_user.email}.",
        current_user.id,
    )
    db.session.commit()

    logout_user()
    flash("Signed out.", "success")
    return redirect(url_for("main.home"))


@accounts.route("/account/password", methods=["GET", "POST"])
@login_required
def change_password():
    form = PasswordChangeForm()

    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            flash("The current password is not correct.", "danger")

        elif form.new_password.data != form.new_password_confirm.data:
            flash("The two new passwords do not match.", "danger")

        elif current_user.check_password(form.new_password.data):
            flash(
                "The new password must be different from the current password.",
                "danger",
            )

        else:
            problem = password_problem(
                form.new_password.data,
                current_user.email,
            )

            if problem:
                flash(problem, "danger")

            else:
                current_user.set_password(form.new_password.data)
                current_user.updated_at = utcnow()

                record(
                    "update",
                    "user",
                    f"Changed the password for {current_user.email}.",
                    current_user.id,
                )
                db.session.commit()

                flash("Password changed.", "success")
                return redirect(url_for("main.home"))

    return render_template("password.html", form=form)


@accounts.route("/users")
@admin_required
def user_list():
    people = (
        db.session.query(User)
        .order_by(User.full_name, User.id)
        .all()
    )

    return render_template("users.html", people=people)


@accounts.route("/users/new", methods=["GET", "POST"])
@admin_required
def user_create():
    form = UserCreateForm()

    if form.validate_on_submit():
        user, error = _save_new_user(
            form.full_name.data,
            form.email.data,
            form.role.data,
            form.password.data,
            form.password_confirm.data,
        )

        if error:
            flash(error, "danger")
        else:
            flash(
                f"Created {user.full_name} ({user.role_label}).",
                "success",
            )
            return redirect(url_for("accounts.user_list"))

    return render_template("user_new.html", form=form)


@accounts.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@admin_required
def user_edit(user_id):
    person = db.session.get(User, user_id)

    if person is None:
        abort(404)

    form = UserEditForm(obj=person)
    editing_self = person.id == current_user.id

    if form.validate_on_submit():
        error = _apply_user_edit(person, form, editing_self)

        if error:
            flash(error, "danger")
        else:
            flash("User updated.", "success")
            return redirect(url_for("accounts.user_list"))

    return render_template(
        "user_edit.html",
        form=form,
        person=person,
        editing_self=editing_self,
    )


def _apply_user_edit(person, form, editing_self):
    name = clean_name(form.full_name.data)

    if not name or len(name) > 120:
        return "Enter a full name of 120 characters or fewer."

    mail = clean_email(form.email.data)

    if mail is None:
        return "Enter an email address like name@example.com."

    new_role = form.role.data

    if new_role not in ROLE_LABELS:
        return "Choose Administrator, Inspector, or Viewer."

    new_active = bool(form.is_active.data)

    if editing_self and (
        new_role != person.role or new_active != person.is_active
    ):
        return (
            "You cannot change your own role or turn off your own account. "
            "Another administrator can do that."
        )

    active_admins = (
        db.session.query(User)
        .filter_by(role="administrator", is_active=True)
        .count()
    )

    only_active_admin = (
        person.role == "administrator"
        and person.is_active
        and active_admins <= 1
    )

    if only_active_admin and (
        new_role != "administrator" or not new_active
    ):
        return (
            "This is the only active administrator. "
            "Create another administrator before changing this role "
            "or turning this account off."
        )

    new_password = form.new_password.data or ""
    confirm = form.new_password_confirm.data or ""

    if new_password or confirm:
        if new_password != confirm:
            return "The two new passwords do not match."

        problem = password_problem(new_password, mail)

        if problem:
            return problem

        person.set_password(new_password)

    taken = (
        db.session.query(User)
        .filter(User.email == mail, User.id != person.id)
        .first()
    )

    if taken is not None:
        return "That email is already used."

    person.full_name = name
    person.email = mail
    person.role = new_role
    person.is_active = new_active
    person.updated_at = utcnow()

    if new_password:
        note = f"Updated the account and password for {person.email}."
    else:
        note = f"Updated the account for {person.email}."

    record("update", "user", note, person.id)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return "That email is already used."

    return None
