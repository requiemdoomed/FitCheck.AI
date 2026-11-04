"""
End-to-end browser tests against the real stack:

  * the Flask server (backend/wsgi.py) on http://localhost:5502, serving the
    pages and /api from one origin, on the MySQL test database (rebuilt for
    the run)
  * a local fake of the photo services (the test machine can't reach them),
    which the server calls exactly as it calls Pollinations and Gemini
  * Chromium through Playwright, each context a fresh browser ("device")

Database settings come from TEST_DB_* (defaults match docs/DEPLOYMENT.md).
"""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
APP_PORT = 5502
FAKE_PORT = 5612
SMTP_PORT = 5614
OUTBOX = None        # folder where the fake mail server drops messages (set by the servers fixture)

ENV = {
    "FITCHECK_TESTING": "1", "FLASK_ENV": "testing", "SECRET_KEY": "e" * 48,
    # Chromium treats http://localhost as a secure context, so Secure cookies work as in production
    "COOKIE_SECURE": "1",
    "DB_HOST": os.getenv("TEST_DB_HOST", "127.0.0.1"), "DB_PORT": os.getenv("TEST_DB_PORT", "3306"),
    "DB_USER": os.getenv("TEST_DB_USER", "fitcheck_app"), "DB_PASSWORD": os.getenv("TEST_DB_PASSWORD", "LocalDevPass_2026"),
    "DB_NAME": os.getenv("TEST_DB_NAME", "fitcheck_test"),
    "POLLINATIONS_IMAGE_URL": f"http://127.0.0.1:{FAKE_PORT}", "POLLINATIONS_GEN_URL": f"http://127.0.0.1:{FAKE_PORT}",
    "GEMINI_URL": f"http://127.0.0.1:{FAKE_PORT}/gemini", "PHOTO_TIMEOUT": "20",
    "PUBLIC_PHOTOS_PER_HOUR": "200",
    "SMTP_HOST": "127.0.0.1", "SMTP_PORT": str(SMTP_PORT), "SMTP_SECURITY": "none", "MAIL_SYNC": "1",
    "MAIL_FROM": "FitCheck.AI <no-reply@localhost>", "APP_URL": f"http://localhost:{APP_PORT}",
}

RESET = """
import db
c = db.connect()
with c.cursor() as cur:
    cur.execute("SET FOREIGN_KEY_CHECKS = 0"); cur.execute("SHOW TABLES")
    for row in cur.fetchall(): cur.execute(f"DROP TABLE `{list(row.values())[0]}`")
    cur.execute("SET FOREIGN_KEY_CHECKS = 1")
c.commit(); db.apply_schema(c); c.close()
"""

SERVE = f"""
from werkzeug.serving import run_simple
from app import create_app
run_simple("127.0.0.1", {APP_PORT}, create_app(), threaded=True)
"""


def _port_open(port):
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _wait_for(url, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status < 500:
                    return True
        except Exception:
            time.sleep(0.25)
    return False


def mails():
    """Messages the server has sent, oldest first, as email.message objects."""
    from email import message_from_bytes, policy
    return [message_from_bytes(p.read_bytes(), policy=policy.default) for p in sorted(Path(OUTBOX).glob("*.eml"))]


def fake(path):
    """Talk to the fake photo service: '__log', '__clear', '__mode/busy', '__mode/quota', '__mode/none'."""
    with urllib.request.urlopen(f"http://127.0.0.1:{FAKE_PORT}/{path}", timeout=5) as r:
        return json.loads(r.read() or b"null")


def sql(statement):
    """Run one statement on the test database (used to age a session)."""
    env = {**os.environ, **ENV}
    code = f"import db\nc = db.connect()\nc.cursor().execute({statement!r})\nc.commit()\nc.close()"
    subprocess.run([sys.executable, "-c", code], cwd=ROOT / "backend", env=env, check=True)


@pytest.fixture(scope="session")
def servers(tmp_path_factory):
    global OUTBOX
    for port in (APP_PORT, FAKE_PORT, SMTP_PORT):
        if _port_open(port):
            pytest.fail(f"Port {port} is busy.")
    env = {**os.environ, **ENV}
    reset = subprocess.run([sys.executable, "-c", RESET], cwd=ROOT / "backend", env=env, capture_output=True, text=True)
    if reset.returncode:
        pytest.skip(f"MySQL test database not reachable: {reset.stderr.strip().splitlines()[-1]}")
    OUTBOX = str(tmp_path_factory.mktemp("outbox"))
    smtp = subprocess.Popen([sys.executable, str(ROOT / "tests/support/fake_smtp.py"), str(SMTP_PORT), OUTBOX],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    photos = subprocess.Popen([sys.executable, str(ROOT / "tests/support/fake_photo_service.py"), str(FAKE_PORT)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log = tmp_path_factory.mktemp("server") / "server.log"
    log_file = open(log, "w")          # a file, not a pipe: an unread pipe fills up and stalls the server
    app = subprocess.Popen([sys.executable, "-c", SERVE], cwd=ROOT / "backend", env=env,
                           stdout=log_file, stderr=subprocess.STDOUT)
    base = f"http://localhost:{APP_PORT}/"
    if not _wait_for(base + "api/health"):
        for proc in (app, photos, smtp):
            proc.kill()
        pytest.fail("Server didn't start: " + log.read_text()[-2000:])
    yield {"base": base}
    for proc in (app, photos, smtp):
        proc.terminate()
        proc.wait(timeout=10)
    log_file.close()


@pytest.fixture(scope="session")
def chrome():
    from playwright.sync_api import sync_playwright
    exe = os.getenv("CHROME_PATH") or ("/usr/bin/google-chrome" if Path("/usr/bin/google-chrome").exists() else None)
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=exe)
        yield b
        b.close()
