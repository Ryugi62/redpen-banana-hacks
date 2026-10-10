"""Vercel-style BaseHTTPRequestHandler wrapping the JSON service."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler

from . import service

MAX_BODY = 6_000_000


def make_handler(route: str):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: dict):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):  # noqa: N802
            try:
                n = int(self.headers.get("Content-Length") or 0)
                if n <= 0 or n > MAX_BODY:
                    return self._send(413, {"error": "Photo too large or empty."})
                payload = json.loads(self.rfile.read(n) or b"{}")
                client = (self.headers.get("x-forwarded-for") or self.client_address[0] or "anon").split(",")[0].strip()
                out = service.grade(payload, client) if route == "grade" else service.regrade(payload)
                self._send(200, out)
            except service.BadRequest as e:
                self._send(400, {"error": str(e)})
            except service.RateLimited as e:
                self._send(429, {"error": str(e)})
            except service.VisionUnavailable:
                self._send(503, {"error": "The reading model is busy right now. Try again in a minute, or open a sample."})
            except json.JSONDecodeError:
                self._send(400, {"error": "Body must be JSON."})
            except Exception:  # never leak internals
                self._send(500, {"error": "Something went wrong while checking this photo."})

        def do_GET(self):  # noqa: N802
            self._send(200, {"ok": True, "route": route})

        def log_message(self, *args):
            pass

    return Handler
