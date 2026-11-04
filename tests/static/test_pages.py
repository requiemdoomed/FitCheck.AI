"""
The pages and scripts the Flask server serves: every page, link and asset is
there, the security policy is current, scripts only talk to their own server
(plus Open-Meteo for the weather button), no secrets ship, and the shared
catalogue/colour maths match the Python reference.
"""

import json
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml"))
sys.path.insert(0, str(ROOT / "scripts"))

from fitcheck_ml import catalog, color  # noqa: E402
import build_sw  # noqa: E402
import update_csp  # noqa: E402

PAGES = sorted(ROOT.glob("*.html"))
NODE = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def test_all_pages_present():
    names = {p.name for p in PAGES}
    for want in ("index.html", "login.html", "register.html", "dashboard.html", "wardrobe.html",
                 "outfit-generator.html", "outfit.html", "saved-outfits.html", "smart-buys.html",
                 "history.html", "profile.html", "404.html", "privacy.html", "terms.html",
                 "forgot-password.html", "reset-password.html", "offline.html"):
        assert want in names


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_page_has_a_current_csp(page):
    html = page.read_text(encoding="utf-8")
    assert html.count("Content-Security-Policy") == 1
    assert update_csp.expected_meta(update_csp.META.sub("", html)).strip() in html, \
        f"{page.name}: inline script changed; run python scripts/update_csp.py"
    assert "localhost:5000" not in html
    # the only off-site address: Open-Meteo for the weather button (photos are made by the server)
    offsite = set(re.findall(r"https://[^\s;'\"]+", update_csp.policy([])))
    assert offsite == {"https://api.open-meteo.com"}


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_every_local_link_and_asset_exists(page):
    html = page.read_text(encoding="utf-8")
    for ref in re.findall(r'(?:href|src)="([^"#?]+)', html):
        if re.match(r"^(https?:|mailto:|data:|blob:)", ref) or "'" in ref:
            continue
        assert (ROOT / ref).exists(), f"{page.name} -> {ref}"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_no_old_wording_left_behind(page):
    html = page.read_text(encoding="utf-8").lower()
    for word in ("indexeddb", "stays on this device", "never leaves your browser", "api_base", "sketch", "dress the model"):
        assert word not in html, f"{page.name} still mentions {word}"
    assert "swayam shakya" in html


def test_js_imports_resolve():
    """Every relative ES module import in assets/js points at a real file."""
    for js in (ROOT / "assets/js").rglob("*.js"):
        if "vendor" in js.parts:
            continue
        text = js.read_text(encoding="utf-8")
        for ref in re.findall(r'(?:from|import)\s*\(?\s*"(\.{1,2}/[^"]+)"', text):
            assert (js.parent / ref).resolve().exists(), f"{js.relative_to(ROOT)} -> {ref}"


def test_scripts_only_talk_to_their_own_server():
    """Pages call /api on the same origin; the only other address is the weather service."""
    for js in (ROOT / "assets/js").rglob("*.js"):
        if "vendor" in js.parts:
            continue
        text = js.read_text(encoding="utf-8")
        assert "localhost:" not in text, js
        urls = set(re.findall(r"https://[a-z0-9.-]+", text)) - {"https://www.w3.org"}
        if js.name == "weather.js":
            assert urls == {"https://api.open-meteo.com"}
        else:
            assert not urls, f"{js.name}: {urls}"
    for gone in ("local/backend.js", "local/db.js", "local/vault.js", "local/openphoto.js", "local/photoreal.js"):
        assert not (ROOT / "assets/js" / gone).exists(), gone


def test_api_client_sends_csrf_and_same_origin_cookies():
    text = (ROOT / "assets/js/api.js").read_text(encoding="utf-8")
    assert '"X-CSRF-Token"' in text and 'credentials: "same-origin"' in text
    assert "localStorage" not in text and "sessionStorage" not in text       # no tokens in page storage


def _js_catalog():
    text = (ROOT / "assets/js/lib/catalog.js").read_text(encoding="utf-8")
    block = re.search(r"/\* catalog-json-start \*/(.*?)/\* catalog-json-end \*/", text, re.S).group(1)
    return json.loads(block)


def test_frontend_catalog_matches_reference():
    js = _js_catalog()
    opts = catalog.options()
    for key in ("categories", "styles", "occasions", "seasons", "weather", "palettes", "subcategories"):
        assert js[key] == opts[key], key
    assert js["colors"] == color.NAMED_COLORS


@NODE
def test_js_and_python_colour_maths_agree():
    rng = random.Random(7)
    hexes = ["#%06x" % rng.randrange(0, 0xFFFFFF) for _ in range(60)]
    pairs = list(zip(hexes[::2], hexes[1::2]))
    script = f"""
      import {{ deltaE2000, hexToLab, pairHarmony, isNeutral }} from "{(ROOT / 'assets/js/lib/color.js').as_posix()}";
      const pairs = {json.dumps(pairs)};
      console.log(JSON.stringify(pairs.map(([a, b]) => [deltaE2000(hexToLab(a), hexToLab(b)),
        pairHarmony(a, b).kind, isNeutral(hexToLab(a))])));
    """
    out = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, check=True)
    js = json.loads(out.stdout)
    for (a, b), (de, kind, neutral) in zip(pairs, js):
        assert de == pytest.approx(color.delta_e(a, b), abs=1e-6)
        assert kind == color.pair_harmony(a, b)[1]
        assert neutral == color.is_neutral(a)


def test_models_ship_for_the_server_and_cutout_model_for_the_browser():
    meta = json.loads((ROOT / "ml/models/model_metadata.json").read_text())
    assert meta["feature_names"] and list((ROOT / "ml/models").glob("*.joblib"))
    assert not (ROOT / "assets/models/taste_models.json").exists()
    assert (ROOT / "assets/models/u2netp.onnx").stat().st_size > 1_000_000
    assert (ROOT / "assets/vendor/ort/ort-wasm-simd-threaded.wasm").exists()


def test_no_file_too_big_for_pages():
    for f in ROOT.joinpath("assets").rglob("*"):
        if f.is_file():
            assert f.stat().st_size < 50 * 1024 * 1024, f


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_page_security_basics(page):
    html = page.read_text(encoding="utf-8")
    assert '<meta name="referrer" content="no-referrer">' in html
    assert "clickjacking" in html                              # the frame-buster runs before paint
    policy = re.search(r'Content-Security-Policy" content="([^"]+)"', html).group(1)
    for directive in ("object-src 'none'", "base-uri 'self'", "form-action 'self'", "frame-src 'none'"):
        assert directive in policy
    assert "'unsafe-eval'" not in policy.replace("'wasm-unsafe-eval'", "")
    assert "script-src 'self' 'wasm-unsafe-eval' 'sha256-" in policy   # no inline scripts beyond the hashed one
    if page.name not in ("404.html",):
        assert 'href="privacy.html"' in html, f"{page.name} doesn't link the privacy policy"


def test_deployment_blueprint():
    """Render runs the server with gunicorn; secrets are generated or entered, never committed."""
    text = (ROOT / "render.yaml").read_text()
    assert "gunicorn" in text and "wsgi:app" in text and "generateValue: true" in text
    assert "DB_PASSWORD" in text and "sync: false" in text
    for key in ("APP_URL", "SMTP_HOST", "SMTP_PASSWORD", "MAIL_FROM"):
        assert f"key: {key}" in text and f"{key}=" in (ROOT / ".env.example").read_text()
    assert not (ROOT / ".env").exists()
    example = (ROOT / ".env.example").read_text()
    assert re.search(r"^SECRET_KEY=$", example, re.M) and re.search(r"^DB_PASSWORD=$", example, re.M)


def test_no_secrets_or_tracking_in_the_site():
    """No API keys, analytics or third-party scripts ship with the app."""
    patterns = [r"AIza[0-9A-Za-z_-]{30,}", r"sk_[0-9A-Za-z]{20,}", r"gtag\(", r"google-analytics", r"googletagmanager",
                r"facebook\.net", r"hotjar"]
    files = list(ROOT.glob("*.html")) + [p for p in (ROOT / "assets/js").rglob("*.js") if "vendor" not in p.parts]
    files += list((ROOT / "backend").glob("*.py")) + [ROOT / "render.yaml"]
    for f in files:
        text = f.read_text(encoding="utf-8")
        for pat in patterns:
            assert not re.search(pat, text), f"{f.name}: {pat}"
    # the only cookie the page itself touches is clearing fc_csrf on sign-out (the server sets both)
    for f in files:
        if f.suffix == ".js":
            for m in re.findall(r"document\.cookie\s*=\s*([^\n]+)", f.read_text(encoding="utf-8")):
                assert m.startswith('"fc_csrf=; Max-Age=0'), f"{f.name}: {m}"


def test_offline_support_is_current_and_never_caches_private_data():
    sw = (ROOT / "sw.js").read_text(encoding="utf-8")
    assert sw == build_sw.render(), "an app file changed; run python scripts/build_sw.py"
    shell = json.loads(re.search(r"const SHELL = (\[.*?\]);", sw, re.S).group(1))
    assert all((ROOT / f).is_file() for f in shell)
    assert not any(f.startswith(("api", "backend", "ml", "tests")) or f.endswith((".py", ".env")) for f in shell)
    assert {"offline.html", "index.html", "assets/js/api.js", "assets/css/app.css"} <= set(shell)
    assert '!url.pathname.startsWith("/api/")' in sw and 'request.method === "GET"' in sw
    m = json.loads((ROOT / "manifest.webmanifest").read_text())
    assert m["start_url"] == "/dashboard.html" and m["display"] == "standalone"
    assert {i["sizes"] for i in m["icons"]} == {"192x192", "512x512"} and any(i.get("purpose") == "maskable" for i in m["icons"])
    from PIL import Image
    for icon in m["icons"]:
        w, h = Image.open(ROOT / icon["src"].lstrip("/")).size
        assert f"{w}x{h}" == icon["sizes"]
    for page in PAGES:
        assert 'rel="manifest" href="manifest.webmanifest"' in page.read_text(encoding="utf-8"), page.name
