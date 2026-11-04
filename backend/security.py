"""
Passwords, sessions, CSRF, rate limits and encrypted secrets.
Swayam Shakya
"""

import base64
import hashlib
import hmac
import json
import re
import secrets as pysecrets
from datetime import datetime, timedelta, timezone
from functools import wraps

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from flask import current_app, g, request
from werkzeug.security import check_password_hash, generate_password_hash

import db
from errors import ApiError

SESSION_COOKIE = "fc_session"
CSRF_COOKIE = "fc_csrf"
CSRF_HEADER = "X-CSRF-Token"

# ---------------------------------------------------------------- passwords

COMMON_PASSWORDS = set((
    "password password1 password12 password123 password1234 passw0rd p@ssword p@ssw0rd 12345678 123456789 "
    "1234567890 12345678910 qwerty123 qwertyuiop qwerty1234 1q2w3e4r 1q2w3e4r5t 1qaz2wsx abc12345 abcd1234 "
    "iloveyou1 iloveyou123 letmein1 welcome1 welcome123 admin123 administrator monkey123 dragon123 football1 "
    "baseball1 sunshine1 princess1 trustno1 starwars1 superman1 asdf1234 zxcvbnm1 changeme1 secret123 hello123 "
    "freedom1 whatever1 qazwsxedc michael1 shadow123 master123 aa123456 fitcheck1 fitcheck123 wardrobe1 wardrobe123"
).split())

# a real hash, checked when the email doesn't exist so timing doesn't reveal accounts
_DUMMY = generate_password_hash("not-a-real-password-0", method="scrypt")


def password_problem(pw, email=""):
    if not isinstance(pw, str) or not pw:
        return "Password is required."
    if len(pw) < 8:
        return "Use at least 8 characters."
    if len(pw) > 128:
        return "Use 128 characters or fewer."
    if pw.isdigit() or re.fullmatch(r"[A-Za-z]+", pw):
        return "Mix letters with numbers or symbols."
    if pw.lower() in COMMON_PASSWORDS:
        return "That's one of the most common passwords. Choose something less guessable."
    name = (email or "").split("@")[0].lower()
    if len(name) >= 4 and name in pw.lower():
        return "Don't use your email address in your password."
    if len(set(pw)) == 1:
        return "Avoid a single repeated character."
    return None


def hash_password(pw):
    return generate_password_hash(pw, method="scrypt")


def check_password(pw, stored):
    if not isinstance(pw, str):
        return False
    return check_password_hash(stored or _DUMMY, pw) and bool(stored)


# ---------------------------------------------------------------- time

def now():
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


# ---------------------------------------------------------------- sessions

def _sha(v):
    return hashlib.sha256(v.encode()).hexdigest()


def start_session(user_id, remember=False):
    token = pysecrets.token_urlsafe(32)
    cfg = current_app.config
    expires = now() + (timedelta(days=cfg["REMEMBER_DAYS"]) if remember else timedelta(hours=cfg["SESSION_HOURS"]))
    db.run("INSERT INTO sessions (user_id, token_hash, expires_at, remember, user_agent, created_at, last_seen_at) "
           "VALUES (%s, %s, %s, %s, %s, %s, %s)",
           (user_id, _sha(token), expires, int(bool(remember)), (request.headers.get("User-Agent") or "")[:160], now(), now()))
    g.set_cookies = {"token": token, "remember": remember, "expires": expires}
    return expires


def end_session():
    s = getattr(g, "session_row", None)
    if s:
        db.run("UPDATE sessions SET revoked_at = %s WHERE id = %s", (now(), s["id"]))
    g.clear_cookies = True


def end_all_sessions(user_id, except_id=None):
    db.run("UPDATE sessions SET revoked_at = %s WHERE user_id = %s AND revoked_at IS NULL AND id <> %s",
           (now(), user_id, except_id or 0))


def current_user(optional=False):
    if "user" in g:
        return g.user
    token = request.cookies.get(SESSION_COOKIE, "")
    row = None
    if token and len(token) < 200:
        row = db.one("SELECT * FROM sessions WHERE token_hash = %s", (_sha(token),))
    t = now()
    reason = "Sign in to continue."
    if row and not row["revoked_at"] and row["expires_at"] > t:
        if not row["remember"] and t - row["last_seen_at"] > timedelta(minutes=current_app.config["IDLE_MINUTES"]):
            db.run("UPDATE sessions SET revoked_at = %s WHERE id = %s", (t, row["id"]))
            row, reason = None, "You were signed out after 30 minutes without activity. Sign in again."
    else:
        if row:
            reason = "Your session has ended. Sign in again."
        row = None
    if not row:
        if optional:
            return None
        g.clear_cookies = bool(token)
        raise ApiError(401, "unauthorized", reason)
    if t - row["last_seen_at"] > timedelta(seconds=60):
        db.run("UPDATE sessions SET last_seen_at = %s WHERE id = %s", (t, row["id"]))
    user = db.one("SELECT id, email, display_name, password_hash, created_at FROM users WHERE id = %s", (row["user_id"],))
    if not user:
        raise ApiError(401, "unauthorized", reason)
    g.user, g.session_row = user, row
    return user


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        current_user()
        return fn(*a, **kw)
    return wrapper


def apply_cookies(response):
    """Set or clear the session and CSRF cookies after a request."""
    secure = current_app.config["COOKIE_SECURE"]
    if getattr(g, "set_cookies", None):
        c = g.set_cookies
        max_age = int((c["expires"] - now()).total_seconds()) if c["remember"] else None
        response.set_cookie(SESSION_COOKIE, c["token"], max_age=max_age, httponly=True, secure=secure,
                            samesite="Lax", path="/")
        response.set_cookie(CSRF_COOKIE, pysecrets.token_urlsafe(24), max_age=max_age, httponly=False,
                            secure=secure, samesite="Strict", path="/")
    elif getattr(g, "clear_cookies", False):
        response.delete_cookie(SESSION_COOKIE, path="/", secure=secure, httponly=True, samesite="Lax")
        response.delete_cookie(CSRF_COOKIE, path="/", secure=secure, samesite="Strict")
    elif request.cookies.get(SESSION_COOKIE) and not request.cookies.get(CSRF_COOKIE):
        response.set_cookie(CSRF_COOKIE, pysecrets.token_urlsafe(24), httponly=False, secure=secure,
                            samesite="Strict", path="/")
    return response


def check_csrf():
    """
    Unsafe methods must come from this site: same Origin (or Referer) and the
    double-submit CSRF token (cookie value echoed in a header).
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    origin = request.headers.get("Origin") or ""
    if origin and origin.rstrip("/") != request.host_url.rstrip("/"):
        raise ApiError(403, "bad_origin", "Requests must come from FitCheck.AI itself.")
    if request.cookies.get(SESSION_COOKIE):
        cookie = request.cookies.get(CSRF_COOKIE, "")
        header = request.headers.get(CSRF_HEADER, "")
        if not cookie or not hmac.compare_digest(cookie, header):
            raise ApiError(403, "csrf_failed", "Your session check failed. Reload the page and try again.")


# ---------------------------------------------------------------- rate limits

def client_ip():
    # Render and most hosts put the real client first in X-Forwarded-For; only trusted behind a proxy
    if current_app.config.get("TRUST_PROXY"):
        return (request.headers.get("X-Forwarded-For") or request.remote_addr or "").split(",")[0].strip()
    return request.remote_addr or ""


def limited(bucket, key, limit, window_minutes):
    """True if `key` has reached `limit` events in the window. Doesn't record."""
    since = now() - timedelta(minutes=window_minutes)
    row = db.one("SELECT COUNT(*) AS n, MIN(created_at) AS first FROM rate_events WHERE bucket = %s AND key_hash = %s AND created_at > %s",
                 (bucket, _sha(key), since))
    if row["n"] >= limit:
        wait = int((row["first"] + timedelta(minutes=window_minutes) - now()).total_seconds())
        return max(1, wait)
    return 0


def record(bucket, key):
    db.run("INSERT INTO rate_events (bucket, key_hash, created_at) VALUES (%s, %s, %s)", (bucket, _sha(key), now()))


def forget(bucket, key):
    db.run("DELETE FROM rate_events WHERE bucket = %s AND key_hash = %s", (bucket, _sha(key)))


def prune_rate_events():
    """Housekeeping: old rate counters, used or expired reset links, sessions ended over 30 days ago."""
    t = now()
    db.run("DELETE FROM rate_events WHERE created_at < %s", (t - timedelta(days=2),))
    db.run("DELETE FROM password_resets WHERE expires_at < %s OR used_at < %s", (t - timedelta(days=1), t - timedelta(days=1)))
    db.run("DELETE FROM sessions WHERE expires_at < %s OR revoked_at < %s", (t - timedelta(days=30), t - timedelta(days=30)))


# ---------------------------------------------------------------- encrypted secrets

def _fernet():
    secret = current_app.config["SECRET_KEY"].encode()
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"fitcheck-secrets-v1", info=b"api-keys").derive(secret)
    return Fernet(base64.urlsafe_b64encode(key))


def seal(value):
    return _fernet().encrypt(json.dumps(value).encode())


def unseal(token):
    if not token:
        return {}
    try:
        return json.loads(_fernet().decrypt(bytes(token)))
    except (InvalidToken, ValueError):
        return {}
