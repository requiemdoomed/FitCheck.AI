# FitCheck.AI test and QA report

_Project author: Swayam Shakya · Report date: 3 November 2026 (round 9, final: offline
support and installable app, fresh screenshots; round 8: password reset by email and
signed-in devices; round 7: Flask + MySQL server)_

This report records what was actually run against this codebase, what failed, and what
was fixed. Every number comes from a run in the build environment.

## Environment

| | |
|---|---|
| OS | Ubuntu 24.04 (container) |
| Server | Python 3.13.18, Flask 3.1.3, Werkzeug 3.1.9, PyMySQL 1.2.3, Pillow 13.0.0, scikit-learn 1.9.1 |
| Database | MySQL 8.0.46; test database `fitcheck_test`, rebuilt from `backend/schema.sql` on every run |
| Browser | Chromium via Playwright 1.63 (headless) |
| Node | 22.23 (JS unit tests) |

## Results

| Suite | Command | Result |
|---|---|---|
| Server, database and email | `pytest tests/backend` | **42 passed** |
| Browser journey against the running server | `pytest tests/frontend` | **29 of 29 steps passed** (175 s) |
| Pages, policy, offline worker, deployment files | `pytest tests/static` | **79 passed** |
| Python engine | `pytest tests/ml` | **28 passed** |
| JS units (Smart buys, weather mapping) | `pytest tests/engine` | **2 passed** |
| **Total** | | **180 passed, 0 failed, 0 skipped** |
| Jupyter notebook | `jupyter nbconvert --execute --inplace` | **26 of 26 code cells ran, 0 errors**; models in `ml/models/` regenerated and loaded by the server |
| Syntax | `py_compile` on `backend/`, `node --check` on the changed modules | 0 errors |
| Dependencies | `pip-audit -r backend/requirements.txt` | Pillow 12.3.0 had 5 advisories → **upgraded to 13.0.0; no known vulnerabilities** |
| Static analysis | `bandit -r backend` (incl. new `mailer.py`, `manage.py`) | 4 reported, all known false positives; **0 real issues** (see SECURITY.md) |
| JS security lint | ESLint `no-unsanitized` + `security` | 67 HTML sinks reviewed (1 new, escaped); 0 `eval` |
| Accessibility | axe-core 4.14, WCAG 2 A/AA + best practice, 16 pages (incl. the offline page) + add-piece dialog, light and dark | **0 violations** |
| Visual QA | screenshots of every page at 1366 px, 390 px and in dark mode | reviewed; no layout breaks or overflow |

### What the server tests cover (`tests/backend`)

**Accounts and sessions**
- Sign-up validation: every field; short, common and email-based passwords refused.
- Cookie flags: `fc_session` is HttpOnly, Secure and Lax; `fc_csrf` is Strict.
- Only the token's hash is stored; the password is stored only as scrypt.
- Duplicate email answers 409.
- Identical errors for unknown and wrong accounts.
- The sign-in limit trips at 8 failures, even for the right password.
- CSRF token and Origin are required.
- Logout-all ends every device; 31 idle minutes ends a session; a password change signs
  out other sessions.

**HTTP layer**
- CSP, HSTS, frame, nosniff, referrer, permissions and COOP headers on pages, the API and
  assets.
- 10 forbidden paths answer 404: source, schema, `.env`, tests, models, workflow, and
  encoded traversal.
- JSON errors without internals.

**Wardrobe and outfits**
- Item validation and CRUD.
- A multipart JPEG with GPS EXIF is stored as WebP with no GPS; a PHP payload pretending
  to be a JPEG is refused.
- Another user gets 404 for items and images, as does a signed-out visitor.
- Six SQL-injection and wildcard strings are inert.
- Generate, with 422 when the wardrobe is incomplete and 409 when no combinations are left.
- Feedback, save, wear, history filter, unsave, dashboard.
- Input validation.
- The 40-piece demo, with 9 patterned pieces.

**Photos and profile**
- The free engine without a key: prompt content, and the photo kept and served.
- Four takes, and choosing a cover.
- Keys sealed in MySQL, not in any response, and sent only as headers: Gemini gets
  `x-goog-api-key` and reference images; Pollinations gets `Bearer`.
- A busy service answers 429 with an explanation.
- Public samples: validated (no `<script>`, no prompt injection), cached, limited per IP.
- Preferences reach the prompt.
- Backup: needs the password, contains no keys, restores on another account.
- Deleting an account cascades everywhere.

**Offline support**
- `/sw.js` is served as JavaScript with `no-cache` and the security headers.
- `/manifest.webmanifest` is served as `application/manifest+json`.
- `sw.js` matches `scripts/build_sw.py`: every precached file exists, and nothing from
  `api`, `backend`, `ml` or `tests` is in the list.
- The manifest icons have the sizes they claim, and every page links the manifest.

**Password reset and devices** (real SMTP code against a local fake mail server)
- The emailed link uses the URL fragment, only its hash is stored, it works once, and
  every device is signed out afterwards. The old password stops working; the new one
  still has to pass the password rules.
- Unknown emails get the identical answer and no mail; invalid emails get 400.
- A newer link cancels the older one; links expire after 30 minutes; malformed tokens
  are refused.
- 3 emails per address (the same answer after that), 10 requests per IP, and 20 reset
  tries per IP.
- Production without SMTP answers 503; the operator `manage.py reset-link` works.
- Device names ("Chrome on Windows", "Safari on iOS"), the current device, signing one
  device out, another account refused (404), signing yourself out clears the cookies.
- Housekeeping removes 40-day-old sessions and expired links.

### What the browser journey covers (`tests/frontend`)

The real server on `localhost:5502`, the MySQL test database, and the photo services
replaced by a local fake that the server calls.

- **Landing:** mixer, sample photo, lookbook, theme.
- **Sign-up and sign-in:**
  - protected pages redirect; sign-up validation;
  - the session cookie is HttpOnly and absent from `document.cookie`, and nothing but the
    theme is in `localStorage`;
  - sign out and back in; no open redirect after login.
- **Wardrobe:**
  - adding pieces, with a photo cut out in the browser and stored on the server;
  - search and filters; edit and remove.
- **Outfits:**
  - generating for rain at 10 °C, with a coat and a photo whose prompt names the trench
    coat; like, save, another;
  - saved, single-outfit and history pages; dashboard; profile and preferences; phone
    layout.
- **The same account from a second browser profile** ("another device").
- **Backup** downloaded and restored into a new account.
- **Every page under the real CSP;** XSS payload shown as text; no console errors.
- **Uploads:** a 12-megapixel photo shrunk to 900 px or less; a dyed stock garment for
  "black hoodie"; the colour suggested from a photo.
- **Demo wardrobe and Smart buys**, with affordable prices.
- **Photo person preferences** reach the prompt.
- **Account deletion** frees the email.
- **Photo engines through the server:**
  - free with no key; kept on reopening; busy service, then Try again;
  - free key sent as Bearer, with the editing model;
  - Gemini key validation, header and reference images;
  - quota error, then retry;
  - Smart buys photo;
  - keys absent from browser storage, `/api/photos/status` and the backup.
- **Forgot password (step 28):**
  - a link from the login page and email validation;
  - the reset link is read from the fake mail server and the token removed from the
    address bar;
  - a common password is refused, then the reset succeeds;
  - the other device is signed out, and the link doesn't work twice;
  - signed in on a phone and a laptop, the laptop lists "Safari on iOS" and signs it out.
- **Offline (step 29):**
  - after signing in and loading the demo, the cache holds the pages and scripts and
    **nothing under `/api`**;
  - offline, a page opened before loads from the cache and explains it can't reach the
    server;
  - a page never opened but precached (Terms) loads;
  - an uncached address shows the offline page, which reloads by itself when the
    connection returns.
- **Other features and security:**
  - local weather with the location rounded to about 1 km;
  - photo takes; worn pieces resting;
  - framing refused (`frame-ancestors 'none'` + `X-Frame-Options: DENY`);
  - sign out everywhere; 30-minute idle sign-out.

## Problems found and fixed in this round

| # | Problem | Fix |
|---|---|---|
| 1 | Image bytes were JSON-decoded when read from MySQL (UnicodeDecodeError) | only text columns are decoded |
| 2 | The server CSP would have blocked the hashed inline theme script | header built with the computed inline hashes |
| 3 | Old tables with the same constraint names blocked the schema | databases recreated; tests rebuild the test DB each run |
| 4 | Pillow 12.3.0 had known vulnerabilities | upgraded to 13.0.0 |
| 5 | Test harness: an unread log pipe stalled the server after many requests | server log written to a file |
| 6 | Wardrobe pictures were phone snapshots with busy backgrounds | clean cut-outs shown as packshots on a studio sweep with a contact shadow |

## Problems found and fixed in round 8

| # | Problem | Fix |
|---|---|---|
| 1 | A `;` inside a schema comment split a statement when loading `schema.sql` | comment lines are removed before splitting |
| 2 | Failed reset attempts would have been rolled back, so the per-IP limit never counted them | `reset_link_invalid` commits its rate record, like failed sign-ins |
| 3 | Test timing: the device count was checked before the list refreshed | the test waits for the refreshed list |

## Problems found and fixed in round 9

| # | Problem | Fix |
|---|---|---|
| 1 | No offline support or install option (left open from round 3) | service worker, offline page, web manifest and icons |
| 2 | Docs screenshots showed an earlier version of the app | all eight retaken from the current app |
| 3 | Test waits that evaluate strings were blocked by the app's own CSP in strict-policy contexts (passed only when already true) | CSP-safe waits (`expect`, a polling helper) |
| 4 | The photo cut-out step could exceed 10 s on a busy machine | 60 s allowance for that step |

## UI changes (rounds 7–9)

- An offline page in the sign-in style; FitCheck.AI can be added to a home screen with
  its own icon.

- Forgot-password and new-password pages in the same style as sign-in; a "Forgot your
  password?" link on sign-in.
- Signed-in devices on Profile → Sign-in and security.

- **Garments:** shown as catalogue packshots, the cut-out on a lit studio sweep with a soft
  contact shadow, in the wardrobe, outfit rails, history and dashboard.
- **Outfit photos:** presented as a print, with a paper mat, a hairline edge and a trace of
  film grain.
- Light and dark tokens for both.

## Not tested / known limits

- **Live photo services:** Pollinations and Google can't be reached from the build
  environment. All photo flows ran against a fake answering in each service's format;
  real photo quality and response times need the live services.
- **Render itself:** `render.yaml` was checked by tests for its content, not deployed from
  here. The Dockerfile and compose file weren't built (no Docker in the container).
- **Physical phones and Safari** weren't available (layouts tested at 390 × 844 in
  Chromium).
- **Model accuracy on real people** is unknown: training ratings are simulated.
