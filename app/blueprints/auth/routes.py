from urllib.parse import urlparse

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ...extensions import db
from ...models import Brand, User, utcnow
from ...utils.audit import audit

bp = Blueprint("auth", __name__)

MAX_FAILED = 8


def home_for(user):
    if user.must_change_password:
        return url_for("auth.change_password")
    if user.is_superadmin:
        return url_for("superadmin.dashboard")
    if user.is_staff:
        return url_for("brand.redeem")
    return url_for("brand.dashboard")


def _safe_next(target):
    if not target:
        return None
    parsed = urlparse(target)
    return target if not parsed.netloc and target.startswith("/") else None


def _attempt_login(brand=None):
    if session.get("failed_logins", 0) >= MAX_FAILED:
        flash("Too many failed attempts. Close the browser and try again later.", "error")
        return None
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    user = User.query.filter_by(email=email).first()
    ok = user is not None and user.check_password(password) and user.is_active
    if ok and brand is not None and user.brand_id != brand.id:
        ok = False
    if not ok:
        session["failed_logins"] = session.get("failed_logins", 0) + 1
        audit("login_failed", brand_id=brand.id if brand else None, actor_label=email or "unknown")
        db.session.commit()
        flash("Invalid email or password.", "error")
        return None
    session.pop("failed_logins", None)
    login_user(user, remember=bool(request.form.get("remember")))
    user.last_login_at = utcnow()
    audit("login", user)
    db.session.commit()
    nxt = _safe_next(request.args.get("next"))
    return redirect(nxt if nxt and not user.must_change_password else home_for(user))


@bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(home_for(current_user))
    return redirect(url_for("auth.login"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(home_for(current_user))
    if request.method == "POST":
        resp = _attempt_login()
        if resp:
            return resp
    return render_template("auth/login.html", brand=None)


@bp.route("/b/<slug>/login", methods=["GET", "POST"])
def brand_login(slug):
    brand = Brand.query.filter_by(slug=slug).first_or_404()
    if not brand.is_active:
        abort(404)
    if current_user.is_authenticated and current_user.brand_id == brand.id:
        return redirect(home_for(current_user))
    if request.method == "POST":
        resp = _attempt_login(brand)
        if resp:
            return resp
    return render_template("auth/login.html", brand=brand)


@bp.route("/logout")
def logout():
    brand = current_user.brand if current_user.is_authenticated else None
    if current_user.is_authenticated:
        audit("logout", current_user)
        db.session.commit()
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("auth.brand_login", slug=brand.slug) if brand else url_for("auth.login"))


@bp.route("/account/password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        if not current_user.check_password(current):
            flash("Your current password is incorrect.", "error")
        elif len(new) < 8:
            flash("New password must be at least 8 characters.", "error")
        elif new != confirm:
            flash("New passwords do not match.", "error")
        else:
            current_user.set_password(new)
            current_user.must_change_password = False
            audit("password_changed", current_user)
            db.session.commit()
            flash("Password updated.", "success")
            return redirect(home_for(current_user))
    return render_template("auth/change_password.html", brand=current_user.brand)
