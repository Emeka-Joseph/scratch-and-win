from functools import wraps

from flask import abort, redirect, request, url_for
from flask_login import current_user


def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login", next=request.full_path))
            if current_user.role not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


superadmin_required = roles_required("superadmin")
