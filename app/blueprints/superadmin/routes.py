from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user

from ... import reports
from ...extensions import db
from ...forms import apply_brand_form, apply_campaign_form, apply_prize_rows, apply_user_form
from ...models import AuditLog, Branch, Brand, Campaign, Participant, Setting, User
from ...services import sync_fallback_prize
from ...utils.audit import audit
from ...utils.codes import temp_password
from ...utils.decorators import superadmin_required
from ...utils.exports import export_response
from ...utils.mailer import send_email

bp = Blueprint("superadmin", __name__)

PER_PAGE = 25


@bp.before_request
@superadmin_required
def _guard():
    return None


def brand_login_url(brand):
    return current_app.config["PUBLIC_BASE_URL"] + url_for("auth.brand_login", slug=brand.slug)


def send_credentials(user, password):
    brand = user.brand
    return send_email(user.email, f"Your {brand.name} dashboard access", "credentials",
                      from_name=current_app.config["GROUP_NAME"],
                      user=user, brand=brand, password=password, login_url=brand_login_url(brand))


# --------------------------------------------------------------------------- dashboard
@bp.route("/")
def dashboard():
    return render_template("superadmin/dashboard.html",
                           k=reports.kpis(),
                           series=reports.daily_series(14),
                           leaderboard=reports.brand_leaderboard(),
                           prizes=reports.prize_breakdown()[:8],
                           activity=reports.recent_activity(12),
                           brand_count=Brand.query.count(),
                           active_brands=Brand.query.filter_by(is_active=True).count())


# --------------------------------------------------------------------------- brands
@bp.route("/brands")
def brands():
    return render_template("superadmin/brands.html", rows=reports.brand_leaderboard())


@bp.route("/brands/new", methods=["GET", "POST"])
def brand_new():
    brand = Brand()
    campaign = Campaign(min_spend=0, currency="SAR", voucher_percent=10, claim_expiry_days=30, fallback_enabled=True)
    form = request.form
    if request.method == "POST":
        errors = apply_brand_form(brand, form, request.files)
        errors += apply_campaign_form(campaign, form)
        admin = User(role=User.ROLE_BRAND_ADMIN, must_change_password=True)
        generated = form.get("admin_password") or temp_password()
        admin_form = form.copy()
        admin_form["full_name"] = form.get("admin_name", "")
        admin_form["email"] = form.get("admin_email", "")
        admin_form["password"] = generated
        user_errors, _ = apply_user_form(admin, admin_form, require_password=True)
        errors += user_errors
        if not errors:
            db.session.add(brand)
            campaign.brand = brand
            campaign.is_active = True
            db.session.add(campaign)
            admin.brand = brand
            db.session.add(admin)
            branch = Branch(brand=brand, name=form.get("branch_name", "").strip() or "Main Branch",
                            code=(form.get("branch_code", "").strip().lower() or "main")[:30])
            db.session.add(branch)
            for p in apply_prize_rows(campaign, form):
                db.session.add(p)
            db.session.flush()
            sync_fallback_prize(campaign)
            audit("brand_created", brand, brand_id=brand.id, name=brand.name, admin=admin.email)
            db.session.commit()
            if form.get("send_credentials"):
                send_credentials(admin, generated)
            session["new_credentials"] = {"email": admin.email, "password": generated}
            flash(f"{brand.name} created. Share the sign-in link and credentials with the brand admin.", "success")
            return redirect(url_for("superadmin.brand_detail", brand_id=brand.id))
        db.session.rollback()
        for e in errors:
            flash(e, "error")
    return render_template("superadmin/brand_form.html", brand=brand, campaign=campaign, form=form, is_new=True)


def _brand_or_404(brand_id):
    brand = db.session.get(Brand, brand_id)
    if not brand:
        abort(404)
    return brand


@bp.route("/brands/<int:brand_id>")
def brand_detail(brand_id):
    brand = _brand_or_404(brand_id)
    return render_template("superadmin/brand_detail.html", brand=brand,
                           k=reports.kpis(brand_id=brand.id),
                           series=reports.daily_series(14, brand_id=brand.id),
                           branches=reports.branch_breakdown(brand.id),
                           login_url=brand_login_url(brand),
                           credentials=session.pop("new_credentials", None))


@bp.route("/brands/<int:brand_id>/edit", methods=["GET", "POST"])
def brand_edit(brand_id):
    brand = _brand_or_404(brand_id)
    if request.method == "POST":
        errors = apply_brand_form(brand, request.form, request.files)
        if errors:
            db.session.rollback()
            for e in errors:
                flash(e, "error")
        else:
            audit("brand_updated", brand, name=brand.name)
            db.session.commit()
            flash("Brand updated.", "success")
            return redirect(url_for("superadmin.brand_detail", brand_id=brand.id))
    return render_template("superadmin/brand_form.html", brand=brand, campaign=brand.current_campaign,
                           form=request.form, is_new=False)


@bp.route("/brands/<int:brand_id>/toggle", methods=["POST"])
def brand_toggle(brand_id):
    brand = _brand_or_404(brand_id)
    brand.is_active = not brand.is_active
    audit("brand_enabled" if brand.is_active else "brand_disabled", brand)
    db.session.commit()
    flash(f"{brand.name} is now {'active' if brand.is_active else 'disabled'}.", "success")
    return redirect(request.referrer or url_for("superadmin.brands"))


@bp.route("/brands/<int:brand_id>/admins", methods=["POST"])
def brand_admin_add(brand_id):
    brand = _brand_or_404(brand_id)
    user = User(role=User.ROLE_BRAND_ADMIN, brand=brand, must_change_password=True)
    form = request.form.copy()
    password = form.get("password") or temp_password()
    form["password"] = password
    errors, _ = apply_user_form(user, form, require_password=True)
    if errors:
        db.session.rollback()
        for e in errors:
            flash(e, "error")
    else:
        db.session.add(user)
        audit("brand_admin_created", user, brand_id=brand.id, email=user.email)
        db.session.commit()
        if request.form.get("send_credentials"):
            send_credentials(user, password)
        session["new_credentials"] = {"email": user.email, "password": password}
        flash("Brand admin added.", "success")
    return redirect(url_for("superadmin.brand_detail", brand_id=brand.id))


@bp.route("/users/<int:user_id>/reset", methods=["POST"])
def user_reset(user_id):
    user = db.session.get(User, user_id) or abort(404)
    if user.is_superadmin and user.id != current_user.id:
        abort(403)
    password = temp_password()
    user.set_password(password)
    user.must_change_password = True
    audit("password_reset", user, brand_id=user.brand_id, email=user.email)
    db.session.commit()
    if request.form.get("send_credentials") and user.brand:
        send_credentials(user, password)
    session["new_credentials"] = {"email": user.email, "password": password}
    flash(f"Password reset for {user.email}.", "success")
    return redirect(url_for("superadmin.brand_detail", brand_id=user.brand_id) if user.brand_id
                    else url_for("superadmin.dashboard"))


@bp.route("/users/<int:user_id>/toggle", methods=["POST"])
def user_toggle(user_id):
    user = db.session.get(User, user_id) or abort(404)
    if user.is_superadmin:
        abort(403)
    user.is_active_flag = not user.is_active_flag
    audit("user_enabled" if user.is_active_flag else "user_disabled", user, brand_id=user.brand_id)
    db.session.commit()
    return redirect(request.referrer or url_for("superadmin.dashboard"))


@bp.route("/brands/<int:brand_id>/manage")
def brand_manage(brand_id):
    """Open the brand dashboard acting as that brand (all actions are audited as the superadmin)."""
    brand = _brand_or_404(brand_id)
    session["acting_brand_id"] = brand.id
    audit("acting_as_brand", brand)
    db.session.commit()
    return redirect(url_for("brand.dashboard"))


@bp.route("/stop-acting")
def stop_acting():
    brand_id = session.pop("acting_brand_id", None)
    return redirect(url_for("superadmin.brand_detail", brand_id=brand_id) if brand_id else url_for("superadmin.dashboard"))


# --------------------------------------------------------------------------- participants & activity
@bp.route("/participants")
def participants():
    q = reports.participant_query(request.args)
    page = q.paginate(page=request.args.get("page", 1, type=int), per_page=PER_PAGE, error_out=False)
    return render_template("superadmin/participants.html", page=page, brands=Brand.query.order_by(Brand.name).all(),
                           branches=Branch.query.order_by(Branch.name).all(), args=request.args)


@bp.route("/participants/<int:pid>")
def participant_detail(pid):
    p = db.session.get(Participant, pid) or abort(404)
    logs = AuditLog.query.filter(AuditLog.target_type.in_(["Participant", "Award"]),
                                 AuditLog.target_id.in_([p.id, p.award.id if p.award else -1])
                                 ).order_by(AuditLog.created_at).all()
    return render_template("shared/participant_detail.html", p=p, logs=logs, layout="layouts/admin.html")


@bp.route("/audit")
def audit_log():
    q = AuditLog.query.order_by(AuditLog.created_at.desc())
    if request.args.get("brand"):
        q = q.filter(AuditLog.brand_id == request.args.get("brand", type=int))
    if request.args.get("action"):
        q = q.filter(AuditLog.action == request.args["action"])
    if request.args.get("q"):
        q = q.filter(AuditLog.actor_label.ilike(f"%{request.args['q']}%"))
    page = q.paginate(page=request.args.get("page", 1, type=int), per_page=50, error_out=False)
    actions = [a for (a,) in db.session.query(AuditLog.action).distinct().order_by(AuditLog.action)]
    return render_template("superadmin/audit.html", page=page, brands=Brand.query.order_by(Brand.name).all(),
                           actions=actions, args=request.args)


@bp.route("/export/<dataset>.<fmt>")
def export(dataset, fmt):
    if fmt not in ("csv", "xlsx"):
        abort(404)
    if dataset == "participants":
        rows = reports.participant_rows(reports.participant_query(request.args).all())
        resp = export_response(fmt, "participants", reports.PARTICIPANT_HEADERS, rows, "Participants")
    elif dataset == "redemptions":
        args = request.args.to_dict()
        args["status"] = "redeemed"
        rows = reports.participant_rows(reports.participant_query(args).all())
        resp = export_response(fmt, "redemptions", reports.PARTICIPANT_HEADERS, rows, "Redemptions")
    elif dataset == "brands":
        resp = export_response(fmt, "brand-summary", reports.BRAND_HEADERS, reports.brand_rows(), "Brands")
    elif dataset == "audit":
        logs = AuditLog.query.order_by(AuditLog.created_at.desc())
        if request.args.get("brand"):
            logs = logs.filter(AuditLog.brand_id == request.args.get("brand", type=int))
        resp = export_response(fmt, "audit-log", reports.AUDIT_HEADERS, reports.audit_rows(logs.all()), "Audit")
    else:
        abort(404)
    audit("export", dataset=dataset, format=fmt, filters=request.args.to_dict())
    db.session.commit()
    return resp


# --------------------------------------------------------------------------- settings
@bp.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        scope = request.form.get("uniqueness_scope")
        if scope in ("campaign", "brand", "group"):
            Setting.set("uniqueness_scope", scope)
            audit("settings_updated", uniqueness_scope=scope)
            db.session.commit()
            flash("Settings saved.", "success")
        return redirect(url_for("superadmin.settings"))
    superadmins = User.query.filter_by(role=User.ROLE_SUPERADMIN).all()
    return render_template("superadmin/settings.html", scope=Setting.get("uniqueness_scope"), superadmins=superadmins)


@bp.route("/settings/test-email", methods=["POST"])
def test_email():
    ok = send_email(current_user.email, "Test email from the promo platform", "test", sync=True, user=current_user)
    flash("Test email sent to " + current_user.email if ok else "Email failed — check the MAIL_* settings and server log.",
          "success" if ok else "error")
    return redirect(url_for("superadmin.settings"))


@bp.route("/settings/superadmins", methods=["POST"])
def superadmin_add():
    user = User(role=User.ROLE_SUPERADMIN)
    errors, _ = apply_user_form(user, request.form, require_password=True)
    if errors:
        db.session.rollback()
        for e in errors:
            flash(e, "error")
    else:
        db.session.add(user)
        audit("superadmin_created", user, email=user.email)
        db.session.commit()
        flash("Superadmin added.", "success")
    return redirect(url_for("superadmin.settings"))

