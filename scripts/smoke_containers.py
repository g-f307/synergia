from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

TARGETS = (
    ("API liveness", "http://127.0.0.1:8000/health/live", "application/json"),
    ("API readiness", "http://127.0.0.1:8000/health/ready", "application/json"),
    ("Web", "http://127.0.0.1:8080/", "text/html"),
    (
        "Web runtime config",
        "http://127.0.0.1:8080/runtime-config.js",
        "javascript",
    ),
)


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


def main() -> None:
    responses = {
        name: wait_for(name, url, expected_type)
        for name, url, expected_type in TARGETS
    }
    readiness = json.loads(responses["API readiness"])
    if readiness.get("status") != "ready":
        raise RuntimeError(f"API is not ready: {readiness}")
    runtime = responses["Web runtime config"].decode("utf-8")
    if "http://localhost:8000" not in runtime:
        raise RuntimeError(
            "runtime config does not expose the expected local API origin"
        )


if __name__ == "__main__":
    main()
