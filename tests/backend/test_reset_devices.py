"""Password reset by email, and the signed-in devices list."""

import re
from datetime import timedelta

from conftest import PASSWORD

NEW = "Fresh-start-2027"


def _link(mailbox, to):
    msg = [m for m in mailbox if m["To"] == to][-1]
    body = msg.get_content()
    return msg, re.search(r"https://fitcheck\.test/reset-password\.html#token=([A-Za-z0-9_-]+)", body).group(1)


def test_reset_email_link_works_once_and_signs_out_everywhere(app, client_for, mailbox):
    a = client_for()
    a.register("reset@example.com")
    b = client_for()                                         # a second device, signed in
    b.post("/api/auth/login", json={"email": "reset@example.com", "password": PASSWORD, "remember": True})

    anon = client_for()
    r = anon.post("/api/auth/forgot", json={"email": "Reset@Example.com"})
    assert r.status_code == 202 and "If an account uses that email" in r.json["message"]
    msg, token = _link(mailbox, "reset@example.com")
    assert msg["Subject"] == "Reset your FitCheck.AI password" and "no-reply@fitcheck.test" in msg["From"]
    assert "?token=" not in msg.get_content()                 # fragment, never a query string

    with app.app_context():                                  # only a hash is stored
        import db
        stored = db.one("SELECT token_hash FROM password_resets ORDER BY id DESC LIMIT 1")["token_hash"]
        db.close()
    assert stored != token and len(stored) == 64

    assert anon.post("/api/auth/reset", json={"token": token, "password": "password123"}).status_code == 400   # still checked
    r = anon.post("/api/auth/reset", json={"token": token, "password": NEW})
    assert r.status_code == 200
    assert a.get("/api/auth/me").status_code == 401 and b.get("/api/auth/me").status_code == 401
    again = anon.post("/api/auth/reset", json={"token": token, "password": "Another-one-2028"})
    assert again.status_code == 400 and again.json["error"]["code"] == "reset_link_invalid"
    assert anon.post("/api/auth/login", json={"email": "reset@example.com", "password": PASSWORD}).status_code == 401
    assert anon.post("/api/auth/login", json={"email": "reset@example.com", "password": NEW}).status_code == 200


def test_unknown_email_gets_the_same_answer_and_no_mail(client_for, mailbox):
    c = client_for()
    before = len(mailbox)
    r = c.post("/api/auth/forgot", json={"email": "nobody-here@example.com"})
    assert r.status_code == 202 and len(mailbox) == before
    c.register("known@example.com")
    known = c.post("/api/auth/forgot", json={"email": "known@example.com"})
    assert known.json == r.json and len(mailbox) == before + 1
    assert c.post("/api/auth/forgot", json={"email": "not-an-email"}).status_code == 400


def test_new_link_replaces_old_and_links_expire(app, client_for, mailbox):
    c = client_for()
    c.register("expiry@example.com")
    c.post("/api/auth/forgot", json={"email": "expiry@example.com"})
    _, first = _link(mailbox, "expiry@example.com")
    c.post("/api/auth/forgot", json={"email": "expiry@example.com"})
    _, second = _link(mailbox, "expiry@example.com")
    assert c.post("/api/auth/reset", json={"token": first, "password": NEW}).status_code == 400
    with app.app_context():
        import db
        db.run("UPDATE password_resets SET expires_at = expires_at - INTERVAL 31 MINUTE")
        db.commit()
        db.close()
    assert c.post("/api/auth/reset", json={"token": second, "password": NEW}).json["error"]["code"] == "reset_link_invalid"
    for bad in ("", "x", "a" * 500, "../../etc", None, 7):
        assert c.post("/api/auth/reset", json={"token": bad, "password": NEW}).status_code == 400


def test_reset_requests_are_limited(client_for, mailbox):
    c = client_for()
    c.register("flood@example.com")
    before = len(mailbox)
    codes = [c.post("/api/auth/forgot", json={"email": "flood@example.com"}).status_code for _ in range(5)]
    assert codes == [202] * 5 and len(mailbox) == before + 3      # 3 emails an hour per address, same answer
    for i in range(6):
        c.post("/api/auth/forgot", json={"email": f"other{i}@example.com"})
    assert c.post("/api/auth/forgot", json={"email": "last@example.com"}).status_code == 429   # 10 per IP per hour
    for _ in range(20):
        c.post("/api/auth/reset", json={"token": "A" * 43, "password": NEW})
    assert c.post("/api/auth/reset", json={"token": "A" * 43, "password": NEW}).status_code == 429


def test_without_mail_setup_production_says_so(app, client_for, monkeypatch):
    monkeypatch.setitem(app.config, "SMTP_HOST", "")
    monkeypatch.setitem(app.config, "ENV", "production")
    r = client_for().post("/api/auth/forgot", json={"email": "someone@example.com"})
    assert r.status_code == 503 and r.json["error"]["code"] == "mail_not_configured"


def test_operator_reset_link(app, client_for, monkeypatch, capsys):
    c = client_for()
    c.register("operator@example.com")
    import manage
    monkeypatch.setattr(manage, "create_app", lambda: app)
    assert manage.main(["manage.py", "reset-link", "operator@example.com"]) == 0
    token = re.search(r"#token=([A-Za-z0-9_-]+)", capsys.readouterr().out).group(1)
    assert client_for().post("/api/auth/reset", json={"token": token, "password": NEW}).status_code == 200
    assert manage.main(["manage.py", "reset-link", "missing@example.com"]) == 1


def test_devices_list_and_signing_one_out(client_for):
    a = client_for()
    a.c.environ_base["HTTP_USER_AGENT"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/141.0 Safari/537.36"
    a.register("devices@example.com")
    b = client_for()
    b.c.environ_base["HTTP_USER_AGENT"] = "Mozilla/5.0 (iPhone; CPU iPhone OS 19_0 like Mac OS X) AppleWebKit/605.1.15 Version/19.0 Mobile Safari/604.1"
    b.post("/api/auth/login", json={"email": "devices@example.com", "password": PASSWORD, "remember": True})
    listed = a.get("/api/auth/sessions").json["sessions"]
    assert {s["device"] for s in listed} == {"Chrome on Windows", "Safari on iOS"}
    assert [s["current"] for s in listed if s["device"] == "Chrome on Windows"] == [True]
    phone = next(s for s in listed if s["device"] == "Safari on iOS")
    assert phone["remember"] and set(phone) == {"id", "device", "signed_in_at", "last_seen_at", "remember", "current"}

    other = client_for()
    other.register("someone-else@example.com")
    assert other.delete(f"/api/auth/sessions/{phone['id']}").status_code == 404     # not theirs
    assert a.delete(f"/api/auth/sessions/{phone['id']}").status_code == 204
    assert b.get("/api/auth/me").status_code == 401 and a.get("/api/auth/me").status_code == 200
    mine = next(s for s in a.get("/api/auth/sessions").json["sessions"] if s["current"])
    r = a.delete(f"/api/auth/sessions/{mine['id']}")
    assert r.status_code == 204 and any(h.startswith("fc_session=;") for h in r.headers.getlist("Set-Cookie"))
    assert a.get("/api/auth/me").status_code == 401


def test_housekeeping_clears_old_records(app, client_for):
    c = client_for()
    c.register("old@example.com")
    with app.app_context():
        import db
        import security as sec
        uid = db.one("SELECT id FROM users WHERE email = 'old@example.com'")["id"]
        old = sec.now() - timedelta(days=40)
        db.run("INSERT INTO sessions (user_id, token_hash, expires_at, created_at, last_seen_at) VALUES (%s, %s, %s, %s, %s)",
               (uid, "f" * 64, old, old, old))
        db.run("INSERT INTO password_resets (user_id, token_hash, expires_at) VALUES (%s, %s, %s)", (uid, "e" * 64, old))
        sec.prune_rate_events()
        left = (db.one("SELECT COUNT(*) AS n FROM sessions WHERE token_hash = %s", ("f" * 64,))["n"],
                db.one("SELECT COUNT(*) AS n FROM password_resets WHERE token_hash = %s", ("e" * 64,))["n"])
        db.commit()
        db.close()
    assert left == (0, 0)
