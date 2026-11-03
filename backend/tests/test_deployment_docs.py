"""Offline contracts for the operational guides; never execute deployment blocks."""

from __future__ import annotations

import ast
import re
import shlex
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

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
    "Efeito",
    "Resultado esperado",
    "Interpretação de falhas",
    "Próxima ação",
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
        if script == "scripts/deploy.py" and not (ROOT / script).exists():
            assert "#166" in content and "indisponível" in content, name
            continue
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
