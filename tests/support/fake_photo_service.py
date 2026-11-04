"""
A stand-in for the photo services during tests (the test machine can't reach
them): answers like Pollinations and Gemini, with a real JPEG, and records what
it was sent.

    python tests/support/fake_photo_service.py 5600
"""

import base64
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHOTO = (ROOT / "assets/images/garments/pale-blue-oxford.jpg").read_bytes()
LOG = []
MODE = {"fail": None}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, status, body, ctype):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _record(self, body=b""):
        LOG.append({"method": self.command, "path": self.path, "auth": self.headers.get("Authorization"),
                    "goog": self.headers.get("x-goog-api-key"), "body": body.decode("latin-1")[:200000]})

    def do_GET(self):
        if not self.path.startswith("/__"):
            self._record()
        if self.path == "/__clear":
            LOG.clear()
            return self._send(200, b"{}", "application/json")
        if self.path == "/__log":
            return self._send(200, json.dumps(LOG).encode(), "application/json")
        if self.path.startswith("/__mode/"):
            MODE["fail"] = self.path.split("/")[-1] or None
            if MODE["fail"] == "none":
                MODE["fail"] = None
            return self._send(200, b"{}", "application/json")
        if self.path.startswith("/image/models"):
            return self._send(200, json.dumps([{"name": "zimage", "input_modalities": ["text"]},
                                               {"name": "klein", "input_modalities": ["text", "image"]},
                                               {"name": "flux", "input_modalities": ["text"]}]).encode(), "application/json")
        if self.path.startswith("/gemini/models"):
            return self._send(200, json.dumps({"models": [{"name": "models/gemini-2.5-flash-image",
                                                           "supportedGenerationMethods": ["generateContent"]}]}).encode(), "application/json")
        if MODE["fail"] == "busy":
            return self._send(429, b"busy", "text/plain")
        return self._send(200, PHOTO, "image/jpeg")

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self._record(body)
        if MODE["fail"] == "busy":
            return self._send(429, b'{"error":{"message":"busy"}}', "application/json")
        if self.path.endswith("/v1/images/edits"):
            return self._send(200, json.dumps({"data": [{"b64_json": base64.b64encode(PHOTO).decode()}]}).encode(), "application/json")
        if ":generateContent" in self.path:
            if MODE["fail"] == "quota":
                return self._send(429, b'{"error":{"message":"Quota exceeded","status":"RESOURCE_EXHAUSTED"}}', "application/json")
            return self._send(200, json.dumps({"modelVersion": "gemini-2.5-flash-image", "candidates": [{"content": {"parts": [
                {"inlineData": {"mimeType": "image/jpeg", "data": base64.b64encode(PHOTO).decode()}}]}}]}).encode(), "application/json")
        return self._send(404, b"{}", "application/json")


def serve(port):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 5600), Handler)
    srv.serve_forever()
