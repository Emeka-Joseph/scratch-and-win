"""Form parsing/validation shared by superadmin and brand-admin screens.

Each apply_* function mutates the model and returns a list of error strings.
"""
import math
from datetime import datetime
from decimal import Decimal, InvalidOperation

from .models import Branch, Brand, Prize, User, utcnow
from .utils.codes import is_valid_email, slugify
from .utils.theming import clean_hex
from .utils.timefmt import local_to_utc
from .utils.uploads import save_image

RESERVED_SLUGS = {"admin", "brand", "login", "logout", "static", "api", "account", "p", "b", "qr"}


def _s(form, key, maxlen=None):
    val = (form.get(key) or "").strip()
    return val[:maxlen] if maxlen else val


def _int(form, key, default=0, lo=None, hi=None):
    try:
        val = int(form.get(key, default))
    except (TypeError, ValueError):
        val = default
    if lo is not None:
        val = max(lo, val)
    if hi is not None:
        val = min(hi, val)
    return val


def _dt(form, key):
    raw = _s(form, key)
    if not raw:
        return None
    try:
        return local_to_utc(datetime.fromisoformat(raw))
    except ValueError:
        return None


def apply_brand_form(brand, form, files):
    errors = []
    brand.name = _s(form, "name", 120)
    brand.name_ar = _s(form, "name_ar", 120) or None
    if not brand.name:
        errors.append("Brand name is required.")
    slug = slugify(_s(form, "slug") or brand.name)
    clash = Brand.query.filter(Brand.slug == slug, Brand.id != (brand.id or 0)).first()
    if slug in RESERVED_SLUGS or clash:
        errors.append(f"The link name '{slug}' is already taken. Choose another.")
    brand.slug = slug
    brand.tagline = _s(form, "tagline", 200) or None
    brand.tagline_ar = _s(form, "tagline_ar", 200) or None
    brand.description = _s(form, "description") or None
    brand.description_ar = _s(form, "description_ar") or None
    brand.primary_color = clean_hex(form.get("primary_color"), "#C8102E")
    brand.secondary_color = clean_hex(form.get("secondary_color"), "#111111")
    brand.background_color = clean_hex(form.get("background_color"), "#FFFFFF")
    brand.contact_email = _s(form, "contact_email", 190) or None
    brand.contact_phone = _s(form, "contact_phone", 40) or None
    try:
        path = save_image(files.get("logo"), "logos")
        if path:
            brand.logo_path = path
    except ValueError as exc:
        errors.append(str(exc))
    if form.get("remove_logo"):
        brand.logo_path = None
    return errors


def campaign_validity_days(starts_at, ends_at, default=30):
    """Prize validity = whole days from campaign start (or now) to end; `default` when open-ended."""
    if not ends_at:
        return default
    seconds = (ends_at - (starts_at or utcnow())).total_seconds()
    return min(max(math.ceil(seconds / 86400), 1), 3650)


def apply_campaign_form(campaign, form):
    errors = []
    campaign.name = _s(form, "campaign_name", 150) or "Scratch & Win"
    campaign.name_ar = _s(form, "campaign_name_ar", 150) or None
    try:
        campaign.min_spend = Decimal(_s(form, "min_spend") or "0")
        if campaign.min_spend < 0:
            raise InvalidOperation
    except InvalidOperation:
        errors.append("Minimum spend must be a positive number.")
    campaign.currency = (_s(form, "currency", 8) or "SAR").upper()
    campaign.voucher_percent = _int(form, "voucher_percent", 10, 1, 100)
    campaign.fallback_enabled = bool(form.get("fallback_enabled"))
    campaign.starts_at = _dt(form, "starts_at")
    campaign.ends_at = _dt(form, "ends_at")
    if campaign.starts_at and campaign.ends_at and campaign.ends_at <= campaign.starts_at:
        errors.append("Campaign end date must be after the start date.")
    campaign.claim_expiry_days = campaign_validity_days(campaign.starts_at, campaign.ends_at)
    campaign.terms_en = _s(form, "terms_en") or None
    campaign.terms_ar = _s(form, "terms_ar") or None
    if "is_active" in form or form.get("_has_active"):
        campaign.is_active = bool(form.get("is_active"))
    return errors


def apply_prize_rows(campaign, form):
    """Create prizes from repeated inputs prize_name[], prize_name_ar[], prize_qty[]."""
    names = form.getlist("prize_name")
    names_ar = form.getlist("prize_name_ar")
    qtys = form.getlist("prize_qty")
    created = []
    for i, name in enumerate(names):
        name = (name or "").strip()
        if not name:
            continue
        p = Prize(campaign=campaign, name=name[:150],
                  name_ar=(names_ar[i].strip()[:150] if i < len(names_ar) and names_ar[i].strip() else None),
                  quantity=max(_safe_int(qtys, i, 0), 0))
        created.append(p)
    return created


def _safe_int(lst, i, default):
    try:
        return int(lst[i])
    except (IndexError, TypeError, ValueError):
        return default


def apply_prize_form(prize, form, brand):
    errors = []
    prize.name = _s(form, "name", 150)
    prize.name_ar = _s(form, "name_ar", 150) or None
    prize.description = _s(form, "description", 255) or None
    prize.description_ar = _s(form, "description_ar", 255) or None
    if not prize.is_fallback:
        if not prize.name:
            errors.append("Prize name is required.")
        qty = _int(form, "quantity", 0, 0, 10_000_000)
        if qty < prize.awarded_count:
            errors.append(f"Quantity can't be lower than the {prize.awarded_count} already awarded.")
        else:
            prize.quantity = qty
        branch_id = _int(form, "branch_id", 0)
        prize.branch_id = branch_id if branch_id and Branch.query.filter_by(id=branch_id, brand_id=brand.id).first() else None
    prize.is_active = bool(form.get("is_active"))
    return errors


def apply_branch_form(branch, form):
    errors = []
    branch.name = _s(form, "name", 120)
    branch.name_ar = _s(form, "name_ar", 120) or None
    branch.address = _s(form, "address", 255) or None
    code = slugify(_s(form, "code") or branch.name)[:30]
    clash = Branch.query.filter(Branch.brand_id == branch.brand_id, Branch.code == code,
                                Branch.id != (branch.id or 0)).first()
    if not branch.name:
        errors.append("Branch name is required.")
    if clash:
        errors.append(f"Branch code '{code}' is already used.")
    branch.code = code
    if "_has_active" in form:
        branch.is_active = bool(form.get("is_active"))
    return errors


def apply_user_form(user, form, require_password):
    errors = []
    user.full_name = _s(form, "full_name", 120)
    email = _s(form, "email", 190).lower()
    if not user.full_name:
        errors.append("Full name is required.")
    if not is_valid_email(email):
        errors.append("A valid email is required.")
    elif User.query.filter(User.email == email, User.id != (user.id or 0)).first():
        errors.append("That email is already used by another account.")
    user.email = email
    password = form.get("password", "")
    if password:
        if len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        else:
            user.set_password(password)
    elif require_password:
        errors.append("Password is required.")
    return errors, password
