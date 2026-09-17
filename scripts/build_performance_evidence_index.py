from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree

REQUIRED_RUN_FILES = (
    "environment.json",
    "workload.json",
    "summary.json",
    "correctness.json",
    "samples.csv",
    "resources.csv",
)


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _relative(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root.resolve()))


def _run(directory: Path, root: Path) -> dict:
    directory = directory.resolve(strict=True)
    missing = [name for name in REQUIRED_RUN_FILES if not (directory / name).is_file()]
    if missing:
        raise ValueError(f"Execução {directory.name} sem arquivos: {missing}")
    environment = json.loads((directory / "environment.json").read_text())
    workload = json.loads((directory / "workload.json").read_text())
    summary = json.loads((directory / "summary.json").read_text())
    correctness = json.loads((directory / "correctness.json").read_text())
    mass = environment.get("mass", {})
    if not mass.get("logical_digest") or not mass.get("entities"):
        raise ValueError(f"Execução {directory.name} sem massa identificada")
    if not environment.get("host") or not environment.get("metadata"):
        raise ValueError(f"Execução {directory.name} sem ambiente identificado")
    checks = correctness.get("checks", [])
    if not checks:
        raise ValueError(f"Execução {directory.name} sem oráculos")
    failures = [item["check"] for item in checks if not item.get("passed")]
    files = [path for path in directory.iterdir() if path.is_file()]
    return {
        "run_id": workload.get("run_id", directory.name),
        "scenario_id": workload.get("scenario_id"),
        "path": _relative(directory, root),
        "classification": "diagnostic" if failures else "exploratory_pass",
        "comparability": environment.get("comparability", "not_available"),
        "environment": environment,
        "workload": workload,
        "checks_total": len(checks),
        "failed_checks": failures,
        "measured_samples": summary.get("measured_samples"),
        "unexpected_errors": summary.get("unexpected_errors"),
        "operations": summary.get("operations", []),
        "resources": summary.get("resources", {}),
        "files": {
            path.name: {"sha256": _sha256(path), "bytes": path.stat().st_size}
            for path in sorted(files)
        },
    }


def _junit(path: Path, root: Path) -> dict:
    path = path.resolve(strict=True)
    document = ElementTree.parse(path).getroot()
    suites = (
        document.findall("testsuite") if document.tag == "testsuites" else [document]
    )
    counts = {
        key: sum(int(suite.attrib.get(key, 0)) for suite in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }
    return {
        "path": _relative(path, root),
        "sha256": _sha256(path),
        **counts,
        "passed": counts["failures"] == 0 and counts["errors"] == 0,
    }


def _plan(directory: Path, root: Path) -> dict:
    directory = directory.resolve(strict=True)
    run = json.loads((directory / "run.json").read_text())
    files = sorted(directory.glob("*.json"))
    if len(files) < 2 or not run.get("mass_logical_digest") or not run.get("plans"):
        raise ValueError(f"Planos incompletos em {directory.name}")
    return {
        "path": _relative(directory, root),
        "run": run,
        "files": {path.name: _sha256(path) for path in files},
    }


def _benchmark(directory: Path, root: Path) -> dict:
    directory = directory.resolve(strict=True)
    path = directory / "run.json"
    run = json.loads(path.read_text())
    if run["rule_evaluations_before"] != run["rule_evaluations_after"]:
        raise ValueError(f"Sonda deixou avaliações em {directory.name}")
    if not run.get("read", {}).get("digest") or not run.get("write", {}).get("samples"):
        raise ValueError(f"Sonda incompleta em {directory.name}")
    return {"path": _relative(directory, root), "sha256": _sha256(path), "run": run}


def _manifest(path: Path, root: Path) -> dict:
    path = path.resolve(strict=True)
    manifest = json.loads(path.read_text())
    if not manifest.get("logical_digest") or not manifest.get("entities"):
        raise ValueError(f"Manifesto {path.name} sem identidade da massa")
    files = []
    for item in manifest.get("files", []):
        source = path.parent / item["file"]
        if not source.is_file():
            raise ValueError(f"Fonte ausente para {path.parent.name}: {item['file']}")
        size = source.stat().st_size
        digest = _sha256(source)
        if size != item["size_bytes"] or digest != item["sha256"]:
            raise ValueError(f"Fonte alterada para {path.parent.name}: {item['file']}")
        files.append({"path": _relative(source, root), "bytes": size, "sha256": digest})
    if not files:
        raise ValueError(f"Manifesto {path.name} sem fontes")
    return {
        "path": _relative(path, root),
        "sha256": _sha256(path),
        "logical_digest": manifest["logical_digest"],
        "entities": manifest["entities"],
        "classification": "generated_only_not_processed",
        "files": files,
    }


def build(args: argparse.Namespace) -> dict:
    root = Path.cwd().resolve()
    runs = [_run(path, root) for path in args.run]
    junits = [_junit(path, root) for path in args.junit]
    plans = [_plan(path, root) for path in args.plan_run]
    benchmarks = [_benchmark(path, root) for path in args.benchmark_run]
    manifests = [_manifest(path, root) for path in args.manifest]
    if len({item["run_id"] for item in runs}) != len(runs):
        raise ValueError("Identificadores de execução repetidos")
    if len(plans) >= 2:
        identities = {
            (item["run"]["mass_logical_digest"], item["run"]["execution_id"])
            for item in plans
        }
        if len(identities) != 1:
            raise ValueError("Planos antes/depois não usam a mesma massa/execução")
    if len(benchmarks) >= 2:
        digests = {item["run"]["read"]["digest"] for item in benchmarks}
        states = {item["run"]["index_present"] for item in benchmarks}
        identities = {
            (
                item["run"]["execution_id"],
                item["run"]["organization_id"],
                item["run"]["workorder_number"],
                item["run"]["mass_manifest"]["logical_digest"],
            )
            for item in benchmarks
        }
        if len(digests) != 1 or states != {False, True} or len(identities) != 1:
            raise ValueError("Sondas antes/depois não são equivalentes")
        if (
            plans
            and next(iter(identities))[3] != plans[0]["run"]["mass_logical_digest"]
        ):
            raise ValueError("Planos e sondas não usam a mesma massa")
    result = {
        "created_at": datetime.now(UTC).isoformat(),
        "baseline_status": "exploratory_non_comparable",
        "release_candidate_status": "not_approved",
        "reason": "V05/PG16, concorrência de referência e perfis de recurso pendentes",
        "runs": runs,
        "junits": junits,
        "plan_runs": plans,
        "benchmark_runs": benchmarks,
        "generated_manifests": manifests,
        "summary": {
            "run_count": len(runs),
            "exploratory_pass_runs": sum(
                item["classification"] == "exploratory_pass" for item in runs
            ),
            "diagnostic_runs": sum(
                item["classification"] == "diagnostic" for item in runs
            ),
            "failed_junits": sum(not item["passed"] for item in junits),
            "generated_only_manifests": len(manifests),
        },
    }
    if args.output.exists():
        raise ValueError("Arquivo de saída já existe")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Valida e indexa artefatos da baseline exploratória pré-RPA"
    )
    parser.add_argument("--run", type=Path, action="append", required=True)
    parser.add_argument("--junit", type=Path, action="append", default=[])
    parser.add_argument("--plan-run", type=Path, action="append", default=[])
    parser.add_argument("--benchmark-run", type=Path, action="append", default=[])
    parser.add_argument("--manifest", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args)
    print(json.dumps(result["summary"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
