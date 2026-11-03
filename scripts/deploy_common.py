"""Private artifacts shared by the host-side deployment commands."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path


class DeploymentError(RuntimeError):
    """An actionable, secret-free error safe to show to the operator."""


def parse_json(raw: str, step: str):
    try:
        return json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise DeploymentError(f"{step}: invalid tool response") from exc


def atomic_json(path: Path, record: Mapping) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=".deploy-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(dict(record), stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        Path(temporary).unlink(missing_ok=True)


def private_json(path: Path) -> dict:
    try:
        details = path.lstat()
        if not path.is_file() or path.is_symlink():
            raise ValueError
        if details.st_uid != os.getuid() or details.st_mode & 0o077:
            raise ValueError
        value = json.loads(path.read_text())
        if not isinstance(value, dict):
            raise ValueError
        return value
    except (OSError, ValueError, TypeError) as exc:
        raise DeploymentError(
            "private deployment artifact invalid; reconcile history"
        ) from exc


def compose_literals(value):
    """A resolved model must survive a second Compose interpolation literally."""
    if isinstance(value, str):
        return value.replace("$", "$$")
    if isinstance(value, dict):
        return {key: compose_literals(item) for key, item in value.items()}
    if isinstance(value, list):
        return [compose_literals(item) for item in value]
    return value


def compose_values(value):
    """Decode the dollar escaping in Compose's round-trippable JSON output."""
    if isinstance(value, str):
        return value.replace("$$", "$")
    if isinstance(value, dict):
        return {key: compose_values(item) for key, item in value.items()}
    if isinstance(value, list):
        return [compose_values(item) for item in value]
    return value
