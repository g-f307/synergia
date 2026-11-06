"""Offline contracts for the operational guides; never execute deployment blocks."""

from __future__ import annotations

import argparse
import ast
import re
import shlex
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

from app.deployment_environment import validate_deployment_environment

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.security_release import SECRET_PATTERNS  # noqa: E402

DOCS = ROOT / "docs" / "deployment"
NAMES = (
    "README.md",
    "environment-reference.md",
    "deployment-guide.md",
    "troubleshooting.md",
    "update-and-rollback.md",
    "post-deployment-checklist.md",
    "lg-email-api.md",
)
METADATA = (
    "Onde executar",
    "Pré-condições",
    "Entradas",
    "Efeito",
    "Resultado esperado",
    "Interpretação de falhas",
    "Próxima ação",
    "Evidência permitida",
)
FENCE = re.compile(r"^```(\w*)\n(.*?)^```", re.MULTILINE | re.DOTALL)
LINK = re.compile(r"\[[^\]]+\]\(([^\s)]+)\)")


def _read(name: str) -> str:
    return (DOCS / name).read_text(encoding="utf-8")


def _anchors(content: str) -> set[str]:
    anchors = set()
    counts: dict[str, int] = {}
    for heading in re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$", content, re.MULTILINE):
        slug = re.sub(r"[^\w\s-]", "", heading.lower()).replace(" ", "-")
        count = counts.get(slug, 0)
        counts[slug] = count + 1
        anchors.add(f"{slug}-{count}" if count else slug)
    return anchors


def test_all_guides_exist_and_are_reachable_from_single_entry() -> None:
    assert all((DOCS / name).is_file() for name in NAMES)
    for path in (
        ROOT / "README.md",
        ROOT / "docs/getting-started.md",
        ROOT / "docs/container-deployment.md",
        ROOT / "docs/deployment-environments.md",
    ):
        destinations = {
            (path.parent / link).resolve()
            for link in LINK.findall(path.read_text(encoding="utf-8"))
            if not urlsplit(link).scheme
        }
        assert DOCS / "README.md" in destinations, path
    for name in NAMES[1:]:
        assert name in LINK.findall(_read("README.md"))


@pytest.mark.parametrize("name", NAMES)
def test_local_links_and_anchors_resolve_inside_repository(name: str) -> None:
    for link in LINK.findall(_read(name)):
        parsed = urlsplit(link)
        if parsed.scheme:
            continue
        target = ((DOCS / name).parent / unquote(parsed.path)).resolve()
        assert target.is_relative_to(ROOT), (name, link)
        assert target.exists(), (name, link)
        if parsed.fragment:
            assert unquote(parsed.fragment) in _anchors(
                target.read_text(encoding="utf-8")
            ), (name, link)


@pytest.mark.parametrize("name", NAMES)
def test_every_shell_block_has_context_and_valid_bash_syntax(name: str) -> None:
    content = _read(name)
    blocks = list(FENCE.finditer(content))
    for index, block in enumerate(blocks):
        assert block[1] == "bash", (name, "unclassified command block")
        end = blocks[index + 1].start() if index + 1 < len(blocks) else len(content)
        explanation = content[block.end() : end]
        for label in METADATA:
            assert re.search(rf"\*\*{label}:\*\*\s+\S", explanation), (
                name,
                index,
                label,
            )
        # Syntax only. In particular, POST/stop/migrations are never executed.
        result = subprocess.run(
            ["bash", "-n"], input=block[2], text=True, capture_output=True, check=False
        )
        assert result.returncode == 0, (name, index, result.stderr)


def test_every_environment_template_key_has_a_reference_row() -> None:
    documented = set(
        re.findall(
            r"^\| `([A-Z][A-Z0-9_]+)` \|",
            _read("environment-reference.md"),
            re.MULTILINE,
        )
    )
    for template in (
        ".env.example",
        ".env.homologation.example",
        ".env.production.example",
    ):
        # Include optional commented settings, too.
        keys = set(
            re.findall(
                r"^(?:#\s*)?([A-Z][A-Z0-9_]+)=",
                (ROOT / template).read_text(encoding="utf-8"),
                re.MULTILINE,
            )
        )
        assert keys <= documented, (template, sorted(keys - documented))


@pytest.mark.parametrize("name", NAMES)
def test_no_known_secret_patterns_or_missing_script_references(name: str) -> None:
    content = _read(name)
    for kind, pattern in SECRET_PATTERNS.items():
        assert not pattern.search(content), (name, kind)
    for script in re.findall(r"scripts/[a-zA-Z0-9_/-]+\.py", content):
        assert (ROOT / script).is_file(), (name, script)


@pytest.mark.parametrize("name", NAMES)
def test_documented_python_cli_options_exist_in_current_scripts(name: str) -> None:
    for block in FENCE.finditer(_read(name)):
        # Join line continuations before examining individual commands.
        for line in block[2].replace("\\\n", " ").splitlines():
            tokens = shlex.split(line)
            for index, token in enumerate(tokens):
                if not re.fullmatch(r"scripts/\w+\.py", token):
                    continue
                tree = ast.parse((ROOT / token).read_text(encoding="utf-8"))
                options = {
                    arg.value
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "add_argument"
                    for arg in node.args
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                }
                for argument in tokens[index + 1 :]:
                    if argument.startswith("--"):
                        assert argument.split("=", 1)[0] in options, (
                            name,
                            token,
                            argument,
                        )


def test_lg_integration_and_independent_acceptance_remain_explicitly_pending() -> None:
    email = _read("lg-email-api.md")
    assert "#171" in email and "#170" in email
    assert re.search(r"ainda\s*\n?>?\s*não é aceito", email)
    assert "multipart/form-data" in email and "uncertain" in email
    assert "permanece pendente" in _read("post-deployment-checklist.md")


def test_reference_tables_have_consistent_columns() -> None:
    for line in _read("environment-reference.md").splitlines():
        if line.startswith("|"):
            assert len(line.split("|")) == 6, line


@pytest.mark.parametrize("name", NAMES)
def test_example_urls_use_reserved_hosts_or_local_probes(name: str) -> None:
    for url in re.findall(r"https?://[A-Za-z0-9_.:-]+", _read(name)):
        hostname = urlsplit(url).hostname
        assert hostname is not None
        assert hostname in {
            "localhost",
            "127.0.0.1",
            "github.com",
        } or hostname.endswith(".invalid"), (name, "use a reserved example hostname")


def _deployment_parser() -> argparse.ArgumentParser:
    """Build the actual CLI parser without invoking Docker or deployment code."""
    tree = ast.parse((ROOT / "scripts/deploy.py").read_text(encoding="utf-8"))
    main = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "main"
    )
    nodes = []
    for node in main.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "parser"
            for target in node.targets
        ):
            nodes.append(node)
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and isinstance(node.value.func.value, ast.Name)
            and node.value.func.value.id == "parser"
            and node.value.func.attr == "add_argument"
        ):
            nodes.append(node)
    namespace = {"argparse": argparse, "Path": Path, "__doc__": "Offline parser"}
    exec(
        compile(ast.Module(body=nodes, type_ignores=[]), "deploy_cli", "exec"),
        namespace,
    )
    return namespace["parser"]


def test_operational_examples_use_real_actions_and_required_cli_arguments() -> None:
    parser = _deployment_parser()
    actions, resolutions = set(), set()
    for name in NAMES:
        for block in FENCE.finditer(_read(name)):
            for line in block[2].replace("\\\n", " ").splitlines():
                tokens = shlex.split(line)
                if "scripts/deploy.py" not in tokens:
                    continue
                args = parser.parse_args(
                    tokens[tokens.index("scripts/deploy.py") + 1 :]
                )
                actions.add(args.action)
                assert args.project and args.env_file.is_absolute()
                assert args.state_dir.is_absolute()
                if args.action == "apply":
                    assert args.revision
                else:
                    assert args.revision is None and not args.initialize
                if args.initialize:
                    assert name == "deployment-guide.md"
                if args.action == "reconcile":
                    assert args.operation
                    resolutions.add(args.resolution)
                else:
                    assert args.operation is None and args.resolution is None
    assert actions == {
        "diagnose",
        "precheck",
        "apply",
        "verify",
        "rollback",
        "reconcile",
    }
    assert resolutions == {None, "resume", "rollback"}


def test_fault_example_changes_only_private_copy_and_rejects_local_origin(
    tmp_path,
) -> None:
    environment = {
        "SYNERGIA_ENV": "homologation",
        "PGPASSWORD": "synthetic-database-password",
        "AUTH_JWT_SIGNING_KEY": "synthetic-signing-key-with-at-least-32-bytes",
        "RATE_LIMIT_KEY_SECRET": "synthetic-rate-key-with-at-least-32-bytes",
        "AUTH_ALLOWED_ORIGINS": "http://web.example.invalid:8080",
        "SYNERGIA_API_ORIGIN": "http://api.example.invalid:8000",
        "AUTH_IDENTITY_PROVIDER": "local",
        "SYNERGIA_LOCAL_AUTH_ENABLED": "false",
        "AUTH_REFRESH_COOKIE_SECURE": "false",
    }
    assert validate_deployment_environment(environment) == "homologation"
    original = tmp_path / "homologation.env"
    fault = tmp_path / "fault.env"
    text = "\n".join(f"{key}={value}" for key, value in environment.items()) + "\n"
    original.write_text(text, encoding="utf-8")
    fault.write_text(text, encoding="utf-8")
    fault.chmod(0o600)
    examples = [
        shlex.split(line)[2]
        for block in FENCE.finditer(_read("post-deployment-checklist.md"))
        for line in block[2].splitlines()
        if line.startswith("python3 -c ") and "fault.env" in line
    ]
    assert len(examples) == 1
    snippet = examples[0].replace(
        "/caminho/privado/synergia-config/fault.env", str(fault)
    )
    subprocess.run([sys.executable, "-c", snippet], check=True, capture_output=True)
    mutated = dict(line.split("=", 1) for line in fault.read_text().splitlines())
    assert mutated == {**environment, "SYNERGIA_API_ORIGIN": "http://localhost:8000"}
    assert original.read_text(encoding="utf-8") == text
    assert fault.stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError, match="SYNERGIA_API_ORIGIN"):
        validate_deployment_environment(mutated)


def test_automation_and_acceptance_gates_match_current_state() -> None:
    reference = _read("environment-reference.md")
    assert "não aceita overlays" in reference
    assert "ignora" in reference and "shell" in reference
    for name in NAMES:
        assert not re.search(
            r"deploy\.py.{0,100}indisponível neste checkout", _read(name)
        )
    email = _read("lg-email-api.md")
    assert "06/11/2026" in email and "Não houve POST" in email
    assert "não identifica isoladamente" in email
    assert "permanece pendente" in _read("post-deployment-checklist.md")
