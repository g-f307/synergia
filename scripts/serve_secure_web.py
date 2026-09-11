from __future__ import annotations

import argparse
import json
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


def api_origin() -> str:
    origin = os.getenv("SYNERGIA_API_ORIGIN", "http://127.0.0.1:8000").rstrip("/")
    parsed = urlparse(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path:
        raise ValueError("SYNERGIA_API_ORIGIN must be an absolute HTTP(S) origin")
    return origin


def content_security_policy(origin: str) -> str:
    return (
        "default-src 'self'; base-uri 'self'; object-src 'none'; "
        "frame-ancestors 'none'; form-action 'self'; script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; font-src 'self'; "
        f"img-src 'self' data:; connect-src 'self' {origin}"
    )


class SecureSpaHandler(SimpleHTTPRequestHandler):
    api_origin = ""

    def end_headers(self) -> None:
        self.send_header(
            "Content-Security-Policy", content_security_policy(self.api_origin)
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Permissions-Policy",
            "camera=(), geolocation=(), microphone=(), payment=(), usb=()",
        )
        super().end_headers()

    def send_head(self):
        path = Path(self.translate_path(self.path))
        if not path.exists() and "." not in Path(urlparse(self.path).path).name:
            self.path = "/index.html"
        return super().send_head()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4200)
    args = parser.parse_args()
    SecureSpaHandler.api_origin = api_origin()
    runtime_config = Path(args.directory) / "runtime-config.js"
    runtime_config.write_text(
        "globalThis.__SYNERGIA_CONFIG__ = "
        + json.dumps({"apiUrl": SecureSpaHandler.api_origin})
        + ";\n",
        encoding="utf-8",
    )
    handler = partial(SecureSpaHandler, directory=args.directory)
    ThreadingHTTPServer((args.host, args.port), handler).serve_forever()


if __name__ == "__main__":
    main()
