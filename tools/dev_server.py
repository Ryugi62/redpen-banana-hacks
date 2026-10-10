"""Local server: static public/ + /api/grade + /api/regrade (same handlers as Vercel). 127.0.0.1 only."""
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from redpen.infrastructure.http import make_handler  # noqa: E402

PUBLIC = os.path.join(os.path.dirname(__file__), "..", "public")
G, R = make_handler("grade"), make_handler("regrade")


class Dev(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=PUBLIC, **k)

    def do_POST(self):  # noqa: N802
        cls = G if self.path.startswith("/api/grade") else R if self.path.startswith("/api/regrade") else None
        if cls is None:
            self.send_error(404)
            return
        cls.do_POST(self)

    _send = G._send


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8787
    ThreadingHTTPServer(("127.0.0.1", port), Dev).serve_forever()
