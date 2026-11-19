"""Serve the immutable benchmark receipt and allowlisted live comparisons on loopback."""

import argparse
import json
import logging
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit

import psycopg

from .db import IN_COMPOSE, postgres
from .measure import compare, queries

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "console" / "dist"


def server(port, receipt):
    class Handler(BaseHTTPRequestHandler):
        def send(self, status, content, mime="application/json"):
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            path = urlsplit(self.path).path
            if (
                self.headers.get("Host")
                not in (
                    f"127.0.0.1:{self.server.server_port}",
                    f"localhost:{self.server.server_port}",
                )
                or self.headers.get("Sec-Fetch-Site") == "cross-site"
            ):
                return self.send(403, b'{"error":"local requests only"}')
            if path == "/api/report":
                try:
                    return self.send(200, receipt.read_bytes())
                except FileNotFoundError:
                    return self.send(503, b'{"error":"benchmark receipt missing"}')
            if (
                path.startswith("/api/compare/")
                and (key := path.removeprefix("/api/compare/")) in queries
            ):
                try:
                    with postgres() as pg:
                        value = compare(pg, key)
                    return self.send(200, json.dumps(value).encode())
                except (
                    psycopg.Error,
                    URLError,
                    TimeoutError,
                    OSError,
                    ValueError,
                ) as error:
                    logging.getLogger(__name__).warning(
                        "live comparison failed: %s", type(error).__name__
                    )
                    return self.send(
                        503, b'{"error":"database comparison unavailable"}'
                    )
            if path == "/":
                asset = DIST / "index.html"
            elif path.startswith("/assets/") and "/" not in path[len("/assets/") :]:
                asset = DIST / "assets" / path[len("/assets/") :]
            else:
                return self.send(404, b'{"error":"not found"}')
            if not asset.is_file():
                return self.send(
                    404, b'{"error":"asset missing; build the console first"}'
                )
            return self.send(
                200,
                asset.read_bytes(),
                mimetypes.guess_type(asset)[0] or "application/octet-stream",
            )

    return ThreadingHTTPServer(
        ("0.0.0.0" if IN_COMPOSE else "127.0.0.1", port), Handler
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=58238)
    parser.add_argument("--report", type=Path, default=ROOT / "evidence/run.json")
    args = parser.parse_args()
    with server(args.port, args.report) as http:
        print(f"http://127.0.0.1:{http.server_port}", flush=True)
        try:
            http.serve_forever()
        except KeyboardInterrupt:
            pass
