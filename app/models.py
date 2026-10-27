"""Database models.

Hierarchy:  Group (superadmin) -> Brand -> Branch -> Staff
            Brand -> Campaign -> Prize
            Campaign -> Participant -> Award (one per participant)
"""
import json
from datetime import datetime, timezone

from flask_login import UserMixin
from sqlalchemy import UniqueConstraint, Index
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)


# --------------------------------------------------------------------------- users
class User(UserMixin, TimestampMixin, db.Model):
    __tablename__ = "users"

    ROLE_SUPERADMIN = "superadmin"
    ROLE_BRAND_ADMIN = "brand_admin"
    ROLE_STAFF = "staff"
    ROLES = (ROLE_SUPERADMIN, ROLE_BRAND_ADMIN, ROLE_STAFF)

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(190), unique=True, nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, index=True)
    brand_id = db.Column(db.Integer, db.ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id", ondelete="SET NULL"), index=True)
    is_active_flag = db.Column("is_active", db.Boolean, default=True, nullable=False)
    must_change_password = db.Column(db.Boolean, default=False, nullable=False)
    last_login_at = db.Column(db.DateTime)

    brand = db.relationship("Brand", back_populates="users", foreign_keys=[brand_id])
    branch = db.relationship("Branch", back_populates="staff", foreign_keys=[branch_id])

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)

    @property
    def is_active(self):
        if not self.is_active_flag:
            return False
        if self.brand is not None and not self.brand.is_active:
            return False
        return True

    @property
    def is_superadmin(self):
        return self.role == self.ROLE_SUPERADMIN

    @property
    def is_brand_admin(self):
        return self.role == self.ROLE_BRAND_ADMIN

    @property
    def is_staff(self):
        return self.role == self.ROLE_STAFF

    @property
    def role_label(self):
        return {"superadmin": "Super Admin", "brand_admin": "Brand Admin", "staff": "Branch Staff"}[self.role]


# --------------------------------------------------------------------------- brands
class Brand(TimestampMixin, db.Model):
    __tablename__ = "brands"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(60), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    name_ar = db.Column(db.String(120))
    tagline = db.Column(db.String(200))
    tagline_ar = db.Column(db.String(200))
    description = db.Column(db.Text)          # goods & services offered
    description_ar = db.Column(db.Text)
    logo_path = db.Column(db.String(255))
    primary_color = db.Column(db.String(7), default="#C8102E", nullable=False)
    secondary_color = db.Column(db.String(7), default="#111111", nullable=False)
    background_color = db.Column(db.String(7), default="#FFF8F0", nullable=False)
    contact_email = db.Column(db.String(190))
    contact_phone = db.Column(db.String(40))
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    users = db.relationship("User", back_populates="brand", foreign_keys="User.brand_id",
                            cascade="all, delete-orphan")
    branches = db.relationship("Branch", back_populates="brand", cascade="all, delete-orphan",
                               order_by="Branch.name")
    campaigns = db.relationship("Campaign", back_populates="brand", cascade="all, delete-orphan",
                                order_by="Campaign.created_at.desc()")

    def localized(self, field, lang):
        if lang == "ar":
            return getattr(self, f"{field}_ar") or getattr(self, field)
        return getattr(self, field)

    @property
    def active_campaign(self):
        now = utcnow()
        for c in self.campaigns:
            if c.is_active and (not c.starts_at or c.starts_at <= now) and (not c.ends_at or c.ends_at >= now):
                return c
        return None

    @property
    def current_campaign(self):
        """Active campaign, or the most recent one for configuration screens."""
        return self.active_campaign or (self.campaigns[0] if self.campaigns else None)

    @property
    def admins(self):
        return [u for u in self.users if u.role == User.ROLE_BRAND_ADMIN]


class Branch(TimestampMixin, db.Model):
    __tablename__ = "branches"
    __table_args__ = (UniqueConstraint("brand_id", "code", name="uq_branch_code"),)

    id = db.Column(db.Integer, primary_key=True)
    brand_id = db.Column(db.Integer, db.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    name_ar = db.Column(db.String(120))
    code = db.Column(db.String(30), nullable=False)
    address = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    brand = db.relationship("Brand", back_populates="branches")
    staff = db.relationship("User", back_populates="branch", foreign_keys="User.branch_id")

    def localized_name(self, lang):
        return (self.name_ar if lang == "ar" and self.name_ar else self.name)


# --------------------------------------------------------------------------- campaigns
class Campaign(TimestampMixin, db.Model):
    __tablename__ = "campaigns"

    id = db.Column(db.Integer, primary_key=True)
    brand_id = db.Column(db.Integer, db.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(150), nullable=False)
    name_ar = db.Column(db.String(150))
    min_spend = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    currency = db.Column(db.String(8), default="SAR", nullable=False)
    voucher_percent = db.Column(db.Integer, default=10, nullable=False)   # fallback prize
    fallback_enabled = db.Column(db.Boolean, default=True, nullable=False)
    claim_expiry_days = db.Column(db.Integer, default=30, nullable=False)
    starts_at = db.Column(db.DateTime)
    ends_at = db.Column(db.DateTime)
    terms_en = db.Column(db.Text)
    terms_ar = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    brand = db.relationship("Brand", back_populates="campaigns")
    prizes = db.relationship("Prize", back_populates="campaign", cascade="all, delete-orphan",
                             order_by="Prize.is_fallback, Prize.id")

    def localized_name(self, lang):
        return (self.name_ar if lang == "ar" and self.name_ar else self.name)

    def terms(self, lang):
        return (self.terms_ar if lang == "ar" and self.terms_ar else self.terms_en) or ""

    @property
    def status(self):
        now = utcnow()
        if not self.is_active:
            return "paused"
        if self.starts_at and self.starts_at > now:
            return "scheduled"
        if self.ends_at and self.ends_at < now:
            return "ended"
        return "live"

    @property
    def fallback_prize(self):
        return next((p for p in self.prizes if p.is_fallback), None)


class Prize(TimestampMixin, db.Model):
    __tablename__ = "prizes"

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id", ondelete="SET NULL"))  # NULL = shared pool
    name = db.Column(db.String(150), nullable=False)
    name_ar = db.Column(db.String(150))
    description = db.Column(db.String(255))
    description_ar = db.Column(db.String(255))
    quantity = db.Column(db.Integer, default=0, nullable=False)
    awarded_count = db.Column(db.Integer, default=0, nullable=False)
    is_fallback = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    campaign = db.relationship("Campaign", back_populates="prizes")
    branch = db.relationship("Branch")

    def localized_name(self, lang):
        return (self.name_ar if lang == "ar" and self.name_ar else self.name)

    @property
    def remaining(self):
        if self.is_fallback:
            return None  # unlimited
        return max(self.quantity - self.awarded_count, 0)


# --------------------------------------------------------------------------- customers
class Participant(TimestampMixin, db.Model):
    __tablename__ = "participants"
    __table_args__ = (
        UniqueConstraint("campaign_id", "email", name="uq_participant_campaign_email"),
        UniqueConstraint("campaign_id", "mobile", name="uq_participant_campaign_mobile"),
        Index("ix_participant_email", "email"),
        Index("ix_participant_mobile", "mobile"),
    )

    id = db.Column(db.Integer, primary_key=True)
    brand_id = db.Column(db.Integer, db.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id", ondelete="SET NULL"), index=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(190), nullable=False)
    mobile = db.Column(db.String(20), nullable=False)
    language = db.Column(db.String(2), default="en", nullable=False)
    accepted_terms = db.Column(db.Boolean, default=False, nullable=False)
    marketing_consent = db.Column(db.Boolean, default=False, nullable=False)

    verify_code_hash = db.Column(db.String(255))
    verify_code_sent_at = db.Column(db.DateTime)
    verify_code_expires_at = db.Column(db.DateTime)
    verify_attempts = db.Column(db.Integer, default=0, nullable=False)
    verify_sends = db.Column(db.Integer, default=0, nullable=False)
    verified_at = db.Column(db.DateTime, index=True)

    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(255))

    brand = db.relationship("Brand")
    campaign = db.relationship("Campaign")
    branch = db.relationship("Branch")
    award = db.relationship("Award", back_populates="participant", uselist=False, cascade="all, delete-orphan")

    @property
    def status(self):
        if self.award:
            return self.award.status
        return "verified" if self.verified_at else "pending_verification"


class Award(TimestampMixin, db.Model):
    __tablename__ = "awards"

    id = db.Column(db.Integer, primary_key=True)
    participant_id = db.Column(db.Integer, db.ForeignKey("participants.id", ondelete="CASCADE"),
                               unique=True, nullable=False)
    prize_id = db.Column(db.Integer, db.ForeignKey("prizes.id", ondelete="SET NULL"))
    brand_id = db.Column(db.Integer, db.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id", ondelete="SET NULL"), index=True)

    prize_name = db.Column(db.String(150), nullable=False)       # snapshot at allocation
    prize_name_ar = db.Column(db.String(150))
    is_fallback = db.Column(db.Boolean, default=False, nullable=False)

    claim_code = db.Column(db.String(16), unique=True, nullable=False)
    qr_token = db.Column(db.String(64), unique=True, nullable=False)

    revealed_at = db.Column(db.DateTime)
    expires_at = db.Column(db.DateTime)
    redeemed_at = db.Column(db.DateTime, index=True)
    redeemed_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    redeemed_branch_id = db.Column(db.Integer, db.ForeignKey("branches.id", ondelete="SET NULL"))
    redemption_ref = db.Column(db.String(20), unique=True)    # auto-generated receipt reference
    confirmation_sent_at = db.Column(db.DateTime)

    participant = db.relationship("Participant", back_populates="award")
    prize = db.relationship("Prize")
    brand = db.relationship("Brand")
    campaign = db.relationship("Campaign")
    branch = db.relationship("Branch", foreign_keys=[branch_id])
    redeemed_by = db.relationship("User")
    redeemed_branch = db.relationship("Branch", foreign_keys=[redeemed_branch_id])

    @property
    def status(self):
        if self.redeemed_at:
            return "redeemed"
        if self.expires_at and self.expires_at < utcnow():
            return "expired"
        if self.revealed_at:
            return "revealed"
        return "allocated"

    def localized_prize(self, lang):
        return (self.prize_name_ar if lang == "ar" and self.prize_name_ar else self.prize_name)


# --------------------------------------------------------------------------- audit / settings
class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    actor_label = db.Column(db.String(190))
    actor_role = db.Column(db.String(20))
    brand_id = db.Column(db.Integer, db.ForeignKey("brands.id", ondelete="SET NULL"), index=True)
    action = db.Column(db.String(60), nullable=False, index=True)
    target_type = db.Column(db.String(40))
    target_id = db.Column(db.Integer)
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(45))

    brand = db.relationship("Brand")

    @property
    def details_dict(self):
        try:
            return json.loads(self.details) if self.details else {}
        except ValueError:
            return {}


class Setting(db.Model):
    __tablename__ = "settings"

    key = db.Column(db.String(60), primary_key=True)
    value = db.Column(db.String(255))

    DEFAULTS = {
        # Scope within which one email / mobile may win only once: campaign | brand | group
        "uniqueness_scope": "campaign",
    }

    @classmethod
    def get(cls, key):
        row = db.session.get(cls, key)
        return row.value if row else cls.DEFAULTS.get(key)

    @classmethod
    def set(cls, key, value):
        row = db.session.get(cls, key)
        if row is None:
            row = cls(key=key)
            db.session.add(row)
        row.value = value
