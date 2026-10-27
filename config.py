import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _bool(name, default="0"):
    return str(os.getenv(name, default)).strip().lower() in ("1", "true", "yes", "on")


class Config:
    ENV_NAME = os.getenv("FLASK_ENV", "development").strip().lower()
    IS_PRODUCTION = ENV_NAME == "production"
    SECRET_KEY = os.getenv("SECRET_KEY", "insecure-dev-key")
    GROUP_NAME = os.getenv("GROUP_NAME", "Razzmattazz Hospitality Group")
    PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:5000").rstrip("/")
    APP_TIMEZONE = os.getenv("APP_TIMEZONE", "UTC")

    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL") or f"sqlite:///{BASE_DIR / 'instance' / 'dev.db'}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}

    UPLOAD_FOLDER = BASE_DIR / "app" / "static" / "uploads"
    MAX_CONTENT_LENGTH = 4 * 1024 * 1024  # 4 MB uploads
    ALLOWED_IMAGE_EXT = {"png", "jpg", "jpeg", "webp", "svg"}

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Production runs behind HTTPS: only send cookies over TLS.
    SESSION_COOKIE_SECURE = REMEMBER_COOKIE_SECURE = IS_PRODUCTION
    PREFERRED_URL_SCHEME = "https" if IS_PRODUCTION else "http"
    # Set to 1 when a proxy/CDN (e.g. Cloudflare) sits in front of cPanel, so client IPs and https are read correctly.
    TRUST_PROXY = _bool("TRUST_PROXY", "0")
    WTF_CSRF_TIME_LIMIT = None

    # Customer verification
    VERIFY_CODE_LENGTH = 7
    VERIFY_CODE_TTL_MINUTES = 15
    VERIFY_MAX_ATTEMPTS = 5
    VERIFY_RESEND_COOLDOWN_SECONDS = 60
    CLAIM_CODE_LENGTH = 8

    # Mail
    MAIL_SERVER = os.getenv("MAIL_SERVER", "").strip()
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USE_TLS = _bool("MAIL_USE_TLS", "1")
    MAIL_USE_SSL = _bool("MAIL_USE_SSL", "0")
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "").strip()
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "").strip()
    MAIL_FROM = os.getenv("MAIL_FROM", "").strip() or MAIL_USERNAME
    MAIL_FROM_NAME = os.getenv("MAIL_FROM_NAME", GROUP_NAME).strip()
    MAIL_SUPPRESS_SEND = _bool("MAIL_SUPPRESS_SEND", "0")

    SUPERADMIN_EMAIL = os.getenv("SUPERADMIN_EMAIL", "admin@razzmattazz.com")
    SUPERADMIN_PASSWORD = os.getenv("SUPERADMIN_PASSWORD", "ChangeMe!2026")


class TestConfig(Config):
    TESTING = True
    IS_PRODUCTION = False
    SESSION_COOKIE_SECURE = REMEMBER_COOKIE_SECURE = False
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    WTF_CSRF_ENABLED = False
    MAIL_SUPPRESS_SEND = True
