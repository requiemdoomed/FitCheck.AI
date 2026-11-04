"""
Adds (or refreshes) a Content-Security-Policy <meta> tag on every page.

The policy also lives in the HTML as a backstop (and for saved copies of a page).
Inline scripts (the tiny theme-before-paint snippet) are allowed by their
SHA-256 hash, so if you edit one, run this again:

    python scripts/update_csp.py

tests/static/test_pages.py checks the hashes are current.

The FitCheck.AI server sends the same policy as a header (backend/app.py
builds it from these hashes); the meta tag keeps pages safe if they're ever
opened from a plain static host. The only off-site address is Open-Meteo for
the weather button; photos come from the app's own server. The cut-out model
needs 'wasm-unsafe-eval' to compile its WebAssembly.
"""

import base64
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INLINE_SCRIPT = re.compile(r"<script>(.*?)</script>", re.S)
META = re.compile(r'\n  <meta http-equiv="Content-Security-Policy"[^>]*>')


WEATHER = "https://api.open-meteo.com"


def policy(hashes):
    script = " ".join(["'self'", "'wasm-unsafe-eval'"] + [f"'sha256-{h}'" for h in hashes])
    return "; ".join([
        "default-src 'self'",
        f"script-src {script}",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob:",
        "font-src 'self'",
        f"connect-src 'self' {WEATHER}",
        "worker-src 'self' blob:",
        "frame-src 'none'",
        "media-src 'self' blob:",
        "manifest-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
    ])


def script_hashes(html):
    return [base64.b64encode(hashlib.sha256(m.encode("utf-8")).digest()).decode()
            for m in INLINE_SCRIPT.findall(html)]


def expected_meta(html):
    return f'\n  <meta http-equiv="Content-Security-Policy" content="{policy(script_hashes(html))}">'


REFERRER = '\n  <meta name="referrer" content="no-referrer">'


def main():
    for page in sorted(ROOT.glob("*.html")):
        html = page.read_text(encoding="utf-8")
        html = META.sub("", html)
        html = html.replace(REFERRER, "")
        # no Referer header to the photo and weather services, or anywhere else
        html = html.replace('<meta charset="utf-8">', '<meta charset="utf-8">' + expected_meta(html) + REFERRER, 1)
        page.write_text(html, encoding="utf-8")
        print(f"{page.name}: {len(script_hashes(html))} inline script(s) allowed")


if __name__ == "__main__":
    main()
