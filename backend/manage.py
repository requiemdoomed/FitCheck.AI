"""
Operator commands (run on the server, e.g. in Render's Shell tab):

    python manage.py reset-link person@example.com   # one-time password-reset link (when email isn't set up)
    python manage.py prune                           # clear old sessions, reset links and rate counters
    python manage.py stats                           # how many accounts, pieces and outfits there are

Uses the same environment variables as the server.
"""

import sys

from app import create_app


def main(argv):
    if len(argv) < 2 or argv[1] not in ("reset-link", "prune", "stats"):
        print(__doc__.strip())
        return 2
    app = create_app()
    base = app.config["APP_URL"] or "http://localhost:8000"
    with app.test_request_context("/", base_url=base):
        import db
        import security as sec
        try:
            if argv[1] == "reset-link":
                if len(argv) != 3:
                    print("Usage: python manage.py reset-link <email>")
                    return 2
                from api_auth import reset_link_for
                user = db.one("SELECT id FROM users WHERE email = %s", (argv[2].strip().lower(),))
                if not user:
                    print("No account uses that email.")
                    return 1
                link = reset_link_for(user["id"])
                db.commit()
                print(f"One-time link (valid {app.config['RESET_MINUTES']} minutes). Send it to the person privately:\n{link}")
            elif argv[1] == "prune":
                sec.prune_rate_events()
                db.commit()
                print("Old sessions, reset links and rate counters cleared.")
            else:
                for table in ("users", "items", "outfits", "images", "sessions"):
                    print(f"{table:10} {db.one(f'SELECT COUNT(*) AS n FROM {table}')['n']}")  # nosec B608: fixed table names
        finally:
            db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
