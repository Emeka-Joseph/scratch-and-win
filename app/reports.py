"""Shared reporting queries for the superadmin (all brands) and brand dashboards (one brand)."""
from datetime import timedelta

from sqlalchemy import func

from .extensions import db
from .models import AuditLog, Award, Branch, Brand, Participant, utcnow
from .utils.timefmt import fmt_dt, local_day_bounds_utc, to_local


def _scoped(q, model, brand_id=None, branch_id=None):
    if brand_id:
        q = q.filter(model.brand_id == brand_id)
    if branch_id:
        q = q.filter(model.branch_id == branch_id)
    return q


def kpis(brand_id=None, branch_id=None):
    p = _scoped(Participant.query, Participant, brand_id, branch_id)
    a = _scoped(Award.query, Award, brand_id, branch_id)
    registrations = p.count()
    verified = p.filter(Participant.verified_at.isnot(None)).count()
    awarded = a.count()
    redeemed = a.filter(Award.redeemed_at.isnot(None)).count()
    expired = a.filter(Award.redeemed_at.is_(None), Award.expires_at < utcnow()).count()
    start, end = local_day_bounds_utc()
    today_reg = p.filter(Participant.created_at >= start, Participant.created_at < end).count()
    today_red = _scoped(Award.query, Award, brand_id).filter(Award.redeemed_at >= start, Award.redeemed_at < end)
    if branch_id:
        today_red = today_red.filter(Award.redeemed_branch_id == branch_id)
    return {
        "registrations": registrations,
        "verified": verified,
        "verification_rate": round(verified * 100 / registrations, 1) if registrations else 0,
        "awarded": awarded,
        "redeemed": redeemed,
        "pending": awarded - redeemed - expired,
        "expired": expired,
        "redemption_rate": round(redeemed * 100 / awarded, 1) if awarded else 0,
        "today_registrations": today_reg,
        "today_redemptions": today_red.count(),
    }


def daily_series(days=14, brand_id=None, branch_id=None):
    """Registrations / wins / redemptions per local day, oldest first."""
    since = utcnow() - timedelta(days=days + 1)
    buckets = {}
    for i in range(days - 1, -1, -1):
        start, _ = local_day_bounds_utc(i)
        buckets[to_local(start).strftime("%Y-%m-%d")] = {"registrations": 0, "awards": 0, "redemptions": 0}

    def add(rows, key):
        for (ts,) in rows:
            day = to_local(ts).strftime("%Y-%m-%d")
            if day in buckets:
                buckets[day][key] += 1

    add(_scoped(db.session.query(Participant.created_at), Participant, brand_id, branch_id)
        .filter(Participant.created_at >= since).all(), "registrations")
    add(_scoped(db.session.query(Award.created_at), Award, brand_id, branch_id)
        .filter(Award.created_at >= since).all(), "awards")
    red = _scoped(db.session.query(Award.redeemed_at), Award, brand_id).filter(Award.redeemed_at >= since)
    if branch_id:
        red = red.filter(Award.redeemed_branch_id == branch_id)
    add(red.all(), "redemptions")
    labels = list(buckets)
    return {
        "labels": [to_local_label(d) for d in labels],
        "registrations": [buckets[d]["registrations"] for d in labels],
        "awards": [buckets[d]["awards"] for d in labels],
        "redemptions": [buckets[d]["redemptions"] for d in labels],
    }


def to_local_label(day):
    y, m, d = day.split("-")
    return f"{int(d)} {['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][int(m) - 1]}"


def brand_leaderboard():
    rows = []
    for brand in Brand.query.order_by(Brand.name).all():
        k = kpis(brand_id=brand.id)
        rows.append({"brand": brand, **k})
    return rows


def branch_breakdown(brand_id):
    rows = []
    for br in Branch.query.filter_by(brand_id=brand_id).order_by(Branch.name).all():
        regs = Participant.query.filter_by(branch_id=br.id).count()
        wins = Award.query.filter_by(branch_id=br.id).count()
        red = Award.query.filter(Award.redeemed_branch_id == br.id).count()
        rows.append({"branch": br, "registrations": regs, "awards": wins, "redemptions": red})
    return rows


def prize_breakdown(brand_id=None):
    q = db.session.query(Award.prize_name, func.count(Award.id), func.count(Award.redeemed_at))
    if brand_id:
        q = q.filter(Award.brand_id == brand_id)
    return [{"prize": n, "awarded": c, "redeemed": r}
            for n, c, r in q.group_by(Award.prize_name).order_by(func.count(Award.id).desc()).all()]


def recent_activity(limit=12, brand_id=None):
    q = AuditLog.query.order_by(AuditLog.created_at.desc())
    if brand_id:
        q = q.filter(AuditLog.brand_id == brand_id)
    return q.limit(limit).all()


# --------------------------------------------------------------------------- participant filters / exports
def participant_query(args, brand_id=None):
    q = Participant.query.outerjoin(Award, Award.participant_id == Participant.id)
    if brand_id:
        q = q.filter(Participant.brand_id == brand_id)
    elif args.get("brand"):
        q = q.filter(Participant.brand_id == int(args["brand"]))
    if args.get("branch"):
        q = q.filter(Participant.branch_id == int(args["branch"]))
    status = args.get("status")
    now = utcnow()
    if status == "unverified":
        q = q.filter(Participant.verified_at.is_(None))
    elif status == "redeemed":
        q = q.filter(Award.redeemed_at.isnot(None))
    elif status == "pending":
        q = q.filter(Award.id.isnot(None), Award.redeemed_at.is_(None), Award.expires_at >= now)
    elif status == "expired":
        q = q.filter(Award.redeemed_at.is_(None), Award.expires_at < now)
    if args.get("q"):
        like = f"%{args['q'].strip()}%"
        q = q.filter(db.or_(Participant.full_name.ilike(like), Participant.email.ilike(like),
                            Participant.mobile.ilike(like), Award.claim_code.ilike(like)))
    if args.get("date_from"):
        q = q.filter(Participant.created_at >= args["date_from"])
    if args.get("date_to"):
        q = q.filter(Participant.created_at < f"{args['date_to']} 23:59:59")
    return q.order_by(Participant.created_at.desc())


PARTICIPANT_HEADERS = ["ID", "Registered", "Brand", "Campaign", "Branch", "Name", "Email", "Mobile", "Language",
                       "Marketing consent", "Verified", "Prize", "Claim code", "Status", "Prize expires",
                       "Redeemed at", "Redemption ref", "Redeemed by", "Redeemed branch", "IP address"]


def participant_rows(participants):
    for p in participants:
        a = p.award
        yield [
            p.id, fmt_dt(p.created_at), p.brand.name if p.brand else "", p.campaign.name if p.campaign else "",
            p.branch.name if p.branch else "", p.full_name, p.email, p.mobile, p.language.upper(),
            "Yes" if p.marketing_consent else "No", fmt_dt(p.verified_at) if p.verified_at else "No",
            a.prize_name if a else "", a.claim_code if a else "", p.status.replace("_", " ").title(),
            fmt_dt(a.expires_at) if a else "", fmt_dt(a.redeemed_at) if a and a.redeemed_at else "",
            a.redemption_ref or "" if a else "",
            a.redeemed_by.email if a and a.redeemed_by else "",
            a.redeemed_branch.name if a and a.redeemed_branch else "", p.ip_address,
        ]


AUDIT_HEADERS = ["Time", "Actor", "Role", "Brand", "Action", "Target", "Target ID", "Details", "IP address"]


def audit_rows(logs):
    for log in logs:
        yield [fmt_dt(log.created_at, "%Y-%m-%d %H:%M:%S"), log.actor_label, log.actor_role,
               log.brand.name if log.brand else "", log.action, log.target_type, log.target_id,
               log.details, log.ip_address]


BRAND_HEADERS = ["Brand", "Status", "Registrations", "Verified", "Verification %", "Prizes won",
                 "Redeemed", "Pending", "Expired", "Redemption %"]


def brand_rows():
    for r in brand_leaderboard():
        yield [r["brand"].name, "Active" if r["brand"].is_active else "Disabled", r["registrations"], r["verified"],
               r["verification_rate"], r["awarded"], r["redeemed"], r["pending"], r["expired"], r["redemption_rate"]]
