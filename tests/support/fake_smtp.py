"""
A tiny SMTP server for tests: accepts any message and keeps it. The server's
real SMTP code (smtplib) talks to it exactly as it would to a mail provider.

    python fake_smtp.py 5613 /path/to/outbox     # each message saved as a .eml file
"""

import socketserver
import sys
import threading
from email import message_from_bytes, policy
from pathlib import Path

INBOX = []          # email.message.EmailMessage objects, oldest first
OUTBOX_DIR = None


class Handler(socketserver.StreamRequestHandler):
    def reply(self, line):
        self.wfile.write(line.encode() + b"\r\n")

    def handle(self):
        self.reply("220 fake-smtp ready")
        data_mode, lines = False, []
        while True:
            raw = self.rfile.readline()
            if not raw:
                return
            if data_mode:
                if raw in (b".\r\n", b".\n"):
                    data_mode = False
                    msg = message_from_bytes(b"".join(lines), policy=policy.default)
                    INBOX.append(msg)
                    if OUTBOX_DIR:
                        (Path(OUTBOX_DIR) / f"{len(INBOX):04d}.eml").write_bytes(b"".join(lines))
                    lines = []
                    self.reply("250 queued")
                else:
                    lines.append(raw[1:] if raw.startswith(b"..") else raw)
                continue
            cmd = raw.decode(errors="replace").strip().upper()
            if cmd.startswith(("EHLO", "HELO")):
                self.reply("250 fake-smtp")
            elif cmd.startswith(("MAIL", "RCPT", "RSET", "NOOP")):
                self.reply("250 ok")
            elif cmd == "DATA":
                data_mode = True
                self.reply("354 end with .")
            elif cmd == "QUIT":
                self.reply("221 bye")
                return
            else:
                self.reply("502 not implemented")


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def serve(port):
    srv = Server(("127.0.0.1", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


if __name__ == "__main__":
    OUTBOX_DIR = sys.argv[2] if len(sys.argv) > 2 else None
    Server(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 5613), Handler).serve_forever()
