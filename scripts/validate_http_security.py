from __future__ import annotations

import json
from pathlib import Path

from serve_secure_web import content_security_policy

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    index = (ROOT / "web/src/index.html").read_text(encoding="utf-8")
    if "Content-Security-Policy" in index:
        raise SystemExit("CSP must be emitted as an HTTP header, not a meta tag")

    template = (ROOT / "web/nginx/default.conf.template").read_text(encoding="utf-8")
    required = ("${SYNERGIA_API_ORIGIN}", "frame-ancestors 'none'", "always")
    if any(item not in template for item in required) or "unsafe-eval" in template:
        raise SystemExit("The executable frontend header policy is incomplete")

    runtime_template = (ROOT / "web/runtime-config.js.template").read_text(
        encoding="utf-8"
    )
    if "${SYNERGIA_API_ORIGIN}" not in runtime_template:
        raise SystemExit("The frontend API runtime configuration is not injectable")

    dockerfile = (ROOT / "web/Dockerfile").read_text(encoding="utf-8")
    if "COPY --chmod=755 docker-entrypoint.d/40-synergia-config.sh" not in dockerfile:
        raise SystemExit("The runtime configuration entrypoint must be executable")
    if "USER nginx" not in dockerfile:
        raise SystemExit("The published frontend must run as a non-root user")

    for environment, origin in {
        "homologation": "https://api.homolog.synergia.example",
        "production": "https://api.synergia.example",
    }.items():
        policy = content_security_policy(origin)
        if origin not in policy or "localhost" in policy or "unsafe-eval" in policy:
            raise SystemExit(f"Invalid CSP for {environment}")

    angular = json.loads((ROOT / "web/angular.json").read_text(encoding="utf-8"))
    production = angular["projects"]["synergia-web"]["architect"]["build"][
        "configurations"
    ]["production"]
    if production.get("optimization", {}).get("styles", {}).get("inlineCritical"):
        raise SystemExit("Inline critical CSS creates CSP-incompatible event handlers")

    forbidden = ("[innerHTML]", "bypassSecurityTrustHtml", "document.write(")
    violations: list[str] = []
    for path in (ROOT / "web/src").rglob("*"):
        if path.suffix not in {".ts", ".html"}:
            continue
        content = path.read_text(encoding="utf-8")
        for pattern in forbidden:
            if pattern in content:
                violations.append(f"{path.relative_to(ROOT)}: {pattern}")
    if violations:
        raise SystemExit("Unsafe DOM sinks found:\n" + "\n".join(violations))

    print("HTTP, CSP and unsafe DOM sink baseline validated.")


if __name__ == "__main__":
    main()
