"""Accounts and sign-in."""

import hashlib
import re
import secrets as pysecrets
from datetime import timedelta

from flask import Blueprint, current_app, g, request

import db
import mailer
import security as sec
import store
from errors import ApiError
from validation import V

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@bp.post("/register")
def register():
    data = request.get_json(silent=True) or {}
    v = V(data).text("display_name", max=60, label="Name").email("email")
    problem = sec.password_problem(data.get("password"), data.get("email") or "")
    if problem:
        v.errors["password"] = problem
    clean = v.done()
    ip = sec.client_ip()
    wait = sec.limited("register", ip, 10, 60)
    if wait:
        raise ApiError(429, "rate_limited", f"Too many new accounts from here. Try again in {wait // 60 + 1} minutes.")
    if db.one("SELECT id FROM users WHERE email = %s", (clean["email"],)):
        raise ApiError(409, "email_taken", "An account with that email already exists.",
                       {"email": "This email is already registered. Try signing in."})
    sec.record("register", ip)
    uid = db.run("INSERT INTO users (email, password_hash, display_name, created_at) VALUES (%s, %s, %s, %s)",
                 (clean["email"], sec.hash_password(data["password"]), clean["display_name"], sec.now()))
    db.run("INSERT INTO preferences (user_id, data) VALUES (%s, %s)", (uid, db.as_json(store.PREF_DEFAULTS)))
    expires = sec.start_session(uid)
    user = db.one("SELECT * FROM users WHERE id = %s", (uid,))
    return {"user": store.public_user(user), "preferences": store.prefs(uid), "expires_at": sec.iso(expires)}, 201


@bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower() if isinstance(data.get("email"), str) else ""
    password = data.get("password") if isinstance(data.get("password"), str) else ""
    if not email or not password:
        missing = {k: "Required." for k, v in (("email", email), ("password", password)) if not v}
        raise ApiError(400, "validation_error", "Enter your email and password.", missing)
    for bucket, key, limit in (("login", email, 8), ("login_ip", sec.client_ip(), 30)):
        wait = sec.limited(bucket, key, limit, 10)
        if wait:
            raise ApiError(429, "rate_limited", f"Too many attempts. Try again in {wait} seconds.")
    user = db.one("SELECT * FROM users WHERE email = %s", (email,))
    ok = sec.check_password(password, user["password_hash"] if user else None)
    if not user or not ok:
        sec.record("login", email)
        sec.record("login_ip", sec.client_ip())
        raise ApiError(401, "invalid_credentials", "That email and password don't match an account.")
    sec.forget("login", email)
    expires = sec.start_session(user["id"], remember=bool(data.get("remember")))
    return {"user": store.public_user(user), "preferences": store.prefs(user["id"]), "expires_at": sec.iso(expires)}


@bp.post("/logout")
def logout():
    if sec.current_user(optional=True):
        sec.end_session()
    else:
        g.clear_cookies = True
    return "", 204


@bp.post("/logout-all")
@sec.login_required
def logout_all():
    sec.end_all_sessions(g.user["id"])
    sec.end_session()
    return "", 204


@bp.get("/me")
@sec.login_required
def me():
    return {"user": store.public_user(g.user), "preferences": store.prefs(g.user["id"])}


# ---------------------------------------------------------------- password reset

RESET_SENT = ("If an account uses that email, a link to choose a new password is on its way. "
              "It works once, for {m} minutes. Check your spam folder too.")


def reset_link_for(user_id):
    """Create a one-time reset token for a user (older unused ones stop working) and return the link."""
    cfg = current_app.config
    token = pysecrets.token_urlsafe(32)
    db.run("UPDATE password_resets SET used_at = %s WHERE user_id = %s AND used_at IS NULL", (sec.now(), user_id))
    db.run("INSERT INTO password_resets (user_id, token_hash, created_at, expires_at) VALUES (%s, %s, %s, %s)",
           (user_id, hashlib.sha256(token.encode()).hexdigest(), sec.now(), sec.now() + timedelta(minutes=cfg["RESET_MINUTES"])))
    base = cfg["APP_URL"] or (request.host_url.rstrip("/") if cfg["ENV"] != "production" else "")
    # the token rides in the #fragment: browsers never send it to a server or put it in logs
    return f"{base}/reset-password.html#token={token}"


@bp.post("/forgot")
def forgot():
    cfg = current_app.config
    data = request.get_json(silent=True) or {}
    clean = V(data).email("email").done()
    if not mailer.configured(cfg):
        raise ApiError(503, "mail_not_configured",
                       "Password reset by email isn't set up on this server yet. Ask the site's operator for a reset link.")
    ip = sec.client_ip()
    wait = sec.limited("forgot_ip", ip, 10, 60)
    if wait:
        raise ApiError(429, "rate_limited", f"Too many reset requests from here. Try again in {wait // 60 + 1} minutes.")
    sec.record("forgot_ip", ip)
    message = {"message": RESET_SENT.format(m=cfg["RESET_MINUTES"])}
    # per email: quietly stop after 3 an hour, with the same answer (no account probing, no inbox flooding)
    if sec.limited("forgot", clean["email"], 3, 60):
        return message, 202
    sec.record("forgot", clean["email"])
    user = db.one("SELECT id, email, display_name FROM users WHERE email = %s", (clean["email"],))
    if user:
        link = reset_link_for(user["id"])
        body = (f"Hi {user['display_name']},\n\n"
                f"Someone (hopefully you) asked to reset the password for your FitCheck.AI account.\n\n"
                f"Choose a new password here (the link works once, for {cfg['RESET_MINUTES']} minutes):\n{link}\n\n"
                f"Didn't ask? Ignore this email: your password stays the same.\n\n"
                f"FitCheck.AI")
        try:
            mailer.send(cfg, user["email"], "Reset your FitCheck.AI password", body)
        except mailer.MailNotConfigured:  # pragma: no cover - checked above
            pass
    return message, 202


@bp.post("/reset")
def reset():
    data = request.get_json(silent=True) or {}
    token = data.get("token") if isinstance(data.get("token"), str) else ""
    ip = sec.client_ip()
    wait = sec.limited("reset_ip", ip, 20, 60)
    if wait:
        raise ApiError(429, "rate_limited", f"Too many tries. Try again in {wait // 60 + 1} minutes.")
    row = None
    if re.fullmatch(r"[A-Za-z0-9_-]{20,100}", token):
        row = db.one("SELECT r.*, u.email FROM password_resets r JOIN users u ON u.id = r.user_id WHERE r.token_hash = %s",
                     (hashlib.sha256(token.encode()).hexdigest(),))
    if not row or row["used_at"] or row["expires_at"] < sec.now():
        sec.record("reset_ip", ip)
        raise ApiError(400, "reset_link_invalid",
                       "This reset link has expired or was already used. Ask for a new one.")
    problem = sec.password_problem(data.get("password"), row["email"])
    if problem:
        raise ApiError(400, "validation_error", problem, {"password": problem})
    db.run("UPDATE users SET password_hash = %s WHERE id = %s", (sec.hash_password(data["password"]), row["user_id"]))
    db.run("UPDATE password_resets SET used_at = %s WHERE user_id = %s AND used_at IS NULL", (sec.now(), row["user_id"]))
    sec.end_all_sessions(row["user_id"])        # anyone signed in with the old password is signed out
    sec.forget("login", row["email"])
    g.clear_cookies = True
    return {"message": "Password changed. Sign in with your new password."}


# ---------------------------------------------------------------- signed-in devices

def device_name(ua):
    ua = ua or ""
    browser = next((name for pat, name in ((r"Edg/", "Edge"), (r"OPR/|Opera", "Opera"), (r"Firefox/", "Firefox"),
                                           (r"Chrome/|CriOS/", "Chrome"), (r"Safari/", "Safari")) if re.search(pat, ua)), "Browser")
    system = next((name for pat, name in ((r"iPhone|iPad|iPod", "iOS"), (r"Android", "Android"), (r"Windows", "Windows"),
                                          (r"Mac OS X|Macintosh", "macOS"), (r"CrOS", "ChromeOS"), (r"Linux", "Linux"))
                   if re.search(pat, ua)), "unknown system")
    return f"{browser} on {system}"


@bp.get("/sessions")
@sec.login_required
def sessions():
    t = sec.now()
    rows = db.all_("SELECT id, created_at, last_seen_at, remember, user_agent FROM sessions "
                   "WHERE user_id = %s AND revoked_at IS NULL AND expires_at > %s ORDER BY last_seen_at DESC",
                   (g.user["id"], t))
    idle = timedelta(minutes=current_app.config["IDLE_MINUTES"])
    live = [r for r in rows if r["remember"] or t - r["last_seen_at"] <= idle]
    return {"sessions": [{"id": r["id"], "device": device_name(r["user_agent"]), "signed_in_at": sec.iso(r["created_at"]),
                          "last_seen_at": sec.iso(r["last_seen_at"]), "remember": bool(r["remember"]),
                          "current": r["id"] == g.session_row["id"]} for r in live]}


@bp.delete("/sessions/<int:sid>")
@sec.login_required
def end_one_session(sid):
    n = db.run("UPDATE sessions SET revoked_at = %s WHERE id = %s AND user_id = %s AND revoked_at IS NULL",
               (sec.now(), sid, g.user["id"]))
    if not n:
        raise ApiError(404, "not_found", "That session isn't active.")
    if sid == g.session_row["id"]:
        g.clear_cookies = True
    return "", 204
