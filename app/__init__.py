import logging

from flask import Flask, render_template, request
from flask_wtf.csrf import CSRFError

from config import Config
from .extensions import csrf, db, login_manager


def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)
    _check_production_config(app)
    if app.config["TRUST_PROXY"]:
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from .blueprints.auth.routes import bp as auth_bp
    from .blueprints.brand.routes import bp as brand_bp
    from .blueprints.customer.routes import bp as customer_bp
    from .blueprints.superadmin.routes import bp as superadmin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(superadmin_bp, url_prefix="/admin")
    app.register_blueprint(brand_bp, url_prefix="/brand")
    app.register_blueprint(customer_bp)

    _register_template_helpers(app)
    _register_error_handlers(app)

    from .cli import register_cli
    register_cli(app)
    return app


def _check_production_config(app):
    """Refuse to start a live server with development defaults."""
    if not app.config.get("IS_PRODUCTION"):
        return
    problems = []
    if len(app.config["SECRET_KEY"]) < 32 or app.config["SECRET_KEY"].startswith(("insecure", "change-me", "dev-")):
        problems.append("SECRET_KEY must be a long random value")
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        problems.append("DATABASE_URL must point at MySQL")
    if not app.config["PUBLIC_BASE_URL"].startswith("https://"):
        problems.append("PUBLIC_BASE_URL must be your https:// domain")
    if problems:
        raise RuntimeError("Production configuration error: " + "; ".join(problems) + " (see .env)")


def _register_template_helpers(app):
    from .i18n import get_lang, t
    from .utils.theming import brand_palette
    from .utils.timefmt import fmt_dt, to_local

    app.jinja_env.globals.update(t=t, brand_palette=brand_palette, get_lang=get_lang)
    app.jinja_env.filters["dt"] = fmt_dt
    app.jinja_env.filters["local"] = to_local
    app.jinja_env.filters["money"] = lambda v: f"{float(v or 0):,.2f}".rstrip("0").rstrip(".")
    app.jinja_env.filters["num"] = lambda v: f"{int(v or 0):,}"
    app.jinja_env.filters["mask"] = lambda v: "•" * max(len(v or "") - 4, 0) + (v or "")[-4:]

    @app.context_processor
    def inject_globals():
        return {"GROUP_NAME": app.config["GROUP_NAME"], "PUBLIC_BASE_URL": app.config["PUBLIC_BASE_URL"]}


def _register_error_handlers(app):
    def render_error(code, title, message):
        return render_template("error.html", code=code, title=title, message=message), code

    app.register_error_handler(403, lambda e: render_error(403, "Access denied", "You don't have permission to view this page."))
    app.register_error_handler(404, lambda e: render_error(404, "Page not found", "The page you're looking for doesn't exist."))
    app.register_error_handler(413, lambda e: render_error(413, "File too large", "Uploads must be 4 MB or smaller."))
    app.register_error_handler(CSRFError, lambda e: render_error(400, "Session expired",
                                                                 "Your form session expired. Go back, refresh the page and try again."))

    @app.errorhandler(500)
    def server_error(e):
        db.session.rollback()
        app.logger.exception("Unhandled error on %s", request.path)
        return render_error(500, "Something went wrong", "Please try again in a moment.")
