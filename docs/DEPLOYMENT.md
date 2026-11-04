# Deploying FitCheck.AI

_Author: Swayam Shakya_

FitCheck.AI is one web service: Flask behind gunicorn. It serves the pages and `/api`
and needs a MySQL 8 database. All configuration comes from environment variables
(listed in `.env.example`).

## Settings

| Variable | Required | Notes |
|---|---|---|
| `SECRET_KEY` | yes | 32+ random characters (`python -c "import secrets; print(secrets.token_urlsafe(48))"`). Keep it stable: it derives the key that seals saved photo-service keys |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER` | yes | defaults `127.0.0.1`, `3306`, `fitcheck`, `fitcheck_app` |
| `DB_PASSWORD` | yes | the app refuses to start in production without it |
| `DB_SSL`, `DB_SSL_CA` | for managed DBs | `DB_SSL=1` requires TLS to MySQL |
| `FLASK_ENV` | no | `production` (default) trusts the host's proxy for client IPs |
| `COOKIE_SECURE` | no | `1` by default; set `0` only for plain-http local use |
| `POLLINATIONS_KEY` | no | a free key from enter.pollinations.ai: better open models for everyone |
| `PHOTOS_PER_HOUR`, `PUBLIC_PHOTOS_PER_HOUR` | no | 40 and 12 |
| `APP_URL` | with email | the public address reset links point to, e.g. `https://fitcheck.onrender.com` |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM` | for reset email | any SMTP provider; `SMTP_SECURITY` is `starttls` (587) or `ssl` (465) |

Tables are created by `python backend/init_db.py`. It is safe to run on every start: every
table is `CREATE TABLE IF NOT EXISTS`.

## 1. Render (recommended)

1. Put the project in a GitHub repository. `.env` is git-ignored, so never commit it.
2. In Render, choose **New → Blueprint** and select the repository. `render.yaml` defines:
   - **fitcheck** (web, Python): `pip install -r backend/requirements.txt`, then
     `init_db.py` and gunicorn; health check `/api/health`;
   - **fitcheck-mysql** (private service, `mysql:8.4` image, 5 GB disk at
     `/var/lib/mysql`). It is not reachable from the internet.
3. When asked:
   - type one long random password into **both** `MYSQL_PASSWORD` (MySQL service) and
     `DB_PASSWORD` (web);
   - optionally fill in `POLLINATIONS_KEY`.

   `SECRET_KEY` and the MySQL root password are generated.
4. Deploy. Open the `.onrender.com` address, which uses HTTPS automatically. Add your own
   domain under **Settings → Custom Domains** if you like.

Notes:
- Both services use the **Starter** plan, because a persistent disk needs a paid
  instance. Turn on disk snapshots for backups.
- **Using a managed MySQL instead** (Aiven, Railway, DigitalOcean…): delete the
  `fitcheck-mysql` service from `render.yaml`, then set `DB_HOST`, `DB_PORT`, `DB_USER`,
  `DB_PASSWORD`, `DB_NAME` and `DB_SSL=1` on the web service.

## 2. Docker / any container host

```bash
cp .env.example .env            # set SECRET_KEY and DB_PASSWORD
docker compose up --build       # MySQL + app on http://localhost:8000
```

The image runs as a non-root user and listens on `$PORT` (default 8000). For a public
server, put an HTTPS reverse proxy in front (Caddy, nginx, or your host's load balancer)
and remove `COOKIE_SECURE: "0"` from `docker-compose.yml`.

## 3. Local development without Docker

```bash
# MySQL: database + least-privilege user
mysql -u root -p <<'SQL'
CREATE DATABASE fitcheck CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER 'fitcheck_app'@'localhost' IDENTIFIED BY 'LocalDevPass_2026';
GRANT ALL ON fitcheck.* TO 'fitcheck_app'@'localhost';
-- for the tests:
CREATE DATABASE fitcheck_test CHARACTER SET utf8mb4;
GRANT ALL ON fitcheck_test.* TO 'fitcheck_app'@'localhost';
SQL

python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
export DB_PASSWORD=LocalDevPass_2026 COOKIE_SECURE=0 FLASK_ENV=development
cd backend && python init_db.py && flask --app wsgi run --port 8000
```

## Password-reset email

1. Pick any SMTP provider. Brevo, Mailgun and SendGrid have free tiers; Gmail works with
   an app password for small use.
2. Verify your sending domain there (SPF and DKIM records), so messages aren't marked as
   spam.
3. Set `APP_URL`, `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` and `MAIL_FROM`. In
   production the server refuses to start with SMTP but no `https://` `APP_URL`.
4. Test it: **Sign in → Forgot your password?**

Without email, development prints the reset link to the server log. In production the
page explains that reset email isn't set up, and you can issue a link yourself (on Render:
the web service → **Shell**):

```bash
cd backend && python manage.py reset-link person@example.com
python manage.py stats      # accounts, pieces, outfits
python manage.py prune      # clear old sessions, reset links and rate counters (also automatic)
```

## Checklist before going public

- HTTPS on (automatic on Render).
- `SECRET_KEY` generated and stored only in the host's settings.
- The database is not reachable from the internet (private service, or an IP allow-list
  with TLS).
- Backups or disk snapshots are turned on.
- Reset email is set up and tested, or you know how to use `manage.py reset-link`.
- Read `SECURITY.md` → *Residual risk*.
