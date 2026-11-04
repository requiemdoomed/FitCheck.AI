"""
Server tests: the real Flask app on a real MySQL test database (rebuilt for
the run), with the photo services replaced by a local fake.

Database settings come from TEST_DB_* (defaults match the local setup in
docs/DEPLOYMENT.md).
"""

import io
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "tests" / "support"))

FAKE_PORT = 5611
SMTP_PORT = 5613
os.environ.update({
    "FITCHECK_TESTING": "1", "FLASK_ENV": "testing", "SECRET_KEY": "t" * 48, "COOKIE_SECURE": "1",
    "DB_HOST": os.getenv("TEST_DB_HOST", "127.0.0.1"), "DB_PORT": os.getenv("TEST_DB_PORT", "3306"),
    "DB_USER": os.getenv("TEST_DB_USER", "fitcheck_app"), "DB_PASSWORD": os.getenv("TEST_DB_PASSWORD", "LocalDevPass_2026"),
    "DB_NAME": os.getenv("TEST_DB_NAME", "fitcheck_test"),
    "POLLINATIONS_IMAGE_URL": f"http://127.0.0.1:{FAKE_PORT}", "POLLINATIONS_GEN_URL": f"http://127.0.0.1:{FAKE_PORT}",
    "GEMINI_URL": f"http://127.0.0.1:{FAKE_PORT}/gemini", "PHOTO_TIMEOUT": "20",
    # email goes to a local fake SMTP server, sent inside the request so tests can read it
    "SMTP_HOST": "127.0.0.1", "SMTP_PORT": str(SMTP_PORT), "SMTP_SECURITY": "none", "MAIL_SYNC": "1",
    "MAIL_FROM": "FitCheck.AI <no-reply@fitcheck.test>", "APP_URL": "https://fitcheck.test",
})

import fake_photo_service  # noqa: E402
import fake_smtp  # noqa: E402

PASSWORD = "Wardrobe-2026"


def _reset_database():
    import db
    from config import Config
    for k in ("DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME"):
        setattr(Config, k, os.environ[k])
    Config.DB_PORT = int(os.environ["DB_PORT"])
    c = db.connect()
    with c.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        cur.execute("SHOW TABLES")
        for row in cur.fetchall():
            cur.execute(f"DROP TABLE `{list(row.values())[0]}`")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
    c.commit()
    db.apply_schema(c)
    c.close()


@pytest.fixture(scope="session")
def fake():
    srv = fake_photo_service.serve(FAKE_PORT)
    yield fake_photo_service
    srv.shutdown()


@pytest.fixture(scope="session")
def app(fake):
    try:
        _reset_database()
    except Exception as err:  # pragma: no cover
        pytest.skip(f"MySQL test database not reachable ({err})")
    from app import create_app
    return create_app({"TESTING": True})


class Client:
    """A browser-like client: keeps cookies, sends the CSRF header and same-site Origin."""

    def __init__(self, app):
        self.c = app.test_client()
        self.c.environ_base["wsgi.url_scheme"] = "https"
        self.c.environ_base["HTTP_HOST"] = "fitcheck.test"

    def _h(self, extra=None):
        ck = self.c.get_cookie("fc_csrf", domain="fitcheck.test")
        h = {"Origin": "https://fitcheck.test", "X-CSRF-Token": ck.value if ck else ""}
        h.update(extra or {})
        return h

    def get(self, url, **kw):
        return self.c.get(url, base_url="https://fitcheck.test", **kw)

    def post(self, url, json=None, data=None, headers=None, **kw):
        return self.c.post(url, base_url="https://fitcheck.test", json=json, data=data, headers=self._h(headers), **kw)

    def put(self, url, json=None, data=None, headers=None, **kw):
        return self.c.put(url, base_url="https://fitcheck.test", json=json, data=data, headers=self._h(headers), **kw)

    def delete(self, url, json=None, headers=None, **kw):
        return self.c.delete(url, base_url="https://fitcheck.test", json=json, headers=self._h(headers), **kw)

    def register(self, email, name="Test Person", password=PASSWORD):
        r = self.post("/api/auth/register", json={"display_name": name, "email": email, "password": password})
        assert r.status_code == 201, r.json
        return r


@pytest.fixture
def client_for(app):
    return lambda: Client(app)


_n = [0]


@pytest.fixture
def user(client_for):
    _n[0] += 1
    c = client_for()
    c.register(f"user{_n[0]}@example.com")
    return c


def jpeg(colour=(200, 40, 44), size=(480, 600), exif_gps=False):
    from PIL import Image
    img = Image.new("RGB", size, (238, 240, 243))
    from PIL import ImageDraw
    ImageDraw.Draw(img).rectangle((120, 80, 360, 540), fill=colour)
    buf = io.BytesIO()
    if exif_gps:
        exif = Image.Exif()
        exif[0x8825] = {1: "N", 2: (43.0, 39.0, 0.0)}
        img.save(buf, "JPEG", exif=exif)
    else:
        img.save(buf, "JPEG")
    return buf.getvalue()


ITEM = {"name": "White shirt", "category": "top", "subcategory": "shirt", "main_color": "#f5f5f2",
        "style": "classic", "seasons": ["spring", "autumn"], "occasions": ["work", "casual"]}


def add_item(c, **over):
    data = {**ITEM, **over}
    r = c.post("/api/wardrobe", json=data)
    assert r.status_code == 201, r.json
    return r.json["item"]


def basic_wardrobe(c):
    add_item(c)
    add_item(c, name="Navy chinos", category="bottom", subcategory="chinos", main_color="#1f2a4a")
    add_item(c, name="Brown loafers", category="footwear", subcategory="loafers", main_color="#6b4428",
             occasions=["work", "casual", "date"], seasons=["spring", "summer", "autumn", "winter"])


@pytest.fixture(autouse=True)
def _fresh_limits(app):
    """Each test starts with empty rate-limit counters (the limits themselves are tested)."""
    with app.app_context():
        import db
        db.run("DELETE FROM rate_events")
        db.commit()
        db.close()
    yield


@pytest.fixture(scope="session")
def mailbox():
    fake_smtp.serve(SMTP_PORT)
    return fake_smtp.INBOX
