from datetime import timedelta

import click
from flask import current_app

from .extensions import db
from .models import Branch, Brand, Campaign, Prize, User, utcnow
from .services import sync_fallback_prize


def register_cli(app):
    @app.cli.command("init-db")
    def init_db():
        """Create all tables."""
        db.create_all()
        click.echo("Database tables created.")

    @app.cli.command("create-superadmin")
    @click.option("--email", default=None)
    @click.option("--password", default=None)
    @click.option("--name", default="Group Super Admin")
    def create_superadmin(email, password, name):
        """Create (or reset) the group superadmin account."""
        email = (email or current_app.config["SUPERADMIN_EMAIL"]).lower()
        password = password or current_app.config["SUPERADMIN_PASSWORD"]
        user = User.query.filter_by(email=email).first()
        if user is None:
            user = User(email=email, full_name=name, role=User.ROLE_SUPERADMIN)
            db.session.add(user)
        user.role = User.ROLE_SUPERADMIN
        user.set_password(password)
        user.is_active_flag = True
        db.session.commit()
        click.echo(f"Superadmin ready: {email}")

    @app.cli.command("seed-demo")
    def seed_demo():
        """Create a demo sub-brand with branches, staff and prizes."""
        if Brand.query.filter_by(slug="oak-grill").first():
            click.echo("Demo brand already exists.")
            return
        brand = Brand(slug="oak-grill", name="Oak Grill", name_ar="أوك جريل",
                      tagline="Fire-kissed flavours since 2012", tagline_ar="نكهات على الجمر منذ 2012",
                      description="Steakhouse, grills and signature desserts.",
                      primary_color="#1F6F43", secondary_color="#0E2A1B", background_color="#F6F1E7")
        db.session.add(brand)
        campaign = Campaign(brand=brand, name="Winter Scratch & Win", name_ar="اكشط واربح الشتوي",
                            min_spend=150, currency="SAR", voucher_percent=10, claim_expiry_days=30,
                            starts_at=utcnow() - timedelta(days=1), ends_at=utcnow() + timedelta(days=60),
                            terms_en="One gift per customer. Valid on dine-in bills only. Prizes are non-transferable.",
                            terms_ar="هدية واحدة لكل عميل. صالح لفواتير الطعام داخل المطعم فقط. الجوائز غير قابلة للتحويل.")
        db.session.add(campaign)
        b1 = Branch(brand=brand, name="Olaya", name_ar="العليا", code="olaya")
        b2 = Branch(brand=brand, name="Corniche", name_ar="الكورنيش", code="corniche")
        db.session.add_all([b1, b2])
        for name, name_ar, qty in [("Free Dessert", "حلى مجاني", 200),
                                   ("Free Mocktail", "موكتيل مجاني", 150),
                                   ("Dinner for Two", "عشاء لشخصين", 10)]:
            db.session.add(Prize(campaign=campaign, name=name, name_ar=name_ar, quantity=qty))
        db.session.flush()
        sync_fallback_prize(campaign)
        admin = User(email="admin@oakgrill.test", full_name="Oak Grill Admin", role=User.ROLE_BRAND_ADMIN, brand=brand)
        admin.set_password("OakAdmin!2026")
        staff = User(email="olaya@oakgrill.test", full_name="Olaya Staff", role=User.ROLE_STAFF, brand=brand, branch=b1)
        staff.set_password("OakStaff!2026")
        db.session.add_all([admin, staff])
        db.session.commit()
        click.echo("Demo brand 'Oak Grill' created.\n"
                   "  Brand admin: admin@oakgrill.test / OakAdmin!2026\n"
                   "  Branch staff: olaya@oakgrill.test / OakStaff!2026\n"
                   "  Brand login: /b/oak-grill/login   Customer page: /p/oak-grill/olaya")
