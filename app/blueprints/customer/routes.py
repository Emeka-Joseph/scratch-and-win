from datetime import timedelta

from flask import (Blueprint, Response, abort, current_app, jsonify, redirect, render_template, request,
                   session, url_for)
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from ...extensions import db
from ...i18n import LANGS, get_lang, t
from ...models import Award, Branch, Brand, Participant, utcnow
from ...services import allocate_prize, conflicting_participants, prizes_available
from ...utils.audit import audit, client_ip
from ...utils.codes import (is_valid_email, is_valid_mobile, normalize_code, normalize_email, normalize_mobile,
                            random_code)
from ...utils.mailer import send_email
from ...utils.qr import qr_png
from ...utils.timefmt import fmt_dt

bp = Blueprint("customer", __name__)


# --------------------------------------------------------------------------- helpers
def _brand(slug):
    brand = Brand.query.filter_by(slug=slug, is_active=True).first()
    if brand is None:
        abort(404)
    return brand


def _skey(brand):
    return f"participant_{brand.id}"


def _current_participant(brand):
    pid = session.get(_skey(brand))
    if not pid:
        return None
    p = db.session.get(Participant, pid)
    return p if p and p.brand_id == brand.id else None


def _render(template, brand, **ctx):
    lang = get_lang()
    return render_template(f"customer/{template}.html", brand=brand, lang=lang,
                           dir="rtl" if lang == "ar" else "ltr", **ctx)


def _send_verify_code(p, brand):
    code = random_code(current_app.config["VERIFY_CODE_LENGTH"])
    p.verify_code_hash = generate_password_hash(code)
    p.verify_code_sent_at = utcnow()
    p.verify_code_expires_at = utcnow() + timedelta(minutes=current_app.config["VERIFY_CODE_TTL_MINUTES"])
    p.verify_attempts = 0
    p.verify_sends = (p.verify_sends or 0) + 1
    lang = p.language
    return send_email(p.email, t("email_verify_subject", lang, brand=brand.localized("name", lang), code=code),
                      "verify_code", from_name=brand.name, reply_to=brand.contact_email, brand=brand, p=p, code=code, lang=lang,
                      ttl=current_app.config["VERIFY_CODE_TTL_MINUTES"])


def _send_prize_email(award):
    p, brand = award.participant, award.brand
    lang = p.language
    staff_url = current_app.config["PUBLIC_BASE_URL"] + url_for("brand.redeem_award_view", token=award.qr_token)
    sent = send_email(p.email, t("email_prize_subject", lang, brand=brand.localized("name", lang),
                          prize=award.localized_prize(lang)),
               "prize", from_name=brand.name, reply_to=brand.contact_email, brand=brand, p=p, award=award, lang=lang,
               expires=fmt_dt(award.expires_at, "%d %b %Y"),
               prize_url=current_app.config["PUBLIC_BASE_URL"] + url_for("customer.prize", slug=brand.slug,
                                                                         token=award.qr_token),
               inline_images={"prizeqr": qr_png(staff_url, box_size=8)})
    if sent:
        award.confirmation_sent_at = utcnow()


# --------------------------------------------------------------------------- language
@bp.route("/lang/<lang>")
def set_lang(lang):
    if lang in LANGS:
        session["lang"] = lang
        session["lang_chosen"] = True
    nxt = request.args.get("next", "/")
    return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else "/")


# --------------------------------------------------------------------------- landing + registration
@bp.route("/p/<slug>/<branch_code>", methods=["GET", "POST"])
def landing(slug, branch_code):
    brand = _brand(slug)
    branch = Branch.query.filter_by(brand_id=brand.id, code=branch_code, is_active=True).first_or_404()
    campaign = brand.active_campaign
    if request.args.get("lang") in LANGS:
        session["lang"] = request.args["lang"]
        session["lang_chosen"] = True
        return redirect(url_for("customer.landing", slug=slug, branch_code=branch_code))
    if campaign is None:
        return _render("message", brand, kind="closed")
    if not prizes_available(campaign, branch.id):
        return _render("message", brand, kind="sold_out")

    p = _current_participant(brand)
    if p and p.campaign_id == campaign.id:
        if p.award:
            return redirect(url_for("customer.scratch", slug=slug) if not p.award.revealed_at
                            else url_for("customer.prize", slug=slug, token=p.award.qr_token))
        if request.method == "GET":
            return redirect(url_for("customer.verify", slug=slug))

    errors, values = {}, {}
    if request.method == "POST":
        lang = get_lang()
        values = {"full_name": request.form.get("full_name", "").strip()[:120],
                  "email": normalize_email(request.form.get("email")),
                  "mobile": normalize_mobile(request.form.get("mobile"))}
        if len(values["full_name"]) < 2:
            errors["full_name"] = t("err_name")
        if not is_valid_email(values["email"]):
            errors["email"] = t("err_email")
        if not is_valid_mobile(values["mobile"]):
            errors["mobile"] = t("err_mobile")
        if not request.form.get("accept_terms"):
            errors["terms"] = t("err_terms")
        if not errors:
            conflicts = conflicting_participants(campaign, values["email"], values["mobile"])
            if any(c.verified_at for c in conflicts):
                errors["form"] = t("err_already")
                audit("registration_blocked_duplicate", brand_id=brand.id, actor_label=values["email"],
                      mobile=values["mobile"])
                db.session.commit()
        if not errors:
            # Unverified attempts with the same email/mobile are superseded by this one.
            for c in conflicts:
                if c.campaign_id == campaign.id:
                    db.session.delete(c)
            db.session.flush()
            p = Participant(brand_id=brand.id, campaign_id=campaign.id, branch_id=branch.id,
                            full_name=values["full_name"], email=values["email"], mobile=values["mobile"],
                            language=lang, accepted_terms=True,
                            marketing_consent=bool(request.form.get("marketing_consent")),
                            ip_address=client_ip(), user_agent=(request.user_agent.string or "")[:255])
            db.session.add(p)
            try:
                db.session.flush()
                mail_ok = _send_verify_code(p, brand)
                audit("customer_registered", p, brand_id=brand.id, actor_label=p.email, branch=branch.code)
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                errors["form"] = t("err_already")
            else:
                session[_skey(brand)] = p.id
                return redirect(url_for("customer.verify", slug=slug, **({} if mail_ok else {"mail_failed": 1})))

    return _render("landing", brand, branch=branch, campaign=campaign, errors=errors, values=values,
                   choose_lang=not session.get("lang_chosen"))


@bp.route("/p/<slug>/terms")
def terms(slug):
    brand = _brand(slug)
    campaign = brand.current_campaign
    return _render("terms", brand, campaign=campaign, back=request.args.get("back"))


# --------------------------------------------------------------------------- verification
def _back_to_landing(brand, p):
    code = p.branch.code if p and p.branch else (brand.branches[0].code if brand.branches else "main")
    return redirect(url_for("customer.landing", slug=brand.slug, branch_code=code))


@bp.route("/p/<slug>/verify", methods=["GET", "POST"])
def verify(slug):
    brand = _brand(slug)
    p = _current_participant(brand)
    if p is None:
        return _back_to_landing(brand, None)
    if p.verified_at:
        return redirect(url_for("customer.scratch", slug=slug))
    cfg = current_app.config
    error = info = None
    if request.method == "POST":
        code = normalize_code(request.form.get("code"))
        if p.verify_attempts >= cfg["VERIFY_MAX_ATTEMPTS"]:
            error = t("err_code_locked")
        elif not p.verify_code_expires_at or p.verify_code_expires_at < utcnow():
            error = t("err_code_expired")
        elif not p.verify_code_hash or not check_password_hash(p.verify_code_hash, code):
            p.verify_attempts += 1
            left = cfg["VERIFY_MAX_ATTEMPTS"] - p.verify_attempts
            error = t("err_code", n=left) if left > 0 else t("err_code_locked")
            db.session.commit()
        else:
            # Re-check uniqueness: the same email/mobile may have won elsewhere since registering.
            if any(c.verified_at and c.id != p.id
                   for c in conflicting_participants(p.campaign, p.email, p.mobile)):
                error = t("err_already")
            else:
                award = allocate_prize(p)
                if award is None:
                    db.session.rollback()
                    return _render("message", brand, kind="sold_out")
                p.verified_at = utcnow()
                p.verify_code_hash = None
                db.session.flush()
                audit("customer_verified", p, brand_id=brand.id, actor_label=p.email)
                audit("prize_allocated", award, brand_id=brand.id, actor_label=p.email,
                      prize=award.prize_name, claim_code=award.claim_code)
                try:
                    db.session.commit()
                except IntegrityError:
                    db.session.rollback()
                    error = t("err_already")
                else:
                    return redirect(url_for("customer.scratch", slug=slug))
    elif request.args.get("mail_failed"):
        error = t("err_email_send")
    elif request.args.get("resent"):
        info = t("code_resent")
    wait = 0
    if p.verify_code_sent_at:
        wait = max(0, cfg["VERIFY_RESEND_COOLDOWN_SECONDS"] - int((utcnow() - p.verify_code_sent_at).total_seconds()))
    return _render("verify", brand, p=p, error=error, info=info, wait=wait,
                   code_len=cfg["VERIFY_CODE_LENGTH"])


@bp.route("/p/<slug>/resend", methods=["POST"])
def resend(slug):
    brand = _brand(slug)
    p = _current_participant(brand)
    if p is None or p.verified_at:
        return redirect(url_for("customer.verify", slug=slug))
    cfg = current_app.config
    if p.verify_code_sent_at and (utcnow() - p.verify_code_sent_at).total_seconds() < cfg["VERIFY_RESEND_COOLDOWN_SECONDS"]:
        return _render("verify", brand, p=p, error=t("err_resend_wait"), info=None, wait=cfg["VERIFY_RESEND_COOLDOWN_SECONDS"],
                       code_len=cfg["VERIFY_CODE_LENGTH"])
    if p.verify_sends >= 5:
        return _render("verify", brand, p=p, error=t("err_resend_limit"), info=None, wait=0,
                       code_len=cfg["VERIFY_CODE_LENGTH"])
    mail_ok = _send_verify_code(p, brand)
    audit("verification_resent", p, brand_id=brand.id, actor_label=p.email)
    db.session.commit()
    return redirect(url_for("customer.verify", slug=slug, **({"resent": 1} if mail_ok else {"mail_failed": 1})))


@bp.route("/p/<slug>/restart", methods=["POST"])
def restart(slug):
    brand = _brand(slug)
    p = _current_participant(brand)
    session.pop(_skey(brand), None)
    if p and not p.verified_at:
        resp = _back_to_landing(brand, p)
        db.session.delete(p)
        db.session.commit()
        return resp
    return _back_to_landing(brand, p)


# --------------------------------------------------------------------------- scratch & prize
@bp.route("/p/<slug>/scratch")
def scratch(slug):
    brand = _brand(slug)
    p = _current_participant(brand)
    if p is None or not p.verified_at or not p.award:
        return redirect(url_for("customer.verify", slug=slug)) if p else _back_to_landing(brand, None)
    if p.award.revealed_at:
        return redirect(url_for("customer.prize", slug=slug, token=p.award.qr_token))
    return _render("scratch", brand, p=p, award=p.award)


@bp.route("/p/<slug>/reveal", methods=["POST"])
def reveal(slug):
    brand = _brand(slug)
    p = _current_participant(brand)
    if p is None or not p.award:
        return jsonify(ok=False), 403
    award = p.award
    if not award.revealed_at:
        award.revealed_at = utcnow()
        audit("prize_revealed", award, brand_id=brand.id, actor_label=p.email)
        _send_prize_email(award)
        db.session.commit()
    return jsonify(ok=True, url=url_for("customer.prize", slug=slug, token=award.qr_token))


@bp.route("/p/<slug>/prize/<token>")
def prize(slug, token):
    brand = _brand(slug)
    award = Award.query.filter_by(qr_token=token, brand_id=brand.id).first_or_404()
    return _render("prize", brand, award=award, p=award.participant)


@bp.route("/qr/award/<token>.png")
def award_qr(token):
    award = Award.query.filter_by(qr_token=token).first_or_404()
    staff_url = current_app.config["PUBLIC_BASE_URL"] + url_for("brand.redeem_award_view", token=award.qr_token)
    return Response(qr_png(staff_url, box_size=10, border=1), mimetype="image/png",
                    headers={"Cache-Control": "private, max-age=3600"})
