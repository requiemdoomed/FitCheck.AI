"""
One person's journey through FitCheck.AI in a real browser, step by step,
against the real Flask server and MySQL database. The steps share a browser
session and run in order. Photo services are a local fake the server calls.
"""

import io
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, unquote, urlparse

import pytest
from PIL import Image
from playwright.sync_api import expect

import conftest
from conftest import fake, mails, sql

EMAIL = "e2e.tester@example.com"
PASSWORD = "Wardrobe-2026"
NAME = "Swayam Tester"

console_problems = []

ROOT = Path(__file__).resolve().parents[2]


def poll(page, js, arg=None, timeout=20):
    """Wait until a JS function returns truthy. Unlike wait_for_function this doesn't
    eval strings inside the page, so it works under the app's strict CSP."""
    import time
    end = time.time() + timeout
    while time.time() < end:
        if page.evaluate(js, arg):
            return
        time.sleep(0.15)
    raise AssertionError(f"timed out waiting for {js}")


def photo_log():
    """Requests the server made to the (fake) photo services, oldest first."""
    return fake("__log")


def last_prompt():
    made = [e for e in photo_log() if e["path"].startswith("/prompt/")]
    return unquote(urlparse(made[-1]["path"]).path)


def fake_photo_services(context):
    """Kept for readability: photo requests now leave from the server, not the browser."""
    return context


def _photo(tmp_path, colour=(240, 240, 236), name="shirt.jpg"):
    img = Image.new("RGB", (480, 600), (238, 240, 243))
    from PIL import ImageDraw
    ImageDraw.Draw(img).polygon([(120, 80), (360, 80), (420, 200), (360, 220), (360, 540), (120, 540),
                                 (120, 220), (60, 200)], fill=colour, outline=(31, 42, 68))
    path = tmp_path / name
    img.save(path, "JPEG")
    return path


@pytest.fixture(scope="module")
def ctx(servers, chrome):
    # Playwright's wait_for_function evaluates strings, which our CSP (rightly)
    # blocks; the journey bypasses CSP and test_18 checks the policy separately.
    context = fake_photo_services(chrome.new_context(viewport={"width": 1366, "height": 900}, bypass_csp=True))
    context.set_default_timeout(10000)
    page = context.new_page()

    def on_console(msg):
        if msg.type != "error":
            return
        # Chrome logs every 4xx response; the journey triggers some on purpose
        if re.search(r"status of 4\d\d", msg.text):
            return
        console_problems.append(f"{page.url}: {msg.text}")

    page.on("console", on_console)
    page.on("pageerror", lambda e: console_problems.append(f"{page.url}: uncaught {e}"))
    yield {"page": page, "base": servers["base"], "context": context}
    context.close()


def go(c, path):
    c["page"].goto(c["base"] + path)


# ---------------------------------------------------------------- public pages

def test_01_landing_page_demo_and_theme(ctx):
    p = ctx["page"]
    go(ctx, "index.html")
    assert "FitCheck.AI" in p.title()
    p.wait_for_function("document.querySelector('[data-score]').textContent.trim() !== '–'")
    before = p.text_content('[data-slot="top"] .strip__name')
    p.click('[data-slot="top"] [data-step="1"]')
    assert p.text_content('[data-slot="top"] .strip__name') != before
    score = int(p.text_content("[data-score]"))
    assert 0 <= score <= 100
    assert "Swayam Shakya" in p.text_content("footer")
    p.wait_for_function("document.querySelector('[data-api-status]').dataset.state === 'up'")

    # every stylesheet and script actually loaded under the sub-path
    broken = p.evaluate("""() => [...document.styleSheets].filter(s => { try { return !s.cssRules.length } catch { return true } }).length""")
    assert broken == 0
    assert p.evaluate("document.fonts.check('16px Bungee')")
    assert p.evaluate("document.fonts.check('16px Rubik')")
    # the model on the landing page wears the pieces, the patterned shirt in its real fabric
    # the mixer shows the real garment photos, and "See it on a person" makes an AI photo
    p.wait_for_selector(".mixer .flatlay img")
    assert p.locator("svg.outfit-render").count() == 0            # no drawn models anywhere
    p.click("[data-wear]")
    p.wait_for_selector(".stage-photo__img")
    assert any(e["path"].startswith("/prompt/") for e in photo_log())
    # the lookbook of colour pairings fills with photos as it scrolls into view
    p.locator(".pairings").scroll_into_view_if_needed()
    p.wait_for_function("document.querySelectorAll('.pairings .look--photo img').length === 4", timeout=20000)
    assert "light blue / navy" in p.text_content(".pairings .look__caption").lower()

    p.click("[data-theme-toggle]")
    theme = p.evaluate("document.documentElement.dataset.theme")
    p.reload()
    assert p.evaluate("document.documentElement.dataset.theme") == theme
    assert p.evaluate("localStorage.getItem('fitcheck.theme')") == theme
    p.click("[data-theme-toggle]")  # back to light for the screenshots that follow


def test_02_protected_pages_redirect_to_login(ctx):
    p = ctx["page"]
    go(ctx, "dashboard.html")
    p.wait_for_url(re.compile(r"login\.html\?next=dashboard\.html"))


def test_03_register_validation_and_account_creation(ctx):
    p = ctx["page"]
    go(ctx, "register.html")
    p.click("button[type=submit]")
    assert p.locator(".field__error").count() == 3
    p.fill("#r-name", NAME)
    p.fill("#r-email", EMAIL)
    p.fill("#r-pass", "short")
    p.click("button[type=submit]")
    assert "8 characters" in p.text_content('[data-error-for="password"]')
    p.fill("#r-pass", PASSWORD)
    p.click("[data-pw-toggle]")
    assert p.get_attribute("#r-pass", "type") == "text"
    p.click("button[type=submit]")
    p.wait_for_url(re.compile(r"wardrobe\.html"))
    p.wait_for_selector("[data-demo]")                 # empty rail offers the demo wardrobe
    assert p.text_content("[data-user-name]") == NAME
    # the session lives in an HttpOnly cookie the page can't read; only the CSRF token is visible
    cookies = {c["name"]: c for c in ctx["context"].cookies()}
    assert cookies["fc_session"]["httpOnly"] and cookies["fc_session"]["sameSite"] == "Lax"
    assert not cookies["fc_csrf"]["httpOnly"] and cookies["fc_csrf"]["sameSite"] == "Strict"
    assert "fc_session" not in p.evaluate("document.cookie")
    assert p.evaluate("Object.keys(localStorage).filter((k) => k !== 'fitcheck.theme').length") == 0


def _add_item(p, name, category, sub, colour_hex, style, seasons, occasions, photo=None):
    if not p.is_visible("#item-dialog[open]"):
        p.click("[data-add-item]")
        p.wait_for_selector("#item-dialog[open]")
    p.fill("#item-name", name)
    p.check(f'[name="category"][value="{category}"]', force=True)
    p.fill("#item-sub", sub)
    p.select_option("#item-style", style)
    p.check(f'[name="main_color"][value="{colour_hex}"]', force=True)
    for s in seasons:
        p.check(f'[name="seasons"][value="{s}"]', force=True)
    for o in occasions:
        p.check(f'[name="occasions"][value="{o}"]', force=True)
    if photo:
        p.set_input_files("#item-image", str(photo))
        p.wait_for_selector("[data-preview] img")
    p.click("[data-submit]")
    # a photo is cut out in the browser first (WebAssembly, one thread): allow for a busy machine
    p.wait_for_selector("#item-dialog", state="hidden", timeout=60000 if photo else 10000)
    p.locator(".item-card", has_text=name).first.wait_for()


def test_04_add_items_with_validation_and_photo(ctx, tmp_path_factory):
    p = ctx["page"]
    # empty form shows every problem at once
    p.click("[data-add-item]")
    p.wait_for_selector("#item-dialog[open]")
    p.click("[data-submit]")
    errors = p.locator("#item-dialog .field__error")
    assert errors.count() >= 6
    assert p.is_visible("#item-dialog[open]")

    photo = _photo(tmp_path_factory.mktemp("img"))
    _add_item(p, "White oxford shirt", "top", "shirt", "#f5f5f2", "classic",
              ["spring", "summer", "autumn"], ["work", "college", "date"], photo=photo)
    img = p.locator('.item-card:has-text("White oxford shirt") img')
    img.wait_for()
    p.wait_for_function("(el) => el.complete && el.naturalWidth > 0", arg=img.element_handle())
    assert img.get_attribute("src").startswith("api/images/")
    # cut out of its background in the browser (U2-Net-p via WebAssembly), then stored on the server
    items = p.evaluate("() => import('./assets/js/api.js').then((m) => m.api.wardrobe.list()).then((r) => r.items)")
    shirt = next(i for i in items if i["name"] == "White oxford shirt")
    assert shirt["cutout_url"].startswith("api/images/")

    _add_item(p, "Navy chinos", "bottom", "chinos", "#1f2a4a", "smart_casual",
              ["spring", "autumn", "winter"], ["work", "college", "casual"])
    _add_item(p, "Brown loafers", "footwear", "loafers", "#6b4428", "classic",
              ["spring", "summer", "autumn", "winter"], ["work", "date"])
    _add_item(p, "Trench coat", "outerwear", "trench coat", "#b8a77a", "classic",
              ["spring", "autumn"], ["work", "travel"])
    _add_item(p, "Orange tee", "top", "t-shirt", "#e2702f", "streetwear",
              ["summer"], ["casual"])
    assert p.text_content("[data-count]") == "5 pieces"


def test_05_search_and_filters(ctx):
    p = ctx["page"]
    p.fill("#f-q", "oxford")
    p.wait_for_function("document.querySelector('[data-count]').textContent === '1 piece'")
    p.click("button[type=reset]")
    p.wait_for_function("document.querySelector('[data-count]').textContent === '5 pieces'")
    p.click('[data-cat="footwear"]')
    p.wait_for_function("document.querySelector('[data-count]').textContent === '1 piece'")
    assert p.is_visible('.item-card:has-text("Brown loafers")')
    p.click('[data-cat=""]')
    p.wait_for_function("document.querySelector('[data-count]').textContent === '5 pieces'")
    p.select_option("#f-color", "navy")
    p.wait_for_selector('.item-card:has-text("Brown loafers")', state="detached")
    p.wait_for_function("document.querySelector('[data-count]').textContent === '1 piece'")
    assert p.is_visible('.item-card:has-text("Navy chinos")')
    p.select_option("#f-color", "")
    p.select_option("#f-season", "winter")
    p.wait_for_function("document.querySelector('[data-count]').textContent === '2 pieces'")
    p.select_option("#f-season", "")
    p.fill("#f-q", "zzz-no-match")
    p.wait_for_selector(".empty-state:has-text('Nothing matches')")
    p.fill("#f-q", "")
    p.wait_for_function("document.querySelector('[data-count]').textContent === '5 pieces'")


def test_06_edit_and_remove_item(ctx):
    p = ctx["page"]
    p.click('.item-card:has-text("Navy chinos") [data-edit]')
    p.wait_for_selector("#item-dialog[open]")
    assert p.input_value("#item-name") == "Navy chinos"
    assert p.is_checked('[name="occasions"][value="work"]')
    p.fill("#item-name", "Navy slim chinos")
    p.click("[data-submit]")
    p.wait_for_selector('.item-card:has-text("Navy slim chinos")')

    p.click('.item-card:has-text("Orange tee") [data-delete]')
    p.click('dialog[open] [value="ok"]')
    p.wait_for_function("document.querySelector('[data-count]').textContent === '4 pieces'")
    assert not p.is_visible('.item-card:has-text("Orange tee")')


def test_07_generate_like_save_and_another(ctx):
    p = ctx["page"]
    p.click('.app-nav a[href="outfit-generator.html"]')
    p.wait_for_selector("[data-gen-form]")
    p.check('[name="occasion"][value="work"]', force=True)
    p.check('[name="weather"][value="rainy"]', force=True)
    p.fill("[data-temp]", "10")
    p.dispatch_event("[data-temp]", "input")
    assert p.text_content("[data-temp-readout]") == "10°C"
    p.click("[data-generate]")
    p.wait_for_selector(".outfit .rail-item")

    # the outfit is drawn on the model, wearing the pieces it lists
    # ...and arrives as a realistic photo from the free engine, no setup needed
    p.wait_for_selector(".outfit-photo__img")
    names = p.locator(".rail-item .swing-tag__name").all_text_contents()
    assert all(n in p.get_attribute(".outfit-photo__img", "alt") for n in names)
    assert "Pollinations" in p.text_content(".outfit-photo__label")
    prompt = last_prompt()
    assert "trench coat" in prompt and "cropped at the chin" in prompt
    with p.expect_download() as dl:
        p.click("[data-download-look]")
    assert dl.value.suggested_filename.endswith(".jpg")
    owned = {"White oxford shirt", "Navy slim chinos", "Brown loafers", "Trench coat"}
    assert set(names) <= owned
    assert "Trench coat" in names            # 10°C and rain needs the coat
    assert "Orange tee" not in names         # removed items never come back
    score = int(p.text_content(".outfit .tape-readout__number"))
    assert 0 <= score <= 100
    assert p.locator(".outfit .care-label__row").count() >= 5
    assert len(p.text_content(".outfit__why")) > 40

    p.click('[data-feedback="like"]')
    p.wait_for_selector('[data-feedback="like"][aria-pressed="true"]')
    p.click("[data-save]")
    p.fill("#save-name", "Rainy Monday")
    p.click('dialog[open] [value="ok"]')
    p.wait_for_selector('[data-save][aria-pressed="true"]')

    first_id = p.get_attribute(".outfit", "data-outfit-id")
    p.click("[data-another]")
    p.wait_for_function(
        "(id) => { const o = document.querySelector('.outfit'); const n = document.querySelector('.notice');"
        " return (o && o.dataset.outfitId !== id) || (n && /every combination/.test(n.textContent)); }",
        arg=first_id)


def test_08_saved_and_single_outfit_pages(ctx):
    p = ctx["page"]
    p.click('.app-nav a[href="saved-outfits.html"]')
    p.wait_for_selector('.outfit-card:has-text("Rainy Monday")')
    p.click('.outfit-card:has-text("Rainy Monday") a:has-text("View")')
    p.wait_for_url(re.compile(r"outfit\.html\?id=\d+"))
    p.wait_for_selector(".outfit .rail-item")
    assert p.text_content("[data-outfit-title]") == "Rainy Monday"
    assert p.get_attribute('[data-feedback="like"]', "aria-pressed") == "true"
    p.click("[data-back]")
    p.wait_for_url(re.compile(r"saved-outfits\.html"))
    p.click('.outfit-card:has-text("Rainy Monday") [data-unsave]')
    p.click('dialog[open] [value="ok"]')
    p.wait_for_selector(".empty-state:has-text('Nothing saved yet')")

    go(ctx, "outfit.html?id=999999")
    p.wait_for_selector(".empty-state:has-text(\"That outfit isn't here\")")


def test_09_history_filter_and_inline_feedback(ctx):
    p = ctx["page"]
    go(ctx, "history.html")
    p.wait_for_selector(".outfit-card")
    total = p.locator(".outfit-card").count()
    assert total >= 1
    p.click('[data-history-filter] [data-verdict="like"]')
    p.wait_for_function("document.querySelectorAll('.outfit-card').length === 1")
    assert "verdict=like" in p.url
    p.click('[data-history-filter] [data-verdict=""]')
    p.wait_for_function(f"document.querySelectorAll('.outfit-card').length === {total}")
    if total > 1:
        last = p.locator(".outfit-card").nth(0)
        last.locator('[data-fb="dislike"]').click()
        p.wait_for_selector('.outfit-card [data-fb="dislike"][aria-pressed="true"]')


def test_10_dashboard(ctx):
    p = ctx["page"]
    go(ctx, "dashboard.html")
    p.wait_for_selector(".ledger")
    assert p.text_content(".ledger__cell:first-child .ledger__value") == "4"
    assert re.match(r"(Good|Up)", p.text_content("[data-greeting]"))
    p.wait_for_function("document.querySelectorAll('canvas[data-chart]').length === 4")
    p.wait_for_function("[...document.querySelectorAll('canvas[data-chart]')].every(c => c.width > 0)")
    assert p.locator(".dash-grid .outfit-card").count() >= 1


def test_11_profile_and_preferences(ctx):
    p = ctx["page"]
    go(ctx, "profile.html")
    p.wait_for_selector("[data-profile]:not([hidden])")
    p.fill("#p-name", "Swayam S.")
    p.click('[data-form="account"] button[type=submit]')
    p.wait_for_function("document.querySelector('[data-user-name]').textContent === 'Swayam S.'")
    p.click(".toast__close")                       # toasts sit bottom-right, over the swatches
    p.wait_for_selector(".toast", state="detached")

    p.check('[name="preferred_styles"][value="classic"]', force=True)
    p.check('[name="preferred_palette"][value="neutral"]', force=True)
    p.check('[name="favorite_colors"][value="navy"]', force=True)
    p.check('[name="avoided_colors"][value="navy"]', force=True)          # unticks the favourite
    assert not p.is_checked('[name="favorite_colors"][value="navy"]')
    p.select_option("#p-unit", "F")
    p.click('[data-form="preferences"] button[type=submit]')
    p.wait_for_selector(".toast:has-text('Preferences saved')")

    p.fill("#p-current", "wrong-password-1")
    p.fill("#p-new", "Another-pass-9")
    p.click('[data-form="password"] button[type=submit]')
    p.wait_for_selector("[data-error-for='current_password']")

    # the unit preference reaches the generator
    go(ctx, "outfit-generator.html")
    p.wait_for_selector("[data-temp-readout]")
    assert p.text_content("[data-temp-readout]").endswith("°F")


def test_12_phone_layout(ctx):
    p = ctx["page"]
    p.set_viewport_size({"width": 390, "height": 844})
    for page in ("dashboard.html", "wardrobe.html", "outfit-generator.html", "saved-outfits.html",
                 "smart-buys.html", "history.html", "profile.html", "index.html"):
        go(ctx, page)
        p.wait_for_load_state("networkidle")
        if page != "index.html":
            p.wait_for_selector("[data-shell-tabbar] a")
            assert p.is_visible(".tabbar"), page
            assert p.locator(".tabbar a").count() == 6
            assert not p.is_visible(".app-nav"), page
        overflow = p.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        assert overflow <= 0, f"{page} scrolls sideways by {overflow}px"
    go(ctx, "wardrobe.html")
    p.click("[data-add-item]")
    p.wait_for_selector("#item-dialog[open]")
    box = p.locator("#item-dialog").bounding_box()
    assert box["width"] <= 390
    p.click("#item-dialog [data-close] >> nth=0")
    p.set_viewport_size({"width": 1366, "height": 900})


def test_13_sign_out_and_back_in(ctx):
    p = ctx["page"]
    go(ctx, "dashboard.html")
    p.wait_for_selector(".account-menu")
    p.click(".account-menu summary")
    p.click("[data-sign-out]")
    p.wait_for_url(re.compile(r"login\.html\?reason=signed_out"))
    assert "signed out" in p.text_content("[data-auth-notice]")
    go(ctx, "history.html")
    p.wait_for_url(re.compile(r"login\.html\?next=history\.html"))

    p.fill("#a-email", EMAIL)
    p.fill("#a-pass", "not-my-password-1")
    p.click("button[type=submit]")
    p.wait_for_selector("[data-auth-notice] .notice--error")

    p.fill("#a-pass", PASSWORD)
    p.click("button[type=submit]")
    p.wait_for_url(re.compile(r"history\.html"))


def test_14_login_never_redirects_off_site(ctx):
    p = ctx["page"]
    ctx["context"].clear_cookies()
    go(ctx, "login.html?next=https://evil.example/phish")
    p.fill("#a-email", EMAIL)
    p.fill("#a-pass", PASSWORD)
    p.click("button[type=submit]")
    p.wait_for_url(re.compile(r"dashboard\.html$"))


def test_15_no_console_errors_during_the_journey(ctx):
    assert console_problems == []


def test_16_the_account_works_from_another_device(ctx, chrome):
    """Another browser profile is another device: the same account and wardrobe are there."""
    other = chrome.new_context()
    page = other.new_page()
    page.goto(ctx["base"] + "login.html")
    page.fill("#a-email", EMAIL)
    page.fill("#a-pass", PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_url(re.compile(r"dashboard\.html"))
    page.goto(ctx["base"] + "wardrobe.html")
    page.wait_for_selector(".item-card img")
    assert page.text_content("[data-count]") == "4 pieces"
    other.close()


def test_17_backup_moves_a_wardrobe_to_another_device(ctx, chrome, tmp_path_factory):
    p = ctx["page"]
    go(ctx, "profile.html")
    p.wait_for_selector("[data-profile]:not([hidden])")
    # a backup holds everything, so it asks for the password; a wrong one is refused
    p.click("[data-export]")
    p.fill("#reauth-pw", "not-my-password-1")
    p.click('dialog[open] [value="ok"]')
    p.wait_for_selector(".toast:has-text('password')")
    p.click("[data-export]")
    p.fill("#reauth-pw", PASSWORD)
    with p.expect_download() as dl:
        p.click('dialog[open] [value="ok"]')
    path = tmp_path_factory.mktemp("backup") / "backup.json"
    dl.value.save_as(path)
    import json
    data = json.loads(path.read_text())
    assert data["format"] == "fitcheck-backup"
    assert len([i for i in data["items"] if not i["deleted_at"]]) == 4      # + the removed tee, kept for history
    assert all(v.startswith("data:image/") for v in data["images"].values())

    other = fake_photo_services(chrome.new_context(bypass_csp=True))
    page = other.new_page()
    page.goto(ctx["base"] + "register.html")
    page.fill("#r-name", "New Phone")
    page.fill("#r-email", "phone@example.com")
    page.fill("#r-pass", PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_url(re.compile(r"wardrobe\.html"))
    page.goto(ctx["base"] + "profile.html")
    page.wait_for_selector("[data-profile]:not([hidden])")
    page.set_input_files("[data-import]", str(path))
    page.click('dialog[open] [value="ok"]')
    page.wait_for_selector(".toast:has-text('Restored 4 pieces')")
    page.goto(ctx["base"] + "wardrobe.html")
    page.wait_for_selector('.item-card:has-text("White oxford shirt") img')
    assert page.text_content("[data-count]") == "4 pieces"
    other.close()


def test_18_content_security_policy_allows_the_app_and_nothing_breaks(ctx, chrome):
    """Every page under the real CSP: no violations, no errors, content renders."""
    context = fake_photo_services(chrome.new_context(viewport={"width": 1280, "height": 900}))
    page = context.new_page()
    problems = []
    page.on("console", lambda m: problems.append(m.text) if m.type == "error" and "status of 4" not in m.text else None)
    page.on("pageerror", lambda e: problems.append(str(e)))
    base = ctx["base"]
    # a new browser profile is a new device, so it needs its own account
    page.goto(base + "register.html")
    page.fill("#r-name", "CSP Check")
    page.fill("#r-email", "csp@example.com")
    page.fill("#r-pass", PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_selector("[data-demo]")
    page.click("[data-demo]")
    page.wait_for_selector(".item-card img", timeout=60000)
    page.goto(base + "outfit-generator.html")
    page.click("[data-generate]")
    page.wait_for_selector(".outfit .rail-item")
    checks = {
        "index.html": ".mixer .flatlay img",
        "dashboard.html": "canvas[data-chart]",
        "wardrobe.html": ".item-card img",
        "outfit-generator.html": "[data-gen-form] .chip",
        "saved-outfits.html": "[data-saved] .empty-state, [data-saved] .outfit-card",
        "smart-buys.html": ".shop-card .shop-card__product",
        "history.html": ".outfit-card",
        "profile.html": "[data-profile]:not([hidden])",
        "404.html": ".lost h1",
    }
    for path, selector in checks.items():
        page.goto(base + path)
        page.wait_for_selector(selector)
    page.goto(base + "outfit-generator.html")
    page.click("[data-generate]")
    page.wait_for_selector(".outfit .rail-item")
    # the cut-out model compiles WebAssembly under the policy
    ok = page.evaluate("() => import('./assets/js/local/images.js').then((m) => m.cutoutModel()).then((s) => Boolean(s))")
    assert ok
    assert page.evaluate("document.documentElement.dataset.theme || 'unset'") in ("light", "dark", "unset")
    assert problems == [], problems
    context.close()


def test_19_user_text_is_never_run_as_html(ctx):
    p = ctx["page"]
    go(ctx, "wardrobe.html")
    p.wait_for_selector(".item-card")
    evil = '<img src=x onerror="window.__xss=1">Bold 😀 <b>tee</b>'
    _add_item(p, evil, "top", "t-shirt", "#c42b2b", "streetwear", ["summer"], ["casual"])
    card = p.locator(".item-card", has_text="Bold 😀")
    assert evil in card.locator(".swing-tag__name").text_content()
    assert p.evaluate("window.__xss === undefined")
    assert p.locator('.item-card img[src="x"]').count() == 0
    card.locator("[data-delete]").click()
    p.click('dialog[open] [value="ok"]')
    p.wait_for_selector('.item-card:has-text("Bold 😀")', state="detached")


def test_20_big_phone_photo_is_shrunk_before_upload(ctx, tmp_path_factory):
    """A 12-megapixel, >5 MB phone photo is shrunk before it's stored."""
    import numpy as np
    p = ctx["page"]
    rng = np.random.default_rng(1)
    pixels = np.clip(rng.normal(128, 60, (4000, 3000, 3)), 0, 255).astype("uint8")
    path = tmp_path_factory.mktemp("big") / "phone.jpg"
    Image.fromarray(pixels).save(path, "JPEG", quality=95)
    assert path.stat().st_size > 5 * 1024 * 1024

    go(ctx, "wardrobe.html")
    p.wait_for_selector(".item-card")
    _add_item(p, "Phone photo jacket", "outerwear", "denim jacket", "#3c5a8a", "streetwear",
              ["spring"], ["casual"], photo=path)
    img = p.locator(".item-card", has_text="Phone photo jacket").locator("img")
    img.wait_for()
    p.wait_for_function("(el) => el.complete && el.naturalWidth > 0", arg=img.element_handle())
    assert p.evaluate("(el) => el.naturalWidth", img.element_handle()) <= 900



def test_21_no_photo_gets_a_real_dyed_garment(ctx):
    """Typing 'black hoodie' without a photo shows a real hoodie picture, not a drawing."""
    p = ctx["page"]
    go(ctx, "wardrobe.html")
    p.wait_for_selector(".item-card")
    _add_item(p, "Black hoodie", "top", "hoodie", "#1b1b1d", "streetwear", ["autumn", "winter"], ["casual"])
    img = p.locator(".item-card", has_text="Black hoodie").locator(".pic--cut img")
    img.wait_for()
    p.wait_for_function("(el) => el.complete && el.naturalWidth > 100", arg=img.element_handle())
    assert img.get_attribute("src").startswith("api/images/")
    assert p.locator(".item-card", has_text="Black hoodie").locator(".pic--swatch").count() == 0


def test_22_photo_colour_is_suggested(ctx, tmp_path_factory):
    p = ctx["page"]
    go(ctx, "wardrobe.html")
    p.wait_for_selector(".item-card")
    p.click("[data-add-item]")
    p.wait_for_selector("#item-dialog[open]")
    photo = _photo(tmp_path_factory.mktemp("red"), colour=(196, 40, 44), name="red.jpg")
    p.set_input_files("#item-image", str(photo))
    p.wait_for_function("document.querySelector('[data-colour-hint]').textContent.includes('red')")
    assert p.is_checked('[name="main_color"][value="#c42b2b"]')
    p.click("#item-dialog [data-close] >> nth=0")


def test_23_demo_wardrobe_and_smart_buys(ctx, chrome):
    context = fake_photo_services(chrome.new_context(viewport={"width": 1280, "height": 900}))
    p = context.new_page()
    problems = []
    p.on("pageerror", lambda e: problems.append(str(e)))
    p.goto(ctx["base"] + "register.html")
    p.fill("#r-name", "Demo Person")
    p.fill("#r-email", "demo@example.com")
    p.fill("#r-pass", PASSWORD)
    p.click("button[type=submit]")
    p.wait_for_selector("[data-demo]")
    p.click("[data-demo]")
    p.wait_for_selector(".item-card", timeout=60000)
    assert int(p.text_content("[data-count]").split()[0]) >= 30

    p.goto(ctx["base"] + "smart-buys.html")
    p.wait_for_selector(".shop-card .shop-card__product")
    cards = p.locator(".shop-card")
    assert 1 <= cards.count() <= 8
    for t in p.locator(".price-tag").all_text_contents():
        assert int(t.split("–")[0].lstrip("$")) <= 45          # affordable
    assert p.locator(".shop-card .look__caption").first.text_content().count("/") == 1
    first = p.text_content(".shop-card .shop-card__name")
    before = int(p.evaluate("() => import('./assets/js/api.js').then((m) => m.api.wardrobe.list()).then((r) => r.items.length)"))
    p.click(".shop-card [data-add]")
    p.wait_for_selector(f".toast:has-text('added to your wardrobe')")
    after = int(p.evaluate("() => import('./assets/js/api.js').then((m) => m.api.wardrobe.list()).then((r) => r.items.length)"))
    assert after == before + 1
    # the list is worked out again, and the piece is gone: it's owned now
    poll(p, "(n) => ![...document.querySelectorAll('.shop-card__name')].some((e) => e.textContent.includes(n))", first.strip())
    assert problems == []
    context.close()


def test_24_model_preferences_change_the_picture(ctx):
    p = ctx["page"]
    go(ctx, "profile.html")
    p.wait_for_selector("[data-profile]:not([hidden])")
    p.check('[name="model_build"][value="fem"]', force=True)
    p.check('[name="model_skin"][value="deep"]', force=True)
    p.click('[data-form="preferences"] button[type=submit]')
    p.wait_for_selector(".toast:has-text('Preferences saved')")
    go(ctx, "outfit-generator.html")
    p.click("[data-generate]")
    p.wait_for_selector(".outfit-photo__img")
    assert "a woman with deep brown skin" in last_prompt()


def test_25_delete_account_frees_the_email(ctx):
    p = ctx["page"]
    go(ctx, "profile.html")
    p.wait_for_selector("[data-profile]:not([hidden])")
    p.fill("#p-del", PASSWORD)
    p.click('[data-form="delete"] button[type=submit]')
    p.click('dialog[open] [value="ok"]')
    p.wait_for_url(re.compile(r"(index|login|register)\.html"), timeout=30000)
    go(ctx, "register.html")
    p.fill("#r-name", NAME)
    p.fill("#r-email", EMAIL)
    p.fill("#r-pass", PASSWORD)
    p.click("button[type=submit]")
    p.wait_for_url(re.compile(r"wardrobe\.html"))
    p.wait_for_selector("[data-demo]")                 # brand-new, empty wardrobe


def test_26_realistic_photos_free_engine_keys_and_gemini(ctx, chrome):
    """
    The photo engines through the server, with the services replaced by a fake
    that answers like the real ones: the free engine with no account, with a
    free key, and switching to Gemini. Keys stay on the server, sealed.
    """
    context = chrome.new_context(viewport={"width": 1280, "height": 900})
    p = context.new_page()
    problems = []
    p.on("pageerror", lambda e: problems.append(str(e)))
    base = ctx["base"]
    p.goto(base + "register.html")
    p.fill("#r-name", "Photo Person")
    p.fill("#r-email", "photo@example.com")
    p.fill("#r-pass", PASSWORD)
    p.click("button[type=submit]")
    p.wait_for_selector("[data-demo]")
    p.click("[data-demo]")
    p.wait_for_selector(".item-card", timeout=60000)

    # 1. no setup at all: the free engine photographs the outfit, without a key
    fake("__clear")
    p.goto(base + "outfit-generator.html")
    p.check('[name="occasion"][value="work"]', force=True)
    p.click("[data-generate]")
    p.wait_for_selector(".outfit-photo__img", timeout=20000)
    poll(p, "() => document.querySelector('.outfit-photo__img').naturalWidth > 0")
    first = [e for e in photo_log() if e["path"].startswith("/prompt/")][-1]
    assert first["auth"] is None
    prompt = last_prompt()
    assert "Photorealistic" in prompt and "cropped at the chin" in prompt
    assert p.get_attribute(".outfit-photo__img", "src").startswith("api/images/")
    assert p.locator("svg.outfit-render").count() == 0

    # kept with the outfit: reopening makes no new request
    outfit_id = p.get_attribute(".outfit", "data-outfit-id")
    count = len(photo_log())
    p.goto(base + f"outfit.html?id={outfit_id}")
    p.wait_for_selector(".outfit-photo__img")
    assert len(photo_log()) == count

    # a busy free service is explained, and Try again works once it's free
    fake("__mode/busy")
    p.click("[data-new-photo]")
    p.wait_for_selector(".photo-wait--error", timeout=30000)
    fake("__mode/none")
    p.click("[data-photo-retry]")
    p.wait_for_selector(".photo-wait", state="detached", timeout=30000)
    p.wait_for_selector(".outfit-photo__img")

    # saved outfits show the photo with the colour pairing
    p.click("[data-save]")
    p.click('dialog[open] [value="ok"]')
    p.wait_for_selector('[data-save][aria-pressed="true"]')
    p.goto(base + "saved-outfits.html")
    p.wait_for_selector(".look--photo img")
    assert "/" in p.text_content(".look--photo .look__caption")

    # 2. a free Pollinations key: the server sends it as a Bearer header, never in a URL
    p.goto(base + "profile.html#photos")
    p.wait_for_selector("[data-photo-status]:has-text('free open-source engine')")
    assert p.is_checked('[name="engine"][value="free"]')
    p.fill("#p-pollen", "sk_free_test_key_1234")
    p.click('[data-form="pollen"] button[type=submit]')
    p.wait_for_selector("[data-photo-status]:has-text('1234')")
    fake("__clear")
    p.goto(base + f"outfit.html?id={outfit_id}")
    p.wait_for_selector(".outfit-photo__img")
    p.click("[data-new-photo]")
    import time
    end = time.time() + 20
    while time.time() < end and not [e for e in photo_log() if not e["path"].endswith("/models")]:
        time.sleep(0.2)
    p.wait_for_selector(".photo-wait", state="detached", timeout=20000)
    made = [e for e in photo_log() if not e["path"].endswith("/models")]
    assert made and all(e["auth"] == "Bearer sk_free_test_key_1234" and "sk_free" not in e["path"] for e in made)
    assert any(e["path"].endswith("/v1/images/edits") for e in made)         # the demo pieces have photos

    # 3. Gemini: pick it, add a key, and the next photo comes from Gemini with the clothing photos
    p.goto(base + "profile.html#photos")
    p.check('[name="engine"][value="gemini"]', force=True)
    p.wait_for_selector('[data-form="photos"]:not([hidden])')
    p.fill("#p-gemini", "not a key")
    p.click('[data-form="photos"] button[type=submit]')
    p.wait_for_selector("[data-error-for='gemini_key']")
    p.fill("#p-gemini", "AIzaSyTESTKEYTESTKEYTESTKEY000")
    p.click('[data-form="photos"] button[type=submit]')
    p.wait_for_selector("[data-photo-status]:has-text('Google Gemini')")
    fake("__clear")
    p.goto(base + "outfit-generator.html")
    p.click("[data-generate]")
    p.wait_for_selector(".outfit-photo__label:has-text('gemini-2.5-flash-image')", timeout=20000)
    call = [e for e in photo_log() if ":generateContent" in e["path"]][-1]
    assert call["goog"] == "AIzaSyTESTKEYTESTKEYTESTKEY000" and "key=" not in call["path"]
    assert call["body"].count('"inlineData"') + call["body"].count('"inline_data"') >= 2

    # Gemini errors are explained, with a working retry
    fake("__mode/quota")
    p.click("[data-new-photo]")
    p.wait_for_selector(".photo-wait--error:has-text('quota')")
    fake("__mode/none")
    p.click("[data-photo-retry]")
    p.wait_for_selector(".photo-wait", state="detached", timeout=20000)

    # Smart buys shows a real product photo, and a suggestion on a person on request
    p.goto(base + "smart-buys.html")
    p.wait_for_selector(".shop-card .shop-card__product")
    p.click(".shop-card [data-photo]")
    p.wait_for_selector(".shop-card__photo", timeout=20000)

    # keys never reach the browser or a backup; removing Gemini returns to the free engine
    p.goto(base + "profile.html")
    p.wait_for_selector("[data-profile]:not([hidden])")
    p.click("[data-export]")
    p.fill("#reauth-pw", PASSWORD)
    with p.expect_download() as dl:
        p.click('dialog[open] [value="ok"]')
    text = Path(dl.value.path()).read_text()
    stored = p.evaluate("() => JSON.stringify(Object.assign({}, localStorage, sessionStorage)) + document.cookie")
    status = p.evaluate("() => fetch('api/photos/status').then((r) => r.text())")
    for blob in (text, stored, status):
        assert "AIzaSyTESTKEY" not in blob and "sk_free_test_key" not in blob
    p.click("[data-photo-remove]")
    p.wait_for_selector("[data-photo-status]:has-text('free open-source engine')")
    assert problems == []
    context.close()


def test_27_more_features_and_security(ctx, chrome):
    """
    Live weather (Open-Meteo, faked), photo takes to choose from, "wearing it
    today", privacy pages, frame protection, sign-out everywhere, and the
    idle sign-out.
    """
    import json
    context = fake_photo_services(chrome.new_context(viewport={"width": 1280, "height": 900}, bypass_csp=True,
                                                     geolocation={"latitude": 43.65107, "longitude": -79.347015},
                                                     permissions=["geolocation"]))
    weather_calls = []

    def meteo(route):
        weather_calls.append(route.request.url)
        route.fulfill(status=200, headers={"content-type": "application/json", "access-control-allow-origin": "*"},
                      body=json.dumps({"current": {"temperature_2m": 6.4, "weather_code": 63, "wind_speed_10m": 12}}))
    context.route("https://api.open-meteo.com/**", meteo)
    p = context.new_page()
    problems = []
    p.on("pageerror", lambda e: problems.append(str(e)))
    base = ctx["base"]

    # privacy and terms are public, linked from sign-up, and say no cookies
    p.goto(base + "register.html")
    p.click(".auth__legal a[href='privacy.html']")
    p.wait_for_selector("h1:has-text('Privacy and cookies')")
    assert "fc_session" in p.text_content("main") and "no tracking" in p.text_content("main").lower()
    assert p.evaluate("document.cookie") == ""          # nothing is set before signing in
    p.goto(base + "terms.html")
    p.wait_for_selector("h1:has-text('Terms of use')")

    # common passwords are refused
    p.goto(base + "register.html")
    p.fill("#r-name", "Extra Person")
    p.fill("#r-email", "extra@example.com")
    p.fill("#r-pass", "password123")
    p.click("button[type=submit]")
    p.wait_for_selector("[data-error-for='password']:has-text('common')")
    p.fill("#r-pass", PASSWORD)
    p.click("button[type=submit]")
    p.wait_for_selector("[data-demo]")
    p.click("[data-demo]")
    p.wait_for_selector(".item-card", timeout=60000)

    # local weather fills the form; the location is rounded before it's sent
    p.goto(base + "outfit-generator.html")
    p.click("[data-local-weather]")
    p.wait_for_function("document.querySelector('[name=weather][value=rainy]').checked")
    assert p.text_content("[data-temp-readout]") == "6°C"
    q = parse_qs(urlparse(weather_calls[-1]).query)
    assert q["latitude"] == ["43.65"] and q["longitude"] == ["-79.35"]

    # the outfit, its photo, a second take, and choosing the first again
    p.click("[data-generate]")
    p.wait_for_selector(".outfit-photo__img")
    p.click("[data-new-photo]")
    p.wait_for_selector(".photo-strip__pick >> nth=1")
    assert p.locator(".photo-strip__pick").count() == 2
    p.click(".photo-strip__pick >> nth=0")
    p.wait_for_function("document.querySelector('.photo-strip__pick').getAttribute('aria-pressed') === 'true'")
    assert p.get_attribute(".photo-strip__pick >> nth=1", "aria-pressed") == "false"

    # wearing it today: logged, and those pieces rest in the next suggestion
    worn = set(p.locator(".rail-item .swing-tag__name").all_text_contents())
    p.click("[data-wear]")
    p.wait_for_selector("[data-wear][aria-pressed='true']")
    p.click("[data-generate]")
    p.wait_for_selector(".outfit-photo__img")
    again = set(p.locator(".rail-item .swing-tag__name").all_text_contents())
    assert again != worn

    # FitCheck.AI refuses to be framed: the server forbids it, and the page hides itself as a backstop
    r = p.request.get(base + "index.html")
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"] and r.headers["x-frame-options"] == "DENY"
    framed = p.evaluate("""() => new Promise((ok) => {
      const f = document.createElement('iframe'); f.src = 'index.html';
      f.onload = () => { let d; try { d = f.contentDocument?.documentElement?.innerHTML || ''; } catch { d = ''; }
        ok(!d.includes('What should I wear')); };
      setTimeout(() => ok(true), 5000); document.body.append(f); })""")
    assert framed

    # sign out everywhere ends this session and locks the keys
    p.goto(base + "profile.html")
    p.wait_for_selector("[data-profile]:not([hidden])")
    p.click("[data-sign-out-all]")
    p.click('dialog[open] [value="ok"]')
    p.wait_for_url(re.compile(r"login\.html\?reason=signed_out"))
    assert p.evaluate("() => fetch('api/auth/me').then((r) => r.status)") == 401

    # a sign-in without "keep me signed in" ends after 30 idle minutes
    p.fill("#a-email", "extra@example.com")
    p.fill("#a-pass", PASSWORD)
    p.click("button[type=submit]")
    p.wait_for_url(re.compile(r"dashboard\.html"))
    sql("UPDATE sessions SET last_seen_at = last_seen_at - INTERVAL 31 MINUTE WHERE revoked_at IS NULL AND remember = 0")
    p.goto(base + "wardrobe.html")
    p.wait_for_url(re.compile(r"login\.html"))
    assert problems == []
    context.close()


def test_28_forgot_password_email_and_signed_in_devices(ctx, chrome):
    """Reset a forgotten password from the emailed link; see and sign out devices."""
    base = ctx["base"]
    phone = chrome.new_context(viewport={"width": 390, "height": 844},
                               user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 19_0 like Mac OS X) AppleWebKit/605.1.15 "
                                          "Version/19.0 Mobile/15E148 Safari/604.1")
    pp = phone.new_page()
    pp.goto(base + "register.html")
    pp.fill("#r-name", "Forgetful")
    pp.fill("#r-email", "forgetful@example.com")
    pp.fill("#r-pass", PASSWORD)
    pp.click("button[type=submit]")
    pp.wait_for_selector("[data-demo]")

    laptop = chrome.new_context(viewport={"width": 1280, "height": 900})
    p = laptop.new_page()
    problems = []
    p.on("pageerror", lambda e: problems.append(str(e)))
    p.goto(base + "login.html")
    p.click("text=Forgot your password?")
    p.wait_for_url(re.compile(r"forgot-password\.html"))
    p.click("button[type=submit]")
    p.wait_for_selector("[data-error-for='email']")
    p.fill("#f-email", "forgetful@example.com")
    p.click("button[type=submit]")
    p.wait_for_selector(".notice--success:has-text('If an account uses that email')")
    msg = [m for m in mails() if m["To"] == "forgetful@example.com"][-1]
    link = re.search(r"http://localhost:\d+/reset-password\.html#token=[A-Za-z0-9_-]+", msg.get_content()).group(0)

    p.goto(link)
    p.wait_for_selector("#n-pass")
    assert "token" not in p.url                      # removed from the address bar straight away
    p.fill("#n-pass", "password123")
    p.click("button[type=submit]")
    p.wait_for_selector("[data-error-for='password']:has-text('common')")
    p.fill("#n-pass", "Brand-new-2027")
    p.click("button[type=submit]")
    p.wait_for_url(re.compile(r"login\.html\?reason=password_reset"))
    assert "Password changed" in p.text_content("[data-auth-notice]")
    # the phone, signed in with the old password, was signed out
    pp.goto(base + "wardrobe.html")
    pp.wait_for_url(re.compile(r"login\.html"))
    # the same link doesn't work twice
    p.goto(link)
    p.fill("#n-pass", "Another-new-2028")
    p.click("button[type=submit]")
    p.wait_for_selector(".notice--error:has-text('expired or was already used')")

    # sign in on both; the laptop lists both devices and signs the phone out
    for page, remember in ((pp, True), (p, False)):
        page.goto(base + "login.html")
        page.fill("#a-email", "forgetful@example.com")
        page.fill("#a-pass", "Brand-new-2027")
        if remember:
            page.check("[name=remember]")
        page.click("button[type=submit]")
        page.wait_for_url(re.compile(r"dashboard\.html"))
    p.goto(base + "profile.html")
    p.wait_for_selector(".device >> nth=1")
    names = p.locator(".device__name").all_text_contents()
    assert any("Safari on iOS" in n for n in names) and any("This device" in n for n in names)
    p.locator(".device", has_text="Safari on iOS").locator("[data-end-session]").click()
    p.wait_for_selector(".toast:has-text('signed out')")
    expect(p.locator(".device")).to_have_count(1)                # the list refreshes (CSP-safe wait)
    pp.goto(base + "wardrobe.html")
    pp.wait_for_url(re.compile(r"login\.html"))
    assert problems == []
    phone.close()
    laptop.close()


def test_29_works_offline_without_storing_personal_data(ctx, chrome):
    """The service worker keeps the pages for offline use, never anything from /api."""
    context = chrome.new_context(viewport={"width": 1280, "height": 900})
    p = context.new_page()
    base = ctx["base"]
    p.goto(base + "register.html")
    p.fill("#r-name", "Offline Person")
    p.fill("#r-email", "offline@example.com")
    p.fill("#r-pass", PASSWORD)
    p.click("button[type=submit]")
    p.wait_for_selector("[data-demo]")
    p.click("[data-demo]")
    p.wait_for_selector(".item-card img", timeout=60000)
    p.evaluate("() => navigator.serviceWorker.ready.then(() => true)")
    p.goto(base + "dashboard.html")                       # now controlled by the worker
    assert p.evaluate("() => navigator.serviceWorker.ready.then(() => navigator.serviceWorker.controller !== null)")
    p.wait_for_selector("canvas[data-chart]")
    cached = p.evaluate("""async () => { const out = [];
      for (const k of await caches.keys()) for (const r of await (await caches.open(k)).keys()) out.push(new URL(r.url).pathname);
      return out; }""")
    assert "/offline.html" in cached and "/assets/js/api.js" in cached and "/dashboard.html" in cached
    assert not [u for u in cached if u.startswith("/api/")]       # no wardrobe, photos or account data

    context.set_offline(True)
    p.goto(base + "wardrobe.html")                            # a page opened before: from the cache
    p.wait_for_selector(".offline-notice")                    # the page explains it can't reach the server
    p.goto(base + "terms.html")                               # precached at install, never opened
    p.wait_for_selector("h1:has-text('Terms of use')")
    p.goto(base + "no-such-page-yet.html")                   # not cached: the offline page
    p.wait_for_selector("h1:has-text(\"You're offline\")")
    assert p.is_visible("[data-retry]")
    context.set_offline(False)                                # reconnecting reloads by itself
    p.wait_for_selector(".lost h1")                           # back online: the real (404) answer
    context.close()
