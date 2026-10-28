from functools import wraps

from flask import (Blueprint, Response, abort, current_app, flash, g, redirect, render_template, request,
                   session, url_for)
from flask_login import current_user

from ... import reports
from ...extensions import db
from ...forms import (apply_branch_form, apply_campaign_form, apply_prize_form, apply_user_form)
from ...models import AuditLog, Award, Branch, Brand, Campaign, Participant, Prize, User
from ...services import RedemptionError, redeem_award, sync_fallback_prize
from ...utils.audit import audit
from ...utils.codes import normalize_code, temp_password
from ...utils.exports import export_response
from ...utils.qr import qr_png
from ...utils.theming import contrast_text
from ...utils.timefmt import local_day_bounds_utc

bp = Blueprint("brand", __name__)


@bp.before_request
def load_brand():
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login", next=request.full_path))
    if current_user.is_superadmin:
        brand_id = session.get("acting_brand_id")
        if not brand_id:
            return redirect(url_for("superadmin.brands"))
        g.brand = db.session.get(Brand, brand_id)
        g.acting = True
    else:
        g.brand = current_user.brand
        g.acting = False
    if g.brand is None:
        abort(403)
    g.campaign = g.brand.current_campaign


@bp.context_processor
def inject_brand():
    return {"brand": g.get("brand"), "campaign": g.get("campaign"), "acting": g.get("acting")}


def admin_only(view):
    """Brand admins and the superadmin; branch staff are limited to redemption."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user.is_staff:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def _owned(model, obj_id):
    obj = db.session.get(model, obj_id)
    if obj is None or getattr(obj, "brand_id", None) != g.brand.id:
        abort(404)
    return obj


def customer_url(branch):
    return current_app.config["PUBLIC_BASE_URL"] + url_for("customer.landing", slug=g.brand.slug, branch_code=branch.code)


# --------------------------------------------------------------------------- dashboard
@bp.route("/")
def dashboard():
    if current_user.is_staff:
        return redirect(url_for("brand.redeem"))
    return render_template("brand/dashboard.html",
                           k=reports.kpis(brand_id=g.brand.id),
                           series=reports.daily_series(14, brand_id=g.brand.id),
                           branches=reports.branch_breakdown(g.brand.id),
                           prizes=g.campaign.prizes if g.campaign else [],
                           activity=reports.recent_activity(10, brand_id=g.brand.id))


# --------------------------------------------------------------------------- campaign
@bp.route("/campaign", methods=["GET", "POST"])
@admin_only
def campaign():
    c = g.campaign
    if c is None:
        c = Campaign(brand=g.brand, name="Scratch & Win", voucher_percent=10, fallback_enabled=True)
    if request.method == "POST":
        form = request.form.copy()
        form["_has_active"] = "1"
        errors = apply_campaign_form(c, form)
        if errors:
            db.session.rollback()
            for e in errors:
                flash(e, "error")
        else:
            db.session.add(c)
            db.session.flush()
            sync_fallback_prize(c)
            audit("campaign_updated", c, brand_id=g.brand.id, min_spend=str(c.min_spend),
                  voucher_percent=c.voucher_percent, active=c.is_active)
            db.session.commit()
            flash("Campaign settings saved.", "success")
            return redirect(url_for("brand.campaign"))
    return render_template("brand/campaign.html", c=c, campaigns=g.brand.campaigns)


@bp.route("/campaign/new", methods=["POST"])
@admin_only
def campaign_new():
    old = g.campaign
    new = Campaign(brand=g.brand, name=request.form.get("name", "").strip() or "New Campaign",
                   min_spend=old.min_spend if old else 0, currency=old.currency if old else "SAR",
                   voucher_percent=old.voucher_percent if old else 10,
                   claim_expiry_days=old.claim_expiry_days if old else 30,
                   terms_en=old.terms_en if old else None, terms_ar=old.terms_ar if old else None,
                   fallback_enabled=True, is_active=True)
    for c in g.brand.campaigns:
        c.is_active = False
    db.session.add(new)
    db.session.flush()
    sync_fallback_prize(new)
    audit("campaign_created", new, brand_id=g.brand.id, name=new.name)
    db.session.commit()
    flash("New campaign started. Add its prizes to go live.", "success")
    return redirect(url_for("brand.prizes"))


@bp.route("/campaign/<int:cid>/activate", methods=["POST"])
@admin_only
def campaign_activate(cid):
    target = _owned(Campaign, cid)
    for c in g.brand.campaigns:
        c.is_active = c.id == target.id
    audit("campaign_activated", target, brand_id=g.brand.id)
    db.session.commit()
    flash(f"'{target.name}' is now the active campaign.", "success")
    return redirect(url_for("brand.campaign"))


# --------------------------------------------------------------------------- prizes
@bp.route("/prizes", methods=["GET", "POST"])
@admin_only
def prizes():
    c = g.campaign
    if c is None:
        flash("Set up your campaign first.", "info")
        return redirect(url_for("brand.campaign"))
    if request.method == "POST":
        prize = Prize(campaign=c, awarded_count=0)
        form = request.form.copy()
        form["is_active"] = "1"
        errors = apply_prize_form(prize, form, g.brand)
        if errors:
            db.session.rollback()
            for e in errors:
                flash(e, "error")
        else:
            db.session.add(prize)
            db.session.flush()
            audit("prize_created", prize, brand_id=g.brand.id, name=prize.name, quantity=prize.quantity)
            db.session.commit()
            flash(f"Prize '{prize.name}' added.", "success")
        return redirect(url_for("brand.prizes"))
    total_remaining = sum(p.remaining for p in c.prizes if p.is_active and not p.is_fallback)
    return render_template("brand/prizes.html", c=c, total_remaining=total_remaining)


@bp.route("/prizes/<int:prize_id>", methods=["POST"])
@admin_only
def prize_edit(prize_id):
    prize = db.session.get(Prize, prize_id)
    if prize is None or prize.campaign.brand_id != g.brand.id:
        abort(404)
    if request.form.get("action") == "delete":
        if prize.awarded_count or prize.is_fallback:
            flash("Prizes that have been won (or the fallback voucher) can't be deleted — disable them instead.", "error")
        else:
            audit("prize_deleted", prize, brand_id=g.brand.id, name=prize.name)
            db.session.delete(prize)
            db.session.commit()
            flash("Prize deleted.", "success")
        return redirect(url_for("brand.prizes"))
    old_names = (prize.name, prize.name_ar)
    errors = apply_prize_form(prize, request.form, g.brand)
    if errors:
        db.session.rollback()
        for e in errors:
            flash(e, "error")
    else:
        if not prize.is_fallback and (prize.name, prize.name_ar) != old_names:
            # A rename is a correction (e.g. a wrong translation): show it on prizes already won too.
            fixed = Award.query.filter_by(prize_id=prize.id).update(
                {"prize_name": prize.name, "prize_name_ar": prize.name_ar}, synchronize_session=False)
            if fixed:
                audit("prize_renamed", prize, brand_id=g.brand.id, old_name=old_names[0], old_name_ar=old_names[1],
                      name=prize.name, name_ar=prize.name_ar, awards_updated=fixed)
        audit("prize_updated", prize, brand_id=g.brand.id, name=prize.name, quantity=prize.quantity,
              active=prize.is_active)
        db.session.commit()
        flash(f"'{prize.name}' updated.", "success")
    return redirect(url_for("brand.prizes"))


# --------------------------------------------------------------------------- branches
@bp.route("/branches", methods=["GET", "POST"])
@admin_only
def branches():
    if request.method == "POST":
        branch = Branch(brand_id=g.brand.id)
        errors = apply_branch_form(branch, request.form)
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            db.session.add(branch)
            db.session.flush()
            audit("branch_created", branch, name=branch.name, code=branch.code)
            db.session.commit()
            flash(f"Branch '{branch.name}' added. Its QR code is ready under QR Codes.", "success")
        return redirect(url_for("brand.branches"))
    return render_template("brand/branches.html", rows=reports.branch_breakdown(g.brand.id))


@bp.route("/branches/<int:branch_id>", methods=["POST"])
@admin_only
def branch_edit(branch_id):
    branch = _owned(Branch, branch_id)
    form = request.form.copy()
    form["_has_active"] = "1"
    errors = apply_branch_form(branch, form)
    if errors:
        db.session.rollback()
        for e in errors:
            flash(e, "error")
    else:
        audit("branch_updated", branch, name=branch.name, active=branch.is_active)
        db.session.commit()
        flash("Branch updated.", "success")
    return redirect(url_for("brand.branches"))


# --------------------------------------------------------------------------- staff
@bp.route("/staff", methods=["GET", "POST"])
@admin_only
def staff():
    if request.method == "POST":
        role = request.form.get("role")
        role = User.ROLE_BRAND_ADMIN if role == "brand_admin" else User.ROLE_STAFF
        user = User(role=role, brand_id=g.brand.id, must_change_password=True)
        form = request.form.copy()
        password = form.get("password") or temp_password()
        form["password"] = password
        errors, _ = apply_user_form(user, form, require_password=True)
        branch_id = request.form.get("branch_id", type=int)
        if role == User.ROLE_STAFF:
            if not branch_id or not Branch.query.filter_by(id=branch_id, brand_id=g.brand.id).first():
                errors.append("Choose the branch this staff member works at.")
            user.branch_id = branch_id
        if errors:
            db.session.rollback()
            for e in errors:
                flash(e, "error")
        else:
            db.session.add(user)
            db.session.flush()
            audit("staff_created", user, email=user.email, role=role)
            db.session.commit()
            _maybe_send_credentials(user, password)
            session["new_credentials"] = {"email": user.email, "password": password}
            flash(f"Account created for {user.full_name}.", "success")
        return redirect(url_for("brand.staff"))
    users = User.query.filter_by(brand_id=g.brand.id).order_by(User.role, User.full_name).all()
    return render_template("brand/staff.html", users=users, credentials=session.pop("new_credentials", None),
                           login_url=current_app.config["PUBLIC_BASE_URL"] + url_for("auth.brand_login", slug=g.brand.slug))


def _maybe_send_credentials(user, password):
    if request.form.get("send_credentials"):
        from ...utils.mailer import send_email
        send_email(user.email, f"Your {g.brand.name} dashboard access", "credentials", from_name=g.brand.name,
                   user=user, brand=g.brand, password=password,
                   login_url=current_app.config["PUBLIC_BASE_URL"] + url_for("auth.brand_login", slug=g.brand.slug))


@bp.route("/staff/<int:user_id>", methods=["POST"])
@admin_only
def staff_action(user_id):
    user = _owned(User, user_id)
    action = request.form.get("action")
    if user.id == current_user.id and action == "toggle":
        flash("You can't disable your own account.", "error")
    elif action == "toggle":
        user.is_active_flag = not user.is_active_flag
        audit("user_enabled" if user.is_active_flag else "user_disabled", user, email=user.email)
        db.session.commit()
        flash(f"{user.full_name} {'enabled' if user.is_active_flag else 'disabled'}.", "success")
    elif action == "reset":
        password = temp_password()
        user.set_password(password)
        user.must_change_password = True
        audit("password_reset", user, email=user.email)
        db.session.commit()
        _maybe_send_credentials(user, password)
        session["new_credentials"] = {"email": user.email, "password": password}
        flash(f"Password reset for {user.full_name}.", "success")
    elif action == "branch":
        branch_id = request.form.get("branch_id", type=int)
        if Branch.query.filter_by(id=branch_id, brand_id=g.brand.id).first():
            user.branch_id = branch_id
            audit("staff_branch_changed", user, branch_id=branch_id)
            db.session.commit()
    return redirect(url_for("brand.staff"))


# --------------------------------------------------------------------------- QR codes
@bp.route("/qr")
@admin_only
def qr_codes():
    branches = Branch.query.filter_by(brand_id=g.brand.id).order_by(Branch.name).all()
    return render_template("brand/qr_codes.html", branches=branches, customer_url=customer_url)


def _qr_ink():
    return g.brand.secondary_color if contrast_text(g.brand.secondary_color) == "#FFFFFF" else "#111111"


@bp.route("/qr/<int:branch_id>.png")
@admin_only
def qr_png_view(branch_id):
    branch = _owned(Branch, branch_id)
    png = qr_png(customer_url(branch), fill=_qr_ink(), box_size=16, border=2)
    disp = "attachment" if request.args.get("download") else "inline"
    return Response(png, mimetype="image/png",
                    headers={"Content-Disposition": f'{disp}; filename="{g.brand.slug}-{branch.code}-qr.png"'})


@bp.route("/qr/<int:branch_id>/poster")
@admin_only
def qr_poster(branch_id):
    branch = _owned(Branch, branch_id)
    return render_template("brand/qr_poster.html", branch=branch, url=customer_url(branch))


# --------------------------------------------------------------------------- participants
@bp.route("/participants")
@admin_only
def participants():
    q = reports.participant_query(request.args, brand_id=g.brand.id)
    page = q.paginate(page=request.args.get("page", 1, type=int), per_page=25, error_out=False)
    return render_template("brand/participants.html", page=page, args=request.args,
                           branches=Branch.query.filter_by(brand_id=g.brand.id).order_by(Branch.name).all())


@bp.route("/participants/<int:pid>")
@admin_only
def participant_detail(pid):
    p = _owned(Participant, pid)
    logs = AuditLog.query.filter(AuditLog.target_type.in_(["Participant", "Award"]),
                                 AuditLog.target_id.in_([p.id, p.award.id if p.award else -1])
                                 ).order_by(AuditLog.created_at).all()
    return render_template("shared/participant_detail.html", p=p, logs=logs, layout="layouts/brand.html")


@bp.route("/export/<dataset>.<fmt>")
@admin_only
def export(dataset, fmt):
    if fmt not in ("csv", "xlsx") or dataset not in ("participants", "redemptions", "audit"):
        abort(404)
    if dataset == "audit":
        logs = AuditLog.query.filter_by(brand_id=g.brand.id).order_by(AuditLog.created_at.desc()).all()
        resp = export_response(fmt, f"{g.brand.slug}-audit", reports.AUDIT_HEADERS, reports.audit_rows(logs), "Audit")
    else:
        args = request.args.to_dict()
        if dataset == "redemptions":
            args["status"] = "redeemed"
        rows = reports.participant_rows(reports.participant_query(args, brand_id=g.brand.id).all())
        resp = export_response(fmt, f"{g.brand.slug}-{dataset}", reports.PARTICIPANT_HEADERS, rows, dataset.title())
    audit("export", brand_id=g.brand.id, dataset=dataset, format=fmt)
    db.session.commit()
    return resp


# --------------------------------------------------------------------------- redemption
def _branch_today():
    start, end = local_day_bounds_utc()
    q = Award.query.filter(Award.brand_id == g.brand.id, Award.redeemed_at >= start, Award.redeemed_at < end)
    rq = Participant.query.filter(Participant.brand_id == g.brand.id, Participant.created_at >= start,
                                  Participant.created_at < end)
    if current_user.is_staff and current_user.branch_id:
        q = q.filter(Award.redeemed_branch_id == current_user.branch_id)
        rq = rq.filter(Participant.branch_id == current_user.branch_id)
    return {"redeemed": q.count(), "registrations": rq.count(),
            "recent": q.order_by(Award.redeemed_at.desc()).limit(8).all()}


@bp.route("/redeem")
def redeem():
    code = normalize_code(request.args.get("code"))
    if code:
        award = Award.query.filter_by(claim_code=code, brand_id=g.brand.id).first()
        if award:
            return redirect(url_for("brand.redeem_award_view", token=award.qr_token))
        flash(f"No prize found for code {code} at {g.brand.name}.", "error")
    return render_template("brand/redeem.html", today=_branch_today())


@bp.route("/redeem/<token>", methods=["GET", "POST"])
def redeem_award_view(token):
    award = Award.query.filter_by(qr_token=token).first_or_404()
    if award.brand_id != g.brand.id:
        return render_template("brand/redeem_result.html", award=None, wrong_brand=True), 403
    branches = Branch.query.filter_by(brand_id=g.brand.id, is_active=True).order_by(Branch.name).all()
    if request.method == "POST":
        branch_id = request.form.get("branch_id", type=int)
        if current_user.is_staff:
            branch_id = current_user.branch_id
        elif branch_id and not any(b.id == branch_id for b in branches):
            branch_id = None
        try:
            redeem_award(award, current_user, branch_id=branch_id)
            audit("prize_redeemed", award, brand_id=g.brand.id, claim_code=award.claim_code,
                  reference=award.redemption_ref, prize=award.prize_name,
                  participant=award.participant.email, branch_id=award.redeemed_branch_id)
            db.session.commit()
            flash(f"Won & delivered: {award.prize_name} for {award.participant.full_name}. "
                  f"Reference {award.redemption_ref}.", "success")
        except RedemptionError as exc:
            db.session.rollback()
            flash(str(exc), "error")
        return redirect(url_for("brand.redeem_award_view", token=token))
    return render_template("brand/redeem_result.html", award=award, branches=branches, wrong_brand=False)
