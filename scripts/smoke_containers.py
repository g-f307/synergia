from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request


def wait_for(name: str, url: str, expected_type: str) -> bytes:
    deadline = time.monotonic() + 120
    last_error = "not attempted"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                body = response.read()
                content_type = response.headers.get_content_type()
                if response.status != 200:
                    raise RuntimeError(f"HTTP {response.status}")
                if expected_type not in content_type:
                    raise RuntimeError(
                        f"unexpected content type {content_type!r}, "
                        f"expected {expected_type!r}"
                    )
                print(f"ok: {name} ({url})", flush=True)
                return body
        except (OSError, RuntimeError, urllib.error.URLError) as exc:
            last_error = str(exc)
            time.sleep(2)
    raise RuntimeError(f"timeout waiting for {name}: {last_error}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--backend-url",
        default=os.environ.get(
            "SMOKE_BACKEND_URL",
            f"http://127.0.0.1:{os.environ.get('BACKEND_PORT', '8000')}",
        ),
    )
    parser.add_argument(
        "--web-url",
        default=os.environ.get(
            "SMOKE_WEB_URL",
            f"http://127.0.0.1:{os.environ.get('WEB_PORT', '8080')}",
        ),
    )
    parser.add_argument(
        "--expected-api-origin",
        default=os.environ.get(
            "SMOKE_EXPECTED_API_ORIGIN",
            os.environ.get("SYNERGIA_API_ORIGIN", "http://localhost:8000"),
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    backend = args.backend_url.rstrip("/")
    web = args.web_url.rstrip("/")
    targets = (
        ("API liveness", f"{backend}/health/live", "application/json"),
        ("API readiness", f"{backend}/health/ready", "application/json"),
        ("Web", f"{web}/", "text/html"),
        ("Web runtime config", f"{web}/runtime-config.js", "javascript"),
    )
    responses = {
        name: wait_for(name, url, expected_type)
        for name, url, expected_type in targets
    }
    readiness = json.loads(responses["API readiness"])
    if readiness.get("status") != "ready":
        raise RuntimeError(f"API is not ready: {readiness}")
    runtime = responses["Web runtime config"].decode("utf-8")
    expected = f"apiUrl: '{args.expected_api_origin}'"
    if expected not in runtime:
        raise RuntimeError(
            f"runtime config does not expose expected API origin: {expected!r}"
        )


if __name__ == "__main__":
    main()
