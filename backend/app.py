"""
FitCheck.AI server: the JSON API under /api and the web pages, from one
origin, so the session cookie is first-party and every response carries
the security headers.
Swayam Shakya

    gunicorn wsgi:app            (production)
    flask --app app run          (development)
"""

import logging
import random
import re

from flask import Flask, abort, g, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

import sys
from pathlib import Path

import db
import security as sec
from config import ROOT, Config
from errors import ApiError

PAGE = re.compile(r"^[a-z0-9-]+\.html$")
ASSET = re.compile(r"^assets/[A-Za-z0-9._/-]+$")

def _inline_hashes(frontend):
    """Hashes of the pages' small inline head scripts (theme and frame-buster)."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import update_csp
    found = set()
    for page in Path(frontend).glob("*.html"):
        found.update(update_csp.script_hashes(page.read_text(encoding="utf-8")))
    return " ".join(f"'sha256-{h}'" for h in sorted(found))


CSP_TEMPLATE = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'wasm-unsafe-eval' {hashes}",  # wasm only for the in-browser photo cut-out model
    "style-src 'self' 'unsafe-inline'",              # colour swatches use inline CSS variables
    "img-src 'self' data: blob:",
    "font-src 'self'",
    "connect-src 'self' https://api.open-meteo.com",
    "worker-src 'self' blob:",
    "frame-src 'none'",
    "frame-ancestors 'none'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "upgrade-insecure-requests",
])


def create_app(overrides=None):
    Config.check()
    app = Flask(__name__, static_folder=None)
    app.config.from_object(Config)
    app.config["MAX_CONTENT_LENGTH"] = 40 * 1024 * 1024          # a backup with photos; uploads are checked again
    app.config["JSON_SORT_KEYS"] = False
    app.config["TRUST_PROXY"] = Config.ENV == "production"
    if overrides:
        app.config.update(overrides)
    app.json.sort_keys = False
    csp = CSP_TEMPLATE.format(hashes=_inline_hashes(app.config["FRONTEND_DIR"]))
    logging.basicConfig(level=logging.INFO)

    from api_auth import bp as auth_bp
    from api_outfits import bp as outfits_bp
    from api_photos import bp as photos_bp
    from api_profile import bp as profile_bp
    from api_wardrobe import bp as wardrobe_bp
    for bp in (auth_bp, wardrobe_bp, outfits_bp, photos_bp, profile_bp):
        app.register_blueprint(bp)

    @app.before_request
    def before():
        if request.path.startswith("/api/"):
            sec.check_csrf()
            if random.random() < 0.01:  # nosec B311: housekeeping now and then
                sec.prune_rate_events()

    @app.after_request
    def after(resp):
        sec.apply_cookies(resp)
        h = resp.headers
        h["Content-Security-Policy"] = csp
        h["X-Content-Type-Options"] = "nosniff"
        h["X-Frame-Options"] = "DENY"
        h["Referrer-Policy"] = "no-referrer"
        h["Permissions-Policy"] = "geolocation=(self), camera=(), microphone=(), payment=(), usb=(), interest-cohort=()"
        h["Cross-Origin-Opener-Policy"] = "same-origin"
        h["Cross-Origin-Resource-Policy"] = "same-origin"
        h["X-Permitted-Cross-Domain-Policies"] = "none"
        if app.config["COOKIE_SECURE"]:
            h["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        if request.path.startswith("/api/") and "Cache-Control" not in h:
            h["Cache-Control"] = "no-store"
        h.pop("Server", None)
        return resp

    @app.teardown_request
    def teardown(error=None):
        db.close(error)

    @app.errorhandler(ApiError)
    def api_error(e):
        g.db_failed = e.status >= 400 and e.code not in ("invalid_credentials", "rate_limited", "unauthorized", "reset_link_invalid")
        return jsonify(e.body()), e.status

    @app.errorhandler(HTTPException)
    def http_error(e):
        if request.path.startswith("/api/"):
            codes = {404: "not_found", 405: "method_not_allowed", 413: "file_too_large"}
            msg = "That request was too large." if e.code == 413 else (e.description or "Request failed.")
            return jsonify({"error": {"code": codes.get(e.code, "http_error"), "message": msg}}), e.code
        if e.code == 404:
            return send_from_directory(app.config["FRONTEND_DIR"], "404.html"), 404
        return e

    @app.errorhandler(Exception)
    def server_error(e):
        app.logger.exception("Unhandled error")
        g.db_failed = True
        return jsonify({"error": {"code": "server_error", "message": "Something went wrong on our side. Try again."}}), 500

    # ---- the web pages: only real pages and the assets folder are served
    @app.get("/")
    def index():
        return send_from_directory(app.config["FRONTEND_DIR"], "index.html")

    # offline support: the service worker must be served from the site root to control every page
    @app.get("/sw.js")
    def service_worker():
        resp = send_from_directory(app.config["FRONTEND_DIR"], "sw.js", mimetype="text/javascript")
        resp.headers["Cache-Control"] = "no-cache"          # always check for a new version
        return resp

    @app.get("/manifest.webmanifest")
    def manifest():
        return send_from_directory(app.config["FRONTEND_DIR"], "manifest.webmanifest", mimetype="application/manifest+json")

    @app.get("/<path:path>")
    def files(path):
        if PAGE.match(path) or (ASSET.match(path) and ".." not in path):
            resp = send_from_directory(app.config["FRONTEND_DIR"], path)
            if path.startswith("assets/"):
                resp.headers["Cache-Control"] = "public, max-age=3600"
            return resp
        abort(404)

    return app
