"""
FitCheck.AI server settings, all from environment variables.
Swayam Shakya

Nothing secret has a default: in production the app refuses to start without
SECRET_KEY and a database password.
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _bool(name, default=False):
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


class Config:
    ENV = os.getenv("FLASK_ENV", "production")
    DEBUG = False
    TESTING = _bool("FITCHECK_TESTING")

    # long random value; signs nothing itself, but derives the key that encrypts
    # stored API keys. Changing it makes saved photo-service keys unreadable.
    SECRET_KEY = os.getenv("SECRET_KEY", "")

    DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
    DB_PORT = int(os.getenv("DB_PORT", "3306"))
    DB_USER = os.getenv("DB_USER", "fitcheck_app")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "fitcheck")
    DB_SSL = _bool("DB_SSL")                     # require TLS to the database (managed hosts)
    DB_SSL_CA = os.getenv("DB_SSL_CA", "")       # optional CA bundle path

    # cookies: Secure everywhere except plain-http local development
    COOKIE_SECURE = _bool("COOKIE_SECURE", True)
    SESSION_HOURS = 12
    REMEMBER_DAYS = 30
    IDLE_MINUTES = 30

    MAX_UPLOAD_MB = 15
    MAX_ITEMS = 500

    FRONTEND_DIR = Path(os.getenv("FRONTEND_DIR", str(ROOT)))
    MODEL_DIR = Path(os.getenv("MODEL_DIR", str(ROOT / "ml" / "models")))

    # photo services (overridable so tests can point them at a local fake)
    POLLINATIONS_IMAGE_URL = os.getenv("POLLINATIONS_IMAGE_URL", "https://image.pollinations.ai")
    POLLINATIONS_GEN_URL = os.getenv("POLLINATIONS_GEN_URL", "https://gen.pollinations.ai")
    GEMINI_URL = os.getenv("GEMINI_URL", "https://generativelanguage.googleapis.com/v1beta")
    # optional server-wide free Pollinations key, so every user gets the better models
    POLLINATIONS_KEY = os.getenv("POLLINATIONS_KEY", "")
    PHOTO_TIMEOUT = int(os.getenv("PHOTO_TIMEOUT", "120"))
    PHOTOS_PER_HOUR = int(os.getenv("PHOTOS_PER_HOUR", "40"))
    PUBLIC_PHOTOS_PER_HOUR = int(os.getenv("PUBLIC_PHOTOS_PER_HOUR", "12"))

    # password-reset email. APP_URL is the public address links point to; it is
    # never taken from the request's Host header (that could be forged).
    APP_URL = os.getenv("APP_URL", "").rstrip("/")
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_SECURITY = os.getenv("SMTP_SECURITY", "starttls")   # starttls | ssl | none (local test servers only)
    MAIL_FROM = os.getenv("MAIL_FROM", "")
    RESET_MINUTES = int(os.getenv("RESET_MINUTES", "30"))
    MAIL_SYNC = _bool("MAIL_SYNC")                           # send inside the request (tests); normally a background thread

    @classmethod
    def check(cls):
        if cls.ENV == "production" and not cls.TESTING:
            problems = []
            if len(cls.SECRET_KEY) < 32:
                problems.append("SECRET_KEY must be set to at least 32 random characters")
            if not cls.DB_PASSWORD:
                problems.append("DB_PASSWORD must be set")
            if cls.SMTP_HOST and not (cls.APP_URL.startswith("https://") and cls.MAIL_FROM):
                problems.append("with SMTP_HOST set, APP_URL (https://...) and MAIL_FROM must be set too")
            if cls.SMTP_HOST and cls.SMTP_SECURITY not in ("starttls", "ssl"):
                problems.append("SMTP_SECURITY must be starttls or ssl in production")
            if problems:
                raise RuntimeError("FitCheck.AI won't start: " + "; ".join(problems))
