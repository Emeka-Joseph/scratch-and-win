"""End-to-end tests: superadmin -> brand -> customer -> staff redemption."""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Award, Brand, Participant, Prize, Setting, User  # noqa: E402
from config import TestConfig  # noqa: E402


@pytest.fixture()
def app():
    app = create_app(TestConfig)

    @app.before_request
    def _isolate_clients():
        # The fixture keeps one app context open for DB assertions, so flask.g would otherwise
        # carry the logged-in user from one test client's request into another's.
        from flask import g
        g.pop("_login_user", None)

    with app.app_context():
        db.create_all()
        sa = User(email="super@test.com", full_name="Group Admin", role=User.ROLE_SUPERADMIN)
        sa.set_password("SuperPass1")
        db.session.add(sa)
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


def outbox(app):
    return app.extensions.setdefault("outbox", [])


def body_text(msg):
    return msg.get_body(preferencelist=("plain",)).get_content()


def login(client, email, password, path="/login"):
    return client.post(path, data={"email": email, "password": password}, follow_redirects=False)


def create_brand(app, client, **overrides):
    data = {
        "name": "Oak Grill", "name_ar": "أوك جريل", "slug": "oak-grill", "tagline": "Fire-kissed",
        "primary_color": "#1F6F43", "secondary_color": "#0E2A1B", "background_color": "#F6F1E7",
        "campaign_name": "Winter Win", "min_spend": "150", "currency": "SAR", "voucher_percent": "15",
        "claim_expiry_days": "30", "fallback_enabled": "1", "terms_en": "Terms", "terms_ar": "شروط",
        "prize_name": ["Free Dessert", "Dinner for Two"], "prize_name_ar": ["حلى", "عشاء"],
        "prize_qty": ["1", "1"],
        "admin_name": "Oak Admin", "admin_email": "admin@oak.test", "admin_password": "OakAdmin123",
        "branch_name": "Olaya", "branch_code": "olaya", "send_credentials": "1",
    }
    data.update(overrides)
    return client.post("/admin/brands/new", data=data)


def register(client, name="Sara Ali", email="sara@example.com", mobile="+966500000001", lang="en"):
    client.get(f"/p/oak-grill/olaya?lang={lang}")
    return client.post("/p/oak-grill/olaya", data={"full_name": name, "email": email, "mobile": mobile,
                                                   "accept_terms": "1", "marketing_consent": "1"})


def last_code(app):
    return re.search(r"^\s+([A-Z0-9]{7})\s*$", body_text(outbox(app)[-1]), re.M).group(1)


def test_full_flow(app):
    sa = app.test_client()
    assert login(sa, "super@test.com", "SuperPass1").status_code == 302
    for url in ["/admin/", "/admin/brands", "/admin/brands/new", "/admin/participants", "/admin/audit", "/admin/settings"]:
        assert sa.get(url).status_code == 200, url

    r = create_brand(app, sa)
    assert r.status_code == 302, r.data[:500]
    brand = Brand.query.filter_by(slug="oak-grill").one()
    assert brand.current_campaign.fallback_prize.name == "15% Discount Voucher"
    assert len(brand.current_campaign.prizes) == 3
    assert outbox(app)[-1]["To"] == "admin@oak.test"   # credentials email
    assert b"OakAdmin123" in sa.get(f"/admin/brands/{brand.id}").data  # shown once
    assert sa.get(f"/admin/brands/{brand.id}/edit").status_code == 200

    # superadmin acting as the brand
    assert sa.get(f"/admin/brands/{brand.id}/manage").status_code == 302
    for url in ["/brand/", "/brand/campaign", "/brand/prizes", "/brand/branches", "/brand/staff", "/brand/qr",
                f"/brand/qr/{brand.branches[0].id}.png", f"/brand/qr/{brand.branches[0].id}/poster",
                "/brand/participants", "/brand/redeem"]:
        assert sa.get(url).status_code == 200, url

    # ---- customer
    cust = app.test_client()
    r = cust.get("/p/oak-grill/olaya")
    assert r.status_code == 200 and b"Choose your language" in r.data
    r = register(cust, lang="ar")
    assert r.status_code == 302 and r.headers["Location"].endswith("/p/oak-grill/verify")
    code = last_code(app)
    page = cust.get("/p/oak-grill/verify")
    assert 'dir="rtl"' in page.get_data(as_text=True)

    r = cust.post("/p/oak-grill/verify", data={"code": "WRONG12"})
    assert "المحاولات المتبقية".encode() in r.data
    r = cust.post("/p/oak-grill/verify", data={"code": code.lower()})
    assert r.status_code == 302 and r.headers["Location"].endswith("/scratch")
    p = Participant.query.filter_by(email="sara@example.com").one()
    assert p.verified_at and p.award and p.award.status == "allocated"
    assert len(p.award.claim_code) == 8

    assert cust.get("/p/oak-grill/scratch").status_code == 200
    assert cust.post("/p/oak-grill/reveal").get_json()["ok"]
    assert outbox(app)[-1]["To"] == "sara@example.com"   # prize confirmation
    assert db.session.get(Award, p.award.id).revealed_at is not None
    assert cust.get(f"/p/oak-grill/prize/{p.award.qr_token}").status_code == 200
    assert cust.get(f"/qr/award/{p.award.qr_token}.png").mimetype == "image/png"

    # ---- one customer, one gift
    other = app.test_client()
    r = register(other, name="Sara Again", email="SARA@example.com", mobile="+966599999999")
    assert b"already taken part" in r.data
    r = register(other, name="Same Phone", email="new@example.com", mobile="00966500000001")
    assert b"already taken part" in r.data

    # ---- brand creates staff; staff redeems
    r = sa.post("/brand/staff", data={"full_name": "Olaya Staff", "email": "staff@oak.test", "role": "staff",
                                      "branch_id": brand.branches[0].id, "password": "StaffPass1"})
    assert r.status_code == 302
    staff = app.test_client()
    r = login(staff, "staff@oak.test", "StaffPass1", "/b/oak-grill/login")
    assert r.headers["Location"].endswith("/account/password")
    r = staff.post("/account/password", data={"current_password": "StaffPass1", "new_password": "StaffPass2",
                                              "confirm_password": "StaffPass2"})
    assert r.headers["Location"].endswith("/brand/redeem")
    assert staff.get("/brand/").status_code == 302          # staff go straight to redeem
    assert staff.get("/brand/prizes").status_code == 403     # and can't manage setup
    award = db.session.get(Award, p.award.id)
    r = staff.get(f"/brand/redeem?code={award.claim_code.lower()}")
    assert r.headers["Location"].endswith(f"/brand/redeem/{award.qr_token}")
    assert b"Won &amp; delivered" in staff.get(f"/brand/redeem/{award.qr_token}").data
    staff.post(f"/brand/redeem/{award.qr_token}")
    db.session.expire_all()
    award = db.session.get(Award, p.award.id)
    assert award.status == "redeemed" and award.redeemed_by.email == "staff@oak.test"
    assert re.fullmatch(r"R\d{6}-[A-Z0-9]{6}", award.redemption_ref)
    assert award.redemption_ref.encode() in staff.get(f"/brand/redeem/{award.qr_token}").data
    r = staff.post(f"/brand/redeem/{award.qr_token}", follow_redirects=True)
    assert b"already been redeemed" in r.data

    # ---- customer's prize page now shows it as redeemed (customer chose Arabic)
    assert "تم الاستلام".encode() in cust.get(f"/p/oak-grill/prize/{award.qr_token}").data

    # ---- superadmin reporting & exports
    assert b"Sara Ali" in sa.get("/admin/participants?status=redeemed").data
    for ds in ["participants", "redemptions", "brands", "audit"]:
        for fmt in ["csv", "xlsx"]:
            r = sa.get(f"/admin/export/{ds}.{fmt}")
            assert r.status_code == 200 and r.data, (ds, fmt)
    csv = sa.get("/admin/export/redemptions.csv").get_data(as_text=True)
    assert "Sara Ali" in csv and award.claim_code in csv and award.redemption_ref in csv
    assert sa.get("/admin/audit?action=prize_redeemed").status_code == 200


def test_stock_runs_out_then_fallback(app):
    sa = app.test_client()
    login(sa, "super@test.com", "SuperPass1")
    create_brand(app, sa)
    won = []
    for i in range(4):
        c = app.test_client()
        register(c, name=f"Guest {i}", email=f"g{i}@ex.com", mobile=f"+96650000010{i}")
        c.post("/p/oak-grill/verify", data={"code": last_code(app)})
        won.append(Participant.query.filter_by(email=f"g{i}@ex.com").one().award.prize_name)
    # two real prizes with quantity 1 each, then the voucher
    assert sorted(won[:2]) == ["Dinner for Two", "Free Dessert"]
    assert won[2:] == ["15% Discount Voucher"] * 2
    assert all(p.awarded_count <= p.quantity for p in Prize.query.filter_by(is_fallback=False))


def test_sold_out_without_fallback(app):
    sa = app.test_client()
    login(sa, "super@test.com", "SuperPass1")
    create_brand(app, sa, fallback_enabled="", prize_name=["Only"], prize_name_ar=[""], prize_qty=["0"])
    r = app.test_client().get("/p/oak-grill/olaya?lang=en", follow_redirects=True)
    assert b"All gifts have been claimed" in r.data


def test_group_wide_uniqueness(app):
    sa = app.test_client()
    login(sa, "super@test.com", "SuperPass1")
    create_brand(app, sa)
    create_brand(app, sa, name="Bay Cafe", slug="bay-cafe", admin_email="admin@bay.test")
    Setting.set("uniqueness_scope", "group")
    db.session.commit()
    c = app.test_client()
    register(c)
    c.post("/p/oak-grill/verify", data={"code": last_code(app)})
    c2 = app.test_client()
    c2.get("/p/bay-cafe/olaya?lang=en")
    r = c2.post("/p/bay-cafe/olaya", data={"full_name": "Sara", "email": "sara@example.com",
                                           "mobile": "+966511111111", "accept_terms": "1"})
    assert b"already taken part" in r.data


def test_brand_isolation(app):
    sa = app.test_client()
    login(sa, "super@test.com", "SuperPass1")
    create_brand(app, sa)
    create_brand(app, sa, name="Bay Cafe", slug="bay-cafe", admin_email="admin@bay.test", admin_password="BayAdmin123")
    c = app.test_client()
    register(c)
    c.post("/p/oak-grill/verify", data={"code": last_code(app)})
    award = Award.query.one()
    bay = app.test_client()
    assert login(bay, "admin@bay.test", "BayAdmin123", "/b/oak-grill/login").status_code == 200  # wrong brand login page
    login(bay, "admin@bay.test", "BayAdmin123", "/b/bay-cafe/login")
    bay.post("/account/password", data={"current_password": "BayAdmin123", "new_password": "BayAdmin456",
                                         "confirm_password": "BayAdmin456"})
    assert bay.get(f"/brand/redeem/{award.qr_token}").status_code == 403
    assert bay.post(f"/brand/redeem/{award.qr_token}").status_code == 403
    assert db.session.get(Award, award.id).redeemed_at is None
    assert bay.get("/admin/").status_code == 403


def test_terms_required_and_validation(app):
    sa = app.test_client()
    login(sa, "super@test.com", "SuperPass1")
    create_brand(app, sa)
    c = app.test_client()
    c.get("/p/oak-grill/olaya?lang=en")
    r = c.post("/p/oak-grill/olaya", data={"full_name": "A", "email": "bad", "mobile": "12"})
    text = r.get_data(as_text=True)
    assert "must accept the Terms" in text and "valid email" in text and "valid mobile" in text
    assert Participant.query.count() == 0


def test_draw_is_proportional_to_remaining_stock():
    from collections import Counter
    from app.services import draw_prize
    big = Prize(name="Big", quantity=900, awarded_count=0)
    small = Prize(name="Small", quantity=150, awarded_count=50)    # 100 left
    gone = Prize(name="Gone", quantity=5, awarded_count=5)         # 0 left: never drawn
    counts = Counter(draw_prize([big, small, gone]).name for _ in range(20000))
    assert counts["Gone"] == 0
    assert 0.87 < counts["Big"] / 20000 < 0.93


def test_prize_validity_follows_campaign_dates(app):
    from datetime import datetime, timedelta
    from app.forms import campaign_validity_days
    from app.models import Campaign
    sa = app.test_client()
    login(sa, "super@test.com", "SuperPass1")
    start, fmt = datetime.now().replace(second=0, microsecond=0) - timedelta(days=1), "%Y-%m-%dT%H:%M"
    create_brand(app, sa, claim_expiry_days="999",   # submitted value is ignored
                 starts_at=start.strftime(fmt), ends_at=(start + timedelta(days=45)).strftime(fmt))
    assert Campaign.query.one().claim_expiry_days == 45
    assert campaign_validity_days(start, start + timedelta(days=10, hours=1)) == 11   # part days round up
    assert campaign_validity_days(start, None) == 30                                  # open-ended


class _FakeSMTP:
    sent, fail = [], None

    def __init__(self, *args, **kwargs):
        if _FakeSMTP.fail:
            raise _FakeSMTP.fail

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def login(self, *args):
        pass

    def send_message(self, msg):
        _FakeSMTP.sent.append(msg)


def test_email_sent_in_request_and_failures_reported(app, monkeypatch):
    import smtplib
    from app.models import AuditLog
    sa = app.test_client()
    login(sa, "super@test.com", "SuperPass1")
    create_brand(app, sa)
    app.config.update(MAIL_SUPPRESS_SEND=False, MAIL_SERVER="smtp.test", MAIL_USE_SSL=False, MAIL_USE_TLS=False)
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)

    # delivered before the response returns (no background thread needed)
    _FakeSMTP.sent, _FakeSMTP.fail = [], None
    r = register(app.test_client())
    assert "mail_failed" not in r.headers["Location"]
    msg = _FakeSMTP.sent[0]
    assert len(_FakeSMTP.sent) == 1 and msg["To"] == "sara@example.com"
    assert msg["Date"] and msg["Message-ID"].endswith(">") and msg["Auto-Submitted"] == "auto-generated"

    # SMTP rejects the login: the customer is told, and the error lands in the audit log
    _FakeSMTP.fail = smtplib.SMTPAuthenticationError(535, b"Incorrect authentication data")
    c = app.test_client()
    r = register(c, name="Omar", email="omar@example.com", mobile="+966500000002")
    assert "mail_failed=1" in r.headers["Location"]
    assert b"couldn&#39;t send the email" in c.get(r.headers["Location"]).data
    log = AuditLog.query.filter_by(action="email_failed").one()
    assert "omar@example.com" in log.details and "Incorrect authentication data" in log.details

    # the superadmin's test email shows the real SMTP error
    r = sa.post("/admin/settings/test-email", follow_redirects=True)
    assert b"Incorrect authentication data" in r.data
    _FakeSMTP.fail = None


def test_brand_logo_is_embedded_in_emails(app, tmp_path):
    from PIL import Image
    sa = app.test_client()
    login(sa, "super@test.com", "SuperPass1")
    create_brand(app, sa)
    (tmp_path / "uploads" / "logos").mkdir(parents=True)
    Image.new("RGB", (300, 120), "#1F6F43").save(tmp_path / "uploads" / "logos" / "oak.webp")
    brand = Brand.query.filter_by(slug="oak-grill").one()
    brand.logo_path = "uploads/logos/oak.webp"
    db.session.commit()
    app.static_folder = str(tmp_path)

    register(app.test_client())
    msg = outbox(app)[-1]
    html = msg.get_body(("html",)).get_content()
    assert 'src="cid:brandlogo"' in html
    logo = next(part for part in msg.walk() if part["Content-ID"] == "<brandlogo>")
    with Image.open(__import__("io").BytesIO(logo.get_content())) as img:
        assert img.format == "PNG" and img.size == (160, 160)   # converted from WEBP, padded square


def test_renaming_a_prize_corrects_prizes_already_won(app):
    sa = app.test_client()
    login(sa, "super@test.com", "SuperPass1")
    create_brand(app, sa, prize_name=["Mug"], prize_name_ar=["وجبة لشخصين"], prize_qty=["5"])  # wrong Arabic
    cust = app.test_client()
    register(cust)
    cust.post("/p/oak-grill/verify", data={"code": last_code(app)})
    award = Participant.query.one().award
    assert award.prize_name_ar == "وجبة لشخصين"

    brand = Brand.query.one()
    sa.get(f"/admin/brands/{brand.id}/manage")
    prize = db.session.get(Prize, award.prize_id)
    sa.post(f"/brand/prizes/{prize.id}", data={"action": "save", "name": "Mug", "name_ar": "كوب",
                                                "quantity": "5", "is_active": "1"})
    db.session.expire_all()
    assert db.session.get(Award, award.id).prize_name_ar == "كوب"
    assert "كوب".encode() in sa.get(f"/brand/redeem/{award.qr_token}").data


def test_new_brand_form_has_no_prefilled_prize_names(app):
    sa = app.test_client()
    login(sa, "super@test.com", "SuperPass1")
    page = sa.get("/admin/brands/new").get_data(as_text=True)
    assert "وجبة لشخصين" not in page and 'value="Meal for Two"' not in page
