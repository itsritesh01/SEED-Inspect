
from functools import wraps
from urllib.parse import urlparse

from flask import abort
from flask_login import current_user


def safe_next(target):
    """Allow a redirect only to a page on this same site."""
    if not target or not target.startswith("/") or target.startswith("//"):
        return None

    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return None

    return target


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        from app import login_manager

        if not current_user.is_authenticated:
            return login_manager.unauthorized()

        if current_user.role != "administrator":
            abort(403)

        return view(*args, **kwargs)

    return wrapped


def editor_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        from app import login_manager

        if not current_user.is_authenticated:
            return login_manager.unauthorized()

        if current_user.role not in ("administrator", "inspector"):
            abort(403)

        return view(*args, **kwargs)

    return wrapped
