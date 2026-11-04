"""
Outgoing email (password-reset links only).

Sends through any SMTP provider (Brevo, Mailgun, SendGrid, Amazon SES, Gmail with an
app password...) using TLS. Messages are plain text, built with EmailMessage, so
header injection isn't possible and nothing in them can run in a mail client.

Without SMTP_HOST:
  * development: the message is written to the server log, so you can copy the link;
  * production: email is "not configured" and the reset page says so. An operator can
    still issue a link with `python manage.py reset-link <email>`.
"""

import logging
import smtplib
import ssl
import threading
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

log = logging.getLogger("fitcheck.mail")


class MailNotConfigured(Exception):
    pass


def configured(cfg):
    return bool(cfg["SMTP_HOST"]) or cfg["ENV"] != "production"


def build(cfg, to, subject, body):
    msg = EmailMessage()
    sender = cfg["MAIL_FROM"] or "FitCheck.AI <no-reply@localhost>"
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain=sender.rsplit("@", 1)[-1].strip("> ") or "localhost")
    msg["Auto-Submitted"] = "auto-generated"
    msg.set_content(body)
    return msg


def _deliver(cfg, msg):
    host, port, security = cfg["SMTP_HOST"], cfg["SMTP_PORT"], cfg["SMTP_SECURITY"]
    timeout = 20
    context = ssl.create_default_context()
    if security == "ssl":
        server = smtplib.SMTP_SSL(host, port, timeout=timeout, context=context)
    else:
        server = smtplib.SMTP(host, port, timeout=timeout)
    try:
        server.ehlo()
        if security == "starttls":
            server.starttls(context=context)
            server.ehlo()
        if cfg["SMTP_USER"]:
            server.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"])
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except Exception:  # nosec B110: closing a connection that may already be gone
            pass


def send(cfg, to, subject, body):
    """
    Send one message. Normally in a background thread, so the response takes the
    same time whether or not an account exists (no account-probing by timing).
    """
    if not cfg["SMTP_HOST"]:
        if cfg["ENV"] == "production":
            raise MailNotConfigured()
        log.warning("Email (SMTP not configured, development only)\nTo: %s\nSubject: %s\n\n%s", to, subject, body)
        return
    msg = build(cfg, to, subject, body)
    settings = {k: cfg[k] for k in ("SMTP_HOST", "SMTP_PORT", "SMTP_SECURITY", "SMTP_USER", "SMTP_PASSWORD")}

    def run():
        try:
            _deliver(settings, msg)
        except Exception as err:  # never surfaces to the person: the answer is the same either way
            log.error("Couldn't send email to %s: %s", to.split("@")[-1], type(err).__name__)

    if cfg["MAIL_SYNC"]:
        run()
    else:
        threading.Thread(target=run, daemon=True).start()
