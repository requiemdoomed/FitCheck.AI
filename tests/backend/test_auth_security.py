"""Accounts, sessions, cookies, CSRF, rate limits, headers and static serving."""

from datetime import timedelta

import pytest

from conftest import PASSWORD


def test_register_validates_everything(client_for):
    c = client_for()
    r = c.post("/api/auth/register", json={})
    assert r.status_code == 400 and set(r.json["error"]["details"]) == {"display_name", "email", "password"}
    for pw, words in (("short1", "8 characters"), ("password123", "common"), ("abcdefgh", "Mix"),
                      ("annabelle99", "email"), ("1111111a1", None)):
        r = c.post("/api/auth/register", json={"display_name": "A", "email": "annabelle@example.com", "password": pw})
        if words:
            assert r.status_code == 400 and words in r.json["error"]["details"]["password"], pw


def test_register_sets_secure_cookies_and_stores_only_a_hash(app, client_for):
    c = client_for()
    r = c.register("Cookie@Example.com")
    cookies = r.headers.getlist("Set-Cookie")
    session = next(h for h in cookies if h.startswith("fc_session="))
    csrf = next(h for h in cookies if h.startswith("fc_csrf="))
    assert "HttpOnly" in session and "Secure" in session and "SameSite=Lax" in session
    assert "HttpOnly" not in csrf and "SameSite=Strict" in csrf and "Secure" in csrf
    token = session.split(";")[0].split("=", 1)[1]
    with app.app_context():
        import db
        u = db.one("SELECT * FROM users WHERE email = 'cookie@example.com'")
        assert u and PASSWORD not in u["password_hash"] and u["password_hash"].startswith("scrypt:")
        assert db.one("SELECT COUNT(*) AS n FROM sessions WHERE token_hash = %s", (token,))["n"] == 0   # only the hash
        db.close()
    assert c.get("/api/auth/me").json["user"]["email"] == "cookie@example.com"
    assert c.post("/api/auth/register", json={"display_name": "B", "email": "cookie@example.com", "password": PASSWORD}).status_code == 409


def test_login_errors_dont_reveal_accounts_and_are_rate_limited(client_for):
    c = client_for()
    c.register("limit@example.com")
    other = client_for()
    a = other.post("/api/auth/login", json={"email": "limit@example.com", "password": "wrong-pass-1"})
    b = other.post("/api/auth/login", json={"email": "nobody@example.com", "password": "wrong-pass-1"})
    assert a.status_code == b.status_code == 401 and a.json == b.json
    for _ in range(7):
        other.post("/api/auth/login", json={"email": "limit@example.com", "password": "wrong-pass-1"})
    r = other.post("/api/auth/login", json={"email": "limit@example.com", "password": PASSWORD})
    assert r.status_code == 429


def test_csrf_and_origin_are_required_for_changes(user):
    ok = user.post("/api/auth/me")      # wrong method is fine to check routing
    assert ok.status_code == 405
    r = user.c.post("/api/recommendations/generate", base_url="https://fitcheck.test", json={},
                    headers={"Origin": "https://fitcheck.test"})
    assert r.status_code == 403 and r.json["error"]["code"] == "csrf_failed"
    r = user.post("/api/recommendations/generate", json={}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and r.json["error"]["code"] == "bad_origin"


def test_logout_logout_all_and_idle_expiry(app, client_for):
    a = client_for()
    a.register("sessions@example.com")
    b = client_for()
    assert b.post("/api/auth/login", json={"email": "sessions@example.com", "password": PASSWORD, "remember": True}).status_code == 200
    assert b.get("/api/auth/me").status_code == 200
    assert a.post("/api/auth/logout-all").status_code == 204
    assert a.get("/api/auth/me").status_code == 401 and b.get("/api/auth/me").status_code == 401
    # idle: a normal sign-in ends after 30 minutes without use
    c = client_for()
    c.post("/api/auth/login", json={"email": "sessions@example.com", "password": PASSWORD})
    with app.app_context():
        import db
        db.run("UPDATE sessions SET last_seen_at = last_seen_at - INTERVAL 31 MINUTE WHERE revoked_at IS NULL AND remember = 0")
        db.commit()
        db.close()
    r = c.get("/api/auth/me")
    assert r.status_code == 401 and "30 minutes" in r.json["error"]["message"]


def test_password_change_signs_out_other_sessions(client_for):
    a = client_for()
    a.register("pw@example.com")
    b = client_for()
    b.post("/api/auth/login", json={"email": "pw@example.com", "password": PASSWORD})
    r = a.put("/api/profile", json={"current_password": "nope-nope-1", "new_password": "Another-pass-9"})
    assert r.status_code == 400 and "current_password" in r.json["error"]["details"]
    assert a.put("/api/profile", json={"current_password": PASSWORD, "new_password": "Another-pass-9"}).status_code == 200
    assert a.get("/api/auth/me").status_code == 200 and b.get("/api/auth/me").status_code == 401


def test_security_headers_on_pages_and_api(client_for):
    c = client_for()
    for path in ("/", "/login.html", "/api/health", "/assets/css/base.css"):
        h = c.get(path).headers
        csp = h["Content-Security-Policy"]
        assert "frame-ancestors 'none'" in csp and "object-src 'none'" in csp and "'unsafe-eval'" not in csp.replace("'wasm-unsafe-eval'", "")
        assert "script-src 'self' 'wasm-unsafe-eval' 'sha256-" in csp
        assert h["X-Content-Type-Options"] == "nosniff" and h["X-Frame-Options"] == "DENY"
        assert h["Referrer-Policy"] == "no-referrer" and "max-age=" in h["Strict-Transport-Security"]
        assert "geolocation=(self)" in h["Permissions-Policy"] and h["Cross-Origin-Opener-Policy"] == "same-origin"
    assert c.get("/api/health").headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("path", ["/backend/app.py", "/backend/config.py", "/ml/models/model_metadata.json",
                                  "/tests/backend/conftest.py", "/.env", "/README.md", "/assets/../backend/app.py",
                                  "/%2e%2e/backend/app.py", "/.github/workflows/pages.yml", "/backend/schema.sql"])
def test_only_pages_and_assets_are_served(client_for, path):
    assert client_for().get(path).status_code == 404


def test_errors_never_leak_internals(user):
    r = user.get("/api/recommendations/999999999")
    assert r.status_code == 404 and set(r.json["error"]) == {"code", "message"}
    r = user.get("/api/nope")
    assert r.status_code == 404 and r.is_json


def test_service_worker_and_manifest_are_served_with_the_right_types(client_for):
    c = client_for()
    sw = c.get("/sw.js")
    assert sw.status_code == 200 and sw.mimetype == "text/javascript" and sw.headers["Cache-Control"] == "no-cache"
    assert "Content-Security-Policy" in sw.headers
    m = c.get("/manifest.webmanifest")
    assert m.status_code == 200 and m.mimetype == "application/manifest+json" and m.json["name"] == "FitCheck.AI"
    assert c.get("/offline.html").status_code == 200
