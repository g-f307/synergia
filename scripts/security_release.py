#!/usr/bin/env python3
"""Release-security gates and sanitized evidence generation.

The module intentionally uses the standard library so the policy can be tested
without network access. External scanners feed their normalized findings into
the same blocking policy in CI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs/security-release-policy.json"
EVIDENCE = ROOT / "reports/security"
SEVERITY = {"unknown": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
SECRET_PATTERNS = {
    "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "github-token": re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b"),
    "aws-access-key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "jwt": re.compile(
        r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"
    ),
}
TEXT_SUFFIXES = {
    ".cfg",
    ".conf",
    ".css",
    ".csv",
    ".dockerfile",
    ".env",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".txt",
    ".yaml",
    ".yml",
}
IGNORED_PARTS = {
    ".git",
    ".venv",
    "node_modules",
    "coverage",
    "dist",
    "reports",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
}


def _write(name: str, document: dict) -> Path:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    target = EVIDENCE / name
    target.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return target


def load_policy() -> dict:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    if policy.get("schema_version") != 1:
        raise ValueError("unsupported security policy schema")
    return policy


def enforce_findings(document: dict, *, now: datetime | None = None) -> None:
    policy = load_policy()
    threshold = SEVERITY[policy["blocking_severity"]]
    clock = now or datetime.now(UTC)
    exceptions = {item["id"]: item for item in policy.get("exceptions", [])}
    blocked: list[str] = []
    for finding in document.get("findings", []):
        if not finding.get("owner") or finding.get("retest") not in {
            "pending",
            "passed",
        }:
            raise ValueError("security finding lacks owner or retest evidence")
        severity = str(finding.get("severity", "unknown")).lower()
        if SEVERITY.get(severity, 0) < threshold or finding.get("status") == "fixed":
            continue
        exception = exceptions.get(finding.get("id"))
        valid_exception = False
        if exception:
            expires = datetime.fromisoformat(
                exception["expires_at"].replace("Z", "+00:00")
            )
            valid_exception = bool(
                exception.get("owner")
                and exception.get("rationale")
                and exception.get("mitigation")
                and expires > clock
            )
        if not valid_exception:
            blocked.append(f"{finding.get('id', 'unknown')} ({severity})")
    if blocked:
        raise ValueError("blocking security findings: " + ", ".join(blocked))


def _candidate_files(root: Path):
    for path in root.rglob("*"):
        ignored = any(
            part in IGNORED_PARTS
            or part.startswith((".test-tmp", ".pytest-", ".tmp", ".review-tmp"))
            for part in path.parts
        )
        if not path.is_file() or ignored:
            continue
        if path.suffix.lower() in TEXT_SUFFIXES or path.name in {
            "Dockerfile",
            ".env.example",
        }:
            yield path


def scan_secrets(root: Path = ROOT) -> dict:
    findings = []
    for path in _candidate_files(root):
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line_number, line in enumerate(content.splitlines(), 1):
            for kind, pattern in SECRET_PATTERNS.items():
                if pattern.search(line):
                    digest = hashlib.sha256(line.encode()).hexdigest()[:12]
                    findings.append(
                        {
                            "id": f"secret:{kind}:{digest}",
                            "severity": "critical",
                            "status": "open",
                            "owner": "security",
                            "retest": "pending",
                            "location": (
                                f"{path.relative_to(root).as_posix()}:{line_number}"
                            ),
                            "kind": kind,
                        }
                    )
    document = {
        "schema_version": 1,
        "scanner": "synergia-secret-scan/1",
        "findings": findings,
    }
    _write("secret-scan.json", document)
    enforce_findings(document)
    return document


def _component(name: str, version: str, component_type: str, scope: str) -> dict:
    return {"type": component_type, "name": name, "version": version, "scope": scope}


def generate_sbom() -> dict:
    components: dict[tuple[str, str, str], dict] = {}
    for requirement in metadata.distributions():
        name = requirement.metadata.get("Name")
        if name:
            item = _component(name, requirement.version, "library", "required")
            components[("python", name.lower(), requirement.version)] = item | {
                "purl": f"pkg:pypi/{name.lower()}@{requirement.version}"
            }
    lock = json.loads((ROOT / "web/package-lock.json").read_text(encoding="utf-8"))
    for path, package in lock.get("packages", {}).items():
        if not path.startswith("node_modules/") or not package.get("version"):
            continue
        name = path.removeprefix("node_modules/")
        version = package["version"]
        scope = "optional" if package.get("dev") else "required"
        item = _component(name, version, "library", scope)
        components[("npm", name, version)] = item | {
            "purl": f"pkg:npm/{name}@{version}"
        }
    docker_sources = [ROOT / "web/Dockerfile", ROOT / "docker-compose.yml"]
    image_pattern = re.compile(r"(?:FROM|image:)\s+([^\s]+)", re.IGNORECASE)
    for source in docker_sources:
        for image in image_pattern.findall(source.read_text(encoding="utf-8")):
            name, _, version = image.partition(":")
            version = version or "latest"
            item = _component(name, version, "container", "required")
            components[("container", name, version)] = item | {
                "purl": f"pkg:docker/{name}@{version}"
            }
    document = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": "urn:uuid:00000000-0000-4000-8000-000000000092",
        "version": 1,
        "metadata": {"component": {"type": "application", "name": "synergia"}},
        "components": [components[key] for key in sorted(components)],
    }
    _write("sbom.cdx.json", document)
    return document


def _request(
    url: str,
    *,
    method: str = "GET",
    headers: dict | None = None,
    data: bytes | None = None,
):
    request = urllib.request.Request(
        url, method=method, headers=headers or {}, data=data
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read()


def run_dast(target: str) -> dict:
    parsed = urllib.parse.urlparse(target)
    authorized = {"127.0.0.1", "localhost", "::1"}
    if parsed.scheme != "http" or parsed.hostname not in authorized:
        raise ValueError(
            "DAST target must be an explicitly disposable loopback HTTP environment"
        )
    base = target.rstrip("/")
    checks = []
    status, headers, body = _request(base + "/health")
    checks.append({"id": "health", "passed": status == 200})
    baseline = {
        "content-security-policy",
        "x-content-type-options",
        "x-frame-options",
        "referrer-policy",
        "cache-control",
    }
    checks.append(
        {
            "id": "security-headers",
            "passed": baseline <= {key.lower() for key in headers},
        }
    )
    payloads = {
        "xss": "<script>synergia-probe</script>",
        "sql-injection": "' UNION SELECT 'synergia-probe' --",
        "command-injection": "; id synergia-probe",
        "html-injection": "<img src=x alt=synergia-probe>",
    }
    for threat, value in payloads.items():
        query = urllib.parse.urlencode({"q": value})
        status, _, body = _request(base + "/definitely-missing?" + query)
        checks.append(
            {
                "id": f"no-reflection-{threat}",
                "passed": b"synergia-probe" not in body and status == 404,
            }
        )
    payload = json.dumps(
        {"email": "nobody@example.invalid' OR '1'='1", "password": "invalid"}
    ).encode()
    status, _, body = _request(
        base + "/auth/login",
        method="POST",
        headers={"Content-Type": "application/json"},
        data=payload,
    )
    checks.append(
        {
            "id": "login-injection-safe",
            "passed": status in {401, 422, 429} and b"traceback" not in body.lower(),
        }
    )
    email = os.environ.get("DAST_EMAIL")
    password = os.environ.get("DAST_PASSWORD")
    if not email or not password:
        raise ValueError(
            "DAST_EMAIL and DAST_PASSWORD are required for authenticated checks"
        )
    login = json.dumps({"email": email, "password": password}).encode()
    status, _, body = _request(
        base + "/auth/login",
        method="POST",
        headers={"Content-Type": "application/json"},
        data=login,
    )
    try:
        access_token = json.loads(body).get("access_token") if status == 200 else None
    except json.JSONDecodeError:
        access_token = None
    checks.append({"id": "authenticated-session", "passed": bool(access_token)})
    if access_token:
        authorization = {"Authorization": f"Bearer {access_token}"}
        status, _, body = _request(base + "/me", headers=authorization)
        checks.append(
            {
                "id": "authenticated-profile",
                "passed": status == 200 and access_token.encode() not in body,
            }
        )
        for threat, value in payloads.items():
            offensive_query = urllib.parse.urlencode(
                {
                    "type": "workorder",
                    "query": value,
                }
            )
            status, _, body = _request(
                base + "/search?" + offensive_query, headers=authorization
            )
            checks.append(
                {
                    "id": f"authenticated-query-{threat}",
                    "passed": status == 200 and b"traceback" not in body.lower(),
                }
            )
        status, _, body = _request(
            base + "/imports/%2e%2e%2f%2e%2e%2fetc%2fpasswd",
            headers=authorization,
        )
        checks.append(
            {
                "id": "path-traversal",
                "passed": status in {400, 404, 422} and b"root:" not in body,
            }
        )
    findings = [
        {
            "id": f"dast:{item['id']}",
            "severity": "high",
            "status": "open",
            "owner": "security",
            "retest": "pending",
        }
        for item in checks
        if not item["passed"]
    ]
    document = {
        "schema_version": 1,
        "scanner": "synergia-controlled-dast/1",
        "target": f"{parsed.scheme}://{parsed.hostname}:{parsed.port or 80}",
        "checks": checks,
        "findings": findings,
    }
    _write("dast-report.json", document)
    enforce_findings(document)
    return document


def normalize_audit(source: Path, ecosystem: str) -> dict:
    raw = json.loads(source.read_text(encoding="utf-8"))
    findings = []
    if ecosystem == "python":
        if not isinstance(raw.get("dependencies"), list):
            raise ValueError("invalid or incomplete pip-audit report")
        for dependency in raw.get("dependencies", []):
            for vulnerability in dependency.get("vulns", []):
                findings.append(
                    {
                        "id": vulnerability["id"],
                        "severity": "high",
                        "status": "open",
                        "owner": "security",
                        "retest": "pending",
                        "component": dependency["name"],
                        "version": dependency["version"],
                    }
                )
    elif ecosystem == "node":
        if raw.get("error") or not isinstance(raw.get("vulnerabilities"), dict):
            raise ValueError("invalid or incomplete npm audit report")
        for name, vulnerability in raw.get("vulnerabilities", {}).items():
            findings.append(
                {
                    "id": f"npm:{name}",
                    "severity": vulnerability.get("severity", "unknown"),
                    "status": "open",
                    "owner": "security",
                    "retest": "pending",
                    "component": name,
                }
            )
    elif ecosystem.startswith("trivy-"):
        if not isinstance(raw.get("Results"), list):
            raise ValueError("invalid or incomplete Trivy report")
        for result in raw["Results"]:
            target = str(result.get("Target", "unknown"))
            for finding_type, items in (
                ("vulnerability", result.get("Vulnerabilities", [])),
                ("misconfiguration", result.get("Misconfigurations", [])),
                ("secret", result.get("Secrets", [])),
            ):
                for item in items or []:
                    identifier = item.get("VulnerabilityID") or item.get("ID")
                    if not identifier:
                        rule = item.get("RuleID", "unknown")
                        identifier = f"secret:{rule}"
                    findings.append(
                        {
                            "id": str(identifier),
                            "severity": str(item.get("Severity", "high")).lower(),
                            "status": "open",
                            "owner": "security",
                            "retest": "pending",
                            "target": target,
                            "kind": finding_type,
                        }
                    )
    else:
        raise ValueError(f"unsupported ecosystem: {ecosystem}")
    document = {"schema_version": 1, "scanner": ecosystem, "findings": findings}
    _write(f"{ecosystem}-dependency-report.json", document)
    enforce_findings(document)
    return document


def validate() -> None:
    policy = load_policy()
    required = {"owner", "rationale", "mitigation", "expires_at"}
    for exception in policy.get("exceptions", []):
        if not required <= exception.keys():
            raise ValueError(
                "security exception lacks owner, rationale, mitigation or expiry"
            )
    scan_secrets()
    sbom = generate_sbom()
    if not any(item["type"] == "container" for item in sbom["components"]):
        raise ValueError("SBOM does not include container images")


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")
    subparsers.add_parser("secrets")
    subparsers.add_parser("sbom")
    dast = subparsers.add_parser("dast")
    dast.add_argument("--target", required=True)
    audit = subparsers.add_parser("audit")
    audit.add_argument(
        "--ecosystem",
        choices=("python", "node", "trivy-filesystem", "trivy-image"),
        required=True,
    )
    audit.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "validate":
            validate()
        elif args.command == "secrets":
            scan_secrets()
        elif args.command == "sbom":
            generate_sbom()
        elif args.command == "dast":
            run_dast(args.target)
        else:
            normalize_audit(args.input, args.ecosystem)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"security gate failed: {error}", file=sys.stderr)
        return 1
    print(f"Security release command '{args.command}' passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
