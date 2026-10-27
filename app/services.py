"""Business rules: registration uniqueness, prize allocation, redemption."""
import secrets
from datetime import timedelta

from sqlalchemy import or_, update

from .extensions import db
from .models import Award, Participant, Prize, Setting, utcnow
from .utils.codes import qr_token, random_code

_rng = secrets.SystemRandom()


# --------------------------------------------------------------------------- uniqueness
def conflicting_participants(campaign, email, mobile):
    """Participants that share the email or mobile within the configured uniqueness scope."""
    scope = Setting.get("uniqueness_scope")
    q = Participant.query.filter(or_(Participant.email == email, Participant.mobile == mobile))
    if scope == "campaign":
        q = q.filter(Participant.campaign_id == campaign.id)
    elif scope == "brand":
        q = q.filter(Participant.brand_id == campaign.brand_id)
    return q.all()


# --------------------------------------------------------------------------- fallback voucher
def fallback_names(percent):
    return f"{percent}% Discount Voucher", f"قسيمة خصم {percent}٪"


def sync_fallback_prize(campaign):
    """Keep the campaign's fallback voucher prize in line with its voucher percentage."""
    fb = campaign.fallback_prize
    if not campaign.fallback_enabled:
        if fb:
            fb.is_active = False
        return fb
    en, ar = fallback_names(campaign.voucher_percent)
    if fb is None:
        fb = Prize(campaign=campaign, is_fallback=True, quantity=0)
        db.session.add(fb)
    fb.name, fb.name_ar = en, ar
    fb.description = "Awarded when other prizes are out of stock"
    fb.description_ar = "تُمنح عند نفاد الجوائز الأخرى"
    fb.is_active = True
    return fb


# --------------------------------------------------------------------------- allocation
def _eligible(prize, branch_id):
    return (prize.is_active and not prize.is_fallback and
            (prize.branch_id is None or prize.branch_id == branch_id))


def prizes_available(campaign, branch_id=None):
    if campaign.fallback_enabled and campaign.fallback_prize and campaign.fallback_prize.is_active:
        return True
    return any(_eligible(p, branch_id) and p.remaining for p in campaign.prizes)


def _claim(prize):
    """Atomically take one unit of stock. Returns True on success (safe under concurrency)."""
    stmt = update(Prize).where(Prize.id == prize.id)
    if not prize.is_fallback:
        stmt = stmt.where(Prize.awarded_count < Prize.quantity)
    res = db.session.execute(stmt.values(awarded_count=Prize.awarded_count + 1))
    return res.rowcount == 1


def draw_prize(pool):
    """Shuffle every remaining unit of stock and pick one, so each unit has the same chance.

    Same result as laying out one ticket per unit and drawing a ticket blind, without
    building a list as long as the total stock.
    """
    remaining = [p.remaining for p in pool]
    ticket = _rng.randrange(sum(remaining))
    for prize, count in zip(pool, remaining):
        if ticket < count:
            return prize
        ticket -= count


def allocate_prize(participant):
    """Random draw across the remaining stock, falling back to the voucher. Returns Award or None."""
    if participant.award:
        return participant.award
    campaign = participant.campaign
    pool = [p for p in campaign.prizes if _eligible(p, participant.branch_id) and p.remaining]
    chosen = None
    while pool:
        pick = draw_prize(pool)
        if _claim(pick):
            chosen = pick
            break
        pool.remove(pick)   # another guest took the last unit a moment ago

    if chosen is None:
        fb = campaign.fallback_prize
        if campaign.fallback_enabled and fb and fb.is_active and _claim(fb):
            chosen = fb
    if chosen is None:
        return None

    award = Award(
        participant=participant,
        prize_id=chosen.id,
        brand_id=participant.brand_id,
        campaign_id=participant.campaign_id,
        branch_id=participant.branch_id,
        prize_name=chosen.name,
        prize_name_ar=chosen.name_ar,
        is_fallback=chosen.is_fallback,
        claim_code=_unique_claim_code(),
        qr_token=qr_token(),
        expires_at=utcnow() + timedelta(days=campaign.claim_expiry_days or 30),
    )
    db.session.add(award)
    return award


def _unique_claim_code():
    from flask import current_app
    length = current_app.config["CLAIM_CODE_LENGTH"]
    while True:
        code = random_code(length)
        if not Award.query.filter_by(claim_code=code).first():
            return code


# --------------------------------------------------------------------------- redemption
class RedemptionError(Exception):
    pass


def _unique_redemption_ref():
    """Receipt reference such as R261027-7KQ4M2: redemption date plus random characters."""
    prefix = "R" + utcnow().strftime("%y%m%d") + "-"
    while True:
        ref = prefix + random_code(6)
        if not Award.query.filter_by(redemption_ref=ref).first():
            return ref


def redeem_award(award, user, branch_id=None):
    if award.redeemed_at:
        raise RedemptionError("This prize has already been redeemed.")
    if award.status == "expired":
        raise RedemptionError("This prize has expired and can no longer be redeemed.")
    # Conditional UPDATE so two devices scanning the same QR can't both redeem it.
    res = db.session.execute(
        update(Award).where(Award.id == award.id, Award.redeemed_at.is_(None)).values(
            redeemed_at=utcnow(),
            redeemed_by_id=user.id,
            redeemed_branch_id=branch_id or user.branch_id or award.branch_id,
            redemption_ref=_unique_redemption_ref(),
        ).execution_options(synchronize_session=False))
    if res.rowcount != 1:
        raise RedemptionError("This prize has already been redeemed.")
    db.session.refresh(award)
    return award
