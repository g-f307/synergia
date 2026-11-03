"""Capacity probes cannot bypass the development-only boundary."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import probe_ai_reevaluation as cli  # noqa: E402
from ai_poc_foundation import PoCFoundationError  # noqa: E402
from ai_reevaluation import configuration  # noqa: E402


def agent():
    return configuration(
        ROOT / "scripts/ai_reevaluation_configs/quality-qwen3-4b-auto-development.json"
    )


@pytest.mark.parametrize("key,value", [("split", "evaluation"), ("mode", "baseline")])
def test_probe_refuses_wrong_split_or_baseline_before_runtime(
    key, value, tmp_path, monkeypatch
):
    c = agent()
    c[key] = value
    monkeypatch.setattr(
        cli, "freeze", lambda _: pytest.fail("No runtime lookup permitted")
    )
    with pytest.raises(PoCFoundationError, match="development_agent"):
        cli.probe(c, "development/QD3-D02.csv", tmp_path / "probe")
    assert not (tmp_path / "probe").exists()


@pytest.mark.parametrize("case", ["evaluation/QD3-E01.csv", "../real.xlsx", "missing"])
def test_probe_cannot_select_reserved_real_or_unknown_case(case, tmp_path, monkeypatch):
    monkeypatch.setattr(
        cli, "freeze", lambda _: pytest.fail("No runtime lookup permitted")
    )
    with pytest.raises(PoCFoundationError, match="known_development_case"):
        cli.probe(agent(), case, tmp_path / "probe")
    assert not (tmp_path / "probe").exists()


def test_probe_refuses_existing_artifacts(tmp_path, monkeypatch):
    output = tmp_path / "probe"
    output.mkdir()
    sentinel = output / "probe.json"
    sentinel.write_text("preserve")
    monkeypatch.setattr(cli, "freeze", lambda _: {})
    with pytest.raises(FileExistsError):
        cli.probe(agent(), "development/QD3-D02.csv", output)
    assert sentinel.read_text() == "preserve"


def test_probe_command_requires_explicit_inference_authorization(tmp_path):
    with pytest.raises(SystemExit) as exc:
        cli.main(
            [
                "--config",
                "unused",
                "--case",
                "development/QD3-D02.csv",
                "--output-dir",
                str(tmp_path),
            ]
        )
    assert exc.value.code == 2
