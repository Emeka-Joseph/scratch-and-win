"""One-off server setup: create the tables and the group superadmin.

Safe to run more than once. Run it from cPanel's "Setup Python App" page ("Execute python script":
deploy/bootstrap.py) or over SSH inside the app's virtualenv:

    python deploy/bootstrap.py                  # create tables + superadmin from .env
    python deploy/bootstrap.py --reset-password # also reset the superadmin password to SUPERADMIN_PASSWORD
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sqlalchemy import inspect, text  # noqa: E402

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import User  # noqa: E402


def main():
    reset = "--reset-password" in sys.argv
    app = create_app()
    with app.app_context():
        url = db.engine.url
        if not app.config["IS_PRODUCTION"]:
            print("WARNING: FLASK_ENV is not 'production' -- this server is using a development .env, "
                  "not the live settings. Replace .env with your production file before going live.")
        print(f"Database: {url.get_backend_name()} {url.host or ''}/{url.database}")
        db.session.execute(text("SELECT 1"))
        before = set(inspect(db.engine).get_table_names())
        db.create_all()
        created = sorted(set(inspect(db.engine).get_table_names()) - before)
        print("Tables created: " + (", ".join(created) if created else "none (already up to date)"))

        email = app.config["SUPERADMIN_EMAIL"].lower()
        password = app.config["SUPERADMIN_PASSWORD"] or ""
        if len(password) < 10 or (app.config["IS_PRODUCTION"] and password == "ChangeMe!2026"):
            sys.exit("Set SUPERADMIN_PASSWORD in .env to a strong password (10+ characters) first.")
        user = User.query.filter_by(email=email).first()
        if user is None:
            user = User(email=email, full_name="Group Super Admin", role=User.ROLE_SUPERADMIN)
            user.set_password(password)
            db.session.add(user)
            print(f"Superadmin created: {email}")
        elif reset:
            user.set_password(password)
            user.is_active_flag = True
            print(f"Superadmin password reset: {email}")
        else:
            print(f"Superadmin already exists: {email} (password unchanged)")
        db.session.commit()

        uploads = app.config["UPLOAD_FOLDER"]
        uploads.mkdir(parents=True, exist_ok=True)
        print(f"Uploads folder: {uploads} ({'writable' if os.access(uploads, os.W_OK) else 'NOT WRITABLE'})")
        print("Done. Sign in at " + app.config["PUBLIC_BASE_URL"] + "/login")


if __name__ == "__main__":
    main()
