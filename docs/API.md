# FitCheck.AI HTTP API

_Author: Swayam Shakya_

The Flask server (`backend/`) serves the pages and a JSON API under `/api` from one
origin. Pages use the client in `assets/js/api.js`. Every call below is also reachable
with any HTTP client that keeps cookies.

## Conventions

- JSON in and out. Uploads use `multipart/form-data`.
- **Session:** sign-in and sign-up set two cookies:
  - `fc_session`: HttpOnly, Secure, SameSite=Lax;
  - `fc_csrf`: Secure, SameSite=Strict, readable by the page.
- **Changes need CSRF:** every POST, PUT and DELETE must send `X-CSRF-Token: <value of
  fc_csrf>`, and the `Origin` must be the site itself. Otherwise the answer is `403`
  `csrf_failed` / `bad_origin`.
- **Errors:**
  `{"error": {"code": "...", "message": "...", "details": {...}}}`

| status | typical `code` |
|---|---|
| 400 | `validation_error` (`details` maps fields to messages), `invalid_image` |
| 401 | `unauthorized`, `invalid_credentials`, `session_expired` |
| 403 | `csrf_failed`, `bad_origin` |
| 400 | `reset_link_invalid` |
| 503 | `mail_not_configured` |
| 404 | `not_found` (also for another account's records) |
| 409 | `email_taken`, `no_more_combinations` |
| 413 | `file_too_large` |
| 422 | `wardrobe_incomplete` (`details.missing` lists what to add) |
| 429 | `rate_limited`, `photo_quota` |
| 5xx | `server_error`, photo service errors (`photo_failed`, `photo_empty`) |

## Health and options

| method | path | returns |
|---|---|---|
| GET | `/api/health` | `{status, service, database, models}` |
| GET | `/api/meta/options` | categories, subcategories, styles, occasions, seasons, weather, palettes, named colours |

## Accounts

| method | path | notes |
|---|---|---|
| POST | `/api/auth/register` | `{display_name, email, password}` → `201 {user, preferences}`. 10 per IP per hour |
| POST | `/api/auth/login` | `{email, password, remember}`. 12 h session (30 min idle), or 30 days with `remember`. 8 failures per email per 10 min → `429` |
| POST | `/api/auth/logout` | `204`, revokes this session |
| POST | `/api/auth/logout-all` | `204`, revokes every session of the account |
| GET | `/api/auth/me` | `{user, preferences}` |
| POST | `/api/auth/forgot` | `{email}` → `202 {message}`, the same answer whether or not the email has an account. Emails a one-time link (`/reset-password.html#token=…`, 30 minutes). 3 emails per address and 10 requests per IP per hour. `503 mail_not_configured` in production without SMTP |
| POST | `/api/auth/reset` | `{token, password}`: sets the new password, signs out every session. `400 reset_link_invalid` for a used, expired or unknown link. 20 tries per IP per hour |
| GET | `/api/auth/sessions` | the account's active sign-ins: `{sessions: [{id, device, signed_in_at, last_seen_at, remember, current}]}` |
| DELETE | `/api/auth/sessions/<id>` | signs out that one device (404 if it isn't yours) |

## Wardrobe

| method | path | notes |
|---|---|---|
| GET | `/api/wardrobe` | query `category, color, season, style, occasion, q, sort` (`newest`, `oldest`, `name`, `category`) → `{items, count, colors}` |
| POST | `/api/wardrobe` | JSON or multipart fields below, plus optional files `image` and `cutout`, `image_source` (`upload`/`stock`) and `pattern` (`""`, `striped`, `patterned`) → `201 {item}` |
| GET / PUT / DELETE | `/api/wardrobe/<id>` | PUT is partial; `remove_image=true` drops the photo; DELETE archives (kept for history) |
| GET | `/api/images/<key>` | the image bytes, to the owner only (public landing samples to anyone) |

Item fields:
- `name` (80 characters or fewer);
- `category` (`top`, `bottom`, `dress`, `outerwear`, `footwear`, `accessory`);
- `subcategory`;
- `main_color` (`#rrggbb`), `secondary_color`;
- `seasons`, `style`, `occasions`;
- `description` (500 characters or fewer).

Limits: up to 500 pieces per account. Photos must be JPEG, PNG or WebP, 15 MB at most;
they are re-encoded to WebP at 900 px or less, with metadata removed.

## Outfits

| method | path | notes |
|---|---|---|
| POST | `/api/recommendations/generate` | `{occasion, weather, temperature_c, style?, palette?, exclude?, previous_id?}` → `201 {outfit}` with items, `score` 0–100, `explanation`, `breakdown`, `engine`, `signature`. Pieces worn in the last 3 days rest |
| GET | `/api/recommendations/history` | `page`, `per_page`, `verdict` |
| GET | `/api/recommendations/<id>` | one outfit with photos |
| POST | `/api/recommendations/<id>/feedback` | `{verdict: "like" \| "dislike" \| null}` |
| POST | `/api/recommendations/<id>/save` | `{name}`; saving again renames |
| POST | `/api/recommendations/<id>/wear` | `{worn: true \| false}` |
| GET | `/api/outfits/saved` | saved outfits |
| DELETE | `/api/outfits/saved/<saved_id>` | unsave |
| GET | `/api/dashboard/summary` | counts, items per category, readiness, recent outfits |
| GET | `/api/dashboard/statistics` | colours, seasons, styles, occasions, weekly counts, most- and never-suggested pieces |

## Realistic photos (made by the server)

| method | path | notes |
|---|---|---|
| GET | `/api/photos/status` | `{engine, model, free: {key_hint}, gemini: {configured, model, hint}}`; keys are never returned |
| PUT | `/api/photos/free` | `{key}`: use the free open-source engine, optionally with your Pollinations key (`""` removes it) |
| POST | `/api/photos/gemini` | `{key}`: checks it with Google, picks the best image model, switches to Gemini |
| POST | `/api/photos/gemini/use` | switch back to Gemini with the saved key |
| DELETE | `/api/photos/gemini` | remove the Gemini key; back to the free engine |
| POST | `/api/photos/outfit/<id>` | `{force?}` → `{photo_url, model, cached, photos}`; the last four takes are kept. 40 per account per hour |
| POST | `/api/photos/outfit/<id>/choose` | `{index}`: which take is the cover |
| POST | `/api/photos/suggestion` | `{basic, item_ids, occasion}`: a Smart buys suggestion worn with your clothes (not stored) |
| POST | `/api/public/photo` | no account: `{pieces: [{role, subcategory, colour}], person?, backdrop?}`. Catalogue words only, cached, 12 per IP per hour |

Keys are sealed at rest (Fernet, key derived from `SECRET_KEY`) and sent only to their own
service, in a header.

## Profile and backup

| method | path | notes |
|---|---|---|
| GET | `/api/profile` | `{user, preferences, stats}` |
| PUT | `/api/profile` | `{display_name?, preferences?, current_password?, new_password?}`; a password change signs out every other session |
| DELETE | `/api/profile` | `{password}`: deletes the account and everything in it |
| POST | `/api/profile/export` | `{password}` → a `fitcheck-backup` JSON with images as data URLs; no keys |
| POST | `/api/profile/import` | a backup; validated completely before this account's wardrobe and history are replaced |
| POST | `/api/demo/load` | adds the 40-piece demo wardrobe (real CC0 photos with cut-outs) |

Smart buys (`api.shop.suggest()` in `api.js`) is worked out in the browser from the
wardrobe list, with `engine/shop.js`.
