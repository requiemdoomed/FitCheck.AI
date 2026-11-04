# FitCheck.AI security and privacy audit

_Author: Swayam Shakya · Audit date: 3 November 2026 (server edition)_

This is the security design of FitCheck.AI and the record of a full audit of the final
build. Every result here comes from a run on this codebase.

## What there is to protect

FitCheck.AI is one Flask server that serves the pages and a JSON API (`/api/...`) from a
single origin, backed by MySQL 8. Assets:

- accounts (email, password hash, sessions), wardrobes, photos and outfit history in MySQL;
- photo-service keys people add (Pollinations, Gemini), plus an optional server-wide key;
- the integrity of the pages (script injection, framing, cross-site requests).

Network traffic leaving the server goes only to the photo services. The browser itself
talks only to its own server, plus Open-Meteo, and only when "Use my local weather" is
pressed:

| Destination | From | When | What is sent |
|---|---|---|---|
| Pollinations | server | an outfit photo is made (default engine) | a text description of the outfit and person; with a key, a board of the outfit's clothing photos |
| Google Gemini | server | only if the person chose Gemini with their own key | the description and the clothing photos |
| Open-Meteo | browser | only when the weather button is pressed | the location, rounded to about 1 km |

Photo services never see the person's IP address, email or account.

## Controls

### Authentication and sessions (`backend/security.py`, `api_auth.py`)
- **Passwords:** scrypt hashes (Werkzeug) with a random salt. A dummy hash is checked for
  unknown emails, so timing doesn't reveal which accounts exist. The error is the same for
  a wrong email and a wrong password.
- **Password rules:**
  - 8–128 characters;
  - not only letters or only digits;
  - not a common breached password;
  - not containing the email name.
- **Sessions:**
  - a random 256-bit token in the `fc_session` cookie: `HttpOnly`, `Secure`,
    `SameSite=Lax`, `Path=/`;
  - the database stores only its **SHA-256 hash**, so a database leak gives no usable
    sessions;
  - a normal sign-in lasts at most 12 hours and ends after **30 minutes idle**;
    "Keep me signed in" (off by default) lasts 30 days.
- **Revocation:**
  - signing out revokes the session on the server;
  - **Sign out everywhere** revokes all of them;
  - a password change revokes every other session.
- **CSRF protection:**
  - double-submit token: the `fc_csrf` cookie (`SameSite=Strict`, readable by the page)
    must match the `X-CSRF-Token` header on every POST, PUT and DELETE;
  - additionally the `Origin` header (or the `Referer`) must be this site.
- **Rate limits** (server-side, in MySQL):
  - sign-in: 8 failures per email and 30 per IP in 10 minutes;
  - sign-up: 10 per IP per hour;
  - photos: 40 per account per hour;
  - landing-page samples: 12 per IP per hour.
- **Re-authentication:** downloading a backup and deleting the account both need the
  password.
- **Password reset by email** (`api_auth.py`, `mailer.py`):
  - one-time 256-bit tokens; the database stores only their SHA-256 hash;
  - links expire after 30 minutes, work once, and a new request cancels older links;
  - the token is in the URL **fragment** (`#token=`), which browsers never send to a
    server or in a Referer; the page removes it from the address bar at once;
  - links are built from the configured `APP_URL`, never from the request's Host header
    (no host-header poisoning);
  - the answer is the same whether or not an account exists, and mail is sent in a
    background thread so timing doesn't reveal it either;
  - limits: 3 emails per address and 10 requests per IP per hour; 20 reset tries per IP
    per hour;
  - a reset signs out every session; the new password goes through the same rules;
  - mail goes out over TLS (STARTTLS or SSL; production refuses anything else), as plain
    text built with `EmailMessage`, so there's no header injection;
  - with no mail service, an operator can issue a link with
    `python manage.py reset-link <email>`.
- **Signed-in devices:** Profile lists each active session (browser and system, last
  activity) and can sign out any one of them; another account's session answers 404.
- **Offline cache (service worker, `sw.js`):**
  - stores only FitCheck.AI's own pages, styles, scripts, fonts and icons;
  - never anything under `/api` (account, wardrobe, photos), never non-GET requests or
    other sites, so signing out leaves no personal data in the browser;
  - fetches from the network first, so the current version is always used when online;
    the cache is versioned by a hash of the files and old versions are deleted.
- **Housekeeping:** rate counters are kept 2 days, used or expired reset links 1 day, and
  ended sessions 30 days.
- **Ownership:** every query is scoped to the signed-in user. Another person's items,
  outfits and images answer **404** (not 403), so their existence isn't revealed.

### API keys
- Keys are sealed with **Fernet** (AES-128-CBC + HMAC-SHA256). The key for that is derived
  with HKDF from `SECRET_KEY` and stored in `secrets.sealed`. There is no plain copy in the
  database, the logs or the browser.
- Keys never go back to the browser. The page only sees the last four characters.
- Keys never go into backups.
- Keys are sent only to their own service, in a header (`Authorization: Bearer`,
  `x-goog-api-key`), never in a URL.
- `SECRET_KEY` and `DB_PASSWORD` come from the environment. In production, the server
  refuses to start without them. `render.yaml` generates the secret, `.env` is git-ignored
  and excluded from the package, and `.env.example` holds no values.

### Database
- **Queries:** every one is parameterised (PyMySQL). The few built with f-strings join only
  constant fragments or whitelisted keys; each was reviewed and is annotated. `LIKE` search
  escapes `%`, `_` and `\`. Tests send SQL-injection strings and see them stored and
  searched as plain text.
- **Least privilege:** the app connects as `fitcheck_app`, which has rights on its own
  database only, never root. TLS to the database is available (`DB_SSL=1`, optional CA)
  for managed hosts.
- **Integrity:** the schema enforces it with foreign keys `ON DELETE CASCADE` and `CHECK`
  constraints (categories, colours as `#rrggbb`, verdicts, engines, MIME types).
- **Uploads:**
  - capped at 15 MB;
  - must decode as JPEG, PNG or WebP (Pillow);
  - limited in pixel count (decompression bombs);
  - re-encoded to WebP at 900 px or less, which removes EXIF/GPS and anything hidden in
    the file.
- **Images:**
  - served only from `/api/images/<32-hex key>`, after an ownership check, with
    `Cache-Control: private`;
  - random keys, not sequential IDs.
- **Backup import is hostile input:** everything is validated before anything is erased.
- **Deleting the account** erases every row and image of the person (cascade), and the
  test checks it.

### HTTP layer (`backend/app.py`)
- **Headers on every response:**
  - **Content-Security-Policy:** `default-src 'self'`; scripts only from the site plus the
    hashed inline theme script; `wasm-unsafe-eval` for the in-browser cut-out model;
    `connect-src 'self' https://api.open-meteo.com`; `object-src 'none'`;
    `frame-ancestors 'none'`; `base-uri 'self'`; `form-action 'self'`;
  - `Strict-Transport-Security` (2 years, includeSubDomains);
  - `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`;
  - `Referrer-Policy: no-referrer`;
  - `Permissions-Policy` (only geolocation, for the site itself);
  - `Cross-Origin-Opener-Policy` and `Cross-Origin-Resource-Policy: same-origin`.
- `Cache-Control: no-store` on API responses.
- **Static whitelist:** only `*.html` pages and `assets/...` are served. `backend/`, `ml/`,
  `tests/`, `.env` and dotfiles answer 404, path traversal included (tested).
- **Errors** are JSON with a code and message. Stack traces are never sent; unexpected
  errors are logged on the server only.
- Behind Render's proxy, the client IP comes from `X-Forwarded-For` only in production
  (`TRUST_PROXY`).

### Privacy, cookies and consent
- **Exactly two cookies, both strictly necessary:** `fc_session` and `fc_csrf`. None is set
  before signing in. No analytics, ads, third-party scripts or tracking, so no consent
  banner is needed. `privacy.html` lists each cookie, what is stored, who it goes to and
  how to delete it.
- Location is asked for only when the weather button is pressed, and is rounded.
- Every AI photo is labelled as AI-generated.

### Dark patterns
None of the following is used:
- pre-ticked boxes;
- confirm-shaming or urgency copy;
- paid upsells (the free engine is the default);
- affiliate links.

Account deletion, key removal and sign-out are direct, plainly labelled actions.

### Removed
The browser-only storage layer, which the server replaces:
- `local/backend.js`, `db.js`, `vault.js`, `security.js`;
- the browser photo clients `openphoto.js` and `photoreal.js`;
- the browser copy of the ML engine and its exported models;
- `_headers` and the GitHub Pages workflow.

Vendored JS: Chart.js 4.6.1 and onnxruntime-web 1.31.1.

## Audit: what was run

| Check | Tool | Result |
|---|---|---|
| Python dependencies | `pip-audit -r backend/requirements.txt` | 5 Pillow advisories found on 12.3.0 → **upgraded to Pillow 13.0.0; no known vulnerabilities** |
| Python static analysis | `bandit -r backend` | 9 reported, each reviewed. 5 × B608: query strings built only from constants and whitelisted keys; values bound; annotated. 2 × B105: error messages mistaken for passwords. 2 × B112: unreadable images skipped on purpose. **0 real issues** |
| Bundled JS | `npm audit` (chart.js, onnxruntime-web) | 0 vulnerabilities |
| JS sinks | ESLint `no-unsanitized` and `security` (previous round, code unchanged in these paths) | every HTML sink escapes with `esc()` or uses fixed values |
| Server behaviour | `tests/backend` (42 tests against MySQL and a fake SMTP server) | see the list below |
| In a browser | `tests/frontend` (29-step journey against the running server, including offline) | HttpOnly session cookie not readable by page script; keys not in browser storage, page responses or backups; XSS payload shown as text; idle sign-out; sign out everywhere; framing refused |
| Accessibility | axe-core 4.14, WCAG 2 A/AA + best practice, 16 pages (incl. the offline page) + add-piece dialog, light and dark | **0 violations** |
| JS sinks (this round) | ESLint `no-unsanitized` + `security` | 67 HTML sinks, each escaped with `esc()`/`Number()` or fixed text; the one new sink (device list) reviewed; no `eval` |
| Page policy | `tests/static` | CSP current on all 17 pages; offline worker current and free of private paths; no secrets, trackers or off-site calls in shipped code |

The backend tests cover:
- cookie flags, and that only the token hash is stored;
- identical errors for unknown and wrong accounts;
- sign-in and public-photo rate limits;
- CSRF and bad-Origin refusals;
- logout, logout-all, idle expiry, and the password change ending other sessions;
- headers on pages, API and assets;
- 10 forbidden paths returning 404;
- other users' items and images returning 404;
- SQL-injection strings staying inert;
- EXIF/GPS removed and non-images refused;
- keys sealed in the database and sent only in headers;
- validation and caching of the public samples;
- a backup needing the password and holding no keys;
- deletion cascading;
- password reset: link by email (fragment, hash-only storage), works once, expires,
  replaced by a newer link, signs out every device; identical answers for unknown
  emails; per-address and per-IP limits; 503 without mail in production; the operator
  link;
- the device list: names, current device, signing out one device, other accounts
  refused;
- housekeeping clears old sessions and links.

## Residual risk

- **Hosting:** HTTPS and the database's own security depend on the host (Render terminates
  TLS). Keep `SECRET_KEY` stable and secret: whoever has it and the database can unseal
  saved keys.
- **The single MySQL service** in `render.yaml` runs on one disk. Turn on Render's disk
  snapshots or use a managed MySQL with backups for real users.
- **`style-src 'unsafe-inline'`** stays, because colour swatches use inline CSS variables.
  Scripts are fully locked down.
- **Third-party photo services** receive the outfit description and clothing photos (not
  identities), and are governed by their own terms.
- **Email depends on the SMTP provider** you configure (deliverability, spam
  filtering). Set up SPF/DKIM for the sending domain. Email addresses aren't verified at
  sign-up, so a typo in an email only matters if that person later needs a reset.
